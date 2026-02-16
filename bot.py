import os
import yfinance as yf
import pandas as pd
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler, Filters
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz
import sqlite3
import random

# 1. Setup Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# 2. Config
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AUTHORIZED_ID = os.environ.get("MY_ID")

USER_CHAT_ID = None
SENT_STOCKS = [] 

# --- DAFTAR RADAR IHSG (Auto Update) ---
IHSG_RADAR = [
    "ASII.JK", "BBCA.JK", "BBNI.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "GOTO.JK",
    "ASSA.JK", "BUMI.JK", "ANTM.JK", "MDKA.JK", "INCO.JK", "PGAS.JK", "UNTR.JK",
    "AMRT.JK", "CPIN.JK", "ICBP.JK", "KLBF.JK", "ADRO.JK", "ITMG.JK", "PTBA.JK",
    "BRIS.JK", "ARTO.JK", "MEDC.JK", "TOWR.JK", "EXCL.JK", "AKRA.JK", "BRPT.JK"
]

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect('bot_data.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS watchlist (symbol TEXT PRIMARY KEY)')
    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    conn.commit()
    conn.close()

def db_manage_watchlist(action, symbol=None):
    conn = sqlite3.connect('bot_data.db', check_same_thread=False)
    c = conn.cursor()
    if action == "add":
        c.execute("INSERT OR IGNORE INTO watchlist VALUES (?)", (symbol,))
    elif action == "remove":
        c.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
    elif action == "list":
        c.execute("SELECT symbol FROM watchlist")
        res = [r[0] for r in c.fetchall()]
        conn.close()
        return res
    conn.commit()
    conn.close()

