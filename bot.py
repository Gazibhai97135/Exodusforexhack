"""
bot.py — ForexSignal Pro Telegram Bot
Auto-signals to channel, /start menu, /lot calculator, /signal command.
Developer: @exodus_own3r

Run: python bot.py
"""

import os, asyncio, logging, time
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, Bot
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)
from telegram.constants import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

from engine import (
    init_db, save_signal, get_signals, get_stats,
    analyze_signal, calc_lot, lot_table_text, SYMBOLS,
)

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

BOT_TOKEN  = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")   # e.g. @your_channel or -1001234567890
WEBAPP_URL = os.getenv("WEBAPP_URL", "http://localhost:5000")
DEV        = "@exodus_own3r"
SCAN_MINS  = 15

# Dedup tracker: symbol+direction → last sent unix timestamp
_last_sent: dict[str, float] = {}

# ── FORMAT SIGNAL ─────────────────────────────────────────────────────────────
def build_signal_msg(sig: dict) -> str:
    sym   = sig["symbol"]
    meta  = SYMBOLS[sym]
    dec   = meta["decimals"]
    ico   = meta["icon"]
    label = meta["label"]
    arrow = "📈" if sig["direction"] == "BUY" else "📉"
    f     = lambda v: f"{v:.{dec}f}"

    sl_dist     = abs(sig["entry"] - sig["sl"])
    lot_section = lot_table_text(sym, sl_dist)
    reasons     = "\n".join(f"   › {r}" for r in sig["reasons"])

    return (
        f"{ico} *{label} SIGNAL*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"*Direction:*  {sig['direction']} {arrow}\n"
        f"*Entry:*      `{f(sig['entry'])}`\n"
        f"*Stop Loss:*  `{f(sig['sl'])}` 🔴\n"
        f"*TP 1:*       `{f(sig['tp1'])}` 🟢\n"
        f"*TP 2:*       `{f(sig['tp2'])}` 🎯\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"*R/R Ratio:*  1:{sig['rr']}\n"
        f"*Confidence:* {sig['confidence']}\n"
        f"*Score:*      {sig['confluence_score']}/{sig['max_factors']} factors\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *LOT SIZE GUIDE (Exness):*\n"
        f"`{lot_section}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *Confluence Factors:*\n"
        f"{reasons}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Dev: {DEV}"
    )

# ── AUTO-SCAN JOB ─────────────────────────────────────────────────────────────
async def auto_scan(app: Application):
    """Runs every SCAN_MINS minutes via AsyncIOScheduler."""
    log.info("[SCAN] Starting market scan…")
    for sym in SYMBOLS:
        try:
            sig = analyze_signal(sym)
        except Exception as e:
            log.error(f"[SCAN ERR] {sym}: {e}")
            continue

        if not sig:
            log.info(f"[NEUTRAL] {sym} — no confluence")
            continue

        # 1-hour dedup: don't resend same direction on same pair within 60 min
        key = f"{sym}_{sig['direction']}"
        now = time.time()
        if key in _last_sent and now - _last_sent[key] < 3600:
            log.info(f"[SKIP] {sym} {sig['direction']} — sent <60 min ago")
            continue

        _last_sent[key] = now
        save_signal(sig)
        msg = build_signal_msg(sig)

        try:
            await app.bot.send_message(
                chat_id=CHANNEL_ID,
                text=msg,
                parse_mode=ParseMode.MARKDOWN,
            )
            log.info(f"[SENT] {sym} {sig['direction']} @ {sig['entry']} → {CHANNEL_ID}")
        except Exception as e:
            log.error(f"[SEND ERR] {sym}: {e}")

# ── /start ────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("📊 Live Dashboard",
                              web_app=WebAppInfo(url=WEBAPP_URL))],
        [
            InlineKeyboardButton("📈 Get Signal Now", callback_data="cb_signal"),
            InlineKeyboardButton("📉 Win Stats",      callback_data="cb_stats"),
        ],
        [InlineKeyboardButton("💰 Lot Calculator",    callback_data="cb_lot_help")],
        [InlineKeyboardButton("👨‍💻 Developer",        url="https://t.me/exodus_own3r")],
    ]
    await update.message.reply_text(
        "🟢 *ForexSignal Pro*\n\n"
        "Real-time *Gold & EUR/USD* signals\n"
        "with Exness lot sizing built in.\n\n"
        "Signals drop automatically every scan.\n"
        "Choose an option 👇",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.MARKDOWN,
    )

# ── /signal ───────────────────────────────────────────────────────────────────
async def _do_signal(target, context):
    """Shared logic for /signal command and callback button."""
    wait = await target.reply_text("⏳ Scanning live markets…")
    sent_any = False
    for sym in SYMBOLS:
        try:
            sig = analyze_signal(sym)
        except Exception as e:
            await target.reply_text(f"❌ {SYMBOLS[sym]['label']}: data error — {e}")
            continue
        if sig:
            await target.reply_text(build_signal_msg(sig), parse_mode=ParseMode.MARKDOWN)
            sent_any = True
        else:
            ico   = SYMBOLS[sym]["icon"]
            label = SYMBOLS[sym]["label"]
            await target.reply_text(
                f"{ico} *{label}*\n"
                f"No confluence at this moment.\n"
                f"Market is consolidating — check again in 15 min.",
                parse_mode=ParseMode.MARKDOWN,
            )
    try:
        await wait.delete()
    except Exception:
        pass

