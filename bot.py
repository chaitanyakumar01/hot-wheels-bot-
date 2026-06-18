import os
import requests
import schedule
import time
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

seen_products = set()

LOCATIONS = [
    {
        "name": "Gym",
        "lat": "26.8147755",
        "lon": "80.9940688",
        "cookie": os.getenv("COOKIE_GYM"),
    },
    {
        "name": "Dost ki Shop",
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
    payload = {"content": message}
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    if response.status_code == 204:
        print("✅ Discord notification bheja!")
    else:
        print(f"❌ Discord error: {response.status_code} — {response.text}")

def check_location(location):
    print(f"🔍 {location['name']} check ho raha hai...")
    try:
        response = requests.post(URL, headers=get_headers(location), params=PARAMS, timeout=10)
        print(f"Status ({location['name']}): {response.status_code}")
        data = response.json()

        snippets = data.get("response", {}).get("snippets", [])
        products = []
        for snippet in snippets:
            if snippet.get("widget_type") == "product_card_snippet_type_2":
                p = snippet.get("data", {})
                products.append(p)

        print(f"Total products mile ({location['name']}): {len(products)}")

        new_items = []
        for p in products:
            pid = str(p.get("product_id") or p.get("identity", {}).get("id")) + "_" + location["name"]
            name = p.get("name", {}).get("text", "")

            if "Hot Wheels" not in name:
                continue

            clean_name = name.replace("Hot Wheels", "").replace("Die Cast Car", "").replace("Die-Cast Car", "").replace("Toy Car", "").replace("Toy Vehicle", "").strip()

            if pid and pid not in seen_products:
                seen_products.add(pid)
                new_items.append(clean_name)

        if new_items:
            msg = f"New Stock at {location['name']}!\n\n" + "\n".join(new_items)
            send_discord_notification(msg)
        else:
            print(f"ℹ️ {location['name']} pe koi naya Hot Wheels nahi.")

    except Exception as e:
        print(f"❌ Error ({location['name']}): {e}")

def check_all():
    for location in LOCATIONS:
        check_location(location)
        time.sleep(2)

if __name__ == "__main__":
    print("🚀 Bot shuru! Har 10 minute mein teenon locations check karega...")
    check_all()

    schedule.every(10).minutes.do(check_all)

    while True:
        schedule.run_pending()
        time.sleep(30)