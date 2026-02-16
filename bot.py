import os
import yfinance as yf
import pandas as pd
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler, Filters
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz
import sqlite3
import random

# 1. Setup Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# 2. Config
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AUTHORIZED_ID = os.environ.get("MY_ID")

USER_CHAT_ID = None
SENT_STOCKS = [] # Tracker agar tiap 5 menit sahamnya beda

# --- DAFTAR RADAR IHSG (Untuk Auto Signal) ---
IHSG_RADAR = [
    "ASII.JK", "BBCA.JK", "BBNI.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "GOTO.JK",
    "ASSA.JK", "BUMI.JK", "ANTM.JK", "MDKA.JK", "INCO.JK", "PGAS.JK", "UNTR.JK",
    "AMRT.JK", "CPIN.JK", "ICBP.JK", "KLBF.JK", "ADRO.JK", "ITMG.JK", "PTBA.JK",
    "BRIS.JK", "ARTO.JK", "MEDC.JK", "TOWR.JK", "EXCL.JK", "AKRA.JK", "BRPT.JK",
    "AMMN.JK", "INKP.JK", "TPIA.JK", "MAPA.JK", "ACES.JK", "HRUM.JK", "PANI.JK"
]

# --- DATABASE LOGIC ---
def init_db():
    conn = sqlite3.connect('bot_data.db', check_same_thread=False)
    c = conn.cursor()
    # Tabel Watchlist Manual
    c.execute('CREATE TABLE IF NOT EXISTS watchlist (symbol TEXT PRIMARY KEY)')
    # Tabel Settings (Modal)
    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    conn.commit()
    conn.close()

def db_manage_watchlist(action, symbol=None):
    conn = sqlite3.connect('bot_data.db', check_same_thread=False)
    c = conn.cursor()
    if action == "add":
        c.execute("INSERT OR IGNORE INTO watchlist VALUES (?)", (symbol,))
    elif action == "remove":
        c.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
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

# --- SECURITY CHECK ---
def is_auth(update: Update):
    uid = str(update.message.from_user.id)
    return AUTHORIZED_ID and uid == str(AUTHORIZED_ID).strip()

# --- ANALYSIS CORE ---
def analyze_stock(sym):
    try:
        df = yf.download(sym, period="3mo", interval="1d", progress=False, auto_adjust=True)
        if df is None or len(df) < 20: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        close = df["Close"]
        curr_p = float(close.iloc[-1])
        ema20 = close.ewm(span=20).mean().iloc[-1]
        ema50 = close.ewm(span=50).mean().iloc[-1]
        
        # RSI
        delta = close.diff()
        up = delta.clip(lower=0).rolling(14).mean().iloc[-1]
        down = (-1 * delta.clip(upper=0)).rolling(14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (up/down))) if down != 0 else 100
        
        status = "HOLD 🟡"
        if ema20 > ema50 and rsi > 55: status = "BUY 🟢"
        elif ema20 < ema50 and rsi < 45: status = "SELL 🔴"
        
        return {"status": status, "price": curr_p, "rsi": rsi}
    except: return None

# --- AUTO SIGNAL JOB (Tiap 5 Menit) ---
def auto_signal_job(context: CallbackContext):
    global USER_CHAT_ID, SENT_STOCKS
    modal = load_modal()
    now = datetime.now(pytz.timezone('Asia/Jakarta'))
    
    # Syarat: Modal ada, Chat ID ada, Jam Bursa (Senin-Jumat 09:00-16:00)
    if USER_CHAT_ID and modal > 0 and (now.weekday() < 5 and 9 <= now.hour < 16):
        results = []
        found_now = []
        
        # Filter pool: cari saham yang tidak dikirim di sesi sebelumnya
        pool = [s for s in IHSG_RADAR if s not in SENT_STOCKS]
        random.shuffle(pool)

        for sym in pool:
            res = analyze_stock(sym)
            if res:
                if modal >= (res["price"] * 100): # Cek budget 1 lot
                    if "BUY" in res["status"]:
                        msg = f"🔥 <b>BUY: {sym.replace('.JK','')}</b>\nHarga: Rp{res['price']:,.0f}\nRSI: {res['rsi']:.1f}"
                        results.append(msg)
                        found_now.append(sym)
            if len(results) >= 3: break # Maksimal 3 saham per update
        
        if results:
            SENT_STOCKS = found_now # Simpan agar sesi depan beda
            text = "🚀 <b>UPDATE SIGNAL (5 MENIT)</b>\n<i>Berdasarkan modal & analisa terbaru</i>\n\n" + "\n\n".join(results)
            context.bot.send_message(chat_id=USER_CHAT_ID, text=text, parse_mode='HTML')

