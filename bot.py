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
logger = logging.getLogger(__name__)

# Mengambil variabel dari Railway
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
USER_CHAT_ID = None 

# Inisialisasi Gemini AI dengan Error Handling lebih kuat
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        ai_model = genai.GenerativeModel('gemini-1.5-flash')
        logger.info("Gemini AI Berhasil Dikonfigurasi")
    else:
        logger.warning("GEMINI_API_KEY tidak ditemukan")
except Exception as e:
    logger.error(f"Gagal Inisialisasi Gemini: {e}")

IHSG_RADAR = ["ASII.JK", "BBCA.JK", "BBNI.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "BRMS.JK", "BUMI.JK", "ANTM.JK", "PANI.JK"]

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
            sym = symbol.upper().replace(".JK", "") + ".JK"
            c.execute("INSERT OR IGNORE INTO watchlist VALUES (?)", (sym,))
            conn.commit()
            return sym
        elif action == "list":
            c.execute("SELECT symbol FROM watchlist")
            return [r[0] for r in c.fetchall()]

# --- 3. ANALYZER ---
def get_technical_data(sym):
    try:
        # Menggunakan data 1 jam terakhir untuk akurasi saat market tutup
        df = yf.download(sym, period="5d", interval="15m", progress=False, auto_adjust=True)
        if df is None or len(df) < 20: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        curr_p = float(df["Close"].iloc[-1])
        ema20 = df["Close"].ewm(span=20).mean().iloc[-1]
        
        status = "SAATNYA BELI ✅" if curr_p >= ema20 else "JANGAN SENTUH 🚫"
        if curr_p < ema20 * 0.99: status = "DISKON SEHAT 🛍️"
        
        low_s = df["Low"].tail(30).min()
        return {"price": curr_p, "status": status, "entry": f"{int(low_s)} - {int(low_s * 1.02)}"}
    except: return None

# --- 4. FITUR /TANYA AI (PERBAIKAN) ---
def tanya_ai(update: Update, context: CallbackContext):
    if not GEMINI_API_KEY:
        return update.message.reply_text("❌ Variabel GEMINI_API_KEY belum ada di Railway.")
    
    query = " ".join(context.args) if context.args else ""
    if not query:
        return update.message.reply_text("Contoh: `/tanya prospek saham BUMI`")

    thinking = update.message.reply_text("🔎 **AI sedang memproses jawaban...**")
    
    # Deteksi ticker saham dalam pertanyaan
    ticker_info = ""
    for word in query.upper().split():
        if len(word) >= 4:
            data = get_technical_data(word + ".JK")
            if data:
                ticker_info = f"Data Teknis {word}: Harga {data['price']}, Status {data['status']}."
                break

    prompt = f"""
    Kamu adalah asisten trading saham profesional Indonesia.
    User bertanya: '{query}'
    {ticker_info}
    Jelaskan dengan gaya bahasa santai, mudah dimengerti ritel, dan berikan alasan logis.
    Jika pasar tutup, jelaskan bahwa data mungkin stagnan.
    """

    try:
        response = ai_model.generate_content(prompt)
        context.bot.edit_message_text(
            chat_id=update.message.chat_id, 
            message_id=thinking.message_id, 
            text=f"🤖 **Analisa AI Mentor:**\n\n{response.text}",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error Gemini: {e}")
        context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=thinking.message_id, text=f"❌ AI Error: {str(e)[:100]}")

# --- 5. AUTOMATION ---
def auto_signal_job(context: CallbackContext):
    if not USER_CHAT_ID: return
    now = datetime.now(pytz.timezone('Asia/Jakarta'))
    # Hanya kirim sinyal Senin-Jumat jam 09:00 - 16:00
    if now.weekday() < 5 and 9 <= now.hour < 16:
        sym = random.choice(IHSG_RADAR)
        res = get_technical_data(sym)
        if res and res["status"] == "SAATNYA BELI ✅":
            msg = f"⚡️ **AUTO SIGNAL**\n🚀 **{sym.replace('.JK','')}**\n💰 Harga: {res['price']:,.0f}\n📥 Entry: {res['entry']}"
            context.bot.send_message(chat_id=USER_CHAT_ID, text=msg)

def scan_manual(update: Update, context: CallbackContext):
    stocks = db_manage_watchlist("list")
    if not stocks: return update.message.reply_text("Watchlist kosong.")
    report = "🏛 **SWING REPORT**\n\n"
    for s in stocks:
        res = get_technical_data(s)
        if res: report += f"**{s.replace('.JK','')}** | {res['status']}\n💰 {res['price']:,.0f}\n\n"
    update.message.reply_text(report)

# --- 6. RUNNER ---
def start(update: Update, context: CallbackContext):
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    init_db()
    update.message.reply_text("🏛 **Bot Siap!**\n\n- `/scan` : Pantau Watchlist\n- `/tanya <hal>` : Tanya AI\n- Auto Signal aktif tiap 5 menit (saat market buka).")

if __name__ == '__main__':
    init_db()
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(auto_signal_job, 'interval', minutes=5, args=[updater])
    scheduler.start()
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("add", lambda u, c: u.message.reply_text(f"✅ {db_manage_watchlist('add', c.args[0])} OK") if c.args else None))
    dp.add_handler(CommandHandler("scan", scan_manual))
    dp.add_handler(CommandHandler("tanya", tanya_ai))
    
    updater.start_polling()
    updater.idle()
