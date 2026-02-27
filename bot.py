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

# --- 1. SETUP & RADAR LEBIH LUAS ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
USER_CHAT_ID = None 

# Daftar saham diperbanyak (IDX80 & Bluechip) agar variatif
IHSG_RADAR = [
    "ASII.JK", "BBCA.JK", "BBNI.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASSA.JK",
    "PANI.JK", "ADRO.JK", "PTBA.JK", "UNTR.JK", "ICBP.JK", "CPIN.JK", "BRMS.JK",
    "BUMI.JK", "GOTO.JK", "MEDC.JK", "TPIA.JK", "AMRT.JK", "PGAS.JK", "ADMR.JK",
    "ANTM.JK", "HRUM.JK", "MDKA.JK", "ITMG.JK", "AKRA.JK", "TINS.JK", "LSIP.JK",
    "DEWA.JK", "ENRG.JK", "BRIS.JK", "BBTN.JK", "MDDK.JK", "KLBF.JK", "SMGR.JK"
]

# --- 2. FUNGSI INDIKATOR MACD ---
def get_macd(close_prices):
    exp1 = close_prices.ewm(span=12, adjust=False).mean()
    exp2 = close_prices.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal

# --- 3. ANALISA KHUSUS SCALPING (AUTO SIGNAL) ---
def analyze_scalping(sym):
    try:
        # Menggunakan data 1 menit untuk reaksi cepat
        df = yf.download(sym, period="1d", interval="1m", progress=False, auto_adjust=True)
        if df is None or len(df) < 30: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        curr_p = float(df["Close"].iloc[-1])
        open_p = float(df["Open"].iloc[0])
        
        # --- FILTER ANTI-DUMP ---
        # Jika harga hari ini sudah turun > 5% atau 5 menit terakhir turun tajam, abaikan.
        price_change_day = ((curr_p - open_p) / open_p) * 100
        five_min_change = ((curr_p - df["Close"].iloc[-6]) / df["Close"].iloc[-6]) * 100
        if price_change_day < -5 or five_min_change < -2:
            return None

        # --- INDIKATOR MACD ---
        macd, signal = get_macd(df["Close"])
        is_macd_bullish = macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] <= signal.iloc[-2]

        # --- VOLUME SPIKE ---
        avg_vol = df["Volume"].tail(15).mean()
        curr_vol = df["Volume"].iloc[-1]
        
        # Sinyal Scalping: MACD Cross UP + Volume Meledak
        if is_macd_bullish and curr_vol > (avg_vol * 2):
            return {
                "price": curr_p,
                "target": curr_p * 1.02,
                "stop": curr_p * 0.98,
                "vol": round(curr_vol/avg_vol, 1)
            }
        return None
    except: return None

# --- 4. JOB AUTO SIGNAL 5 MENIT ---
def auto_signal_job(context: CallbackContext):
    global USER_CHAT_ID
    if not USER_CHAT_ID: return
    
    now = datetime.now(pytz.timezone('Asia/Jakarta'))
    # Hanya jalan saat Market Buka (Senin-Jumat, 09:00 - 16:00)
    if now.weekday() < 5 and 9 <= now.hour < 16:
        # Ambil 15 saham acak agar tidak membosankan
        random_pool = random.sample(IHSG_RADAR, 15)
        for sym in random_pool:
            res = analyze_scalping(sym)
            if res:
                msg = (f"🔥 **SCALPING ALERT (MACD + VOL)**\n\n"
                       f"🚀 **{sym.replace('.JK','')}**\n"
                       f"💰 Entry: {res['price']:,.0f}\n"
                       f"📊 Vol Spike: {res['vol']}x\n"
                       f"🎯 Target (2%): {res['target']:,.0f}\n"
                       f"🛑 Stop Loss: {res['stop']:,.0f}\n\n"
                       f"⚠️ *Hati-hati, eksekusi cepat!*")
                context.bot.send_message(chat_id=USER_CHAT_ID, text=msg, parse_mode='Markdown')
                break # Kirim satu sinyal terbaik per 5 menit agar tidak spam

# --- 5. RUNNER ---
def start(update: Update, context: CallbackContext):
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    update.message.reply_text("🏛 **Bot Scalping MACD Aktif!**\nSinyal otomatis dikirim tiap 5 menit jika ada momentum.")

if __name__ == '__main__':
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Scheduler: Jeda tepat 5 menit
    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(auto_signal_job, 'interval', minutes=5, args=[updater])
    scheduler.start()
    
    dp.add_handler(CommandHandler("start", start))
    # Handler lain (add/scan) bisa ditambahkan di sini...
    
    updater.start_polling()
    updater.idle()