# --- COMMAND HANDLERS ---
def start(update: Update, context: CallbackContext):
    if not is_auth(update): return
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    modal = load_modal()
    if modal == 0:
        update.message.reply_text("👋 <b>Selamat Datang!</b>\n\nSilakan masukkan <b>Modal Investasi</b> Anda (angka saja):", parse_mode='HTML')
    else:
        update.message.reply_text(f"✅ <b>Bot Aktif</b>\nModal: Rp{modal:,.0f}\n\nPerintah:\n/scan - Cek Watchlist\n/add KODE - Tambah Saham\n/remove KODE - Hapus Saham\n/list - Lihat Watchlist\n/ubah_modal - Ganti Modal", parse_mode='HTML')

def handle_text(update: Update, context: CallbackContext):
    if not is_auth(update): return
    text = update.message.text.strip()
    if text.isdigit():
        val = int(text)
        save_modal(val)
        update.message.reply_text(f"✅ Modal disimpan: <b>Rp{val:,.0f}</b>\nSinyal otomatis akan aktif setiap 5 menit di jam bursa.", parse_mode='HTML')
    elif not text.startswith('/'):
        update.message.reply_text("Masukkan angka nominal modal atau gunakan /perintah.")

def add_stock(update: Update, context: CallbackContext):
    if not is_auth(update) or not context.args: return
    sym = context.args[0].upper()
    if ".JK" not in sym: sym += ".JK"
    db_manage_watchlist("add", sym)
    update.message.reply_text(f"✅ {sym} ditambah ke watchlist manual.")

def remove_stock(update: Update, context: CallbackContext):
    if not is_auth(update) or not context.args: return
    sym = context.args[0].upper()
    if ".JK" not in sym: sym += ".JK"
    db_manage_watchlist("remove", sym)
    update.message.reply_text(f"🗑 {sym} dihapus dari watchlist.")

def list_watchlist(update: Update, context: CallbackContext):
    if not is_auth(update): return
    stocks = db_manage_watchlist("list")
    txt = "📋 <b>Watchlist Anda:</b>\n" + "\n".join([f"- {s}" for s in stocks]) if stocks else "Watchlist kosong."
    update.message.reply_text(txt, parse_mode='HTML')

def scan_watchlist(update: Update, context: CallbackContext):
    if not is_auth(update): return
    stocks = db_manage_watchlist("list")
    if not stocks:
        update.message.reply_text("Watchlist kosong. Gunakan /add dulu.")
        return
    update.message.reply_text("🔎 Menganalisa watchlist manual Anda...")
    res_list = []
    for s in stocks:
        r = analyze_stock(s)
        if r: res_list.append(f"<b>{s.replace('.JK','')}</b>: {r['status']} | Rp{r['price']:,.0f}")
    update.message.reply_text("\n".join(res_list), parse_mode='HTML')

def ubah_modal(update: Update, context: CallbackContext):
    if not is_auth(update): return
    update.message.reply_text("Silakan masukkan nominal modal baru Anda:")

# --- MAIN ---
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

    logger.info("Bot is running...")
    updater.start_polling(drop_pending_updates=True)
    updater.idle()
