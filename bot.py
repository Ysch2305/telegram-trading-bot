import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
import yfinance as yf
import numpy as np
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import logging
import sqlite3
import time
import random
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz

# --- 1. SETUP ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AUTHORIZED_ID = os.environ.get("MY_ID")
USER_CHAT_ID = None 

# Daftar Radar Lebih Luas agar Saham Variatif
IHSG_RADAR = [
    "ASII.JK", "BBCA.JK", "BBNI.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASSA.JK",
    "PANI.JK", "ADRO.JK", "PTBA.JK", "UNTR.JK", "ICBP.JK", "CPIN.JK", "BRMS.JK",
    "BUMI.JK", "GOTO.JK", "MEDC.JK", "TPIA.JK", "AMRT.JK", "PGAS.JK", "ADMR.JK",
    "ANTM.JK", "HRUM.JK", "MDKA.JK", "ITMG.JK", "AKRA.JK", "TINS.JK", "LSIP.JK"
]

def get_realtime_price(sym):
    try:
        ticker = sym.split('.')[0]
        url = f"https://www.google.com/finance/quote/{ticker}:IDX?rand={time.time()}"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=7)
        soup = BeautifulSoup(response.text, 'html.parser')
        price_class = soup.find("div", {"class": "YMlSbc"})
        if price_class:
            return float(price_class.text.replace('IDR', '').replace(',', '').strip())
        return None
    except: return None

# --- 2. DATABASE ---
def init_db():
    with sqlite3.connect('bot_data.db', check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS watchlist (symbol TEXT PRIMARY KEY)')
        conn.commit()

def db_manage_watchlist(action, symbol=None):
    with sqlite3.connect('bot_data.db', check_same_thread=False) as conn:
        c = conn.cursor()
        if action == "add" and symbol:
            sym = symbol.upper()
            if not sym.endswith(".JK"): sym += ".JK"
            c.execute("INSERT OR IGNORE INTO watchlist VALUES (?)", (sym,))
            conn.commit()
            return sym
        elif action == "list":
            c.execute("SELECT symbol FROM watchlist")
            return [r[0] for r in c.fetchall()]

# --- 3. ANALISA KHUSUS SCALPING (AUTO SIGNAL) ---
def analyze_scalping(sym):
    try:
        df = yf.download(sym, period="1d", interval="1m", progress=False, auto_adjust=True) # Data 1 Menit
        if df is None or len(df) < 20: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        curr_p = float(df["Close"].iloc[-1])
        prev_p = float(df["Close"].iloc[-2])
        
        # 1. Deteksi Ledakan Volume (VSA)
        avg_vol = df["Volume"].tail(10).mean()
        curr_vol = df["Volume"].iloc[-1]
        
        # 2. Deteksi Breakout High (Momentum)
        high_5m = df["High"].tail(5).max()
        
        # Logika Scalping: Volume Meledak + Harga Tembus High Terakhir
        if curr_vol > (avg_vol * 2.5) and curr_p >= high_5m:
            return {
                "type": "SCALPING 🔥",
                "price": curr_p,
                "target": curr_p * 1.02, # Target 2% saja
                "stop": curr_p * 0.985   # Stop loss ketat 1.5%
            }
        return None
    except: return None

# --- 4. ANALISA KHUSUS SWING (SCAN MANUAL) ---
def analyze_swing(sym):
    try:
        rt_price = get_realtime_price(sym)
        df = yf.download(sym, period="1mo", interval="5m", progress=False, auto_adjust=True)
        if df is None or len(df) < 50: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        curr_p = rt_price if rt_price else float(df["Close"].iloc[-1])
        ema20 = df["Close"].ewm(span=20).mean().iloc[-1]
        
        # Area Antri Support
        low_support = df["Low"].tail(100).min()
        
        status = "SAATNYA BELI ✅" if curr_p > ema20 else "DISKON SEHAT 🛍️"
        if curr_p < ema20 * 0.98: status = "JANGAN SENTUH 🚫"

        return {
            "status": status,
            "price": curr_p,
            "entry": f"{int(low_support)} - {int(low_support * 1.02)}",
            "tp": curr_p * 1.07,
            "sl": low_support * 0.97
        }
    except: return None

# --- 5. JOB AUTO SIGNAL (TIAP 5 MENIT) ---
def auto_signal_job(context: CallbackContext):
    global USER_CHAT_ID
    if not USER_CHAT_ID: return
    
    now = datetime.now(pytz.timezone('Asia/Jakarta'))
    if now.weekday() < 5 and 9 <= now.hour < 16:
        # Acak 10 saham dari radar agar tidak bosan
        pool = random.sample(IHSG_RADAR, 10)
        for sym in pool:
            res = analyze_scalping(sym)
            if res:
                msg = (f"⚡️ **SCALPING SIGNAL (1M/5M)**\n\n"
                       f"🚀 **{sym.replace('.JK','')}**\n"
                       f"💰 Masuk: {res['price']:,.0f}\n"
                       f"🎯 Bungkus (2%): {res['target']:,.0f}\n"
                       f"🛑 Keluar (1.5%): {res['stop']:,.0f}\n\n"
                       f"*Sinyal berdasarkan ledakan volume realtime!*")
                context.bot.send_message(chat_id=USER_CHAT_ID, text=msg, parse_mode='Markdown')
                time.sleep(1) # Jeda agar tidak dianggap spam

# --- 6. COMMAND HANDLERS ---
def start(update: Update, context: CallbackContext):
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    init_db()
    update.message.reply_text("🏛 **Bot Dua Mode Aktif!**\n\n1. **Auto Signal (5m)**: Khusus Scalping (Otomatis).\n2. **Scan Manual**: Khusus Swing (Ketik /scan).")

def scan_manual(update: Update, context: CallbackContext):
    stocks = db_manage_watchlist("list")
    if not stocks: return update.message.reply_text("Watchlist kosong.")
    
    msg = update.message.reply_text("🔎 **Menganalisa tren Swing...**")
    report = "🏛 **SWING ANALYSIS REPORT**\n\n"
    
    for s in stocks:
        res = analyze_swing(s)
        if res:
            report += (f"**{s.replace('.JK','')}** | {res['status']}\n"
                       f"💰 Harga: {res['price']:,.0f}\n"
                       f"📥 Area Antri: {res['entry']}\n"
                       f"🎯 Target Jual: {res['tp']:,.0f}\n\n")
    context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=msg.message_id, text=report, parse_mode='HTML')

# --- 7. MAIN ---
if __name__ == '__main__':
    init_db()
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Scheduler untuk Scalping 5 Menit
    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(auto_signal_job, 'interval', minutes=5, args=[updater])
    scheduler.start()
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("add", lambda u, c: u.message.reply_text(f"✅ {db_manage_watchlist('add', c.args[0])} masuk!") if c.args else None))
    dp.add_handler(CommandHandler("scan", scan_manual))
    
    updater.start_polling()
    updater.idle()
