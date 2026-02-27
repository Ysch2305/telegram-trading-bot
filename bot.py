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

# Inisialisasi Gemini
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        ai_model = genai.GenerativeModel('gemini-pro') 
        logger.info("AI Mentor Aktif")
except Exception as e:
    logger.error(f"Gagal koneksi AI: {e}")

# Daftar Saham Luas agar Sinyal Bervariasi (Radar IDX30/80)
IHSG_RADAR = [
    "ASII.JK", "BBCA.JK", "BBNI.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "BRMS.JK", 
    "BUMI.JK", "ANTM.JK", "PANI.JK", "ADRO.JK", "PTBA.JK", "UNTR.JK", "CPIN.JK", 
    "MEDC.JK", "GOTO.JK", "AMRT.JK", "PGAS.JK", "BRIS.JK", "TPIA.JK", "MDKA.JK"
]

# --- DATABASE ---
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

# --- ANALISA TEKNIKAL DENGAN MACD ---
def get_technical_data(sym):
    try:
        df = yf.download(sym, period="5d", interval="15m", progress=False, auto_adjust=True)
        if df is None or len(df) < 30: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # Harga & EMA20
        curr_p = float(df["Close"].iloc[-1])
        ema20 = df["Close"].ewm(span=20).mean().iloc[-1]
        
        # LOGIKA MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal_line = macd.ewm(span=9, adjust=False).mean()
        
        # Kondisi Bullish: Harga > EMA20 DAN MACD > Signal Line
        is_bullish = curr_p >= ema20 and macd.iloc[-1] > signal_line.iloc[-1]
        
        status = "SAATNYA BELI ✅" if is_bullish else "JANGAN SENTUH 🚫"
        if not is_bullish and curr_p < ema20 * 0.99:
            status = "DISKON SEHAT 🛍️"
            
        low_s = df["Low"].tail(30).min()
        return {
            "price": curr_p, 
            "status": status, 
            "entry": f"{int(low_s)} - {int(low_s * 1.02)}",
            "macd_val": macd.iloc[-1],
            "macd_sig": signal_line.iloc[-1]
        }
    except:
        return None

# --- AUTO SIGNAL (5 MENIT) ---
def auto_signal_job(context: CallbackContext):
    global USER_CHAT_ID
    if not USER_CHAT_ID: return
    
    now = datetime.now(pytz.timezone('Asia/Jakarta'))
    # Hanya jalan hari Senin-Jumat jam bursa (09:00 - 16:00)
    if now.weekday() < 5 and 9 <= now.hour < 16:
        # Ambil 10 saham acak dari radar agar sinyal variatif
        pool = random.sample(IHSG_RADAR, 10)
        for sym in pool:
            res = get_technical_data(sym)
            if res and res["status"] == "SAATNYA BELI ✅":
                msg = (f"⚡️ **AUTO SIGNAL (MACD BULLISH)**\n"
                       f"🚀 **{sym.replace('.JK','')}**\n"
                       f"💰 Harga: {res['price']:,.0f}\n"
                       f"📥 Area Entry: {res['entry']}\n"
                       f"📊 MACD: {res['macd_val']:.2f} > {res['macd_sig']:.2f}")
                context.bot.send_message(chat_id=USER_CHAT_ID, text=msg)
                break # Kirim 1 sinyal terbaik saja setiap 5 menit

# --- FITUR /TANYA AI ---
def tanya_ai(update: Update, context: CallbackContext):
    if not GEMINI_API_KEY: return update.message.reply_text("❌ API Key belum terpasang.")
    query = " ".join(context.args)
    if not query: return update.message.reply_text("Contoh: `/tanya BUMI`")
    
    wait = update.message.reply_text("🔎 **AI Mentor menganalisa...**")
    try:
        response = ai_model.generate_content(f"Jawab santai sebagai ahli saham Indonesia: {query}")
        context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=wait.message_id, text=f"🤖 **AI:**\n\n{response.text}")
    except Exception as e:
        context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=wait.message_id, text=f"❌ Error: {str(e)[:50]}")

# --- SCAN MANUAL ---
def scan_manual(update: Update, context: CallbackContext):
    stocks = db_manage_watchlist("list")
    if not stocks: return update.message.reply_text("Watchlist kosong.")
    report = "🏛 **SWING REPORT (MACD)**\n\n"
    for s in stocks:
        res = get_technical_data(s)
        if res:
            report += f"**{s.replace('.JK','')}** | {res['status']}\n💰 Rp{res['price']:,.0f}\n\n"
    update.message.reply_text(report)

# --- RUNNER ---
def start(update: Update, context: CallbackContext):
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    init_db()
    update.message.reply_text("🏛 **Bot Pro Aktif!**\n- Sinyal MACD otomatis tiap 5 menit.\n- /scan : Pantau Watchlist\n- /add <kode> : Tambah Saham")

if __name__ == '__main__':
    init_db()
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # scheduler untuk Auto Signal 5 Menit
    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(auto_signal_job, 'interval', minutes=5, args=[updater])
    scheduler.start()
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("scan", scan_manual))
    dp.add_handler(CommandHandler("add", lambda u, c: u.message.reply_text(f"✅ {db_manage_watchlist('add', c.args[0])} OK") if c.args else None))
    dp.add_handler(CommandHandler("tanya", tanya_ai))
    
    updater.start_polling()
    updater.idle()
