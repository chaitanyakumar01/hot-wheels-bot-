import argparse
import json
import logging
import os
import requests
import schedule
import signal
import threading
import queue
import sqlite3
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
RETRY_COUNT = 3
RETRY_DELAY = 5

# logging
logger = logging.getLogger("hotwheels")


class SeenStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        # allow waiting for locks and concurrent reads/writes
        self.conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        # queue + writer thread to serialize writes and avoid DB locks
        self._q: "queue.Queue[str]" = queue.Queue()
        self._writer_stop = threading.Event()
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        # enable WAL for better concurrency
        try:
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA busy_timeout=30000;")
        except Exception:
            pass
        self._init_db()
        # start background writer
        self._writer_thread.start()

    def _init_db(self):
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS seen (
                product_id TEXT PRIMARY KEY,
                first_seen TEXT
            )
            """
        )
        self.conn.commit()

    def is_new_and_mark(self, product_id: str) -> bool:
        # Check existence using read connection, enqueue write if new.
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM seen WHERE product_id = ?", (product_id,))
        if cur.fetchone():
            return False
        # enqueue for background writer (writer will INSERT OR IGNORE)
        try:
            self._q.put_nowait(product_id)
        except Exception:
            # fallback: attempt direct insert
            try:
                with sqlite3.connect(self.db_path, timeout=30) as conn:
                    conn.execute("PRAGMA busy_timeout=30000;")
                    conn.execute("INSERT OR IGNORE INTO seen (product_id, first_seen) VALUES (?, ?)", (product_id, datetime.now(timezone.utc).isoformat()))
                    conn.commit()
            except Exception:
                logger.exception("Fallback write failed for %s", product_id)
        return True

    def _writer_loop(self):
        # single writer connection
        try:
            # try to open writer connection with retries (avoid transient lock at startup)
            conn = None
            for _ in range(8):
                try:
                    conn = sqlite3.connect(self.db_path, timeout=30)
                    break
                except sqlite3.OperationalError:
                    time.sleep(0.2)
            if conn is None:
                raise RuntimeError("Could not open writer DB connection")
            try:
                conn.execute("PRAGMA busy_timeout=30000;")
            except Exception:
                pass
            cur = conn.cursor()
            while not self._writer_stop.is_set() or not self._q.empty():
                try:
                    pid = self._q.get(timeout=0.5)
                except queue.Empty:
                    continue
                try:
                    cur.execute("INSERT OR IGNORE INTO seen (product_id, first_seen) VALUES (?, ?)", (pid, datetime.now(timezone.utc).isoformat()))
                    conn.commit()
                except Exception:
                    logger.exception("Writer failed to insert %s", pid)
                finally:
                    self._q.task_done()
        except Exception:
            logger.exception("Writer thread failed")
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

    def is_empty(self) -> bool:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(1) FROM seen")
        r = cur.fetchone()
        return (r[0] if r else 0) == 0

    def close(self):
        # stop writer thread and close connection
        try:
            self._writer_stop.set()
            if hasattr(self, '_writer_thread'):
                self._writer_thread.join(timeout=5)
        except Exception:
            pass
        try:
            self.conn.close()
        except Exception:
            pass


seen_store: SeenStore | None = None

# graceful shutdown event
stop_event = threading.Event()
health_server = None
health_thread = None


def _signal_handler(signum, frame):
    logger.info("Received signal %s, shutting down...", signum)
    stop_event.set()


def start_health_server(port: int):
    global health_server, health_thread

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                body = b'{"status":"ok"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            logger.debug("Health server: %s", format % args)

    health_server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    health_thread = threading.Thread(target=health_server.serve_forever, daemon=True)
    health_thread.start()
    logger.info("Health server listening on port %s", port)


def stop_health_server():
    global health_server, health_thread
    if health_server is not None:
        health_server.shutdown()
        health_server.server_close()
        health_server = None
    if health_thread is not None:
        health_thread.join(timeout=2)
        health_thread = None

# register signals later in __main__ after logger is configured


# legacy JSON state replaced by SQLite SeenStore


def request_with_retries(url, **kwargs):
    last_error = None
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            response = requests.post(url, **kwargs)
            if 200 <= response.status_code < 300:
                return response
            last_error = f"status {response.status_code}"
            logger.warning("Request attempt %d failed with %s", attempt, last_error)
        except requests.RequestException as exc:
            last_error = exc
            logger.warning("Request attempt %d exception: %s", attempt, exc)

        if attempt < RETRY_COUNT:
            time.sleep(RETRY_DELAY * attempt)

    raise RuntimeError(f"Failed to fetch {url} after {RETRY_COUNT} attempts: {last_error}")


# seen_store will be initialized from CLI args in __main__

LOCATIONS = [
    {
        "name": "Gym",
        "lat": "26.8147755",
        "lon": "80.9940688",
        "cookie": os.getenv("COOKIE_GYM"),
    },
    {
        "name": "Anubhav",
        "lat": "26.7843739",
        "lon": "80.8919504",
        "cookie": os.getenv("COOKIE_DOST"),
    },
    {
        "name": "Kushagra ke Ghar",
        "lat": "26.8147755",
        "lon": "80.9940688",
        "cookie": os.getenv("COOKIE_KUSHAGRA"),
    },
]

URL = "https://blinkit.com/v1/layout/search"

PARAMS = {
    "offset": 0,
    "limit": 20,
    "actual_query": "hot+wheels",
    "last_snippet_type": "product_card_snippet_type_2",
    "last_widget_type": "listing_container",
    "page_index": 1,
    "q": "hot+wheels",
    "search_count": 9,
    "search_method": "similarity",
    "search_type": "auto_suggest",
    "tab_position": 0,
    "total_entities_processed": 1,
    "total_pagination_items": 1028,
}

def get_headers(location):
    return {
        "Accept": "/",
        "Accept-Language": "en-GB,en;q=0.7",
        "Access_token": "v2::ef02f7b4-67d0-47d2-b4a7-e10fee3267a7",
        "App_client": "consumer_web",
        "App_version": "1010101010",
        "Auth_key": "c761ec3633c22afad934fb17a66385c1c06c5472b4898b866b7306186d0bb477",
        "Content-Type": "application/json",
        "Device_id": "bbb8e102c7a0ca19",
        "Lat": location["lat"],
        "Lon": location["lon"],
        "Origin": "https://blinkit.com",
        "Referer": "https://blinkit.com/s/?q=hot%20wheels",
        "Rn_bundle_version": "1009003012",
        "Session_uuid": "58a72deb-b356-4aa3-99fb-124123ac3db3",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "Web_app_version": "1008010016",
        "Cookie": location["cookie"],
        "Sec-Ch-Ua": '"Brave";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }

def send_discord_notification(message):
    if not DISCORD_WEBHOOK_URL:
        logger.warning("Discord webhook not configured; skipping notification")
        return

    payload = {"content": message}
    try:
        response = request_with_retries(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 204 or 200 <= response.status_code < 300:
            logger.info("Discord notification sent")
        else:
            logger.error("Discord error: %s — %s", response.status_code, response.text)
    except Exception as exc:
        logger.exception("Failed to send Discord notification: %s", exc)

def check_location(location):
    logger.info("Checking %s", location["name"])
    if not location.get("cookie"):
        logger.warning("No cookie configured for %s; skipping location", location["name"])
        return

    try:
        response = request_with_retries(URL, headers=get_headers(location), params=PARAMS, timeout=10)
        logger.info("Status (%s): %s", location["name"], response.status_code)
        data = response.json()

        snippets = data.get("response", {}).get("snippets", [])
        products = [s.get("data", {}) for s in snippets if s.get("widget_type") == "product_card_snippet_type_2"]

        logger.info("Total products found (%s): %d", location["name"], len(products))

        new_items = []
        for p in products:
            pid = str(p.get("product_id") or p.get("identity", {}).get("id")) + "_" + location["name"]
            name = p.get("name", {}).get("text", "")

            if "Hot Wheels" not in name:
                continue

            clean_name = name.replace("Hot Wheels", "").replace("Die Cast Car", "").replace("Die-Cast Car", "").replace("Toy Car", "").replace("Toy Vehicle", "").strip()

            if pid and seen_store.is_new_and_mark(pid):
                new_items.append(clean_name)

        if new_items:
            msg = f"New Stock at {location['name']}!\n\n" + "\n".join(new_items)
            send_discord_notification(msg)
        else:
            logger.info("No new Hot Wheels at %s", location["name"])

    except Exception as e:
        logger.exception("Error checking %s: %s", location["name"], e)

def validate_config():
    missing = []
    if not DISCORD_WEBHOOK_URL:
        missing.append("DISCORD_WEBHOOK_URL")

    for location in LOCATIONS:
        if not location.get("cookie"):
            missing.append(f"COOKIE for {location['name']}")

    if missing:
        logger.warning("Missing optional configuration for deployment; the service will start but notifications will be skipped until you add values:")
        for item in missing:
            logger.warning("  - %s", item)


def check_all():
    for location in LOCATIONS:
        check_location(location)
        time.sleep(2)


def seed_seen_store():
    """Scan current product ids and mark them as seen without sending notifications.
    This prevents initial-run spam when the DB is empty.
    """
    logger.info("Seeding seen state from current search results (no notifications)")
    total_marked = 0
    for location in LOCATIONS:
        try:
            response = request_with_retries(URL, headers=get_headers(location), params=PARAMS, timeout=10)
            data = response.json()
            snippets = data.get("response", {}).get("snippets", [])
            products = [s.get("data", {}) for s in snippets if s.get("widget_type") == "product_card_snippet_type_2"]
            for p in products:
                pid = str(p.get("product_id") or p.get("identity", {}).get("id")) + "_" + location["name"]
                name = p.get("name", {}).get("text", "")
                if "Hot Wheels" not in name:
                    continue
                if pid:
                    if seen_store.is_new_and_mark(pid):
                        total_marked += 1
        except Exception:
            logger.exception("Failed to seed from %s", location["name"])

    logger.info("Seeding complete, marked %d existing items as seen", total_marked)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hot Wheels monitor")
    parser.add_argument("--once", action="store_true", help="Run one check and exit")
    parser.add_argument("--interval", type=int, default=10, help="Polling interval in minutes")
    parser.add_argument("--state-file", default="seen_products.db", help="SQLite DB path for seen state")
    parser.add_argument("--log-file", default=None, help="Optional log file path")
    parser.add_argument("--send-test", action="store_true", help="Send a single test Discord message and exit")
    parser.add_argument("--force-notify", action="store_true", help="Skip seeding and notify for current items")
    parser.add_argument("--health-port", type=int, default=None, help="Optional port for /health HTTP endpoint")
    args = parser.parse_args()

    # logging setup
    level = logging.INFO
    handlers = [logging.StreamHandler()]
    if args.log_file:
        from logging.handlers import RotatingFileHandler

        handlers.append(RotatingFileHandler(args.log_file, maxBytes=10 * 1024 * 1024, backupCount=3))

    logging.basicConfig(level=level, format='%(asctime)s %(levelname)s %(message)s', handlers=handlers)

    logger.info("Starting Hot Wheels monitor")

    # optional health endpoint for deployment platforms
    if args.health_port is None:
        args.health_port = int(os.getenv("PORT", "0")) or None
    if args.health_port:
        start_health_server(args.health_port)

    # initialize seen store
    seen_store = SeenStore(args.state_file)

    validate_config()

    # send a single test message and exit if requested
    if args.send_test:
        logger.info("Sending single test notification and exiting")
        send_discord_notification("Test message from hotwheels-monitor")
        seen_store.close()
        raise SystemExit(0)

    # seed DB on first run unless user forces notifications
    if seen_store.is_empty():
        if args.force_notify:
            logger.warning("--force-notify specified: skipping seeding and allowing notifications for existing items")
        else:
            seed_seen_store()

    if args.once:
        check_all()
        seen_store.close()
        raise SystemExit(0)

    logger.info("Bot starting: checking every %d minutes", args.interval)
    check_all()
    schedule.every(args.interval).minutes.do(check_all)

    # register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        while not stop_event.is_set():
            schedule.run_pending()
            time.sleep(1)
    finally:
        logger.info("Shutting down")
        seen_store.close()