# ForexSignal Pro
**Real-time Gold & EUR/USD signals — Telegram bot + live dashboard**
Developer: @exodus_own3r

---

## Quick Setup (5 minutes)

### 1. Install
```bash
pip install -r requirements.txt
```

### 2. Edit .env (only file you touch)
```
BOT_TOKEN      = your bot token from @BotFather
CHANNEL_ID     = @your_channel  (bot must be admin there)
TWELVE_DATA_KEY= free key from twelvedata.com
WEBAPP_URL     = your public URL (ngrok or VPS)
```

### 3. Run both processes

**Terminal 1 — Telegram bot + auto-signals:**
```bash
python bot.py
```

**Terminal 2 — Live dashboard website:**
```bash
python main.py
```

---

## Bot Commands
| Command | What it does |
|---------|-------------|
| `/start` | Main menu with Dashboard button |
| `/signal` | Get current signals on demand |
| `/stats` | Win rate and performance |
| `/lot 1000 1` | Lot size for $1,000 account, 1% risk |
| `/lot 5000 2` | Lot size for $5,000 account, 2% risk |

---

## Signal Logic (5-factor confluence)
| Factor | Description |
|--------|-------------|
| H1 EMA Trend | EMA 21 vs EMA 50 on H1 — confirms trend direction |
| M15 EMA Cross | EMA 9 crossing EMA 21 on M15 — entry timing |
| RSI | RSI 14 zone — momentum confirmation |
| MACD Histogram | Histogram reversal — momentum shift |
| Stochastic | %K/%D cross at extremes — additional filter |

**Minimum 3/5 factors must agree before a signal fires.**

---

## Lot Size Formula (Exness)

**Gold (XAUUSD):**
```
lot = (balance × risk%) / (SL_distance_in_$ × 100)
```

**EUR/USD:**
```
lot = (balance × risk%) / (SL_pips × $10)
```

---

## For Real-Time Data
Get a **free** Twelve Data API key:
1. Go to https://twelvedata.com
2. Sign up (free)
3. Copy API key → paste in .env

Without it, falls back to yfinance (~15 min delayed).

---

## Public URL (for Dashboard button in Telegram)
**Local testing:** use ngrok
```bash
ngrok http 5000
# Copy the https:// URL into WEBAPP_URL in .env
```

**Production:** deploy to Railway, Render, or any VPS.
