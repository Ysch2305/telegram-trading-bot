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
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
USER_CHAT_ID = None 

# --- DATABASE LOGIC ---
def init_db():
    conn = sqlite3.connect('watchlist.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stocks (symbol TEXT PRIMARY KEY)''')
    c.execute("SELECT count(*) FROM stocks")
    if c.fetchone()[0] == 0:
        default_stocks = ["BUMI.JK", "BBCA.JK", "GOTO.JK", "BBRI.JK", "BMRI.JK", "ANTM.JK"]
        for s in default_stocks:
            c.execute("INSERT OR IGNORE INTO stocks VALUES (?)", (s,))
    conn.commit()
    conn.close()

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
    if df is None or len(df) < 20: return None
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

# --- AUTO SCAN JOB (POTENSI NAIK) ---
def auto_scan_job(context: CallbackContext):
    global USER_CHAT_ID
    if USER_CHAT_ID and is_market_open():
        current_watchlist = get_watchlist()
        results = []
        for sym in current_watchlist:
            try:
                df = yf.download(sym, period="3mo", interval="1d", progress=False, auto_adjust=True)
                res = analyze_symbol(sym, df)
                if res:
                    # Filter untuk Auto-Signal saja
                    if res["status"] == "BUY 🟢":
                        results.append(f"🔥 <b>SINYAL MATANG:</b>\n{res['msg']}")
                    elif res["status"] == "HOLD 🟡" and "Tinggi 📈" in res["vol"]:
                        results.append(f"👀 <b>POTENSI NAIK (Akumulasi Vol):</b>\n{res['msg']}")
                    elif res["status"] == "SELL 🔴":
                        results.append(f"⚠️ <b>SINYAL JUAL:</b>\n{res['msg']}")
            except: continue
        
        if results:
            full_text = "🔔 <b>AUTO-SIGNAL UPDATE</b>\n\n" + "\n\n".join(results)
            context.bot.send_message(chat_id=USER_CHAT_ID, text=full_text, parse_mode='HTML')

# --- BOT COMMANDS ---
def start(update: Update, context: CallbackContext):
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    update.message.reply_text(
        "🚀 <b>SwingWatchBit Pro Aktif!</b>\n\n"
        "• <b>Auto-Signal</b>: Aktif tiap 5 menit (Cek Potensi).\n"
        "• <b>/scan</b>: Analisis semua saham di watchlist.\n"
        "• <b>/add KODE</b>: Tambah saham baru.\n"
        "• <b>/remove KODE</b>: Hapus saham.\n"
        "• <b>/list</b>: Cek isi watchlist.",
        parse_mode='HTML'
    )

def scan(update: Update, context: CallbackContext):
    update.message.reply_text("🔎 Menganalisis seluruh watchlist Anda secara detail...")
    current_watchlist = get_watchlist()
    results = []
    for sym in current_watchlist:
        try:
            df = yf.download(sym, period="3mo", interval="1d", progress=False, auto_adjust=True)
            res = analyze_symbol(sym, df)
            if res: results.append(res["msg"])
        except: continue
    if results:
        update.message.reply_text("\n\n".join(results), parse_mode='HTML')
    else:
        update.message.reply_text("Watchlist kosong atau gagal mengambil data.")

def add_stock(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Gunakan: /add GOTO")
        return
    code = context.args[0].upper()
    if ".JK" not in code: code += ".JK"
    update.message.reply_text(f"⏳ Memvalidasi {code}...")
    try:
        test = yf.download(code, period="1d", progress=False)
        if test.empty:
            update.message.reply_text("❌ Kode saham tidak valid.")
            return
        add_to_db(code)
        update.message.reply_text(f"✅ {code} ditambahkan ke database!")
    except:
        update.message.reply_text("❌ Terjadi kesalahan.")

def remove_stock(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Gunakan: /remove GOTO")
        return
    code = context.args[0].upper()
    if ".JK" not in code: code += ".JK"
    remove_from_db(code)
    update.message.reply_text(f"🗑 {code} dihapus dari watchlist.")

def list_watchlist(update: Update, context: CallbackContext):
    current_watchlist = get_watchlist()
    msg = "📋 <b>Watchlist Anda:</b>\n\n" + "\n".join([f"- {s}" for s in current_watchlist])
    update.message.reply_text(msg, parse_mode='HTML')

if __name__ == '__main__':
    updater = Updater(TOKEN)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("scan", scan))
    dp.add_handler(CommandHandler("add", add_stock))
    dp.add_handler(CommandHandler("remove", remove_stock))
    dp.add_handler(CommandHandler("list", list_watchlist))

    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(auto_scan_job, 'interval', minutes=5, args=[updater])
    scheduler.start()

    updater.start_polling(drop_pending_updates=True)
    updater.idle()
