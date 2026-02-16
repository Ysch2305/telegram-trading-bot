import os
import yfinance as yf
import pandas as pd
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

# Ambil Token dari Environment Variable Railway
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Daftar saham awal (Default)
watchlist = ["BUMI.JK", "BBCA.JK", "BUVA.JK", "BBRI.JK", "BMRI.JK", "ANTM.JK"]

def analyze_symbol(sym, df):
    # Pastikan data cukup untuk menghitung EMA 50
    if len(df) < 50:
        return "DATA KURANG", "Data historis tidak cukup untuk analisis (min. 50 hari)."
    
    close = df["Close"]
    
    # Hitung EMA 20 dan EMA 50
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    
    # Hitung RSI (14)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = (-delta).clip(lower=0).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1]))
    
    # Penentuan Sinyal dan Alasan
    if ema20 > ema50 and rsi > 55:
        signal = "BUY 🟢"
        reason = f"Tren Bullish (EMA20 > EMA50) & Momentum Kuat (RSI: {rsi:.1f})"
    elif ema20 < ema50 and rsi < 45:
        signal = "SELL 🔴"
        reason = f"Tren Bearish (EMA20 < EMA50) & Momentum Lemah (RSI: {rsi:.1f})"
    else:
        signal = "HOLD 🟡"
        reason = f"Konsolidasi / Sideways (RSI: {rsi:.1f})"
        
    return signal, reason

def scan(update: Update, context: CallbackContext):
    update.message.reply_text("🔎 Sedang menganalisis pasar, mohon tunggu...")
    msgs = []
    
    for sym in watchlist:
        try:
            # Ambil data 3 bulan agar perhitungan EMA akurat
            df = yf.download(sym, period="3mo", interval="1d", progress=False)
            
            if df.empty:
                continue
            
            # Perbaikan untuk versi yfinance terbaru (hapus MultiIndex)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            signal, reason = analyze_symbol(sym, df)
            name = sym.replace('.JK','')
            msgs.append(f"<b>{name}</b>: {signal}\n└ <i>{reason}</i>")
            
        except Exception as e:
            msgs.append(f"❌ {sym}: Gagal dianalisis.")

    # Kirim hasil scan
    update.message.reply_text("\n\n".join(msgs), parse_mode='HTML')

def add_stock(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Cara pakai: /add [KODE]\nContoh: /add TLKM.JK")
        return
    
    new_stock = context.args[0].upper()
    if ".JK" not in new_stock:
        new_stock += ".JK"
        
    if new_stock not in watchlist:
        watchlist.append(new_stock)
        update.message.reply_text(f"✅ {new_stock} ditambahkan ke watchlist!")
    else:
        update.message.reply_text(f"ℹ️ {new_stock} sudah ada di daftar.")

def list_watchlist(update: Update, context: CallbackContext):
    daftar = "\n".join([f"- {s}" for s in watchlist])
    update.message.reply_text(f"📋 Watchlist Saat Ini:\n{daftar}")

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 Bot Saham Aktif!\n\n"
        "Gunakan perintah berikut:\n"
        "/scan - Cek semua sinyal saham\n"
        "/add [KODE] - Tambah saham ke daftar\n"
        "/list - Lihat daftar saham kamu"
    )

if __name__ == '__main__':
    updater = Updater(TOKEN)
    dp = updater.dispatcher

    # Daftarkan Command
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("scan", scan))
    dp.add_handler(CommandHandler("add", add_stock))
    dp.add_handler(CommandHandler("list", list_watchlist))

    # Mulai Bot
    updater.start_polling()
    updater.idle()
