# ForexSignal Pro — Render Deploy Guide
Developer: @exodus_own3r

## Why this version?
Zero heavy dependencies (no pandas/numpy/ta/yfinance).
Pure Python indicators + direct HTTP data fetch.
Builds in seconds on any platform.

## Requirements (6 packages — all pure Python)
python-telegram-bot, requests, flask, gunicorn, apscheduler, python-dotenv

## Setup

### 1. Edit .env
BOT_TOKEN       = from @BotFather
CHANNEL_ID      = @your_channel  (bot must be admin)
TWELVE_DATA_KEY = free at twelvedata.com (real-time data)
WEBAPP_URL      = your Render web service URL

### 2. Deploy on Render (with render.yaml — automatic)
- Push to GitHub
- New → Blueprint → select repo → Render reads render.yaml automatically
- Add 4 env vars in Render dashboard
- Copy web service URL → paste as WEBAPP_URL

### 3. Run locally
pip install -r requirements.txt
python main.py   # terminal 1 — dashboard
python bot.py    # terminal 2 — bot + auto-signals

## Commands
/start          Main menu + Dashboard button
/signal         Live signal now
/stats          Win rate
/lot 1000 1     Lot size for $1,000 at 1% risk

## Data sources
Primary:  Twelve Data API (real-time, free key at twelvedata.com)
Fallback: Yahoo Finance direct API (no library — pure HTTP)

## Render SQLite note
Render web services have ephemeral storage.
Add a "Disk" in Render → mount at /data → set DB_PATH=/data/signals.db in .env
