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

# --- 1. SETUP LOGGING ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AUTHORIZED_ID = os.environ.get("MY_ID")

USER_CHAT_ID = None

IHSG_RADAR = [
    "ASII.JK", "BBCA.JK", "BBNI.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASSA.JK",
    "PANI.JK", "ADRO.JK", "PTBA.JK", "UNTR.JK", "ICBP.JK", "CPIN.JK", "BRMS.JK",
    "BUMI.JK", "GOTO.JK", "MEDC.JK", "TPIA.JK", "AMRT.JK", "PGAS.JK"
]

# --- 2. ENGINE REALTIME ---
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
    except:
        return None

# --- 3. DATABASE ---
def init_db():
    with sqlite3.connect('bot_data.db', check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS watchlist (symbol TEXT PRIMARY KEY)')
        c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
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
        elif action == "remove" and symbol:
            sym = symbol.upper()
            if not sym.endswith(".JK"): sym += ".JK"
            c.execute("DELETE FROM watchlist WHERE symbol = ?", (sym,))
            conn.commit()
            return sym

# --- 4. SWING 5-MINUTE ENGINE ---
def analyze_swing(sym):
    try:
        rt_price = get_realtime_price(sym)
        # Menggunakan interval 5m dengan period 1mo (maksimal yfinance untuk 5m adalah 60 hari)
        df = yf.download(sym, period="1mo", interval="5m", progress=False, auto_adjust=True)
        
        if df is None or len(df) < 100: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        curr_p = rt_price if rt_price else float(df["Close"].iloc[-1])
        
        # RSI Wilder (Disesuaikan untuk intraday 5m agar lebih stabil)
        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean().iloc[-1]
        avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (avg_gain/avg_loss))) if avg_loss != 0 else 100
        
        # EMA Institutional (Basis 5 Menit)
        ema20 = df["Close"].ewm(span=20).mean().iloc[-1]
        ema50 = df["Close"].ewm(span=50).mean().iloc[-1]
        
        # Support & Resistance (Melihat 200 candle terakhir dalam timeframe 5m)
        lookback = 150 
        low_recent = df["Low"].tail(lookback).min()
        high_recent = df["High"].tail(lookback).max()
        
        # --- LOGIKA STATUS ---
        if curr_p > ema20 and ema20 > ema50 and 45 <= rsi <= 70:
            status = "ACCUMULATION 💎" 
        elif rsi < 35:
            status = "OVERSOLD ⏳"
        elif curr_p < ema20:
            status = "REJECTION ❌"
        else:
            status = "RETRACING ⏳"

        # Area Entry: Support Terdekat dalam timeframe 5m + toleransi 1%
        entry_start = int(low_recent)
        entry_end = int(low_recent * 1.015) 
        entry_zone = f"{entry_start} - {entry_end}"

        # TP (Target High Terdekat) & SL (Sedikit di bawah support)
        tp = high_recent if high_recent > curr_p else curr_p * 1.05
        sl = low_recent * 0.985

        return {
            "status": status, "price": curr_p, "tp": tp, "sl": sl, 
            "rsi": int(rsi), "entry": entry_zone
        }
    except Exception as e:
        logger.error(f"Error analyzing {sym}: {e}")
        return None

# --- 5. TELEGRAM HANDLERS ---
def is_auth(update: Update):
    uid = str(update.message.from_user.id)
    return AUTHORIZED_ID and uid == str(AUTHORIZED_ID).strip()

def start(update: Update, context: CallbackContext):
    if not is_auth(update): return
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    init_db()
    update.message.reply_text("🏛 **Institutional 5M Bot Active**\n\n- `/add <kode>`: Tambah Saham\n- `/scan`: Analisa Watchlist\n- `/list`: Lihat Daftar")

def add_stock(update: Update, context: CallbackContext):
    if not is_auth(update) or not context.args: return
    ticker = context.args[0]
    added_sym = db_manage_watchlist("add", ticker)
    update.message.reply_text(f"✅ **{added_sym}** Added.")

def scan_watchlist(update: Update, context: CallbackContext):
    if not is_auth(update): return
    stocks = db_manage_watchlist("list")
    if not stocks: return update.message.reply_text("Watchlist kosong.")
    
    msg = update.message.reply_text("🔎 **Scanning 5m Timeframe...**")
    report = "🏛 **5M TIMEFRAME ANALYSIS**\n\n"
    
    for s in stocks:
        res = analyze_swing(s)
        if res:
            report += (f"**{s.replace('.JK','')}** | {res['status']}\n"
                       f"💰 Price: Rp{res['price']:,.0f} (RSI: {res['rsi']})\n"
                       f"📥 Entry: {res['entry']}\n"
                       f"🎯 TP: {res['tp']:,.0f} | 🛑 SL: {res['sl']:,.0f}\n\n")
    
    context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=msg.message_id, text=report, parse_mode='HTML')

def auto_signal_job(context: CallbackContext):
    global USER_CHAT_ID
    now = datetime.now(pytz.timezone('Asia/Jakarta'))
    if USER_CHAT_ID and (now.weekday() < 5 and 9 <= now.hour < 16):
        signals = []
        pool = random.sample(IHSG_RADAR, 8)
        for sym in pool:
            res = analyze_swing(sym)
            if res and res["status"] == "ACCUMULATION 💎":
                signals.append(f"🏛 **INSTITUTIONAL ACCUMULATION (5M)**\n\n"
                               f"🔥 **Stock: {sym.replace('.JK','')}**\n"
                               f"Entry Area: {res['entry']}\n"
                               f"Current: {res['price']:,.0f}\n"
                               f"🎯 Target: {res['tp']:,.0f}\n"
                               f"🛑 Risk: {res['sl']:,.0f}")
            if len(signals) >= 2: break
        if signals:
            context.bot.send_message(chat_id=USER_CHAT_ID, text="\n\n".join(signals), parse_mode='HTML')

if __name__ == '__main__':
    init_db()
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("add", add_stock))
    dp.add_handler(CommandHandler("remove", lambda u, c: db_manage_watchlist("remove", c.args[0])))
    dp.add_handler(CommandHandler("scan", scan_watchlist))
    dp.add_handler(CommandHandler("list", lambda u, c: u.message.reply_text(f"📋 Watchlist: {', '.join(db_manage_watchlist('list'))}")))
    
    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(auto_signal_job, 'interval', minutes=10, args=[updater])
    scheduler.start()
    
    updater.start_polling(drop_pending_updates=True)
    updater.idle()
