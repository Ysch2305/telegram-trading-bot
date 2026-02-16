import os
import yfinance as yf
import pandas as pd
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz

# 1. Setup Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
# Variabel global untuk menyimpan chat_id kamu agar bot tahu ke mana harus kirim auto-chat
USER_CHAT_ID = None

# Daftar saham awal
watchlist = ["BUMI.JK", "BBCA.JK", "BUVA.JK", "BBRI.JK", "BMRI.JK", "ANTM.JK"]

def is_market_open():
    """Mengecek apakah saat ini jam buka Bursa Efek Indonesia (BEI)."""
    tz_jakarta = pytz.timezone('Asia/Jakarta')
    now = datetime.now(tz_jakarta)
    
    # Senin = 0, Minggu = 6
    day_of_week = now.weekday()
    current_time = now.time()
    
    start_time = datetime.strptime("09:00", "%H:%M").time()
    end_time = datetime.strptime("16:00", "%H:%M").time()
    
    # Cek jika hari kerja dan di dalam jam bursa
    if day_of_week < 5 and (start_time <= current_time <= end_time):
        return True
    return False

def analyze_symbol(sym, df):
    """Analisis teknikal lengkap dengan Volume & Trade Plan."""
    if len(df) < 50: return None
    
    close = df["Close"]
    volume = df["Volume"]
    current_price = close.iloc[-1]
    
    # Indikator
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = (-delta).clip(lower=0).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1]))
    
    avg_vol = volume.rolling(window=20).mean().iloc[-1]
    vol_status = "Tinggi 📈" if volume.iloc[-1] > avg_vol else "Rendah 📉"
    
    # Trade Plan (TP 5%, SL 3%)
    tp = current_price * 1.05
    sl = current_price * 0.97
    
    if ema20 > ema50 and rsi > 55:
        return f"<b>{sym.replace('.JK','')}</b> | Rp{current_price:,.0f}\nSinyal: BUY 🟢\nAnalisa: Bullish, Vol {vol_status}\n🎯 TP: {tp:,.0f} | 🛑 SL: {sl:,.0f}"
    elif ema20 < ema50 and rsi < 45:
        return f"<b>{sym.replace('.JK','')}</b> | Rp{current_price:,.0f}\nSinyal: SELL 🔴\nAnalisa: Bearish, Vol {vol_status}\n⚠️ Amankan Profit/Modal!"
    
    return None # Tidak kirim jika sinyalnya HOLD/Netral untuk auto-chat

def auto_scan_job(context: CallbackContext):
    """Fungsi yang dijalankan otomatis setiap 5 menit."""
    global USER_CHAT_ID
    if USER_CHAT_ID and is_market_open():
        results = []
        for sym in watchlist:
            try:
                df = yf.download(sym, period="3mo", interval="1d", progress=False)
                if df.empty: continue
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                
                res = analyze_symbol(sym, df)
                if res: results.append(res)
            except: continue
        
        if results:
            context.bot.send_message(
                chat_id=USER_CHAT_ID, 
                text="🔔 <b>AUTO-SIGNAL UPDATE (Setiap 5 Menit)</b>\n\n" + "\n\n".join(results),
                parse_mode='HTML'
            )

def start(update: Update, context: CallbackContext):
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id # Simpan ID chat kamu
    update.message.reply_text(
        "🚀 <b>SwingWatchBit Auto-Pilot Aktif!</b>\n\n"
        "Bot akan otomatis mengirim sinyal setiap 5 menit saat jam bursa (09:00 - 16:00 WIB).\n\n"
        "Perintah manual tetap tersedia:\n/scan - Cek semua sekarang\n/list - Cek watchlist",
        parse_mode='HTML'
    )

def scan(update: Update, context: CallbackContext):
    update.message.reply_text("🔎 Menganalisis pasar secara manual...")
    # (Logika scan manual sama seperti sebelumnya, kirim semua status BUY/SELL/HOLD)
    # ... (untuk ringkasnya, gunakan logika scan dari kode sebelumnya di sini)

def add_stock(update: Update, context: CallbackContext):
    if not context.args: return
    code = context.args[0].upper()
    if ".JK" not in code: code += ".JK"
    if code not in watchlist: watchlist.append(code)
    update.message.reply_text(f"✅ {code} ditambahkan!")

if __name__ == '__main__':
    updater = Updater(TOKEN)
    dp = updater.dispatcher
    
    # Register Commands
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("scan", scan))
    dp.add_handler(CommandHandler("add", add_stock))
    
    # Setup Scheduler untuk Auto-Scan setiap 5 menit
    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(auto_scan_job, 'interval', minutes=5, args=[updater])
    scheduler.start()
    
    print("Bot Auto-Pilot Berjalan...")
    updater.start_polling(drop_pending_updates=True)
    updater.idle()
