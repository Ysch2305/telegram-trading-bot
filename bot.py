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

# List Radar untuk Auto Signal (Saham Liquid & Potensial Swing)
IHSG_RADAR = [
    "ASII.JK", "BBCA.JK", "BBNI.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASSA.JK",
    "PANI.JK", "ADRO.JK", "PTBA.JK", "UNTR.JK", "ICBP.JK", "CPIN.JK", "BRMS.JK",
    "BUMI.JK", "GOTO.JK", "MEDC.JK", "TPIA.JK", "AMRT.JK", "PGAS.JK"
]

# --- 2. ENGINE REALTIME (BYPASS CACHE) ---
def get_realtime_price(sym):
    try:
        ticker = sym.split('.')[0]
        # Penambahan timestamp agar Google tidak memberi data lama
        url = f"https://www.google.com/finance/quote/{ticker}:IDX?rand={time.time()}"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=7)
        soup = BeautifulSoup(response.text, 'html.parser')
        price_class = soup.find("div", {"class": "YMlSbc"})
        if price_class:
            return float(price_class.text.replace('IDR', '').replace(',', '').strip())
        return None
    except Exception as e:
        logger.error(f"Error Scrape {sym}: {e}")
        return None

# --- 3. DATABASE STABILIZER ---
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
        elif action == "remove" and symbol:
            sym = symbol.upper()
            if not sym.endswith(".JK"): sym += ".JK"
            c.execute("DELETE FROM watchlist WHERE symbol = ?", (sym,))
            conn.commit()
            return sym
        elif action == "list":
            c.execute("SELECT symbol FROM watchlist")
            return [r[0] for r in c.fetchall()]

def save_modal(val):
    with sqlite3.connect('bot_data.db', check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings VALUES ('modal', ?)", (str(val),))
        conn.commit()

def load_modal():
    with sqlite3.connect('bot_data.db', check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key = 'modal'")
        res = c.fetchone()
        return int(res[0]) if res else 0

# --- 4. SWING SEMI-INSTITUTIONAL ANALYSIS ---
def analyze_swing(sym):
    try:
        rt_price = get_realtime_price(sym)
        df = yf.download(sym, period="6mo", interval="1d", progress=False, auto_adjust=True)
        if df is None or len(df) < 50: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        curr_p = rt_price if rt_price else float(df["Close"].iloc[-1])
        
        # RSI Wilder (Sama dengan Stockbit)
        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean().iloc[-1]
        avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (avg_gain/avg_loss))) if avg_loss != 0 else 100
        
        # Institutional EMA
        ema20 = df["Close"].ewm(span=20).mean().iloc[-1]
        ema50 = df["Close"].ewm(span=50).mean().iloc[-1]
        
        # Volume Flow
        vol_ma20 = df["Volume"].rolling(window=20).mean().iloc[-1]
        curr_vol = df["Volume"].iloc[-1]
        
        # Status Logic
        if curr_p > ema20 and ema20 > ema50 and 45 <= rsi <= 68:
            status = "SWING BUY 🚀"
            note = "Big Money Flowing" if curr_vol > vol_ma20 else "Healthy Trend"
        elif rsi < 35:
            status = "WATCH 🟡"
            note = "Oversold/Bottom"
        elif curr_p < ema20:
            status = "SELL/AVOID 🔴"
            note = "Down Grade Trend"
        else:
            status = "NEUTRAL ⚪"
            note = "Sideways Market"

        # TP/SL Swing (2-5 Hari)
        tp = df["High"].tail(10).max() # Resistance 10 hari
        if tp <= curr_p: tp = curr_p * 1.08
        
        sl = df["Low"].tail(5).min() # Support 5 hari
        if sl >= curr_p: sl = curr_p * 0.96

        return {
            "status": status, "price": curr_p, "tp": tp, "sl": sl, 
            "rsi": int(rsi), "note": note
        }
    except Exception as e:
        logger.error(f"Analisis Error {sym}: {e}")
        return None

# --- 5. COMMAND HANDLERS ---
def is_auth(update: Update):
    uid = str(update.message.from_user.id)
    return AUTHORIZED_ID and uid == str(AUTHORIZED_ID).strip()

