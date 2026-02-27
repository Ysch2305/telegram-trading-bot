import os
import logging
import yfinance as yf
import pandas as pd
import google.generativeai as genai
import sqlite3
import random
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz

# --- SETUP LOGGING ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
USER_CHAT_ID = None 

# --- FIX ERROR 404: Inisialisasi Gemini ---
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        # Menggunakan 'gemini-pro' karena model 'flash' sering 404 pada versi library tertentu
        ai_model = genai.GenerativeModel('gemini-pro') 
        logger.info("AI Mentor Berhasil Aktif")
except Exception as e:
    logger.error(f"Gagal koneksi AI: {e}")

# --- DATABASE (Fitur Add Anda) ---
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

# --- ANALISA TEKNIKAL (Logika Asli Anda) ---
def get_technical_data(sym):
    try:
        df = yf.download(sym, period="5d", interval="15m", progress=False, auto_adjust=True)
        if df is None or len(df) < 20: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        curr_p = float(df["Close"].iloc[-1])
        ema20 = df["Close"].ewm(span=20).mean().iloc[-1]
        
        status = "SAATNYA BELI ✅" if curr_p >= ema20 else "JANGAN SENTUH 🚫"
        if curr_p < ema20 * 0.99: status = "DISKON SEHAT 🛍️"
        
        low_s = df["Low"].tail(30).min()
        return {"price": curr_p, "status": status, "entry": f"{int(low_s)} - {int(low_s * 1.02)}"}
    except:
        return None

# --- FITUR /TANYA (PERBAIKAN TOTAL) ---
def tanya_ai(update: Update, context: CallbackContext):
    if not GEMINI_API_KEY:
        return update.message.reply_text("❌ API Key belum terpasang di Railway.")
    
    query = " ".join(context.args)
    if not query:
        return update.message.reply_text("Contoh: `/tanya prospek saham BUMI`")
    
    wait_msg = update.message.reply_text("🔎 **AI Mentor sedang menganalisa...**")
    
    try:
        # Kirim prompt sederhana agar AI bisa menjawab
        response = ai_model.generate_content(f"Jawab pertanyaan investor saham Indonesia ini dengan santai: {query}")
        
        context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=wait_msg.message_id,
            text=f"🤖 **Analisa AI Mentor:**\n\n{response.text}",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error AI: {e}")
        context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=wait_msg.message_id,
            text=f"❌ AI sedang pusing. Error: {str(e)[:50]}"
        )

# --- FITUR SCAN (Logika Asli Anda) ---
def scan_manual(update: Update, context: CallbackContext):
    stocks = db_manage_watchlist("list")
    if not stocks: return update.message.reply_text("Watchlist kosong.")
    report = "🏛 **SWING REPORT**\n\n"
    for s in stocks:
        res = get_technical_data(s)
        if res:
            report += f"**{s.replace('.JK','')}** | {res['status']}\n💰 Harga: {res['price']:,.0f}\n📥 Entry: {res['entry']}\n\n"
    update.message.reply_text(report)

# --- RUNNER ---
def start(update: Update, context: CallbackContext):
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    init_db()
    update.message.reply_text("🏛 **Bot Aktif!**\n/scan - Cek Watchlist\n/add <kode> - Tambah Saham\n/tanya <hal> - Tanya AI")

if __name__ == '__main__':
    init_db()
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("scan", scan_manual))
    dp.add_handler(CommandHandler("add", lambda u, c: u.message.reply_text(f"✅ {db_manage_watchlist('add', c.args[0])} OK") if c.args else None))
    dp.add_handler(CommandHandler("tanya", tanya_ai))
    
    updater.start_polling()
    updater.idle()
