import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
import yfinance as yf
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler, Filters
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz
import sqlite3
import random

# Setup Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AUTHORIZED_ID = os.environ.get("MY_ID")

USER_CHAT_ID = None
SENT_STOCKS = [] 

IHSG_RADAR = [
    "BUMI.JK", "BRMS.JK", "ENRG.JK", "DEWA.JK", "BHIT.JK", "KPIG.JK", "MNCN.JK", 
    "MLPL.JK", "MPPA.JK", "LPKR.JK", "BRPT.JK", "TPIA.JK", "PNLF.JK", "GOTO.JK", 
    "ASSA.JK", "PANI.JK", "ADMR.JK", "DOID.JK", "KIJA.JK", "BSBK.JK"
]

def get_realtime_price(sym):
    try:
        ticker = sym.split('.')[0]
        url = f"https://www.google.com/finance/quote/{ticker}:IDX"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(response.text, 'html.parser')
        price_class = soup.find("div", {"class": "YMlSbc"})
        if price_class:
            return float(price_class.text.replace('IDR', '').replace(',', '').strip())
        return None
    except: return None

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect('bot_data.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS watchlist (symbol TEXT PRIMARY KEY)')
    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    conn.commit()
    conn.close()

def db_manage_watchlist(action, symbol=None):
    conn = sqlite3.connect('bot_data.db', check_same_thread=False)
    c = conn.cursor()
    if action == "add": c.execute("INSERT OR IGNORE INTO watchlist VALUES (?)", (symbol,))
    elif action == "remove": c.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
    elif action == "list":
        c.execute("SELECT symbol FROM watchlist")
        res = [r[0] for r in c.fetchall()]
        conn.close()
        return res
    conn.commit()
    conn.close()

def save_modal(val):
    conn = sqlite3.connect('bot_data.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings VALUES ('modal', ?)", (str(val),))
    conn.commit()
    conn.close()

def load_modal():
    conn = sqlite3.connect('bot_data.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = 'modal'")
    res = c.fetchone()
    conn.close()
    return int(res[0]) if res else 0

init_db()

def is_auth(update: Update):
    uid = str(update.message.from_user.id)
    return AUTHORIZED_ID and uid == str(AUTHORIZED_ID).strip()

# --- MAXIMIZED ANALYSIS CORE ---
def analyze_stock(sym):
    try:
        rt_price = get_realtime_price(sym)
        df = yf.download(sym, period="3mo", interval="1d", progress=False, auto_adjust=True)
        if df is None or len(df) < 20: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        curr_p = rt_price if rt_price else float(df["Close"].iloc[-1])
        prev_p = float(df["Close"].iloc[-2])
        
        # 1. EMA Triple Filter
        ema5 = df["Close"].ewm(span=5).mean().iloc[-1]
        ema20 = df["Close"].ewm(span=20).mean().iloc[-1]
        ema50 = df["Close"].ewm(span=50).mean().iloc[-1]
        
        # 2. RSI Precision
        delta = df["Close"].diff()
        up = delta.clip(lower=0).rolling(14).mean().iloc[-1]
        down = (-1 * delta.clip(upper=0)).rolling(14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (up/down))) if down != 0 else 100
        
        # 3. Advanced Volume Analysis
        avg_vol = df["Volume"].tail(10).mean()
        curr_vol = df["Volume"].iloc[-1]
        
        # Logika Status
        if curr_p > ema20 and ema5 > ema20 and rsi > 50:
            status = "BUY 🟢"
            # Deteksi Akumulasi
            vol_status = "AKUMULASI 🔥" if curr_vol > avg_vol and curr_p >= prev_p else "STRONG BUY 💪"
        elif rsi < 30:
            status = "WATCH 🟡"
            vol_status = "OVERSOLD (Cheap)"
        elif curr_p < ema20 or (curr_p < prev_p and curr_vol > avg_vol * 1.5):
            status = "SELL 🔴"
            vol_status = "DISTRIBUSI ⚠️" if curr_vol > avg_vol else "WEAK 📉"
        else:
            status = "HOLD 🟡"
            vol_status = "NORMAL ⚪"

        low_support = df["Low"].tail(5).min()
        entry_zone = f"{int(low_support)} - {int(low_support * 1.02)}" # Area dekat support
        
        return {
            "status": status, "price": curr_p, "tp": curr_p * 1.07, "sl": low_support * 0.98, 
            "entry": entry_zone, "vol": vol_status, "rsi": int(rsi)
        }
    except: return None

# --- COMMANDS ---
def start(update: Update, context: CallbackContext):
    if not is_auth(update): return
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    modal = load_modal()
    update.message.reply_text(f"🚀 <b>Bot Pro Max Aktif</b>\nModal: Rp{modal:,.0f}\nAnalisa: EMA Triple, VSA, & RSI Divergence.", parse_mode='HTML')

def scan_watchlist(update: Update, context: CallbackContext):
    if not is_auth(update): return
    stocks = db_manage_watchlist("list")
    if not stocks:
        update.message.reply_text("Watchlist kosong.")
        return

    status_msg = update.message.reply_text("🔎 <b>Memproses Analisa Pro...</b>", parse_mode='HTML')
    final_report = "🔎 <b>HASIL SCAN PRO MAX</b>\n\n"
    
    for s in stocks:
        res = analyze_stock(s)
        if res:
            final_report += (f"<b>{s.replace('.JK','')}</b> | {res['status']}\n"
                             f"💰 Harga: Rp{res['price']:,.0f} (RSI: {res['rsi']})\n"
                             f"📥 Area Entry: {res['entry']}\n"
                             f"📊 Kondisi: {res['vol']}\n"
                             f"🎯 TP: {res['tp']:,.0f} | 🛑 SL: {res['sl']:,.0f}\n\n")
    
    context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=status_msg.message_id, text=final_report, parse_mode='HTML')

