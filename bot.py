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

# --- DATABASE LOGIC ---
def init_db():
    conn = sqlite3.connect('watchlist.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stocks (symbol TEXT PRIMARY KEY)''')
    # Masukkan saham default jika tabel baru dibuat
    default_stocks = ["BUMI.JK", "BBCA.JK", "BUVA.JK", "BBRI.JK", "BMRI.JK", "ANTM.JK"]
    for s in default_stocks:
        c.execute("INSERT OR IGNORE INTO stocks VALUES (?)", (s,))
    conn.commit()
    conn.close()

def get_watchlist():
    conn = sqlite3.connect('watchlist.db')
    c = conn.cursor()
    c.execute("SELECT symbol FROM stocks")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def add_to_db(symbol):
    conn = sqlite3.connect('watchlist.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO stocks VALUES (?)", (symbol,))
    conn.commit()
    conn.close()

# Inisialisasi Database saat pertama kali jalan
init_db()

# --- MARKET & ANALYSIS LOGIC ---
def is_market_open():
    tz_jakarta = pytz.timezone('Asia/Jakarta')
    now = datetime.now(tz_jakarta)
    if now.weekday() < 5 and (datetime.strptime("09:00", "%H:%M").time() <= now.time() <= datetime.strptime("16:00", "%H:%M").time()):
        return True
    return False

def analyze_symbol(sym, df):
    if len(df) < 50: return None
    close = df["Close"]
    volume = df["Volume"]
    current_price = close.iloc[-1]
    
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = (-delta).clip(lower=0).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1]))
    
    avg_vol = volume.rolling(window=20).mean().iloc[-1]
    vol_status = "Tinggi 📈" if volume.iloc[-1] > avg_vol else "Rendah 📉"
    
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

# --- BOT COMMANDS ---
def auto_scan_job(context: CallbackContext):
    global USER_CHAT_ID
    if USER_CHAT_ID and is_market_open():
        current_watchlist = get_watchlist()
        results = []
        for sym in current_watchlist:
            try:
                df = yf.download(sym, period="3mo", interval="1d", progress=False)
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                res = analyze_symbol(sym, df)
                if res and (res["status"] == "BUY 🟢" or res["status"] == "SELL 🔴"):
                    results.append(res["msg"])
            except: continue
        if results:
            context.bot.send_message(chat_id=USER_CHAT_ID, text="🔔 <b>AUTO-SIGNAL</b>\n\n" + "\n\n".join(results), parse_mode='HTML')

def start(update: Update, context: CallbackContext):
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    update.message.reply_text("🚀 <b>Bot Pro Aktif!</b>\nSaham yang Anda tambah akan tersimpan permanen.\n\n/add KODE.JK - Tambah\n/list - Cek Daftar\n/scan - Scan Manual", parse_mode='HTML')

def scan(update: Update, context: CallbackContext):
    update.message.reply_text("🔎 Scanning manual seluruh watchlist...")
    current_watchlist = get_watchlist()
    results = [analyze_symbol(s, yf.download(s, period="3mo", interval="1d", progress=False)) for s in current_watchlist]
    clean_results = [r["msg"] for r in results if r]
    if clean_results:
        update.message.reply_text("\n\n".join(clean_results), parse_mode='HTML')

def add_stock(update: Update, context: CallbackContext):
    if not context.args: return
    code = context.args[0].upper()
    if ".JK" not in code: code += ".JK"
    add_to_db(code)
    update.message.reply_text(f"✅ {code} tersimpan permanen di database!")

def list_watchlist(update: Update, context: CallbackContext):
    current_watchlist = get_watchlist()
    msg = "📋 <b>Watchlist Database:</b>\n\n" + "\n".join([f"- {s}" for s in current_watchlist])
    update.message.reply_text(msg, parse_mode='HTML')

if __name__ == '__main__':
    updater = Updater(TOKEN)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("scan", scan))
    dp.add_handler(CommandHandler("add", add_stock))
    dp.add_handler(CommandHandler("list", list_watchlist))

    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(auto_scan_job, 'interval', minutes=5, args=[updater])
    scheduler.start()

    updater.start_polling(drop_pending_updates=True)
    updater.idle()
