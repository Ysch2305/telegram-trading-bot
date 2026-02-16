import os
import yfinance as yf
import pandas as pd
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Daftar awal (default)
watchlist = ["BUMI.JK", "BBCA.JK", "BUVA.JK", "BBRI.JK", "BMRI.JK", "ANTM.JK"]

def analyze_symbol(sym, df):
    # Minimal butuh data secukupnya untuk indikator
    if len(df) < 50:
        return "DATA KURANG", "Butuh lebih banyak data historis."
    
    close = df["Close"]
    
    # Hitung EMA
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    
    # Hitung RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = (-delta).clip(lower=0).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1]))
    
    # Logika Signal & Alasan
    if ema20 > ema50 and rsi > 55:
        return "BUY 🟢", f"Tren Bullish (EMA20 > EMA50) dan RSI Kuat ({rsi:.1f})"
    elif ema20 < ema50 and rsi < 45:
        return "SELL 🔴", f"Tren Bearish (EMA20 < EMA50) dan RSI Lemah ({rsi:.1f})"
    else:
        return "HOLD 🟡", f"Pasar Sideways / Konsolidasi (RSI: {rsi:.1f})"

def scan(update: Update, context: CallbackContext):
    update.message.reply_text("🔎 Sedang memindai pasar...")
    msgs = []
    
    for sym in watchlist:
        try:
            # Ambil data 3 bulan terakhir agar EMA50 akurat
            df = yf.download(sym, period="3mo", interval="1d", progress=False)
            if df.empty: continue
            
            # Jika kolom MultiIndex (versi yfinance baru), bersihkan
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            signal, reason = analyze_symbol(sym, df)
            msgs.append(f"<b>{sym.replace('.JK','')}</b>: {signal}\n└ <i>{reason}</i>")
        except Exception as e:
            msgs.append(f"❌ {sym}: Gagal ambil data")

    update.message.reply_text("\n\n".join(msgs), parse_mode='HTML')

def add_stock(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Gunakan format: /add KODE_SAHAM\nContoh: /add TLKM.JK")
        return
    
    new_stock = context.args[0].upper()
    if ".JK" not in new_stock:
        new_stock += ".JK"
        
    if new_stock not in watchlist:
        watchlist.append(new_stock)
        update.message.reply_text(f"✅ {new_stock} berhasil ditambah ke watchlist!")
    else:
        update.message.reply_text(f"ℹ️ {new_stock} sudah ada di daftar.")

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 Bot Saham Siap!\n\n"
        "Command:\n"
        "/scan - Analisis semua saham\n"
        "/add [KODE] - Tambah saham ke daftar\n"
        "/list - Lihat daftar saham saat ini"
    )

def list_watchlist(update: Update, context: CallbackContext):
    txt = "\n".join([f"- {s}" for s in watchlist])
    update.message.reply_text(f"📋 Watchlist Kamu:\n{txt}")

# Setup Bot
updater = Updater(TOKEN)
dp = updater.dispatcher

dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("scan", scan))
dp.add_handler(CommandHandler("add", add_stock))
dp.add_handler(CommandHandler("list", list_watchlist))

updater.start_polling()
updater.idle()
