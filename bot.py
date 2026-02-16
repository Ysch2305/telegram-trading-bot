import os
import yfinance as yf
import pandas as pd
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz
import sqlite3

# 1. Setup Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
USER_CHAT_ID = None 

# --- DAFTAR RADAR IHSG ---
IHSG_SCAN_LIST = [
    "ASII.JK", "BBCA.JK", "BBNI.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "GOTO.JK", 
    "ASSA.JK", "BUMI.JK", "ANTM.JK", "MDKA.JK", "INCO.JK", "PGAS.JK", "UNTR.JK", 
    "AMRT.JK", "CPIN.JK", "ICBP.JK", "KLBF.JK", "ADRO.JK", "ITMG.JK", "PTBA.JK",
    "BRIS.JK", "ARTO.JK", "MEDC.JK", "TOWR.JK", "EXCL.JK", "AKRA.JK", "BRPT.JK",
    "AMMN.JK", "INKP.JK", "TPIA.JK", "MAPA.JK", "ACES.JK", "HRUM.JK", "BELL.JK"
]

# --- DATABASE LOGIC ---
def init_db():
    try:
        conn = sqlite3.connect('watchlist.db', check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS stocks (symbol TEXT PRIMARY KEY)''')
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB Error: {e}")

def get_watchlist():
    conn = sqlite3.connect('watchlist.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT symbol FROM stocks")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def add_to_db(symbol):
    conn = sqlite3.connect('watchlist.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO stocks VALUES (?)", (symbol,))
    conn.commit()
    conn.close()

def remove_from_db(symbol):
    conn = sqlite3.connect('watchlist.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("DELETE FROM stocks WHERE symbol = ?", (symbol,))
    conn.commit()
    conn.close()

init_db()

# --- MARKET LOGIC ---
def is_market_open():
    tz_jakarta = pytz.timezone('Asia/Jakarta')
    now = datetime.now(tz_jakarta)
    day_of_week = now.weekday()
    current_time = now.time()
    start_time = datetime.strptime("09:00", "%H:%M").time()
    end_time = datetime.strptime("16:00", "%H:%M").time()
    return day_of_week < 5 and (start_time <= current_time <= end_time)

# --- ANALYSIS CORE ---
def analyze_symbol(sym, df):
    if df is None or len(df) < 20: 
        return None
    
    # Perbaikan baris yang sempat error
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    close = df["Close"]
    volume = df["Volume"]
    current_price = float(close.iloc[-1])
    
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = (-delta).clip(lower=0).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1]))
    
    avg_vol = volume.rolling(window=20).mean().iloc[-1]
    vol_now = float(volume.iloc[-1])
    vol_status = "Tinggi 📈" if vol_now > float(avg_vol) else "Rendah 📉"
    
    tp = current_price * 1.05
    sl = current_price * 0.97
    clean_name = sym.replace('.JK','')
    
    if ema20 > ema50 and rsi > 55:
        status = "BUY 🟢"
    elif ema20 < ema50 and rsi < 45:
        status = "SELL 🔴"
    else:
        status = "HOLD 🟡"
        
    msg = (f"<b>{clean_name}</b> | Rp{current_price:,.0f}\n"
           f"Sinyal: {status}\n"
           f"Vol: {vol_status}\n"
           f"🎯 TP: {tp:,.0f} | 🛑 SL: {sl:,.0f}")
    
    return {"status": status, "vol": vol_status, "msg": msg}

# --- AUTO SCAN JOB ---
def auto_scan_job(context: CallbackContext):
    global USER_CHAT_ID
    if USER_CHAT_ID and is_market_open():
        results = []
        for sym in IHSG_SCAN_LIST:
            try:
                df = yf.download(sym, period="3mo", interval="1d", progress=False, auto_adjust=True)
                res = analyze_symbol(sym, df)
                if res:
                    if res["status"] == "BUY 🟢":
                        results.append(f"🔥 <b>REKOMENDASI BUY:</b>\n{res['msg']}")
                    elif res["status"] == "HOLD 🟡" and "Tinggi 📈" in res["vol"]:
                        results.append(f"👀 <b>POTENSI NAIK (Akumulasi):</b>\n{res['msg']}")
            except: 
                continue
        
        if results:
            full_text = "🚀 <b>RADAR POTENSI IHSG</b>\n\n" + "\n\n".join(results[:5])
            context.bot.send_message(chat_id=USER_CHAT_ID, text=full_text, parse_mode='HTML')

# --- COMMANDS ---
def start(update: Update, context: CallbackContext):
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    update.message.reply_text(
        "🚀 <b>SwingWatchBit Pro Online!</b>\n\n"
        "• <b>Auto-Radar</b>: Aktif otomatis tiap 5 menit.\n"
        "• <b>/scan</b>: Analisis watchlist pribadi.\n"
        "• <b>/add KODE</b>: Tambah saham.\n"
        "• <b>/remove KODE</b>: Hapus saham.\n"
        "• <b>/list</b>: Cek watchlist.",
        parse_mode='HTML'
    )

def scan(update: Update, context: CallbackContext):
    update.message.reply_text("🔎 Menganalisis watchlist pribadi...")
    current_watchlist = get_watchlist()
    if not current_watchlist:
        update.message.reply_text("Watchlist pribadi Anda kosong.")
        return
    results = []
    for sym in current_watchlist:
        try:
            df = yf.download(sym, period="3mo", interval="1d", progress=False, auto_adjust=True)
            res = analyze_symbol(sym, df)
            if res: results.append(res["msg"])
        except: continue
    if results:
        update.message.reply_text("\n\n".join(results), parse_mode='HTML')

def add_stock(update: Update, context: CallbackContext):
    if not context.args: return
    code = context.args[0].upper()
    if ".JK" not in code: code += ".JK"
    add_to_db(code)
    update.message.reply_text(f"✅ {code} masuk watchlist pribadi!")

def remove_stock(update: Update, context: CallbackContext):
    if not context.args: return
    code = context.args[0].upper()
    if ".JK" not in code: code += ".JK"
    remove_from_db(code)
    update.message.reply_text(f"🗑 {code} dihapus.")

def list_watchlist(update: Update, context: CallbackContext):
    current_watchlist = get_watchlist()
    msg = "📋 <b>Watchlist Anda:</b>\n\n" + "\n".join([f"- {s}" for s in current_watchlist])
    update.message.reply_text(msg, parse_mode='HTML')

# --- MAIN RUNNER ---
if __name__ == '__main__':
    if not TOKEN:
        print("❌ ERROR: TOKEN KOSONG!")
    else:
        init_db()
        updater = Updater(TOKEN, use_context=True)
        dp = updater.dispatcher
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("scan", scan))
        dp.add_handler(CommandHandler("add", add_stock))
        dp.add_handler(CommandHandler("remove", remove_stock))
        dp.add_handler(CommandHandler("list", list_watchlist))

        scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
        scheduler.add_job(auto_scan_job, 'interval', minutes=5, args=[updater])
        scheduler.start()

        print("✅ Bot is Online...")
        updater.start_polling(drop_pending_updates=True)
        updater.idle()
