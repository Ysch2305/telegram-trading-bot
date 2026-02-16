import os
import yfinance as yf
import pandas as pd
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import logging

# Setup Logging sederhana untuk melihat error di Railway Logs
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Daftar saham awal
watchlist = ["BUMI.JK", "BBCA.JK", "BUVA.JK", "BBRI.JK", "BMRI.JK", "ANTM.JK"]

def analyze_symbol(sym, df):
    if len(df) < 50:
        return "DATA KURANG", "Butuh data lebih banyak."
    
    close = df["Close"]
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = (-delta).clip(lower=0).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1]))
    
    if ema20 > ema50 and rsi > 55:
        return "BUY 🟢", f"RSI: {rsi:.1f}"
    elif ema20 < ema50 and rsi < 45:
        return "SELL 🔴", f"RSI: {rsi:.1f}"
    else:
        return "HOLD 🟡", f"RSI: {rsi:.1f}"

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 <b>Bot Aktif!</b>\n\n"
        "/scan - Cek Saham\n"
        "/list - Daftar Saham",
        parse_mode='HTML'
    )

def scan(update: Update, context: CallbackContext):
    update.message.reply_text("🔎 Menganalisis pasar...")
    results = []
    
    for sym in watchlist:
        try:
            df = yf.download(sym, period="3mo", interval="1d", progress=False)
            if df.empty: continue
            
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            status, reason = analyze_symbol(sym, df)
            clean_sym = sym.replace('.JK','')
            
            # Format teks sangat sederhana untuk menghindari error HTML
            results.append(f"<b>{clean_sym}</b>: {status}\n{reason}")
            
        except Exception as e:
            logging.error(f"Error di {sym}: {str(e)}")
            results.append(f"❌ {sym}: Gagal")

    if results:
        # Kirim hasil. Jika error HTML, kirim tanpa format HTML
        try:
            update.message.reply_text("\n\n".join(results), parse_mode='HTML')
        except:
            update.message.reply_text("\n\n".join(results)) 
    else:
        update.message.reply_text("Daftar kosong.")

if __name__ == '__main__':
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN tidak ditemukan!")
    else:
        updater = Updater(TOKEN)
        dp = updater.dispatcher
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("scan", scan))

        print("Bot berjalan...")
        # Kunci utama menghindari Conflict
        updater.start_polling(drop_pending_updates=True)
        updater.idle()
