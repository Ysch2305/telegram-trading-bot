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

# 1. Setup Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# 2. Config
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AUTHORIZED_ID = os.environ.get("MY_ID") 

USER_CHAT_ID = None 
USER_MODAL = 0
SENT_STOCKS = [] # Untuk tracking agar tidak mengirim saham yang sama terus

# --- DAFTAR RADAR IHSG ---
IHSG_SCAN_LIST = [
    "ASII.JK", "BBCA.JK", "BBNI.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "GOTO.JK", 
    "ASSA.JK", "BUMI.JK", "ANTM.JK", "MDKA.JK", "INCO.JK", "PGAS.JK", "UNTR.JK", 
    "AMRT.JK", "CPIN.JK", "ICBP.JK", "KLBF.JK", "ADRO.JK", "ITMG.JK", "PTBA.JK",
    "BRIS.JK", "ARTO.JK", "MEDC.JK", "TOWR.JK", "EXCL.JK", "AKRA.JK", "BRPT.JK",
    "AMMN.JK", "INKP.JK", "TPIA.JK", "MAPA.JK", "ACES.JK", "HRUM.JK", "BELL.JK",
    "PANI.JK", "CUAN.JK", "TBNI.JK", "FILM.JK", "JSMR.JK", "MYOR.JK"
]

# --- DATABASE LOGIC ---
def init_db():
    conn = sqlite3.connect('watchlist.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stocks (symbol TEXT PRIMARY KEY)''')
    # Tabel modal
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit()
    conn.close()

