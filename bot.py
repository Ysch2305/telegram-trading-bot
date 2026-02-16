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
USER_CHAT_ID = None # Akan terisi otomatis saat Anda klik /start

# Daftar saham awal
watchlist = ["BUMI.JK", "BBCA.JK", "BUVA.JK", "BBRI.JK", "BMRI.JK", "ANTM.JK"]

def is_market_open():
    """Mengecek apakah saat ini jam buka Bursa Efek Indonesia (BEI) 09:00 - 16:00 WIB."""
    tz_jakarta = pytz.timezone('Asia/Jakarta')
    now = datetime.now(tz_jakarta)
    day_of_week = now.weekday() # Senin=0, Minggu=6
    current_time = now.time()
    
    start_time = datetime.strptime("09:00", "%H:%M").time()
    end_time = datetime.strptime("16:00", "%H:%M").time()
    
    if day_of_week < 5 and (start_time <= current_time <= end_time):
        return True
    return False

def analyze_symbol(sym, df):
    """Analisis teknikal lengkap."""
    if len(df) < 50: return None
    
    close = df["Close"]
    volume = df["Volume"]
    current_price = close.iloc[-1]
    
    # Indikator EMA & RSI
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = (-delta).clip(lower=0).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1]))
    
    avg_vol = volume.rolling(window=20).mean().iloc[-1]
    vol_status = "Tinggi 📈" if volume.iloc[-1] > avg_vol else "Rendah 📉"
    
    tp = current_price * 1.05
    sl = current_price * 0.97
    
    clean_name = sym.replace('.JK','')
    
    if ema20 > ema50 and rsi > 55:
        return {
            "status": "BUY 🟢",
            "msg": f"<b>{clean_name}</b> | Rp{current_price:,.0f}\nSinyal: BUY 🟢\nAnalisa: Bullish, Vol {vol_status}\n🎯 TP: {tp:,.0f} | 🛑 SL: {sl:,.0f}"
        }
    elif ema20 < ema50 and rsi < 45:
        return {
            "status": "SELL 🔴",
            "msg": f"<b>{clean_name}</b> | Rp{current_price:,.0f}\nSinyal: SELL 🔴\nAnalisa: Bearish, Vol {vol_status}\n⚠️ Amankan modal!"
        }
    else:
        return {
            "status": "HOLD 🟡",
            "msg": f"<b>{clean_name}</b> | Rp{current_price:,.0f}\nSinyal: HOLD 🟡\nAnalisa: Sideways, Vol {vol_status}"
        }

def auto_scan_job(context: CallbackContext):
    """Fungsi otomatis setiap 5 menit (hanya kirim BUY/SELL)."""
    global USER_CHAT_ID
    if USER_CHAT_ID and is_market_open():
        results = []
        for sym in watchlist:
            try:
                df = yf.download(sym, period="3mo", interval="1d", progress=False)
                if df.empty: continue
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                
                res = analyze_symbol(sym, df)
                if res and (res["status"] == "BUY 🟢" or res["status"] == "SELL 🔴"):
                    results.append(res["msg"])
            except: continue
        
        if results:
            context.bot.send_message(
                chat_id=USER_CHAT_ID, 
                text="🔔 <b>AUTO-SIGNAL UPDATE</b>\n\n" + "\n\n".join(results),
                parse_mode='HTML'
            )

def start(update: Update, context: CallbackContext):
    global USER_CHAT_ID
    USER_CHAT_ID = update.message.chat_id
    update.message.reply_text(
        "🚀 <b>SwingWatchBit Pro Aktif!</b>\n\n"
        "Sinyal otomatis dikirim setiap 5 menit saat jam bursa.\n"
        "Gunakan /add KODE.JK untuk menambah saham baru.",
        parse_mode='HTML'
    )

def scan(update: Update, context: CallbackContext):
    """Scan manual menampilkan semua status (BUY/SELL/HOLD)."""
    update.message.reply_text("🔎 Menganalisis pasar secara manual...")
    results = []
    for sym in watchlist:
        try:
            df = yf.download(sym, period="3mo", interval="1d", progress=False)
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            res = analyze_symbol(sym, df)
            if res: results.append(res["msg"])
        except: continue
    
    if results:
        update.message.reply_text("\n\n".join(results), parse_mode='HTML')

def add_stock(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Contoh: /add TLKM.JK")
        return
    code = context.args[0].upper()
    if ".JK" not in code: code += ".JK"
    if code not in watchlist:
        watchlist.append(code)
        update.message.reply_text(f"✅ {code} ditambahkan ke watchlist!")
    else:
        update.message.reply_text(f"ℹ️ {code} sudah ada.")

def list_watchlist(update: Update, context: CallbackContext):
    msg = "📋 <b>Daftar Pantauan Anda:</b>\n\n" + "\n".join([f"- {s}" for s in watchlist])
    update.message.reply_text(msg, parse_mode='HTML')

if __name__ == '__main__':
    if not TOKEN:
        print("Token tidak ditemukan!")
    else:
        updater = Updater(TOKEN)
        dp = updater.dispatcher

        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("scan", scan))
        dp.add_handler(CommandHandler("add", add_stock))
        dp.add_handler(CommandHandler("list", list_watchlist))

        # Scheduler
        scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
        scheduler.add_job(auto_scan_job, 'interval', minutes=5, args=[updater])
        scheduler.start()

        updater.start_polling(drop_pending_updates=True)
        updater.idle()