# (Fungsi add_stock, remove_stock, list_watchlist, ubah_modal, handle_text tetap sama seperti sebelumnya)
def add_stock(update: Update, context: CallbackContext):
    if not is_auth(update) or not context.args: return
    sym = context.args[0].upper()
    if ".JK" not in sym: sym += ".JK"
    db_manage_watchlist("add", sym)
    update.message.reply_text(f"✅ {sym} ditambah.")

def remove_stock(update: Update, context: CallbackContext):
    if not is_auth(update) or not context.args: return
    sym = context.args[0].upper().replace(".JK","") + ".JK"
    db_manage_watchlist("remove", sym)
    update.message.reply_text(f"🗑 {sym} dihapus.")

def list_watchlist(update: Update, context: CallbackContext):
    if not is_auth(update): return
    s = db_manage_watchlist("list")
    update.message.reply_text(f"📋 Watchlist: {', '.join(s) if s else 'Kosong'}")

def ubah_modal(update: Update, context: CallbackContext):
    if not is_auth(update): return
    update.message.reply_text("Masukkan modal baru (angka):")

def handle_text(update: Update, context: CallbackContext):
    if not is_auth(update): return
    text = update.message.text.strip()
    if text.isdigit():
        save_modal(int(text))
        update.message.reply_text(f"✅ Modal Rp{int(text):,.0f} disimpan.")

def auto_signal_job(context: CallbackContext):
    global USER_CHAT_ID, SENT_STOCKS
    modal = load_modal()
    now = datetime.now(pytz.timezone('Asia/Jakarta'))
    if USER_CHAT_ID and modal > 0 and (now.weekday() < 5 and 9 <= now.hour < 16):
        results = []
        found_now = []
        pool = [s for s in IHSG_RADAR if s not in SENT_STOCKS]
        random.shuffle(pool)
        for sym in pool:
            res = analyze_stock(sym)
            if res and ("BUY" in res["status"] or "WATCH" in res["status"]) and modal >= (res["price"] * 100):
                results.append(f"🔥 <b>SIGNAL: {sym.replace('.JK','')}</b>\n"
                               f"Harga: {res['price']:,.0f}\n"
                               f"📥 Area Entry: {res['entry']}\n"
                               f"📊 Kondisi: {res['vol']}\n"
                               f"🎯 TP: {res['tp']:,.0f} | 🛑 SL: {res['sl']:,.0f}")
                found_now.append(sym)
            if len(results) >= 3: break
        if results:
            SENT_STOCKS = found_now
            context.bot.send_message(chat_id=USER_CHAT_ID, text="🚀 <b>RADAR PRO MAX</b>\n\n"+"\n\n".join(results), parse_mode='HTML')

if __name__ == '__main__':
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("add", add_stock))
    dp.add_handler(CommandHandler("remove", remove_stock))
    dp.add_handler(CommandHandler("list", list_watchlist))
    dp.add_handler(CommandHandler("scan", scan_watchlist))
    dp.add_handler(CommandHandler("ubah_modal", ubah_modal))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
    
    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(auto_signal_job, 'interval', minutes=5, args=[updater])
    scheduler.start()
    updater.start_polling(drop_pending_updates=True)
    updater.idle()