def save_modal(val):
    conn = sqlite3.connect('watchlist.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings VALUES ('modal', ?)", (str(val),))
    conn.commit()
    conn.close()

def load_modal():
    conn = sqlite3.connect('watchlist.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = 'modal'")
    res = c.fetchone()
    conn.close()
    return int(res[0]) if res else 0

def get_watchlist():
    conn = sqlite3.connect('watchlist.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT symbol FROM stocks")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

init_db()
USER_MODAL = load_modal()

# --- MARKET LOGIC ---
def is_market_open():
    tz_jakarta = pytz.timezone('Asia/Jakarta')
    now = datetime.now(tz_jakarta)
    return now.weekday() < 5 and (9 <= now.hour < 16)

def analyze_symbol(sym, df):
    if df is None or len(df) < 20: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    
    close = df["Close"]
    volume = df["Volume"]
    current_price = float(close.iloc[-1])
    
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = (-delta).clip(lower=0).rolling(window=14).mean()
    rsi = 100 - (100 / (1 + (gain / loss).iloc[-1]))
    
    vol_status = "Tinggi 📈" if float(volume.iloc[-1]) > volume.rolling(window=20).mean().iloc[-1] else "Rendah 📉"
    
    status = "HOLD 🟡"
    if ema20 > ema50 and rsi > 55: status = "BUY 🟢"
    elif ema20 < ema50 and rsi < 45: status = "SELL 🔴"
        
    return {"status": status, "price": current_price, "vol": vol_status, "rsi": rsi}

# --- AUTO SCAN JOB (DENGAN LOGIKA MODAL & VARIASI) ---
def auto_scan_job(context: CallbackContext):
    global USER_CHAT_ID, USER_MODAL, SENT_STOCKS
    if USER_CHAT_ID and is_market_open() and USER_MODAL > 0:
        results = []
        found_stocks = []
        
        # Shuffle atau putar daftar agar tidak selalu scan dari urutan yang sama
        import random
        random.shuffle(IHSG_SCAN_LIST)

        for sym in IHSG_SCAN_LIST:
            # Lewati jika saham ini baru saja dikirim di sesi sebelumnya
            if sym in SENT_STOCKS: continue
            
            try:
                df = yf.download(sym, period="3mo", interval="1d", progress=False, auto_adjust=True)
                res = analyze_symbol(sym, df)
                
                if res:
                    price_per_lot = res["price"] * 100
                    # Filter: Apakah modal cukup untuk beli minimal 1 lot?
                    if USER_MODAL >= price_per_lot:
                        if res["status"] == "BUY 🟢" or (res["status"] == "HOLD 🟡" and "Tinggi 📈" in res["vol"]):
                            tag = "🔥 REKOMENDASI" if res["status"] == "BUY 🟢" else "👀 POTENSI"
                            max_lot = int(USER_MODAL // price_per_lot)
                            
                            msg = (f"{tag}: <b>{sym.replace('.JK','')}</b>\n"
                                   f"Harga: Rp{res['price']:,.0f}\n"
                                   f"Modal Anda Cukup: {max_lot} Lot\n"
                                   f"Sinyal: {res['status']} | Vol: {res['vol']}")
                            results.append(msg)
                            found_stocks.append(sym)
                            
                if len(results) >= 3: break # Ambil 3 saham berbeda saja per 5 menit
            except: continue
        
        if results:
            SENT_STOCKS = found_stocks # Simpan daftar yang baru dikirim
            full_text = "🚀 <b>SIGNAL SESUAI MODAL</b>\n\n" + "\n\n".join(results)
            context.bot.send_message(chat_id=USER_CHAT_ID, text=full_text, parse_mode='HTML')
        else:
            # Jika semua saham di-skip karena duplikasi, reset tracker
            SENT_STOCKS = []

# --- COMMANDS ---
def is_auth(update):
    return str(update.message.from_user.id) == str(AUTHORIZED_ID)

def start(update: Update, context: CallbackContext):
    if not is_auth(update): return
    global USER_CHAT_ID, USER_MODAL
    USER_CHAT_ID = update.message.chat_id
    
    if USER_MODAL == 0:
        update.message.reply_text("👋 <b>Halo! Silakan masukkan modal investasi Anda sekarang:</b>\n(Contoh ketik: 5000000)", parse_mode='HTML')
        return 1 # State input modal
    else:
        update.message.reply_text(f"🚀 Bot Aktif.\nModal saat ini: <b>Rp{USER_MODAL:,.0f}</b>\n\nGunakan /ubah_modal jika ingin ganti.", parse_mode='HTML')

def handle_message(update: Update, context: CallbackContext):
    if not is_auth(update): return
    global USER_MODAL
    try:
        text = update.message.text.replace(".", "").replace(",", "")
        val = int(text)
        if val < 50000:
            update.message.reply_text("Modal terlalu kecil untuk beli 1 lot saham apa pun. Masukkan minimal 50000.")
            return
        USER_MODAL = val
        save_modal(val)
        update.message.reply_text(f"✅ Modal diset ke: <b>Rp{USER_MODAL:,.0f}</b>\nBot akan mencari saham yang sesuai budget Anda.", parse_mode='HTML')
    except:
        update.message.reply_text("Masukkan angka saja tanpa titik/koma.")

def ubah_modal(update: Update, context: CallbackContext):
    if not is_auth(update): return
    update.message.reply_text("Silakan masukkan nominal modal baru Anda:")

# --- PERINTAH LAINNYA (TETAP SAMA) ---
def scan(update, context):
    if not is_auth(update): return
    update.message.reply_text("🔎 Scan watchlist pribadi...")
    wl = get_watchlist()
    res_list = []
    for s in wl:
        df = yf.download(s, period="3mo", interval="1d", progress=False, auto_adjust=True)
        r = analyze_symbol(s, df)
        if r: res_list.append(f"<b>{s.replace('.JK','')}</b>: {r['status']} | Rp{r['price']:,.0f}")
    if res_list: update.message.reply_text("\n".join(res_list), parse_mode='HTML')

if __name__ == '__main__':
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("ubah_modal", ubah_modal))
    dp.add_handler(CommandHandler("scan", scan))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(auto_scan_job, 'interval', minutes=5, args=[updater])
    scheduler.start()

    print("✅ Bot Private dengan Sistem Modal Aktif...")
    updater.start_polling(drop_pending_updates=True)
    updater.idle()