async def cmd_signal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _do_signal(update.message, ctx)

async def cb_signal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await _do_signal(update.callback_query.message, ctx)

# ── /stats ────────────────────────────────────────────────────────────────────
async def _do_stats(target):
    s       = get_stats()
    pending = max(0, s["total"] - s["wins"] - s["losses"])
    text = (
        f"📊 *Signal Performance*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Total Signals: *{s['total']}*\n"
        f"✅ Wins:        *{s['wins']}*\n"
        f"❌ Losses:      *{s['losses']}*\n"
        f"⏳ Pending:     *{pending}*\n"
        f"Win Rate:      *{s['win_rate']}%*\n"
        f"Avg Pips:      *{s['avg_pips']}*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Dev: {DEV}"
    )
    await target.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _do_stats(update.message)

async def cb_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await _do_stats(update.callback_query.message)

# ── /lot <balance> <risk%> ────────────────────────────────────────────────────
async def _do_lot_help(target):
    await target.reply_text(
        "💰 *Lot Calculator*\n\n"
        "Usage: `/lot <balance> <risk_percent>`\n\n"
        "Examples:\n"
        "  `/lot 1000 1`  — 1% risk on $1,000\n"
        "  `/lot 5000 2`  — 2% risk on $5,000\n"
        "  `/lot 500 1.5` — 1.5% risk on $500\n\n"
        "Calculates exact Exness lot size for current\n"
        "Gold & EUR/USD signals based on your SL distance.",
        parse_mode=ParseMode.MARKDOWN,
    )

async def cmd_lot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if len(args) < 2:
        await _do_lot_help(update.message)
        return

    try:
        balance  = float(args[0].replace(",", ""))
        risk_pct = float(args[1])
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid values.\nExample: `/lot 1000 1`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if balance <= 0 or not (0.1 <= risk_pct <= 10):
        await update.message.reply_text("❌ Balance must be > 0, risk between 0.1% and 10%.")
        return

    lines = [f"💰 *Lot Sizes — ${balance:,.0f} account, {risk_pct}% risk*",
             "━━━━━━━━━━━━━━━━━━━"]

    for sym in SYMBOLS:
        meta  = SYMBOLS[sym]
        label = meta["label"]
        ico   = meta["icon"]

        sig = analyze_signal(sym)
        if not sig:
            lines.append(f"\n{ico} *{label}*: No active signal right now")
            continue

        sl_dist = abs(sig["entry"] - sig["sl"])
        lot     = calc_lot(sym, balance, risk_pct, sl_dist)
        dec     = meta["decimals"]
        risk_usd = balance * risk_pct / 100

        lines += [
            f"\n{ico} *{label}*",
            f"   Direction: *{sig['direction']}*",
            f"   Entry:     `{sig['entry']:.{dec}f}`",
            f"   SL:        `{sig['sl']:.{dec}f}`  (dist: {sl_dist:.{dec}f})",
            f"   Max Risk:  *${risk_usd:,.2f}*",
            f"   ✅ *Lot size: {lot:.2f} lots*",
        ]

    lines += ["━━━━━━━━━━━━━━━━━━━", f"⚡ Dev: {DEV}"]
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def cb_lot_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await _do_lot_help(update.callback_query.message)

# ── MAIN ──────────────────────────────────────────────────────────────────────
async def post_init(app: Application):
    """Called once after bot starts — run initial scan + start scheduler."""
    init_db()
    log.info(f"[BOT] Token: ...{BOT_TOKEN[-8:]}")
    log.info(f"[BOT] Channel: {CHANNEL_ID}")
    log.info(f"[BOT] Dashboard: {WEBAPP_URL}")

    sched = AsyncIOScheduler()
    sched.add_job(auto_scan, "interval", minutes=SCAN_MINS, args=[app])
    sched.start()
    log.info(f"[SCHED] Auto-scan every {SCAN_MINS} min — running first scan now…")

    # First scan immediately at startup
    asyncio.create_task(auto_scan(app))

def main():
    if not BOT_TOKEN:
        raise SystemExit("❌ BOT_TOKEN missing in .env")
    if not CHANNEL_ID:
        raise SystemExit("❌ CHANNEL_ID missing in .env")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("signal", cmd_signal))
    app.add_handler(CommandHandler("stats",  cmd_stats))
    app.add_handler(CommandHandler("lot",    cmd_lot))

    app.add_handler(CallbackQueryHandler(cb_signal,  pattern="^cb_signal$"))
    app.add_handler(CallbackQueryHandler(cb_stats,   pattern="^cb_stats$"))
    app.add_handler(CallbackQueryHandler(cb_lot_help,pattern="^cb_lot_help$"))

    log.info("🚀 ForexSignal Pro Bot starting…")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
