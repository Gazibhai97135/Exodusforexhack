"""
engine.py — ForexSignal Pro Core
Shared signal logic, database, data fetching, indicators, lot calculator.
Uses 'ta' library (pure Python — no build issues on Render/Railway).
Developer: @exodus_own3r
"""

import os, sqlite3, time, logging
import requests
import pandas as pd
import ta
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

# ── CONFIG ────────────────────────────────────────────────────────────────────
TWELVE_KEY = os.getenv("TWELVE_DATA_KEY", "")
DB_PATH    = "signals.db"

SYMBOLS = {
    "XAUUSD": {
        "td":             "XAU/USD",
        "yf":             "GC=F",
        "decimals":       2,
        "label":          "GOLD (XAU/USD)",
        "icon":           "🥇",
        "pip_size":       0.01,
        "lot_multiplier": 100.0,
    },
    "EURUSD": {
        "td":             "EUR/USD",
        "yf":             "EURUSD=X",
        "decimals":       5,
        "label":          "EUR/USD",
        "icon":           "💶",
        "pip_size":       0.0001,
        "lot_multiplier": 100000.0,
    },
}

# Indicator params
EMA_FAST,  EMA_SLOW,  EMA_TREND  = 9,  21, 50
RSI_LEN,   RSI_OS,    RSI_OB     = 14, 35, 65
MACD_FAST, MACD_SLOW, MACD_SIG   = 12, 26,  9
ATR_LEN                          = 14
ATR_SL,    ATR_TP                = 1.5, 2.5
MIN_CONF                         = 3

