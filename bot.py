import os
import logging
import yfinance as yf
import google.generativeai as genai
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

# --- FIX ERROR 404: Inisialisasi Gemini ---
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        # Menggunakan 'gemini-pro' sebagai fallback jika flash bermasalah
        ai_model = genai.GenerativeModel('gemini-pro') 
        logger.info("AI Mentor Berhasil Aktif")
except Exception as e:
    logger.error(f"Gagal koneksi AI: {e}")

# --- ANALISA TEKNIKAL ---
def get_stock_analysis(ticker):
    try:
        if not ticker.endswith(".JK"): ticker += ".JK"
        df = yf.download(ticker, period="5d", interval="15m", progress=False)
        if df.empty: return None
        
        last_price = df['Close'].iloc[-1]
        ema20 = df['Close'].ewm(span=20).mean().iloc[-1]
        status = "SAATNYA BELI ✅" if last_price >= ema20 else "JANGAN SENTUH 🚫"
        
        return {"price": last_price, "status": status, "ticker": ticker.replace(".JK", "")}
    except: return None

# --- FITUR /TANYA (DIPERBAIKI) ---
def tanya_ai(update: Update, context: CallbackContext):
    query = " ".join(context.args)
    if not query:
        return update.message.reply_text("Contoh: `/tanya prospek BUMI`")
    
    wait_msg = update.message.reply_text("🔎 **AI Mentor sedang menganalisa...**")
    
    # Ambil data teknis sederhana untuk referensi AI
    ticker = context.args[0].upper() if context.args else ""
    tech = get_stock_analysis(ticker)
    
    info_tambahan = ""
    if tech:
        info_tambahan = f"Data teknis {tech['ticker']}: Harga {tech['price']:.0f}, Status {tech['status']}."

    prompt = f"{info_tambahan} User bertanya: {query}. Jawab dengan gaya bahasa santai investor ritel Indonesia."

    try:
        response = ai_model.generate_content(prompt)
        context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=wait_msg.message_id,
            text=f"🤖 **Analisa AI Mentor:**\n\n{response.text}"
        )
    except Exception as e:
        context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=wait_msg.message_id,
            text=f"❌ AI sedang sibuk. Coba lagi nanti.\nError: {str(e)[:50]}"
        )

# --- FITUR SCAN & AUTO SIGNAL ---
def scan_saham(update: Update, context: CallbackContext):
    watchlist = ["BBRI", "BMRI", "BUMI", "ANTM", "TLKM"]
    pesan = "🏛 **SWING REPORT**\n\n"
    for s in watchlist:
        res = get_stock_analysis(s)
        if res:
            pesan += f"**{res['ticker']}** | {res['status']}\n💰 Harga: {res['price']:,.0f}\n\n"
    update.message.reply_text(pesan, parse_mode='Markdown')

def start(update: Update, context: CallbackContext):
    update.message.reply_text("🏛 **Bot Aktif!**\n\n/scan - Cek Watchlist\n/tanya <hal> - Tanya AI Mentor")

if __name__ == '__main__':
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("scan", scan_saham))
    dp.add_handler(CommandHandler("tanya", tanya_ai))
    
    updater.start_polling()
    updater.idle()
