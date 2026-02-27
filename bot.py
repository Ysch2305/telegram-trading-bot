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

# --- 1. SETUP & AUTH ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
USER_CHAT_ID = None 

# Inisialisasi Gemini AI jika Key ada
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    ai_model = genai.GenerativeModel('gemini-1.5-flash')

# Daftar Radar IDX
IHSG_RADAR = [
    "ASII.JK", "BBCA.JK", "BBNI.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "BRMS.JK", 
    "BUMI.JK", "GOTO.JK", "ANTM.JK", "MEDC.JK", "ADRO.JK", "PTBA.JK", "PANI.JK"
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
            sym = symbol.upper().replace(".JK", "") + ".JK"
            c.execute("INSERT OR IGNORE INTO watchlist VALUES (?)", (sym,))
            conn.commit()
            return sym
        elif action == "list":
            c.execute("SELECT symbol FROM watchlist")
            return [r[0] for r in c.fetchall()]
        elif action == "remove" and symbol:
            sym = symbol.upper().replace(".JK", "") + ".JK"
            c.execute("DELETE FROM watchlist WHERE symbol = ?", (sym,))
            conn.commit()
            return sym

# --- 3. CORE ANALYZER (SWING & SCALPING) ---
def get_technical_data(sym, interval="5m"):
    try:
        df = yf.download(sym, period="1mo", interval=interval, progress=False, auto_adjust=True)
        if df is None or len(df) < 50: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # Harga & EMA
        curr_p = float(df["Close"].iloc[-1])
        ema20 = df["Close"].ewm(span=20).mean().iloc[-1]
        
        # MACD
        exp1 = df["Close"].ewm(span=12, adjust=False).mean()
        exp2 = df["Close"].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal_line = macd.ewm(span=9, adjust=False).mean()
        
        # Volume Spike
        avg_vol = df["Volume"].tail(20).mean()
        curr_vol = df["Volume"].iloc[-1]
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 0
        
        status = "SAATNYA BELI ✅" if curr_p > ema20 else "JANGAN SENTUH 🚫"
        low_support = df["Low"].tail(50).min()
        
        return {
            "price": curr_p, "status": status, "macd": macd.iloc[-1], 
            "signal": signal_line.iloc[-1], "ema20": ema20, "vol_ratio": vol_ratio,
            "entry": f"{int(low_support)} - {int(low_support * 1.02)}",
            "tp": curr_p * 1.07, "sl": low_support * 0.97
        }
    except Exception as e:
        logger.error(f"Error data {sym}: {e}")
        return None

# --- 4. FEATURE: /TANYA AI MENTOR ---
def tanya_ai(update: Update, context: CallbackContext):
    if not GEMINI_API_KEY:
        return update.message.reply_text("❌ GEMINI_API_KEY belum di-set di Railway Variables.")
    
    if not context.args:
        return update.message.reply_text("Contoh: `/tanya kenapa BUMI jangan sentuh?`")

    query = " ".join(context.args)
    ticker = context.args[0].upper().replace("?", "").replace(".JK", "") + ".JK"
    
    thinking = update.message.reply_text("🤔 **AI Mentor sedang menganalisa...**")
    
    # Ambil data teknis asli sebagai bahan AI
    data = get_technical_data(ticker)
    
    prompt = f"""
    Kamu adalah asisten ahli saham Indonesia. User bertanya: '{query}'
    Data Teknis {ticker}: 
    Harga Sekarang: {data['price'] if data else 'N/A'}, 
    Status Bot: {data['status'] if data else 'N/A'},
    MACD: {data['macd'] if data else 'N/A'}.

    Jelaskan kepada user kenapa statusnya demikian. Gunakan bahasa gaul ritel saham Indonesia (santai, tidak kaku). 
    Berikan edukasi kenapa harga tersebut layak dibeli atau harus dihindari.
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
        logger.error(f"Gemini Error: {e}")
        context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=thinking.message_id, text=f"❌ AI lagi pusing: {e}")

# --- 5. AUTOMATION & SCAN ---
def auto_signal_job(context: CallbackContext):
    global USER_CHAT_ID
    if not USER_CHAT_ID: return
    
    now = datetime.now(pytz.timezone('Asia/Jakarta'))
    # Market Buka Senin-Jumat jam 9-4 sore
    if now.weekday() < 5 and 9 <= now.hour < 16:
        sym = random.choice(IHSG_RADAR)
        res = get_technical_data(sym, interval="1m") # Pakai 1m untuk Scalping
        
        # Syarat Scalping: MACD Golden Cross + Volume Meledak
        if res and res["vol_ratio"] > 2.0 and res["macd"] > res["signal"]:
            msg = (f"⚡️ **SCALPING ALERT**\n🚀 **{sym.replace('.JK','')}**\n"
                   f"💰 Harga: {res['price']:,.0f}\n📊 Vol Spike: {res['vol_ratio']:.1f}x\n"
                   f"🎯 Target Copet: {res['price']*1.02:,.0f}")
            context.bot.send_message(chat_id=USER_CHAT_ID, text=msg)

def scan_manual(update: Update, context: CallbackContext):
    stocks = db_manage_watchlist("list")
    if not stocks: return update.message.reply_text("Watchlist kosong. Pakai `/add <kode>`")
    
    report = "🏛 **SWING REPORT**\n\n"
    for s in stocks:
        res = get_technical_data(s)
        if res:
            report += f"**{s.replace('.JK','')}** | {res['status']}\n💰 Rp{res['price']:,.0f}\n📥 Entry: {res['entry']}\n\n"
    update.message.reply_text(report, parse_mode='HTML')

# --- 6. MAIN ---
if __name__ == '__main__':
    init_db()
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(auto_signal_job, 'interval', minutes=5, args=[updater])
