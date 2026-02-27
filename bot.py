import os
import requests
import pandas as pd
import yfinance as yf
import numpy as np
import logging
import sqlite3
import time
import random
import google.generativeai as genai
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz

# --- 1. SETUP ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
USER_CHAT_ID = None 

# Inisialisasi Gemini AI
genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel('gemini-1.5-flash')

# Daftar Radar Luas
IHSG_RADAR = ["ASII.JK", "BBCA.JK", "BBNI.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "BRMS.JK", "BUMI.JK", "GOTO.JK", "ANTM.JK", "MEDC.JK", "ADRO.JK", "PTBA.JK"]

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

# --- 3. ANALISA TEKNIKAL ---
def get_analysis_data(sym):
    try:
        df = yf.download(sym, period="1mo", interval="5m", progress=False, auto_adjust=True)
        if df is None or len(df) < 50: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        curr_p = float(df["Close"].iloc[-1])
        ema20 = df["Close"].ewm(span=20).mean().iloc[-1]
        
        # MACD
        exp1 = df["Close"].ewm(span=12, adjust=False).mean()
        exp2 = df["Close"].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        
        status = "SAATNYA BELI ✅" if curr_p > ema20 else "JANGAN SENTUH 🚫"
        low_support = df["Low"].tail(50).min()
        
        return {
            "price": curr_p, "status": status, "macd": macd.iloc[-1], 
            "signal": signal.iloc[-1], "ema20": ema20, 
            "entry": f"{int(low_support)} - {int(low_support * 1.02)}"
        }
    except: return None

# --- 4. FITUR /TANYA (AI MENTOR) ---
def tanya_ai(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Contoh: `/tanya kenapa BUMI jangan sentuh?`")
        return

    query = " ".join(context.args)
    ticker = context.args[0].upper().replace("?", "")
    if not ticker.endswith(".JK"): ticker += ".JK"
    
    thinking_msg = update.message.reply_text("🤔 **Sedang menganalisa data...**")
    data = get_analysis_data(ticker)
    
    prompt = f"""
    Kamu adalah asisten ahli saham Indonesia. User bertanya: '{query}'
    
    Data Teknis {ticker}:
    - Harga: {data['price'] if data else 'N/A'}
    - Status Bot: {data['status'] if data else 'N/A'}
    - Posisi Harga vs EMA20: {'Diatas Rata-rata' if data and data['price'] > data['ema20'] else 'Dibawah Rata-rata'}
    
    Jelaskan dengan bahasa ritel santai dan mudah (seperti peer-to-peer). 
    Gunakan istilah 'saatnya beli', 'diskon sehat', atau 'jangan sentuh'.
    Berikan alasan logis kenapa statusnya begitu.
    """

    try:
        response = ai_model.generate_content(prompt)
        context.bot.edit_message_text(
            chat_id=update.message.chat_id, 
            message_id=thinking_msg.message_id, 
            text=f"🤖 **Analisa AI Mentor:**\n\n{response.text}",
            parse_mode='Markdown'
        )
    except:
        context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=thinking_msg.message_id, text="AI lagi pusing, Bos. Coba lagi!")

# --- 5. MANUAL SCAN & AUTO SIGNAL ---
def scan_manual(update: Update, context: CallbackContext):
    stocks = db_manage_watchlist("list")
    if not stocks: return update.message.reply_text("Watchlist kosong.")
    report = "🏛 **SWING REPORT**\n\n"
    for s in stocks:
        res = get_analysis_data(s)
        if res: report += f"**{s.replace('.JK','')}** | {res['status']}\n💰 {res['price']:,.0f}\n📥 {res['entry']}\n\n"
    update.message.reply_text(report, parse_mode='HTML')

def auto_signal_job(context: CallbackContext):
    if not USER_CHAT_ID: return
    now = datetime.now(pytz.timezone('Asia/Jakarta'))
    if now.weekday() < 5 and 9 <= now.hour < 16:
        sym = random.choice(IHSG_RADAR)
        res = get_analysis_data(sym)
        if res and res["status"] == "SAATNYA BELI ✅":
            msg = f"⚡️ **AUTO SIGNAL**\n🚀 **{sym.replace('.JK','')}**\n💰 Harga: {res['price']:,.0f}\n📥 Area Antri: {res['entry']}"
            context.bot.send_message(chat_id=USER_CHAT_ID, text=msg)

# --- 6. RUNNER ---
def start(update: Update, context: CallbackContext):
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    init_db()
    update.message.reply_text("🏛 **Bot AI Mentor Aktif!**\n\n- `/scan` : Cek Watchlist\n- `/add <kode>` : Tambah Saham\n- `/tanya <pertanyaan>` : Konsultasi AI")

if __name__ == '__main__':
    init_db()
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(auto_signal_job, 'interval', minutes=5, args=[updater])
    scheduler.start()
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("add", lambda u, c: u.message.reply_text(f"✅ {db_manage_watchlist('add', c.args[0])} OK!") if c.args else None))
    dp.add_handler(CommandHandler("scan", scan_manual))
    dp.add_handler(CommandHandler("tanya", tanya_ai))
    
    updater.start_polling()
    updater.idle()
