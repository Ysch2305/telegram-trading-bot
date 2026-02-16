import os
import yfinance as yf
import pandas as pd
import requests
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
# Gunakan list global (akan reset jika bot restart di Railway)
# Untuk permanen, idealnya menggunakan Database seperti Supabase/PostgreSQL
current_watchlist = ["BUMI.JK", "BBCA.JK", "BBRI.JK", "ANTM.JK"]

def analyze_symbol(sym, df):
    if len(df) < 50:
        return "Data Tidak Cukup", "Butuh minimal 50 hari data."
    
    close = df["Close"]
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    
    # RSI Calculation
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1]))
    
    # Logika Sinyal & Alasan
    if ema20 > ema50 and rsi > 55:
        reason = f"Tren naik (EMA20 > EMA50) & Momentum kuat (RSI: {rsi:.1f})"
        return "BUY 🟢", reason
    elif ema20 < ema50 and rsi < 45:
        reason = f"Tren turun (EMA20 < EMA50) & Momentum lemah (RSI: {rsi:.1f})"
        return "SELL 🔴", reason
    else:
        reason = f"Konsolidasi / Sideways (RSI: {rsi:.1f})"
        return "HOLD 🟡", reason

def scan(update: Update, context: CallbackContext):
    update.message.reply_text("Sedang memproses data, mohon tunggu...")
    msgs = []
    for sym in current_watchlist:
        try:
            df = yf.download(sym, period="3mo", interval="1d", progress=False)
            if df.empty: continue
            
            signal, reason = analyze_symbol(sym, df)
            name = sym.replace('.JK','')
            msgs.append(f"<b>{name}</b>: {signal}\n└ <i>{reason}</i>")
        except Exception as e:
            msgs.append(f"{sym}: Error ambil data")

    update.message.reply_text("\n\n".join(msgs), parse_mode='HTML')

def add_watchlist(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Contoh cara pakai: /add ASII.JK")
        return
    
    new_stock = context.args[0].upper()
    if ".JK" not in new_stock:
        new_stock += ".JK"
        
    if new_stock not in current_watchlist:
        current_watchlist.append(new_stock)
        update.message.reply_text(f"✅ {new_stock} berhasil ditambah ke watchlist!")
    else:
        update.message.reply_text(f"ℹ️ {new_stock} sudah ada di daftar.")

def show_list(update: Update, context: CallbackContext):
    pilihan = "\n".join([f"- {s}" for s in current_watchlist])
    update.message.reply_text(f"Daftar Pantau Saat Ini:\n{pilihan}")

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Bot Saham Aktif!\n\n"
        "Commands:\n"
        "/scan - Analisis semua watchlist\n"
        "/add [KODE] - Tambah saham (contoh: /add TLKM.JK)\n"
        "/list - Lihat daftar saham"
    )

updater = Updater(TOKEN)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("scan", scan))
dp.add_handler(CommandHandler("add", add_watchlist))
dp.add_handler(CommandHandler("list", show_list))

updater.start_polling()
updater.idle()
