import os
import yfinance as yf
import pandas as pd
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz
import sqlite3

# 1. Setup Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
USER_CHAT_ID = None 

# --- DATABASE LOGIC (Sistem Penyimpanan Permanen) ---
def init_db():
    conn = sqlite3.connect('watchlist.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stocks (symbol TEXT PRIMARY KEY)''')
    # Saham default hanya dimasukkan jika database kosong
    c.execute("SELECT count(*) FROM stocks")
    if c.fetchone()[0] == 0:
        default_stocks = ["BUMI.JK", "BBCA.JK", "BUVA.JK", "BBRI.JK", "BMRI.JK", "ANTM.JK"]
        for s in default_stocks:
            c.execute("INSERT OR IGNORE INTO stocks VALUES (?)", (s,))
    conn.commit()
    conn.close()

def get_watchlist():
    conn = sqlite3.connect('watchlist.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT symbol FROM stocks")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def add_to_db(symbol):
    conn = sqlite3.connect('watchlist.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO stocks VALUES (?)", (symbol,))
    conn.commit()
    conn.close()

def remove_from_db(symbol):
    conn = sqlite3.connect('watchlist.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("DELETE FROM stocks WHERE symbol = ?", (symbol,))
    conn.commit()
    conn.close()

# Jalankan inisialisasi database
init_db()

# --- LOGIKA PASAR (Waktu Jakarta) ---
def is_market_open():
    tz_jakarta = pytz.timezone('Asia/Jakarta')
    now = datetime.now(tz_jakarta)
    day_of_week = now.weekday()
    current_time = now.time()
    
    start_time = datetime.strptime("09:00", "%H:%M").time()
    end_time = datetime.strptime("16:00", "%H:%M").time()
    
    # Senin-Jumat jam 09:00-16:00
    return day_of_week < 5 and (start_time <= current_time <= end_time)

# --- ANALISIS TEKNIKAL ---
def analyze_symbol(sym, df):
    if df is None or len(df) < 20: return None
    
    # Membersihkan format data yfinance
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    close = df["Close"]
    volume = df["Volume"]
    current_price = float(close.iloc[-1])
    
    # EMA (Exponential Moving Average)
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    
    # RSI (Relative Strength Index)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = (-delta).clip(lower=0).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1]))
    
    # Volume Analysis
    avg_vol = volume.rolling(window=20).mean().iloc[-1]
    vol_status = "Tinggi 📈" if float(volume.iloc[-1]) > float(avg_vol) else "Rendah 📉"
    
    # Risk/Reward Plan
    tp = current_price * 1.05
    sl = current_price * 0.97
    clean_name = sym.replace('.JK','')
    
    if ema20 > ema50 and rsi > 55:
        status = "BUY 🟢"
    elif ema20 < ema50 and rsi < 45:
        status = "SELL 🔴"
    else:
        status = "HOLD 🟡"
        
    msg = (f"<b>{clean_name}</b> | Rp{current_price:,.0f}\n"
           f"Sinyal: {status}\n"
           f"Analisa: Vol {vol_status}\n"
           f"🎯 TP: {tp:,.0f} | 🛑 SL: {sl:,.0f}")
    
    return {"status": status, "msg": msg}

# --- FUNGSI OTOMATIS (AUTO-SIGNAL) ---
def auto_scan_job(context: CallbackContext):
    global USER_CHAT_ID
    if USER_CHAT_ID and is_market_open():
        current_watchlist = get_watchlist()
        results = []
        for sym in current_watchlist:
            try:
                # auto_adjust=True memastikan harga GOTO dkk akurat
                df = yf.download(sym, period="3mo", interval="1d", progress=False, auto_adjust=True)
                res = analyze_symbol(sym, df)
                # Hanya kirim jika sinyal BUY atau SELL
                if res and (res["status"] == "BUY 🟢" or res["status"] == "SELL 🔴"):
                    results.append(res["msg"])
            except: continue
        
        if results:
            context.bot.send_message(
                chat_id=USER_CHAT_ID, 
                text="🔔 <b>AUTO
