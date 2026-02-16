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

# --- DAFTAR RADAR IHSG ---
IHSG_SCAN_LIST = [
    "ASII.JK", "BBCA.JK", "BBNI.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "GOTO.JK", 
    "ASSA.JK", "BUMI.JK", "ANTM.JK", "MDKA.JK", "INCO.JK", "PGAS.JK", "UNTR.JK", 
    "AMRT.JK", "CPIN.JK", "ICBP.JK", "KLBF.JK", "ADRO.JK", "ITMG.JK", "PTBA.JK",
    "BRIS.JK", "ARTO.JK", "MEDC.JK", "TOWR.JK", "EXCL.JK", "AKRA.JK", "BRPT.JK",
    "AMMN.JK", "INKP.JK", "TPIA.JK", "MAPA.JK", "ACES.JK", "HRUM.JK", "BELL.JK"
]

# --- DATABASE LOGIC ---
def init_db():
    conn = sqlite3.connect('watchlist.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stocks (symbol TEXT PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit()
    conn.close()

def save_modal(val):
    conn = sqlite3.connect('watchlist.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings VALUES ('modal', ?)", (str(val),))
    conn.commit()
    conn.close()

def load_modal():
    conn = sqlite3.connect('watchlist.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = 'modal'")
    res = c.fetchone()
    conn.close()
    return int(res[0]) if res else 0

init_db()

# --- SECURITY CHECK ---
def is_auth(update: Update):
    user_id = str(update.message.from_user.id)
    logger.info(f"USER COBA AKSES: {user_id}")
    if AUTHORIZED_ID and user_id == str(AUTHORIZED_ID):
        return True
    return False

# --- ANALYSIS CORE ---
def analyze_symbol(sym, df):
    if df is None or len(df) < 20: 
        return None
    if isinstance(df.columns, pd.MultiIndex): 
        df.columns = df.columns.get_level_values(0)
    
    close = df["Close"]
    volume = df["Volume"]
    curr_p = float(close.iloc[-1])
    
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    
    # RSI Calculation (Broken down to avoid copy-paste errors)
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    
    ma_up = up.rolling(window=14).mean().iloc[-1]
    ma_down = down.rolling(window=14).mean().iloc[-1]
    
    if ma_down == 0: 
        rsi = 100
    else:
        rs = ma_up / ma_down
        rsi = 100 - (100 / (1 + rs))
    
    avg_vol = volume.rolling(window=20).mean().iloc[-1]
    vol_status = "Tinggi 📈" if float(volume.iloc[-1]) > avg_vol else "Rendah 📉"
    
    status = "HOLD 🟡"
    if ema20 > ema50 and rsi > 55: 
        status = "BUY 🟢"
    elif ema20 < ema50 and rsi < 45: 
        status = "SELL 🔴"
        
    return {"status": status, "price": curr_p, "vol": vol_status}

# --- AUTO SCAN JOB ---
def auto_scan_job(context: CallbackContext):
    global USER_CHAT_ID, SENT_STOCKS
    modal = load_modal()
    now = datetime.now(pytz.timezone('Asia/Jakarta'))
    
    if USER_CHAT_ID and modal > 0 and (now.weekday() < 5 and 9 <= now.hour < 16):
        results = []
        found_now = []
        pool = [s for s in IHSG_SCAN_LIST if s not in SENT_STOCKS]
        random.shuffle(pool)

        for sym in pool:
            try:
                df = yf.download(sym, period="3mo", interval="1d", progress=False, auto_adjust=True)
                res = analyze_symbol(sym, df)
                if res:
                    price_lot = res["price"] * 100
                    if modal >= price_lot:
                        if res["status"] == "BUY 🟢" or (res["status"] == "HOLD 🟡" and "Tinggi 📈" in res["vol"]):
                            tag = "🔥 REKOMENDASI" if res["status"] == "BUY 🟢" else "👀 POTENSI"
                            results.append(f"{tag}: <b>{sym.replace('.JK','')}</b>\nHarga: Rp{res['price']:,.0f}\nStatus: {res['status']}")
                            found_now.append(sym)
                if len(results) >= 3: break
            except: continue
        
        if results:
            SENT_STOCKS = (SENT_STOCKS + found_now)[-10:] 
            context.bot.send_message(chat_id=USER_CHAT_ID, text="🚀 <b>RADAR SIGNAL BARU</b>\n\n" + "\n\n".join(results), parse_mode='HTML')

# --- COMMANDS ---
def start(update: Update, context: CallbackContext):
    if not is_auth(update):
        update.message.reply_text("⛔ Akses Ditolak. Pastikan MY_ID benar.")
        return
    
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    modal = load_modal()
    
    if modal == 0:
        update.message.reply_text("👋 <b>Halo Bos!</b>\nMasukkan modal Anda (Angka saja):", parse_mode='HTML')
    else:
        update.message.reply_text(f"🚀 Bot Aktif.\nModal: <b>Rp{modal:,.0f}</b>\n/ubah_modal untuk ganti.", parse_mode='HTML')

def handle_msg(update: Update, context: CallbackContext):
    if not is_auth(update): return
    try:
        val = int(update.message.text.replace(".", "").replace(",", ""))
        save_modal(val)
        update.message.reply_text(f"✅ Modal diset: <b>Rp{val:,.0f}</b>")
