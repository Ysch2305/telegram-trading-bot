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

# --- SETUP ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AUTHORIZED_ID = os.environ.get("MY_ID")

USER_CHAT_ID = None

# Daftar saham dengan kapitalisasi pasar lumayan / liquid untuk swing
IHSG_RADAR = [
    "ASII.JK", "BBCA.JK", "BBNI.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASSA.JK",
    "PANI.JK", "ADRO.JK", "PTBA.JK", "UNTR.JK", "ICBP.JK", "CPIN.JK", "BRMS.JK",
    "BUMI.JK", "GOTO.JK", "MEDC.JK", "ANAM.JK", "TPIA.JK", "AMRT.JK"
]

def get_realtime_price(sym):
    try:
        ticker = sym.split('.')[0]
        url = f"https://www.google.com/finance/quote/{ticker}:IDX?rand={time.time()}"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        price_class = soup.find("div", {"class": "YMlSbc"})
        if price_class:
            return float(price_class.text.replace('IDR', '').replace(',', '').strip())
        return None
    except: return None

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
    if action == "add": c.execute("INSERT OR IGNORE INTO watchlist VALUES (?)", (symbol,))
    elif action == "remove": c.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
    elif action == "list":
        c.execute("SELECT symbol FROM watchlist")
        res = [r[0] for r in c.fetchall()]
        conn.close()
        return res
    conn.commit()
    conn.close()

init_db()

# --- SWING SEMI-INSTITUTIONAL ENGINE ---
def analyze_swing(sym):
    try:
        rt_price = get_realtime_price(sym)
        df = yf.download(sym, period="6mo", interval="1d", progress=False, auto_adjust=True)
        if df is None or len(df) < 50: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        curr_p = rt_price if rt_price else float(df["Close"].iloc[-1])
        
        # 1. RSI Wilder (14)
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0))
        loss = (-delta.where(delta < 0, 0))
        avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean().iloc[-1]
        avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (avg_gain/avg_loss))) if avg_loss != 0 else 100
        
        # 2. Moving Averages (Institutional Standard)
        ema20 = df["Close"].ewm(span=20).mean().iloc[-1]
        ema50 = df["Close"].ewm(span=50).mean().iloc[-1]
        
        # 3. Volume Accumulation (Volume MA 20)
        vol_ma20 = df["Volume"].rolling(window=20).mean().iloc[-1]
        curr_vol = df["Volume"].iloc[-1]
        
        # --- LOGIKA SWING SEMI-INSTITUTIONAL ---
        # Syarat BUY: Harga > EMA20, EMA20 > EMA50, RSI antara 45-65 (Bukan Pucuk)
        if curr_p > ema20 and ema20 > ema50 and 45 <= rsi <= 68:
            status = "SWING BUY 🚀"
            note = "Institusi Akumulasi" if curr_vol > vol_ma20 else "Trend Stabil"
        elif rsi < 35:
            status = "POTENTIAL REBOUND 🟡"
            note = "Bottom Fishing Area"
        elif curr_p < ema20:
            status = "AVOID 🔴"
            note = "Tren Rusak"
        else:
            status = "HOLD / NEUTRAL ⚪"
            note = "Menunggu Konfirmasi"

        # --- TP/SL DINAMIS (SWING 2-5 HARI) ---
        # Swing High 10 hari terakhir sebagai TP
        # Swing Low 5 hari terakhir sebagai SL
        tp_target = df["High"].tail(10).max()
        if tp_target <= curr_p: tp_target = curr_p * 1.08 # Jika breakout, incar 8%
        
        sl_target = df["Low"].tail(5).min()
        if sl_target >= curr_p: sl_target = curr_p * 0.96 # Jika mepet, SL 4%
        
        return {
            "status": status, "price": curr_p, "tp": tp_target, "sl": sl_target, 
            "rsi": int(rsi), "note": note
        }
    except: return None

# --- HANDLERS ---
def scan_watchlist(update: Update, context: CallbackContext):
    stocks = db_manage_watchlist("list")
    if not stocks: return update.message.reply_text("Watchlist kosong.")
    
    msg = update.message.reply_text("🔎 Analyzing Swing Opportunities...")
    report = "🏛 <b>SWING INSTITUTIONAL REPORT</b>\n\n"
    
    for s in stocks:
        res = analyze_swing(s)
        if res:
            report += (f"<b>{s.replace('.JK','')}</b> | {res['status']}\n"
                       f"💰 Price: Rp{res['price']:,.0f} (RSI: {res['rsi']})\n"
                       f"💡 Note: {res['note']}\n"
                       f"🎯 TP: {res['tp']:,.0f} | 🛑 SL: {res['sl']:,.0f}\n\n")
    
    context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=msg.message_id, text=report, parse_mode='HTML')

def auto_swing_signal(context: CallbackContext):
    global USER_CHAT_ID
    now = datetime.now(pytz.timezone('Asia/Jakarta'))
    if USER_CHAT_ID and (now.weekday() < 5 and 9 <= now.hour < 16):
        signals = []
        pool = random.sample(IHSG_RADAR, 12) # Scan 12 saham liquid secara acak
        
        for sym in pool:
            res = analyze_swing(sym)
            if res and "SWING BUY" in res["status"]:
                signals.append(f"🏛 <b>SWING SIGNAL: {sym.replace('.JK','')}</b>\n"
                               f"Entry: Rp{res['price']:,.0f}\n"
                               f"Note: {res['note']}\n"
                               f"🎯 Target: {res['tp']:,.0f}\n"
                               f"🛑 Risk: {res['sl']:,.0f}")
            if len(signals) >= 2: break
        
        if signals:
            context.bot.send_message(chat_id=USER_CHAT_ID, text="📢 <b>RADAR INSTITUSI (SWING)</b>\n\n" + "\n\n".join(signals), parse_mode='HTML')

# (Bagian main / start / add tetap sama seperti kode sebelumnya)
def start(update: Update, context: CallbackContext):
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    update.message.reply_text("✅ Swing Bot Semi-Institutional Aktif.\n/scan untuk analisa manual.")

if __name__ == '__main__':
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("scan", scan_watchlist))
    
    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(auto_swing_signal, 'interval', minutes=15, args=[updater]) # Cek tiap 15 menit agar tidak berisik
    scheduler.start()
    
    updater.start_polling()
    updater.idle()
