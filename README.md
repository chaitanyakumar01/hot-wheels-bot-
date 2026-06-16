# 🚗 Hot Wheels Blinkit Monitor

A bot that monitors Blinkit for Hot Wheels availability and sends Discord notifications when new stock appears.

## What it does
- Checks Blinkit every 10 minutes for Hot Wheels
- Monitors multiple delivery locations simultaneously
- Filters out non-Hot Wheels products automatically
- Sends instant Discord notifications on new stock

## Project Structure
hotwheels-monitor/

├── bot.py              # Main bot logic

├── requirements.txt    # Python dependencies

├── Procfile           # Railway deployment config

└── .env               # API credentials (not tracked)


## Setup

### 1. Clone the repo
```bash
git clone https://github.com/chaitanyakumar01/hot-wheels-bot-
cd hot-wheels-bot-
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Create `.env` file
DISCORD_WEBHOOK_URL=cant_disclose_hehe

### 4. Run locally
```bash
python bot.py
```

## Deployment
Deployed on [Railway](https://railway.app) for 24/7 monitoring.

## Environment Variables
| Variable | Description |
|---|---|
| `DISCORD_WEBHOOK_URL` | Discord webhook URL for notifications |

## Monitored Locations
- Gym area (Lucknow)
- Dost ki Shop (Lucknow)

## Tech Stack
- Python
- Requests
- Schedule
- Discord Webhooks
- Blinkit API
