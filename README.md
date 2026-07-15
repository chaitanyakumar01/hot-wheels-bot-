# 🚗 Hot Wheels Blinkit Monitor

A Python bot that monitors Blinkit for Hot Wheels stock and sends Discord notifications when new items appear.

## What this project does
- Checks Blinkit search results for Hot Wheels products
- Monitors multiple locations using location-specific cookies
- Avoids duplicate alerts by storing seen product IDs in a SQLite database
- Sends Discord notifications for newly detected stock
- Supports a health endpoint for deployment platforms
- Can run locally, in Docker, or on a cloud host

## What has been added
- Persistent seen-state storage so the bot does not repeatedly notify about the same products after restarts
- Retry logic for network requests so temporary failures do not immediately stop checks
- Config validation and safer startup behavior for deployment environments
- Graceful shutdown support for cleaner container and host stops
- Optional health endpoint for platforms like Render, Railway, and similar services
- Docker and deployment-ready configuration files

## Project structure
- [bot.py](bot.py) — main bot logic, polling, notification handling, and health server
- [requirements.txt](requirements.txt) — Python dependencies
- [Procfile](Procfile) — startup command for hosting platforms
- [Dockerfile](Dockerfile) — container build configuration
- [docker-compose.yml](docker-compose.yml) — local container setup
- [.env.example](.env.example) — example environment configuration
- [.dockerignore](.dockerignore) — files excluded from Docker builds

## Deployment
This project can be deployed to supported hosting platforms such as Render, Railway, or other Docker-compatible environments.

For Render, you can deploy directly from the repository using the included Render configuration file.

Typical deployment steps:
1. Push the repository to GitHub.
2. Create a new service on your hosting platform and connect the repository.
3. Set the required environment variables listed below.
4. Start the service using the included startup configuration.

## Local setup

### 1. Install dependencies
```bash
python3 -m pip install -r requirements.txt
```

### 2. Create a `.env` file
Copy [.env.example](.env.example) and fill in your values:
```bash
cp .env.example .env
```

### 3. Run once
```bash
python3 bot.py --once
```

### 4. Run continuously
```bash
python3 bot.py
```

## Health check
The bot can expose a simple health endpoint for deployment platforms:
```bash
python3 bot.py --health-port 8000
```
Then check it with:
```bash
curl http://localhost:8000/health
```

## Docker
Build and run locally with Docker:
```bash
docker build -t hotwheels-monitor .
docker run --rm --env-file .env hotwheels-monitor --once
```

You can also use Docker Compose:
```bash
docker-compose up --build
```

## Deployment options
This project is ready for:
- Render
- Railway
- Heroku-style platforms
- Docker-compatible hosts

For platforms that expect a web process, the included [Procfile](Procfile) starts the bot with a health-enabled entrypoint.

## Environment variables
| Variable | Description |
|---|---|
| `DISCORD_WEBHOOK_URL` | Discord webhook URL for notifications |
| `COOKIE_GYM` | Cookie for the Gym location |
| `COOKIE_DOST` | Cookie for the Anubhav/Dost location |
| `COOKIE_KUSHAGRA` | Cookie for the Kushagra location |
| `PORT` | Optional port used by hosting platforms for the health endpoint |

## Notes
- The bot uses a local SQLite database file to remember previously seen products.
- If configuration values are missing, the bot will still start safely and skip affected checks instead of crashing immediately.
- For best results, make sure your webhook URL and cookies are configured before relying on live alerts.