# ── DATABASE ──────────────────────────────────────────────────────────────────
def init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol           TEXT    NOT NULL,
                direction        TEXT    NOT NULL,
                entry_price      REAL    NOT NULL,
                sl               REAL    NOT NULL,
                tp1              REAL    NOT NULL,
                tp2              REAL    NOT NULL,
                confidence       TEXT,
                confluence_score INTEGER,
                timeframe        TEXT    DEFAULT "M15/H1",
                strategy         TEXT,
                timestamp        DATETIME DEFAULT CURRENT_TIMESTAMP,
                outcome          TEXT    DEFAULT "PENDING",
                pnl_pips         REAL
            )
        ''')
    log.info("[DB] Ready")

def save_signal(s: dict) -> int:
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute('''
            INSERT INTO signals
              (symbol, direction, entry_price, sl, tp1, tp2,
               confidence, confluence_score, timeframe, strategy)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        ''', (s["symbol"], s["direction"], s["entry"], s["sl"],
              s["tp1"],  s["tp2"],  s.get("confidence", ""),
              s.get("confluence_score", 0),
              s.get("timeframe", "M15/H1"), s.get("strategy", "")))
        return cur.lastrowid

def get_signals(limit: int = 30) -> list:
    with sqlite3.connect(DB_PATH) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute(
            "SELECT * FROM signals ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]

def get_stats() -> dict:
    with sqlite3.connect(DB_PATH) as c:
        r = c.execute('''
            SELECT
                COUNT(*)                                         AS total,
                SUM(CASE WHEN outcome="WIN"  THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN outcome="LOSS" THEN 1 ELSE 0 END) AS losses,
                AVG(COALESCE(pnl_pips, 0))                      AS avg_pips
            FROM signals WHERE outcome != "PENDING"
        ''').fetchone()
    total, wins, losses, avg = r
    total = total or 0; wins = wins or 0; losses = losses or 0
    return {
        "total":    total,
        "wins":     wins,
        "losses":   losses,
        "avg_pips": round(avg or 0.0, 1),
        "win_rate": round(wins / total * 100 if total else 0.0, 1),
    }

# ── DATA FETCHER ──────────────────────────────────────────────────────────────
def _twelve_data(td_symbol: str, interval: str, outputsize: int = 200) -> pd.DataFrame:
    if not TWELVE_KEY:
        raise ValueError("TWELVE_DATA_KEY not set")
    resp = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol":     td_symbol,
            "interval":   interval,
            "outputsize": outputsize,
            "apikey":     TWELVE_KEY,
            "format":     "JSON",
        },
        timeout=12,
    ).json()
    if "values" not in resp:
        raise ValueError(resp.get("message", "Twelve Data error"))
    df = pd.DataFrame(resp["values"])
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.iloc[::-1].reset_index(drop=True)
    return df.dropna()

def _yfinance_fallback(yf_sym: str, period: str, interval: str) -> pd.DataFrame:
    df = yf.download(yf_sym, period=period, interval=interval,
                     progress=False, auto_adjust=True)
    if df.empty:
        raise ValueError(f"yfinance: no data for {yf_sym}")
    # Flatten multi-index columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={"Open": "open", "High": "high",
                             "Low":  "low",  "Close": "close"})
    df = df[["open", "high", "low", "close"]].dropna()
    return df.reset_index(drop=True)

def get_multi_tf(symbol: str):
    """Returns (df_h1, df_m15). Tries Twelve Data first, yfinance fallback."""
    meta = SYMBOLS[symbol]
    try:
        df_h1  = _twelve_data(meta["td"], "1h",    outputsize=200)
        df_m15 = _twelve_data(meta["td"], "15min", outputsize=150)
        return df_h1, df_m15
    except Exception as e:
        log.warning(f"[TD→YF] {symbol}: {e}")
    df_h1  = _yfinance_fallback(meta["yf"], "10d", "1h")
    df_m15 = _yfinance_fallback(meta["yf"], "3d",  "15m")
    return df_h1, df_m15

def get_current_price(symbol: str) -> float:
    meta = SYMBOLS[symbol]
    try:
        r = requests.get(
            "https://api.twelvedata.com/price",
            params={"symbol": meta["td"], "apikey": TWELVE_KEY},
            timeout=8,
        ).json()
        return float(r.get("price", 0))
    except Exception:
        pass
    try:
        df = _yfinance_fallback(meta["yf"], "1d", "1m")
        return float(df["close"].iloc[-1])
    except Exception:
        return 0.0

# ── INDICATORS (using 'ta' — pure Python, no build deps) ─────────────────────
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["close"]
    high  = df["high"]
    low   = df["low"]

    # EMAs
    df["ema_fast"]  = ta.trend.EMAIndicator(close, window=EMA_FAST,  fillna=False).ema_indicator()
    df["ema_slow"]  = ta.trend.EMAIndicator(close, window=EMA_SLOW,  fillna=False).ema_indicator()
    df["ema_trend"] = ta.trend.EMAIndicator(close, window=EMA_TREND, fillna=False).ema_indicator()

    # RSI
    df["rsi"] = ta.momentum.RSIIndicator(close, window=RSI_LEN, fillna=False).rsi()

    # ATR
    df["atr"] = ta.volatility.AverageTrueRange(
        high, low, close, window=ATR_LEN, fillna=False
    ).average_true_range()

    # MACD histogram
    macd = ta.trend.MACD(
        close,
        window_slow=MACD_SLOW,
        window_fast=MACD_FAST,
        window_sign=MACD_SIG,
        fillna=False,
    )
    df["macd_hist"] = macd.macd_diff()

    # Stochastic
    stoch = ta.momentum.StochasticOscillator(
        high, low, close, window=14, smooth_window=3, fillna=False
    )
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()

    return df.dropna()

# ── SIGNAL ENGINE ─────────────────────────────────────────────────────────────
def analyze_signal(symbol: str) -> dict | None:
    try:
        df_h1, df_m15 = get_multi_tf(symbol)
    except Exception as e:
        log.error(f"[ERR] {symbol}: {e}")
        return None

    df_h1  = add_indicators(df_h1)
    df_m15 = add_indicators(df_m15)

    if len(df_h1) < 3 or len(df_m15) < 3:
        return None

    h1,  h1p  = df_h1.iloc[-1],  df_h1.iloc[-2]
    m15, m15p = df_m15.iloc[-1], df_m15.iloc[-2]

    price = float(m15["close"])
    atr   = float(m15["atr"])
    bull, bear, reasons = 0, 0, []

    # Factor 1: H1 EMA trend
    if   float(h1["ema_slow"]) > float(h1["ema_trend"]):
        bull += 1;  reasons.append("H1 Trend: Bullish EMA stack")
    elif float(h1["ema_slow"]) < float(h1["ema_trend"]):
        bear += 1;  reasons.append("H1 Trend: Bearish EMA stack")

    # Factor 2: M15 EMA fast/slow crossover
    cu = (float(m15p["ema_fast"]) < float(m15p["ema_slow"]) and
          float(m15["ema_fast"])  > float(m15["ema_slow"]))
    cd = (float(m15p["ema_fast"]) > float(m15p["ema_slow"]) and
          float(m15["ema_fast"])  < float(m15["ema_slow"]))
    if cu:   bull += 1;  reasons.append("M15 EMA Cross: Bullish")
    elif cd: bear += 1;  reasons.append("M15 EMA Cross: Bearish")

    # Factor 3: RSI zone
    rsi = float(m15["rsi"])
    if   rsi <= RSI_OS:         bull += 1;  reasons.append(f"RSI {rsi:.1f} — Oversold reversal")
    elif RSI_OS < rsi < 55:     bull += 1;  reasons.append(f"RSI {rsi:.1f} — Bullish momentum")
    elif 45 < rsi < RSI_OB:     bear += 1;  reasons.append(f"RSI {rsi:.1f} — Bearish momentum")
    elif rsi >= RSI_OB:         bear += 1;  reasons.append(f"RSI {rsi:.1f} — Overbought reversal")

    # Factor 4: MACD histogram turn
    hist  = float(m15["macd_hist"])
    histp = float(m15p["macd_hist"])
    if   histp < 0 and hist > histp: bull += 1;  reasons.append("MACD: Histogram reversing upward")
    elif histp > 0 and hist < histp: bear += 1;  reasons.append("MACD: Histogram reversing downward")

    # Factor 5: Stochastic cross
    sk = float(m15["stoch_k"]);  sd = float(m15["stoch_d"])
    if   sk < 25 and sk > sd:   bull += 1;  reasons.append(f"Stoch {sk:.0f} — Oversold cross")
    elif sk > 75 and sk < sd:   bear += 1;  reasons.append(f"Stoch {sk:.0f} — Overbought cross")

    direction, score = None, 0
    if   bull >= MIN_CONF and bull > bear: direction, score = "BUY",  bull
    elif bear >= MIN_CONF and bear > bull: direction, score = "SELL", bear
    if not direction:
        return None

    # ATR-based SL/TP
    if direction == "BUY":
        sl  = round(price - atr * ATR_SL,       5)
        tp1 = round(price + atr * ATR_TP,       5)
        tp2 = round(price + atr * ATR_TP * 1.8, 5)
    else:
        sl  = round(price + atr * ATR_SL,       5)
        tp1 = round(price - atr * ATR_TP,       5)
        tp2 = round(price - atr * ATR_TP * 1.8, 5)

    risk   = abs(price - sl)
    reward = abs(tp1 - price)
    rr     = round(reward / risk, 2) if risk else 0
    conf   = ("VERY HIGH 🔥" if score >= 5 else
              "HIGH ✅"      if score >= 4 else "MEDIUM ⚡")

    return {
        "symbol":           symbol,
        "direction":        direction,
        "entry":            price,
        "sl":               sl,
        "tp1":              tp1,
        "tp2":              tp2,
        "rr":               rr,
        "confluence_score": score,
        "max_factors":      5,
        "confidence":       conf,
        "reasons":          reasons[:5],
        "timeframe":        "M15/H1",
        "strategy":         "EMA+RSI+MACD+Stoch",
        "rsi":              round(rsi, 1),
        "atr":              round(atr, 5),
    }

# ── LOT SIZE CALCULATOR (Exness) ──────────────────────────────────────────────
def calc_lot(symbol: str, balance: float, risk_pct: float, sl_distance: float) -> float:
    meta        = SYMBOLS[symbol]
    risk_amount = balance * risk_pct / 100.0

    if symbol == "XAUUSD":
        # 1 lot = 100 oz; $1 move = $100 per lot
        lot = risk_amount / (sl_distance * meta["lot_multiplier"])
    else:
        # 1 pip = $0.0001; pip value = $10 per standard lot
        sl_pips = sl_distance / meta["pip_size"]
        lot     = risk_amount / (sl_pips * 10.0)

    return max(0.01, round(lot, 2))

def lot_table_text(symbol: str, sl_distance: float) -> str:
    rows = []
    for bal in (300, 500, 1_000, 2_000, 5_000, 10_000):
        l1 = calc_lot(symbol, bal, 1.0, sl_distance)
        l2 = calc_lot(symbol, bal, 2.0, sl_distance)
        rows.append(f"  ${bal:>7,}  │  1%→{l1:.2f}  │  2%→{l2:.2f}")
    header = f"  {'Balance':>8}  │  1% risk  │  2% risk"
    sep    = "  " + "─" * 36
    return "\n".join([header, sep] + rows)
