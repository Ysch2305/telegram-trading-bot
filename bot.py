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

# --- DAFTAR RADAR IHSG (Untuk Auto Update tiap 5 menit) ---
IHSG_RADAR = [
    "ASII.JK", "BBCA.JK", "BBNI.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "GOTO.JK",
    "ASSA.JK", "BUMI.JK", "ANTM.JK", "MDKA.JK", "INCO.JK", "PGAS.JK", "UNTR.JK",
    "AMRT.JK", "CPIN.JK", "ICBP.JK", "KLBF.JK", "ADRO.JK", "ITMG.JK", "PTBA.JK",
    "BRIS.JK", "ARTO.JK", "MEDC.JK", "TOWR.JK", "EXCL.JK", "AKRA.JK", "BRPT.JK",
    "AMMN.JK", "INKP.JK", "TPIA.JK", "MAPA.JK", "ACES.JK", "HRUM.JK", "PANI.JK"
]

# --- DATABASE LOGIC ---
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

# --- SECURITY CHECK ---
def is_auth(update: Update):
    uid = str(update.message.from_user.id)
    return AUTHORIZED_ID and uid == str(AUTHORIZED_ID).strip()

# --- ANALYSIS CORE ---
def analyze_stock(sym):
    try:
        df = yf.download(sym, period="3mo", interval="1d", progress=False, auto_adjust=True)
        if df is None or len(df) < 20: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        close = df["Close"]
        curr_p = float(close.iloc[-1])
        
        # Indikator EMA (Trend)
        ema20 = close.ewm(span=20).mean().iloc[-1]
        ema50 = close.ewm(span=50).mean().iloc[-1]
        
        # Indikator RSI (Momentum)
        delta = close.diff()
        up = delta.clip(lower=0).rolling(14).mean().iloc[-1]
        down = (-1 * delta.clip(upper=0)).rolling(14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (up/down))) if down != 0 else 100
        
        # Target Price (5%) & Stop Loss (3%)
        tp = curr_p * 1.05
        sl = curr_p * 0.97
        
        # Logika Sinyal & Penjelasan
        if ema20 > ema50 and rsi > 55:
            status = "BUY 🟢"
            reason = "Trend Bullish (EMA Golden Cross) & Momentum Kuat (RSI > 55)."
        elif ema20 < ema50 and rsi < 45:
            status = "SELL 🔴"
            reason = "Trend Bearish (EMA Death Cross) & Momentum Lemah (RSI < 45)."
        else:
            status = "HOLD 🟡"
            reason = "Market sedang konsolidasi/Sideways. Tunggu konfirmasi EMA/RSI."
            
        return {
            "status": status, 
            "price": curr_p, 
            "tp": tp, 
            "sl": sl, 
            "reason": reason,
            "rsi": rsi
        }
    except Exception as e:
        logger.error(f"Error analyze {sym}: {e}")
        return None

# --- AUTO SIGNAL JOB (Tiap 5 Menit) ---
def auto_signal_job(context: CallbackContext):
    global USER_CHAT_ID, SENT_STOCKS
    modal = load_modal()
    now = datetime.now(pytz.timezone('Asia/Jakarta'))
    
    # Syarat: Jam Bursa Senin-Jumat 09:00-16:00
    if USER_CHAT_ID and modal > 0 and (now.weekday() < 5 and 9 <= now.hour < 16):
        results = []
        found_now = []
        
        pool = [s for s in IHSG_RADAR if s not in SENT_STOCKS]
        random.shuffle(pool)

        for sym in pool:
            res = analyze_stock(sym)
            if res and "BUY" in res["status"]:
                price_lot = res["price"] * 100
                if modal >= price_lot:
                    msg = (f"🔥 <b>SIGNAL BUY: {sym.replace('.JK','')}</b>\n"
                           f"Harga: Rp{res['price']:,.0f}\n"
                           f"🎯 TP: Rp{res['tp']:,.0f}\n"
                           f"🛑 SL: Rp{res['sl']:,.0f}\n"
                           f"📝 Analisa: {res['reason']}")
                    results.append(msg)
                    found_now.append(sym)
            if len(results) >= 3: break
        
        if results:
            SENT_STOCKS = found_now
            text = "🚀 <b>RADAR SIGNAL (5 MENITAN)</b>\n\n" + "\n\n".join(results)
            context.bot.send_message(chat_id=USER_CHAT_ID, text=text, parse_mode='HTML')

# --- COMMAND HANDLERS ---
def start(update: Update, context: CallbackContext):
    if not is_auth(update): return
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    modal = load_modal()
    if modal == 0:
        update.message.reply_text("👋 <b>Akses Diterima!</b>\n\nSilakan masukkan <b>Modal Investasi</b> Anda (angka saja):", parse_mode='HTML')
    else:
        update.message.reply_text(f"✅ <b>Bot Aktif</b>\nModal: Rp{modal:,.0f}\n\n<b>Menu:</b>\n/scan - Cek Watchlist Manual\n/list - Lihat Watchlist\n/add KODE - Tambah Saham\n/remove KODE - Hapus Saham\n/ubah_modal - Ganti Modal", parse_mode='HTML')

def handle_text(update: Update, context: CallbackContext):
    if not is_auth(update): return
    text = update.message.text.strip()
    if text.isdigit():
        val = int(text)
        save_modal(val)
        update.message.reply_text(f"✅ Modal disimpan: <b>Rp{val:,.0f}</b>\nSinyal otomatis akan berjalan tiap 5 menit jika modal cukup untuk membeli 1 lot saham.", parse_mode='HTML')

def add_stock(update: Update, context: CallbackContext):
    if not is_auth(update) or not context.args: return
    sym = context.args[0].upper()
    if ".JK" not in sym: sym += ".JK"
    db_manage_watchlist("add", sym)
    update.message.reply_text(f"✅ {sym} berhasil ditambah.")

def remove_stock(update: Update, context: CallbackContext):
    if not is_auth(update) or not context.args: return
    sym = context.args[0].upper()
    if ".JK" not in sym: sym += ".JK"
    db_manage_watchlist("remove", sym)
    update.message.reply_text(f"🗑 {sym} dihapus.")

def list_watchlist(update: Update, context: CallbackContext):
    if not is_auth(update): return
    stocks = db_manage_watchlist("list")
    txt = "📋 <b>Watchlist Manual:</b>\n" + "\n".join([f"- {s}" for s in stocks]) if stocks else "Kosong."
    update.message.reply_text(txt, parse_mode='HTML')

def scan_watchlist(update: Update, context: CallbackContext):
    if not is_auth(update): return
    stocks = db_manage_watchlist("list")
    if not stocks:
        update.message.reply_text("Gunakan /add dulu untuk mengisi watchlist.")
        return
    update.message.reply_text("🔎 Menganalisa watchlist manual...")
    for s in stocks:
        res = analyze_stock(s)
        if res:
            msg = (f"🔍 <b>{s.replace('.JK','')}</b>\n"
                   f"Status: {res['status']}\n"
                   f"Harga: Rp{res['price']:,.0f}\n"
                   f"🎯 TP: Rp{res['tp']:,.0f}\n"
                   f"🛑 SL: Rp{res['sl']:,.0f}\n"
                   f"📝 Analisa: {res['reason']}")
            update.message.reply_text(msg, parse_mode='HTML')

def ubah_modal(update: Update, context: CallbackContext):
    if not is_auth(update): return
    update.message.reply_text("Silakan masukkan nominal modal baru Anda:")

# --- RUNNER ---
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

    logger.info("Bot Online...")
    updater.start_polling(drop_pending_updates=True)
    updater.idle()
