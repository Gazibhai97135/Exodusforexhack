"""
engine.py — ForexSignal Pro Core
Pure Python — no pandas, no numpy, no ta, no yfinance.
Zero compilation. Builds on any platform instantly.
Developer: @exodus_own3r
"""

import os, sqlite3, time, logging, math
import requests
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

TWELVE_KEY = os.getenv("TWELVE_DATA_KEY", "")
DB_PATH    = "signals.db"

SYMBOLS = {
    "XAUUSD": {
        "td":             "XAU/USD",
        "yf":             "GC%3DF",        # GC=F URL-encoded
        "decimals":       2,
        "label":          "GOLD (XAU/USD)",
        "icon":           "🥇",
        "pip_size":       0.01,
        "lot_multiplier": 100.0,
    },
    "EURUSD": {
        "td":             "EUR/USD",
        "yf":             "EURUSD%3DX",    # EURUSD=X URL-encoded
        "decimals":       5,
        "label":          "EUR/USD",
        "icon":           "💶",
        "pip_size":       0.0001,
        "lot_multiplier": 100000.0,
    },
}

EMA_FAST,  EMA_SLOW,  EMA_TREND  = 9,  21, 50
RSI_WIN,   RSI_OS,    RSI_OB     = 14, 35, 65
MACD_FAST, MACD_SLOW, MACD_SIG   = 12, 26,  9
ATR_WIN                          = 14
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
              s["tp1"], s["tp2"], s.get("confidence", ""),
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
            SELECT COUNT(*) t,
                   SUM(CASE WHEN outcome="WIN"  THEN 1 ELSE 0 END) w,
                   SUM(CASE WHEN outcome="LOSS" THEN 1 ELSE 0 END) l,
                   AVG(COALESCE(pnl_pips,0)) ap
            FROM signals WHERE outcome != "PENDING"
        ''').fetchone()
    t, w, l, ap = r
    t = t or 0; w = w or 0; l = l or 0
    return {
        "total":    t,
        "wins":     w,
        "losses":   l,
        "avg_pips": round(ap or 0.0, 1),
        "win_rate": round(w / t * 100 if t else 0.0, 1),
    }

# ── DATA FETCHERS (no yfinance — direct HTTP) ─────────────────────────────────
def _clean_ohlcv(raw_list: list) -> dict:
    """Filter Nones and return dict of lists."""
    clean = [(o, h, l, c) for o, h, l, c in raw_list
             if all(v is not None and not math.isnan(float(v))
                    for v in (o, h, l, c))]
    if not clean:
        raise ValueError("No valid candles after cleaning")
    opens, highs, lows, closes = zip(*clean)
    return {
        "open":  [float(x) for x in opens],
        "high":  [float(x) for x in highs],
        "low":   [float(x) for x in lows],
        "close": [float(x) for x in closes],
    }

def _twelve_fetch(td_symbol: str, interval: str, outputsize: int = 200) -> dict:
    """Twelve Data REST API — real-time data."""
    if not TWELVE_KEY:
        raise ValueError("No TWELVE_DATA_KEY")
    resp = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol":     td_symbol,
            "interval":   interval,
            "outputsize": outputsize,
            "apikey":     TWELVE_KEY,
        },
        timeout=12,
    ).json()
    if "values" not in resp:
        raise ValueError(resp.get("message", "Twelve Data error"))
    vals = resp["values"][::-1]   # reverse to oldest→newest
    raw  = [(float(v["open"]), float(v["high"]),
             float(v["low"]),  float(v["close"])) for v in vals]
    return _clean_ohlcv(raw)

def _yahoo_fetch(yf_symbol: str, yf_interval: str, yf_range: str) -> dict:
    """
    Yahoo Finance chart API — no library, direct JSON.
    Free, real-time quotes (Forex/Futures ~15 min delayed on free).
    """
    url  = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}"
    resp = requests.get(url, params={
        "interval": yf_interval,
        "range":    yf_range,
    }, headers={
        "User-Agent": "Mozilla/5.0 (compatible; ForexBot/1.0)",
        "Accept":     "application/json",
    }, timeout=12)
    data = resp.json()
    res  = data["chart"]["result"][0]
    q    = res["indicators"]["quote"][0]
    raw  = list(zip(q["open"], q["high"], q["low"], q["close"]))
    return _clean_ohlcv(raw)

def get_multi_tf(symbol: str) -> tuple[dict, dict]:
    """
    Returns (h1_ohlcv, m15_ohlcv).
    Tries Twelve Data first (real-time), falls back to Yahoo Finance.
    """
    meta = SYMBOLS[symbol]
    try:
        h1  = _twelve_fetch(meta["td"], "1h",    200)
        m15 = _twelve_fetch(meta["td"], "15min", 150)
        log.debug(f"[TD] {symbol} OK")
        return h1, m15
    except Exception as e:
        log.warning(f"[TD→YF] {symbol}: {e}")

    h1  = _yahoo_fetch(meta["yf"], "1h",  "10d")
    m15 = _yahoo_fetch(meta["yf"], "15m", "3d")
    log.debug(f"[YF] {symbol} OK")
    return h1, m15

def get_current_price(symbol: str) -> float:
    """Live price for header ticker."""
    meta = SYMBOLS[symbol]
    if TWELVE_KEY:
        try:
            r = requests.get(
                "https://api.twelvedata.com/price",
                params={"symbol": meta["td"], "apikey": TWELVE_KEY},
                timeout=6,
            ).json()
            return float(r.get("price", 0))
        except Exception:
            pass
    try:
        d = _yahoo_fetch(meta["yf"], "1m", "1d")
        return d["close"][-1]
    except Exception:
        return 0.0

# ── PURE PYTHON INDICATORS ────────────────────────────────────────────────────
# All return (prev_value, curr_value) — the two most recent data points.
# That's all we need for crossover detection and zone checks.

def _ema2(prices: list, window: int) -> tuple[float, float]:
    """EMA — returns (prev, curr)."""
    if len(prices) < window + 1:
        s = sum(prices) / len(prices)
        return s, s
    k   = 2.0 / (window + 1)
    val = sum(prices[:window]) / window
    prv = val
    for p in prices[window:]:
        prv = val
        val = p * k + val * (1 - k)
    return prv, val

def _rsi(prices: list, window: int = 14) -> float:
    """RSI — current value only."""
    if len(prices) < window + 2:
        return 50.0
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains  = [max(d, 0.0) for d in deltas]
    losses = [abs(min(d, 0.0)) for d in deltas]
    ag = sum(gains[:window]) / window
    al = sum(losses[:window]) / window
    for i in range(window, len(deltas)):
        ag = (ag * (window - 1) + gains[i]) / window
        al = (al * (window - 1) + losses[i]) / window
    rs = ag / al if al else 100.0
    return 100.0 - 100.0 / (1.0 + rs)

def _atr(highs: list, lows: list, closes: list, window: int = 14) -> float:
    """ATR (Wilder's) — current value only."""
    if len(closes) < window + 2:
        return (max(highs) - min(lows)) / 10.0   # rough fallback
    tr  = [max(highs[i] - lows[i],
               abs(highs[i] - closes[i-1]),
               abs(lows[i]  - closes[i-1]))
           for i in range(1, len(closes))]
    val = sum(tr[:window]) / window
    for t in tr[window:]:
        val = (val * (window - 1) + t) / window
    return val

def _macd_hist2(prices: list, fast=12, slow=26, sig=9) -> tuple[float, float]:
    """MACD histogram — returns (prev, curr)."""
    min_len = slow + sig + 2
    if len(prices) < min_len:
        return 0.0, 0.0
    k_f   = 2.0 / (fast  + 1)
    k_s   = 2.0 / (slow  + 1)
    k_sig = 2.0 / (sig   + 1)
    # Seed both EMAs from same SMA(slow) starting point
    ef = es = sum(prices[:slow]) / slow
    macd_line: list[float] = []
    for p in prices[slow:]:
        ef = p * k_f + ef * (1 - k_f)
        es = p * k_s + es * (1 - k_s)
        macd_line.append(ef - es)
    if len(macd_line) < sig + 2:
        return 0.0, 0.0
    sv = sum(macd_line[:sig]) / sig
    sv_prev = sv
    for m in macd_line[sig:]:
        sv_prev = sv
        sv = m * k_sig + sv * (1 - k_sig)
    return macd_line[-2] - sv_prev, macd_line[-1] - sv

def _stoch2(highs: list, lows: list, closes: list,
            k_win: int = 14, d_win: int = 3) -> tuple[float, float, float, float]:
    """Stochastic — returns (k_prev, k_curr, d_prev, d_curr)."""
    if len(closes) < k_win + d_win + 1:
        return 50.0, 50.0, 50.0, 50.0
    k_series: list[float] = []
    for i in range(k_win - 1, len(closes)):
        hh = max(highs[i - k_win + 1: i + 1])
        ll = min(lows[i  - k_win + 1: i + 1])
        k_series.append(50.0 if hh == ll else (closes[i] - ll) / (hh - ll) * 100.0)
    if len(k_series) < d_win + 1:
        return k_series[-1], k_series[-1], 50.0, 50.0
    d_series: list[float] = [
        sum(k_series[i - d_win + 1: i + 1]) / d_win
        for i in range(d_win - 1, len(k_series))
    ]
    return k_series[-2], k_series[-1], d_series[-2], d_series[-1]

# ── SIGNAL ENGINE ─────────────────────────────────────────────────────────────
def analyze_signal(symbol: str) -> dict | None:
    try:
        h1, m15 = get_multi_tf(symbol)
    except Exception as e:
        log.error(f"[ERR] {symbol}: {e}")
        return None

    if len(h1["close"]) < 60 or len(m15["close"]) < 60:
        log.warning(f"[ERR] {symbol}: insufficient candles")
        return None

    # H1 indicators
    _, h1_ema_slow  = _ema2(h1["close"], EMA_SLOW)
    _, h1_ema_trend = _ema2(h1["close"], EMA_TREND)

    # M15 indicators
    m15_fast_p, m15_fast = _ema2(m15["close"], EMA_FAST)
    m15_slow_p, m15_slow = _ema2(m15["close"], EMA_SLOW)
    rsi                  = _rsi(m15["close"],  RSI_WIN)
    atr                  = _atr(m15["high"],   m15["low"], m15["close"], ATR_WIN)
    hist_p, hist         = _macd_hist2(m15["close"])
    stoch_kp, stoch_k, stoch_dp, stoch_d = _stoch2(m15["high"], m15["low"], m15["close"])

    price = m15["close"][-1]
    bull, bear, reasons = 0, 0, []

    # ── Factor 1: H1 EMA trend direction ──
    if   h1_ema_slow > h1_ema_trend:
        bull += 1;  reasons.append("H1 Trend: Bullish EMA stack")
    elif h1_ema_slow < h1_ema_trend:
        bear += 1;  reasons.append("H1 Trend: Bearish EMA stack")

    # ── Factor 2: M15 EMA fast/slow crossover ──
    if   m15_fast_p < m15_slow_p and m15_fast > m15_slow:
        bull += 1;  reasons.append("M15 EMA Cross: Bullish")
    elif m15_fast_p > m15_slow_p and m15_fast < m15_slow:
        bear += 1;  reasons.append("M15 EMA Cross: Bearish")

    # ── Factor 3: RSI zone ──
    if   rsi <= RSI_OS:           bull += 1;  reasons.append(f"RSI {rsi:.1f} — Oversold reversal")
    elif RSI_OS < rsi < 55:       bull += 1;  reasons.append(f"RSI {rsi:.1f} — Bullish momentum")
    elif 45 < rsi < RSI_OB:       bear += 1;  reasons.append(f"RSI {rsi:.1f} — Bearish momentum")
    elif rsi >= RSI_OB:           bear += 1;  reasons.append(f"RSI {rsi:.1f} — Overbought reversal")

    # ── Factor 4: MACD histogram turn ──
    if   hist_p < 0 and hist > hist_p:  bull += 1;  reasons.append("MACD: Histogram reversing upward")
    elif hist_p > 0 and hist < hist_p:  bear += 1;  reasons.append("MACD: Histogram reversing downward")

    # ── Factor 5: Stochastic cross at extremes ──
    if   stoch_k < 25 and stoch_k > stoch_d:  bull += 1;  reasons.append(f"Stoch {stoch_k:.0f} — Oversold cross")
    elif stoch_k > 75 and stoch_k < stoch_d:  bear += 1;  reasons.append(f"Stoch {stoch_k:.0f} — Overbought cross")

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
    reward = abs(tp1  - price)
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

# ── LOT CALCULATOR (Exness) ───────────────────────────────────────────────────
def calc_lot(symbol: str, balance: float, risk_pct: float, sl_distance: float) -> float:
    meta        = SYMBOLS[symbol]
    risk_amount = balance * risk_pct / 100.0
    if symbol == "XAUUSD":
        lot = risk_amount / (sl_distance * meta["lot_multiplier"])
    else:
        sl_pips = sl_distance / meta["pip_size"]
        lot     = risk_amount / (sl_pips * 10.0)
    return max(0.01, round(lot, 2))

def lot_table_text(symbol: str, sl_distance: float) -> str:
    rows = []
    for bal in (300, 500, 1_000, 2_000, 5_000, 10_000):
        l1 = calc_lot(symbol, bal, 1.0, sl_distance)
        l2 = calc_lot(symbol, bal, 2.0, sl_distance)
        rows.append(f"  ${bal:>7,}  │  1%→{l1:.2f}  │  2%→{l2:.2f}")
    hdr = f"  {'Balance':>8}  │  1% risk  │  2% risk"
    sep = "  " + "─" * 36
    return "\n".join([hdr, sep] + rows)
