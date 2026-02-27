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

# --- 1. SETUP & LOGGING ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
USER_CHAT_ID = None 

# --- FIX FITUR TANYA: Inisialisasi Gemini ---
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        # Menggunakan gemini-pro agar tidak error 404 di Railway
        ai_model = genai.GenerativeModel('gemini-pro') 
        logger.info("AI Mentor Berhasil Aktif")
except Exception as e:
    logger.error(f"Gagal Inisialisasi Gemini: {e}")

IHSG_RADAR = ["ASII.JK", "BBCA.JK", "BBNI.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "BRMS.JK", "BUMI.JK", "ANTM.JK", "PANI.JK"]

# --- 2. DATABASE (Fitur Add) ---
def init_db():
    with sqlite3.connect('bot_data.db', check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS watchlist (symbol TEXT PRIMARY KEY)')
        conn.commit()

def db_manage_watchlist(action, symbol=None):
    with sqlite3.connect('bot_data.db', check_same_thread=False) as conn:
        c = conn.cursor()
        if action == "add" and symbol:
            sym = symbol.upper().replace(".JK", "") + ".JK"
            c.execute("INSERT OR IGNORE INTO watchlist VALUES (?)", (sym,))
            conn.commit()
            return sym
        elif action == "list":
            c.execute("SELECT symbol FROM watchlist")
            return [r[0] for r in c.fetchall()]

# --- 3. ANALYSER (Tetap Seperti Semula) ---
def get_technical_data(sym):
    try:
        df = yf.download(sym, period="5d", interval="15m", progress=False, auto_adjust=True)
        if df is None or len(df) < 20: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        curr_p = float(df["Close"].iloc[-1])
        ema20 = df["Close"].ewm(span=20).mean().iloc[-1]
        
        # Logika Status
        if curr_p >= ema20:
            status = "SAATNYA BELI ✅"
        elif curr_p < ema20 * 0.99:
            status = "DISKON SEHAT 🛍️"
        else:
            status = "JANGAN SENTUH 🚫"
            
        low_s = df["Low"].tail(30).min()
        return {"price": curr_p, "status": status, "entry": f"{int(low_s)} - {int(low_s * 1.02)}"}
    except:
        return None

# --- 4. PERBAIKAN FITUR /TANYA ---
def tanya_ai(update: Update, context: CallbackContext):
    if not GEMINI_API_KEY:
        return update.message.reply_text("❌ GEMINI_API_KEY belum dipasang di Railway.")
    
    query = " ".join(context.args)
    if not query:
        return update.message.reply_text("Contoh: `/tanya kenapa BUMI jangan sentuh?`")

    thinking = update.message.reply_text("🤔 **AI Mentor sedang menganalisa...**")
    
    # Deteksi info tambahan jika user menyebut saham
    ticker_info = ""
    for word in query.upper().split():
        if len(word) >= 4:
            data = get_technical_data(word + ".JK")
            if data:
                ticker_info = f"Data Teknis {word}: Harga {data['price']}, Status {data['status']}."
                break

    prompt = f"Kamu adalah ahli saham Indonesia. {ticker_info} Jawab pertanyaan ini dengan gaya bahasa santai ritel: {query}"

    try:
        response = ai_model.generate_content(prompt)
        context.bot.edit_message_text(
            chat_id=update.message.chat_id, 
            message_id=thinking.message_id, 
            text=f"🤖 **Analisa AI Mentor:**\n\n{response.text}"
        )
    except Exception as e:
        logger.error(f"Error AI: {e}")
        context.bot.edit_message_text(
            chat_id=update.message.chat_id, 
            message_id=thinking.message_id, 
            text="❌ AI lagi sibuk. Coba tanya hal umum dulu seperti '/tanya apa itu saham?'"
        )

# --- 5. FITUR SCAN & AUTO SIGNAL (Tetap Aktif) ---
def scan_manual(update: Update, context: CallbackContext):
    stocks = db_manage_watchlist("list")
    if not stocks: return update.message.reply_text("Watchlist kosong. Gunakan /add")
    report = "🏛 **HASIL SCAN WATCHLIST**\n\n"
    for s in stocks:
        res = get_technical_data(s)
        if res:
            report += f"**{s.replace('.JK','')}** | {res['status']}\n💰 Harga: {res['price']:,.0f}\n📥 Entry: {res['entry']}\n\n"
    update.message.reply_text(report)

def auto_signal_job(context: CallbackContext):
    if not USER_CHAT_ID: return
    now = datetime.now(pytz.timezone('Asia/Jakarta'))
    if now.weekday() < 5 and 9 <= now.hour < 16:
        sym = random.choice(IHSG_RADAR)
        res = get_technical_data(sym)
        if res and res["status"] == "SAATNYA BELI ✅":
            msg = f"⚡️ **AUTO SIGNAL**\n🚀 **{sym.replace('.JK','')}**\n💰 Harga: {res['price']:,.0f}\n📥 Entry: {res['entry']}"
            context.bot.send_message(chat_id=USER_CHAT_ID, text=msg)

# --- 6. RUNNER ---
def start(update: Update, context: CallbackContext):
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    init_db()
    update.message.reply_text("🏛 **Bot Trading Aktif!**\n/scan - Pantau Watchlist\n/add <kode> - Tambah Saham\n/tanya <hal> - Konsultasi AI")

if __name__ == '__main__':
    init_db()
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Scheduler Auto Signal 5 Menit
    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(auto_signal_job, 'interval', minutes=5, args=[updater])
    scheduler.start()
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("scan", scan_manual))
    dp.add_handler(CommandHandler("add", lambda u, c: u.message.reply_text(f"✅ {db_manage_watchlist('add', c.args[0])} OK") if c.args else None))
    dp.add_handler(CommandHandler("tanya", tanya_ai))
    
    updater.start_polling()
    updater.idle()
