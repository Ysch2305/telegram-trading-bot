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
USER_CHAT_ID = None 

# Radar diperluas untuk variasi sinyal
IHSG_RADAR = [
    "ASII.JK", "BBCA.JK", "BBNI.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASSA.JK",
    "PANI.JK", "ADRO.JK", "PTBA.JK", "UNTR.JK", "ICBP.JK", "CPIN.JK", "BRMS.JK",
    "BUMI.JK", "GOTO.JK", "MEDC.JK", "TPIA.JK", "AMRT.JK", "PGAS.JK", "ADMR.JK",
    "ANTM.JK", "HRUM.JK", "MDKA.JK", "ITMG.JK", "AKRA.JK", "TINS.JK", "LSIP.JK"
]

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
        elif action == "remove" and symbol:
            sym = symbol.upper()
            if not sym.endswith(".JK"): sym += ".JK"
            c.execute("DELETE FROM watchlist WHERE symbol = ?", (sym,))
            conn.commit()
            return sym

# --- 3. INDIKATOR MACD ---
def get_macd(close_prices):
    exp1 = close_prices.ewm(span=12, adjust=False).mean()
    exp2 = close_prices.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal

# --- 4. ANALISA SCALPING (AUTO) ---
def analyze_scalping(sym):
    try:
        df = yf.download(sym, period="1d", interval="1m", progress=False, auto_adjust=True)
        if df is None or len(df) < 30: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        curr_p = float(df["Close"].iloc[-1])
        open_p = float(df["Open"].iloc[0])
        
        # Anti-Dump Filter
        price_change_day = ((curr_p - open_p) / open_p) * 100
        if price_change_day < -5: return None

        macd, signal = get_macd(df["Close"])
        # Sinyal jika MACD baru saja memotong Signal Line ke atas
        if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] <= signal.iloc[-2]:
            avg_vol = df["Volume"].tail(15).mean()
            if df["Volume"].iloc[-1] > (avg_vol * 2):
                return {"price": curr_p, "target": curr_p * 1.02, "stop": curr_p * 0.985}
        return None
    except: return None

# --- 5. ANALISA SWING (MANUAL SCAN) ---
def analyze_swing(sym):
    try:
        df = yf.download(sym, period="1mo", interval="5m", progress=False, auto_adjust=True)
        if df is None or len(df) < 50: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        curr_p = float(df["Close"].iloc[-1])
        ema20 = df["Close"].ewm(span=20).mean().iloc[-1]
        low_support = df["Low"].tail(100).min()
        
        status = "SAATNYA BELI ✅" if curr_p > ema20 else "DISKON SEHAT 🛍️"
        return {
            "status": status,
            "price": curr_p,
            "entry": f"{int(low_support)} - {int(low_support * 1.02)}",
            "tp": curr_p * 1.07
        }
    except: return None

# --- 6. HANDLERS ---
def start(update: Update, context: CallbackContext):
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    init_db()
    update.message.reply_text("🏛 **Bot Pro Aktif!**\n\n- `/scan` : Cek Watchlist (Swing)\n- `/add <kode>` : Tambah Saham\n- Auto Signal (Scalping) jalan tiap 5 menit.")

def add_stock(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Contoh: `/add BBCA`")
        return
    res = db_manage_watchlist("add", context.args[0])
    update.message.reply_text(f"✅ {res} dipantau!")

def scan_manual(update: Update, context: CallbackContext):
    stocks = db_manage_watchlist("list")
    if not stocks:
        update.message.reply_text("Watchlist kosong. Gunakan `/add` dulu.")
        return
    
    msg = update.message.reply_text("🔎 **Menganalisa Watchlist...**")
    report = "🏛 **SWING ANALYSIS REPORT**\n\n"
    for s in stocks:
        res = analyze_swing(s)
        if res:
            report += f"**{s.replace('.JK','')}** | {res['status']}\n💰 Harga: {res['price']:,.0f}\n📥 Area Antri: {res['entry']}\n🎯 Target: {res['tp']:,.0f}\n\n"
    
    context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=msg.message_id, text=report, parse_mode='HTML')

def auto_signal_job(context: CallbackContext):
    if not USER_CHAT_ID: return
    now = datetime.now(pytz.timezone('Asia/Jakarta'))
    if now.weekday() < 5 and 9 <= now.hour < 16:
        pool = random.sample(IHSG_RADAR, 10)
        for sym in pool:
            res = analyze_scalping(sym)
            if res:
                msg = (f"⚡️ **SCALPING ALERT**\n🚀 **{sym.replace('.JK','')}**\n"
                       f"💰 Entry: {res['price']:,.0f}\n🎯 Target (2%): {res['target']:,.0f}\n🛑 SL: {res['stop']:,.0f}")
                context.bot.send_message(chat_id=USER_CHAT_ID, text=msg)
                break

# --- 7. MAIN ---
if __name__ == '__main__':
    init_db()
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(auto_signal_job, 'interval', minutes=5, args=[updater])
    scheduler.start()
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("add", add_stock))
    dp.add_handler(CommandHandler("scan", scan_manual))
    dp.add_handler(CommandHandler("remove", lambda u, c: u.message.reply_text(f"🗑 {db_manage_watchlist('remove', c.args[0])} dihapus") if c.args else None))
    
    updater.start_polling()
    updater.idle()
