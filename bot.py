import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
import yfinance as yf
import numpy as np
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler, Filters
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz
import sqlite3
import random
import time

# --- 1. SETUP ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AUTHORIZED_ID = os.environ.get("MY_ID")

IHSG_RADAR = [
    "ASII.JK", "BBCA.JK", "BBNI.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASSA.JK",
    "PANI.JK", "ADRO.JK", "PTBA.JK", "UNTR.JK", "ICBP.JK", "CPIN.JK", "BRMS.JK",
    "BUMI.JK", "GOTO.JK", "MEDC.JK", "TPIA.JK", "AMRT.JK", "PGAS.JK", "ADMR.JK"
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
        elif action == "remove" and symbol:
            sym = symbol.upper()
            if not sym.endswith(".JK"): sym += ".JK"
            c.execute("DELETE FROM watchlist WHERE symbol = ?", (sym,))
            conn.commit()
            return sym
        elif action == "list":
            c.execute("SELECT symbol FROM watchlist")
            return [r[0] for r in c.fetchall()]

# --- 3. ANALISA VOLUME SPIKE & TREND ---
def analyze_stock(sym):
    try:
        rt_price = get_realtime_price(sym)
        # Ambil data 5 menit untuk presisi hari ini
        df = yf.download(sym, period="1mo", interval="5m", progress=False, auto_adjust=True)
        if df is None or len(df) < 50: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        curr_p = rt_price if rt_price else float(df["Close"].iloc[-1])
        
        # 1. Volume Spike Analysis
        # Bandingkan volume saat ini dengan rata-rata volume 20 periode terakhir
        avg_vol = df["Volume"].rolling(window=20).mean().iloc[-1]
        curr_vol = df["Volume"].iloc[-1]
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 0
        
        # 2. Trend Indicators
        ema20 = df["Close"].ewm(span=20).mean().iloc[-1]
        ema50 = df["Close"].ewm(span=50).mean().iloc[-1]
        
        # 3. RSI Wilder
        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0).ewm(alpha=1/14, min_periods=14).mean().iloc[-1]
        loss = -delta.where(delta < 0, 0).ewm(alpha=1/14, min_periods=14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (gain/loss))) if loss != 0 else 100
        
        # --- LOGIKA STATUS ---
        status = ""
        pesan = ""
        
        # Kondisi Volume Meledak (Spike)
        is_spike = vol_ratio >= 2.0  # Volume 2x lipat lebih besar dari biasanya
        
        if is_spike and curr_p > ema20:
            status = "ADA BANDAR MASUK 🔥"
            pesan = f"Volume meledak {vol_ratio:.1f}x lipat! Uang besar masuk."
        elif curr_p > ema20 and ema20 > ema50 and 45 <= rsi <= 70:
            status = "SAATNYA BELI ✅"
            pesan = "Tren naik stabil, Bos-bos lagi borong."
        elif rsi < 35:
            status = "SUDAH KEMURAHAN 📉"
            pesan = "Harga lecek, potensi mantul balik."
        elif curr_p < ema20:
            status = "JANGAN SENTUH 🚫"
            pesan = "Lagi dibuang pasar, tren lagi rusak."
        else:
            status = "DISKON SEHAT 🛍️"
            pesan = "Harga istirahat sejenak, pantau area antri."

        # Area Antri & Target
        low_support = df["Low"].tail(100).min()
        entry_zone = f"{int(low_support)} - {int(low_support * 1.02)}"
        tp = df["High"].tail(100).max()
        if tp <= curr_p: tp = curr_p * 1.08
        sl = low_support * 0.98

        return {
            "status": status, "pesan": pesan, "price": curr_p, 
            "tp": tp, "sl": sl, "entry": entry_zone, "rsi": int(rsi), "spike": is_spike
        }
    except: return None

# --- 4. TELEGRAM COMMANDS ---
def start(update: Update, context: CallbackContext):
    init_db()
    update.message.reply_text("🏛 **Bot Swing Pro Aktif!**\n\nAnalisa sekarang pakai **Volume Spike** (Deteksi Bandar).")

def scan_watchlist(update: Update, context: CallbackContext):
    stocks = db_manage_watchlist("list")
    if not stocks: return update.message.reply_text("Daftar pantauan kosong.")
    
    msg = update.message.reply_text("🔎 **Mendeteksi pergerakan bandar...**")
    report = "🏛 **HASIL ANALISA REALTIME**\n\n"
    
    for s in stocks:
        res =
