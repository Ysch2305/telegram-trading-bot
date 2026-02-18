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
    "BUMI.JK", "GOTO.JK", "MEDC.JK", "TPIA.JK", "AMRT.JK", "PGAS.JK"
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

# --- 3. ANALISA (PENGGUNAAN BAHASA MUDAH) ---
def analyze_stock(sym):
    try:
        rt_price = get_realtime_price(sym)
        # Interval 5 Menit agar lincah
        df = yf.download(sym, period="1mo", interval="5m", progress=False, auto_adjust=True)
        if df is None or len(df) < 50: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        curr_p = rt_price if rt_price else float(df["Close"].iloc[-1])
        
        # Indikator Dasar
        ema20 = df["Close"].ewm(span=20).mean().iloc[-1]
        ema50 = df["Close"].ewm(span=50).mean().iloc[-1]
        
        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean().iloc[-1]
        avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (avg_gain/avg_loss))) if avg_loss != 0 else 100
        
        # --- LOGIKA STATUS BAHASA SANTAI ---
        if curr_p > ema20 and ema20 > ema50 and 45 <= rsi <= 70:
            status = "SAATNYA BELI ✅"
            pesan = "Bos-bos lagi borong barang."
        elif rsi < 35:
            status = "SUDAH KEMURAHAN 📉"
            pesan = "Harganya lecek, siap-siap mantul."
        elif curr_p < ema20:
            status = "JANGAN SENTUH 🚫"
            pesan = "Lagi loyo, mending jauhin dulu."
        else:
            status = "DISKON SEHAT 🛍️"
            pesan = "Harga lagi istirahat, pantau dulu."

        # Area Entry (Lantai Support)
        low_support = df["Low"].tail(100).min()
        entry_zone = f"{int(low_support)} - {int(low_support * 1.02)}"
        
        # Target Profit & Batas Rugi
        tp = df["High"].tail(100).max()
        if tp <= curr_p: tp = curr_p * 1.07
        sl = low_support * 0.98

        return {
            "status": status, "pesan": pesan, "price": curr_p, 
            "tp": tp, "sl": sl, "entry": entry_zone, "rsi": int(rsi)
        }
    except: return None

# --- 4. COMMANDS ---
def start(update: Update, context: CallbackContext):
    init_db()
    update.message.reply_text("🏛 **Bot Saham Gampang Aktif!**\n\n- `/add <kode>` : Masukin saham ke pantauan\n- `/scan` : Cek saham yang ada di pantauan\n- `/list` : Liat daftar saham Anda")

def add_stock(update: Update, context: CallbackContext):
    if not context.args: return
    ticker = context.args[0]
    res = db_manage_watchlist("add", ticker)
    update.message.reply_text(f"✅ {res} udah masuk daftar pantau ya!")

def scan_watchlist(update: Update, context: CallbackContext):
    stocks = db_manage_watchlist("list")
    if not stocks: return update.message.reply_text("Daftar pantauan masih kosong, Bos.")
    
    msg = update.message.reply_text("🔎 **Lagi cek harga sebentar...**")
    report = "🏛 **HASIL CEK SAHAM**\n\n"
    
    for s in stocks:
        res = analyze_stock(s)
        if res:
            report += (f"**{s.replace('.JK','')}** | {res['status']}\n"
                       f"💡 {res['pesan']}\n"
                       f"💰 Harga: Rp{res['price']:,.0f} (RSI: {res['rsi']})\n"
                       f"📥 Area Antri: {res['entry']}\n"
                       f"🎯 Jual di: {res['tp']:,.0f} | 🛑 Cut Loss: {res['sl']:,.0f}\n\n")
    
    context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=msg.message_id, text=report, parse_mode='HTML')

# --- 5. RUNNER ---
if __name__ == '__main__':
    init_db()
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("add", add_stock))
    dp.add_handler(CommandHandler("scan", scan_watchlist))
    dp.add_handler(CommandHandler("list", lambda u, c: u.message.reply_text(f"📋 Daftar Pantau: {', '.join(db_manage_watchlist('list'))}")))
    dp.add_handler(CommandHandler("remove", lambda u, c: u.message.reply_text(f"🗑 {db_manage_watchlist('remove', c.args[0])} dihapus.")))
    
    updater.start_polling()
    updater.idle()
