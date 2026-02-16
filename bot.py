import os
import yfinance as yf
import pandas as pd
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

# Token diambil dari Environment Variable Railway
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Daftar saham awal (Default)
watchlist = ["BUMI.JK", "BBCA.JK", "BUVA.JK", "BBRI.JK", "BMRI.JK", "ANTM.JK"]

def analyze_symbol(sym, df):
    if len(df) < 50:
        return "DATA KURANG", "Butuh minimal 50 hari data historis."
    
    close = df["Close"]
    
    # Indikator EMA 20 & 50
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    
    # Indikator RSI 14
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = (-delta).clip(lower=0).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1]))
    
    # Penentuan Sinyal dan Alasan
    if ema20 > ema50 and rsi > 55:
        return "BUY 🟢", f"Tren Naik (EMA20 > EMA50) & RSI Kuat ({rsi:.1f})"
    elif ema20 < ema50 and rsi < 45:
        return "SELL 🔴", f"Tren Turun (EMA20 < EMA50) & RSI Lemah ({rsi:.1f})"
    else:
        return "HOLD 🟡", f"Pasar Sideways (RSI: {rsi:.1f})"

def scan(update: Update, context: CallbackContext):
    update.message.reply_text("🔎 Sedang menganalisis pasar...")
    msgs = []
    
    for sym in watchlist:
        try:
            df = yf.download(sym, period="3mo", interval="1d", progress=False)
            if df.empty: continue
            
            # Bersihkan MultiIndex (untuk library yfinance versi baru)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            signal, reason = analyze_symbol(sym, df)
            msgs.append(f"<b>{sym.replace('.JK','')}</b>: {signal}\n└ <i>{reason}</i>")
        except:
            msgs.append(f"❌ {sym}: Gagal ambil data")

    update.message.reply_text("\n\n".join(msgs), parse_mode='HTML')

def add_stock(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Format: /add KODE\nContoh: /add TLKM.JK")
        return
    
    new_stock = context.args[0].upper()
    if ".JK" not in new_stock: new_stock += ".JK"
        
    if new_stock not in watchlist:
        watchlist.append(new_stock)
        update.message.reply_text(f"✅ {new_stock} masuk watchlist!")
    else:
        update.message.reply_text(f"ℹ️ {new_stock} sudah ada.")

def list_watchlist(update: Update, context: CallbackContext):
    txt = "\n".join([f"- {s}" for s in watchlist])
    update.message.reply_text(f"📋 Watchlist:\n{txt}")

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 Bot Saham Aktif!\n\n"
        "/scan - Cek sinyal semua saham\n"
        "/add [KODE] - Tambah saham baru\n"
        "/list - Lihat daftar saham"
    )

if __name__ == '__main__':
    updater = Updater(TOKEN)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("scan", scan))
    dp.add_handler(CommandHandler("add", add_stock))
    dp.add_handler(CommandHandler("list", list_watchlist))

    # clean=True membantu menghapus pesan 'nyangkut' saat bot baru nyala
    updater.start_polling(clean=True)
    updater.idle()