def save_modal(val):
    conn = sqlite3.connect('bot_data.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings VALUES ('modal', ?)", (str(val),))
    conn.commit()
    conn.close()

def load_modal():
    conn = sqlite3.connect('bot_data.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = 'modal'")
    res = c.fetchone()
    conn.close()
    return int(res[0]) if res else 0

init_db()

def is_auth(update: Update):
    uid = str(update.message.from_user.id)
    return AUTHORIZED_ID and uid == str(AUTHORIZED_ID).strip()

# --- ANALYSIS CORE ---
def analyze_stock(sym):
    try:
        # Mengambil data 3 bulan terakhir
        df = yf.download(sym, period="3mo", interval="1d", progress=False, auto_adjust=True)
        if df is None or len(df) < 20: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        close = df["Close"]
        curr_p = float(close.iloc[-1])
        ema20 = close.ewm(span=20).mean().iloc[-1]
        ema50 = close.ewm(span=50).mean().iloc[-1]
        
        delta = close.diff()
        up = delta.clip(lower=0).rolling(14).mean().iloc[-1]
        down = (-1 * delta.clip(upper=0)).rolling(14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (up/down))) if down != 0 else 100
        
        tp = curr_p * 1.05
        sl = curr_p * 0.97
        
        if ema20 > ema50 and rsi > 55:
            status, reason = "BUY 🟢", "Trend Bullish & Momentum Kuat."
        elif ema20 < ema50 and rsi < 45:
            status, reason = "SELL 🔴", "Trend Bearish & Momentum Lemah."
        else:
            status, reason = "HOLD 🟡", "Sideways/Konsolidasi."
            
        return {"status": status, "price": curr_p, "tp": tp, "sl": sl, "reason": reason}
    except: return None

# --- COMMANDS ---
def start(update: Update, context: CallbackContext):
    if not is_auth(update): return
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    modal = load_modal()
    if modal == 0:
        update.message.reply_text("👋 Masukkan <b>Modal Investasi</b> Anda (angka saja):", parse_mode='HTML')
    else:
        update.message.reply_text(f"✅ Bot Aktif. Modal: Rp{modal:,.0f}\n/scan untuk cek watchlist.")

def scan_watchlist(update: Update, context: CallbackContext):
    if not is_auth(update): return
    stocks = db_manage_watchlist("list")
    if not stocks:
        update.message.reply_text("Watchlist kosong. Gunakan /add KODE")
        return

    # Kirim pesan status awal
    status_msg = update.message.reply_text("🔎 Sedang menganalisa... Mohon tunggu.")
    
    final_report = "🔎 <b>HASIL SCAN WATCHLIST</b>\n\n"
    for s in stocks:
        res = analyze_stock(s)
        if res:
            final_report += (f"<b>{s.replace('.JK','')}</b> | {res['status']}\n"
                             f"💰 Harga: {res['price']:,.0f}\n"
                           f"🎯 TP: {res['tp']:,.0f} | 🛑 SL: {res['sl']:,.0f}\n"
                           f"📝 {res['reason']}\n\n")
        else:
            final_report += f"❌ <b>{s}</b>: Gagal mengambil data.\n\n"
    
    # Kirim satu pesan besar berisi semua hasil
    context.bot.edit_message_text(
        chat_id=update.message.chat_id,
        message_id=status_msg.message_id,
        text=final_report,
        parse_mode='HTML'
    )

def handle_text(update: Update, context: CallbackContext):
    if not is_auth(update): return
    text = update.message.text.strip()
    if text.isdigit():
        save_modal(int(text))
        update.message.reply_text(f"✅ Modal diset: Rp{int(text):,.0f}")

def add_stock(update: Update, context: CallbackContext):
    if not is_auth(update) or not context.args: return
    sym = context.args[0].upper()
    if ".JK" not in sym: sym += ".JK"
    db_manage_watchlist("add", sym)
    update.message.reply_text(f"✅ {sym} ditambah.")

def remove_stock(update: Update, context: CallbackContext):
    if not is_auth(update) or not context.args: return
    sym = context.args[0].upper()
    db_manage_watchlist("remove", sym + ".JK" if ".JK" not in sym else sym)
    update.message.reply_text(f"🗑 {sym} dihapus.")

def list_watchlist(update: Update, context: CallbackContext):
    if not is_auth(update): return
    s = db_manage_watchlist("list")
    update.message.reply_text(f"📋 Watchlist: {', '.join(s) if s else 'Kosong'}")

def ubah_modal(update: Update, context: CallbackContext):
    if not is_auth(update): return
    update.message.reply_text("Masukkan modal baru:")

# --- AUTO SIGNAL (5 MENIT) ---
def auto_signal_job(context: CallbackContext):
    global USER_CHAT_ID, SENT_STOCKS
    modal = load_modal()
    now = datetime.now(pytz.timezone('Asia/Jakarta'))
    if USER_CHAT_ID and modal > 0 and (now.weekday() < 5 and 9 <= now.hour < 16):
        results = []
        found_now = []
        pool = [s for s in IHSG_RADAR if s not in SENT_STOCKS]
        random.shuffle(pool)
        for sym in pool:
            res = analyze_stock(sym)
            if res and "BUY" in res["status"] and modal >= (res["price"] * 100):
                results.append(f"🔥 <b>BUY: {sym.replace('.JK','')}</b>\nHarga: {res['price']:,.0f}\n🎯 TP: {res['tp']:,.0f}\n📝 {res['reason']}")
                found_now.append(sym)
            if len(results) >= 3: break
        if results:
            SENT_STOCKS = found_now
            context.bot.send_message(chat_id=USER_CHAT_ID, text="🚀 <b>UPDATE SIGNAL</b>\n\n"+"\n\n".join(results), parse_mode='HTML')

if __name__ == '__main__':
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("add", add_stock))
    dp.add_handler(CommandHandler("remove", remove_stock))
    dp.add_handler(CommandHandler("list", list_watchlist))
    dp.add_handler(CommandHandler("scan", scan_watchlist))
    dp.add_handler(CommandHandler("ubah_modal", ubah_modal))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
    
    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(auto_signal_job, 'interval', minutes=5, args=[updater])
    scheduler.start()
    
    updater.start_polling(drop_pending_updates=True)
    updater.idle()