def start(update: Update, context: CallbackContext):
    if not is_auth(update): return
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    init_db()
    modal = load_modal()
    update.message.reply_text(
        f"🏛 **Semi-Institutional Swing Bot**\n\n"
        f"• Status: `Ready`\n"
        f"• Modal: `Rp{modal:,.0f}`\n\n"
        f"Gunakan `/add <kode>` untuk watchlist.\n"
        f"Gunakan `/scan` untuk analisa realtime.", 
        parse_mode='Markdown'
    )

def add_stock(update: Update, context: CallbackContext):
    if not is_auth(update) or not context.args: return
    ticker = context.args[0]
    added_sym = db_manage_watchlist("add", ticker)
    update.message.reply_text(f"✅ **{added_sym}** masuk ke watchlist.", parse_mode='Markdown')

def remove_stock(update: Update, context: CallbackContext):
    if not is_auth(update) or not context.args: return
    ticker = context.args[0]
    removed = db_manage_watchlist("remove", ticker)
    update.message.reply_text(f"🗑 **{removed}** dihapus.", parse_mode='Markdown')

def list_watchlist(update: Update, context: CallbackContext):
    if not is_auth(update): return
    stocks = db_manage_watchlist("list")
    if not stocks:
        update.message.reply_text("📋 Watchlist kosong.")
    else:
        update.message.reply_text(f"📋 **Watchlist:**\n`" + "`, `".join(stocks) + "`", parse_mode='Markdown')

def scan_watchlist(update: Update, context: CallbackContext):
    if not is_auth(update): return
    stocks = db_manage_watchlist("list")
    if not stocks:
        return update.message.reply_text("Watchlist kosong. Pakai /add dulu.")
    
    msg = update.message.reply_text("🔎 **Menganalisa Market...**", parse_mode='Markdown')
    report = "🏛 **SWING INSTITUTIONAL REPORT**\n\n"
    
    for s in stocks:
        res = analyze_swing(s)
        if res:
            report += (f"**{s.replace('.JK','')}** | {res['status']}\n"
                       f"💰 Price: Rp{res['price']:,.0f} (RSI: {res['rsi']})\n"
                       f"💡 Note: {res['note']}\n"
                       f"🎯 TP: {res['tp']:,.0f} | 🛑 SL: {res['sl']:,.0f}\n\n")
    
    context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=msg.message_id, text=report, parse_mode='HTML')

def auto_swing_job(context: CallbackContext):
    global USER_CHAT_ID
    modal = load_modal()
    now = datetime.now(pytz.timezone('Asia/Jakarta'))
    
    # Hanya kirim jika market buka (Senin-Jumat, 09:00-16:00 WIB)
    if USER_CHAT_ID and (now.weekday() < 5 and 9 <= now.hour < 16):
        signals = []
        pool = random.sample(IHSG_RADAR, 10)
        
        for sym in pool:
            res = analyze_swing(sym)
            if res and "SWING BUY" in res["status"]:
                if modal >= (res["price"] * 100):
                    signals.append(f"🏛 **SWING SIGNAL: {sym.replace('.JK','')}**\n"
                                   f"Entry: Rp{res['price']:,.0f}\n"
                                   f"Note: {res['note']}\n"
                                   f"🎯 Target: {res['tp']:,.0f}\n"
                                   f"🛑 Risk: {res['sl']:,.0f}")
            if len(signals) >= 2: break
        
        if signals:
            context.bot.send_message(chat_id=USER_CHAT_ID, text="📢 **RADAR INSTITUSI**\n\n" + "\n\n".join(signals), parse_mode='HTML')

def handle_text(update: Update, context: CallbackContext):
    if not is_auth(update): return
    text = update.message.text.strip()
    if text.isdigit():
        save_modal(int(text))
        update.message.reply_text(f"✅ Modal Rp{int(text):,.0f} disimpan.")

# --- 6. MAIN RUNNER ---
if __name__ == '__main__':
    init_db()
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("add", add_stock))
    dp.add_handler(CommandHandler("remove", remove_stock))
    dp.add_handler(CommandHandler("list", list_watchlist))
    dp.add_handler(CommandHandler("scan", scan_watchlist))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
    
    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    # Interval 15 menit agar tidak berisik untuk swing
    scheduler.add_job(auto_swing_job, 'interval', minutes=15, args=[updater])
    scheduler.start()
    
    updater.start_polling(drop_pending_updates=True)
    logger.info("Bot is running...")
    updater.idle()
