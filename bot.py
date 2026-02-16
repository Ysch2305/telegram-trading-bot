import os
import yfinance as yf
import pandas as pd
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

# Mengambil Token dari environment variable Railway
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Daftar saham awal (Default)
watchlist = ["BUMI.JK", "BBCA.JK", "BUVA.JK", "BBRI.JK", "BMRI.JK", "ANTM.JK"]

def analyze_symbol(sym, df):
    """Fungsi analisis teknikal sederhana."""
    if len(df) < 50:
        return "DATA KURANG", "Butuh minimal 50 hari data."
    
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
    
    # Logika Sinyal
    if ema20 > ema50 and rsi > 55:
        return "BUY 🟢", f"EMA20 > EMA50 | RSI: {rsi:.1f}"
    elif ema20 < ema50 and rsi < 45:
        return "SELL 🔴", f"EMA20 < EMA50 | RSI: {rsi:.1f}"
    else:
        return "HOLD 🟡", f"RSI: {rsi:.1f}"

def start(update: Update, context: CallbackContext):
    """Menu awal bot."""
    update.message.reply_text(
        "👋 <b>Bot SwingWatchBit Aktif!</b>\n\n"
        "Gunakan perintah:\n"
        "/scan - Analisis semua saham\n"
        "/add [KODE] - Tambah saham (ex: /add TLKM.JK)\n"
        "/list - Lihat daftar saham",
        parse_mode='HTML'
    )

def scan(update: Update, context: CallbackContext):
    """Menganalisis saham di watchlist."""
    update.message.reply_text("🔎 Sedang menganalisis pasar...")
    results = []
    
    for sym in watchlist:
        try:
            # Download data
            df = yf.download(sym, period="3mo", interval="1d", progress=False)
            if df.empty: continue
            
            # Bersihkan data MultiIndex
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            status, reason = analyze_symbol(sym, df)
            
            # Format teks sederhana agar tidak error HTML
            clean_sym = sym.replace('.JK','')
            results.append(f"<b>{clean_sym}</b>: {status}\n{reason}")
            
        except Exception as e:
            results.append(f"❌ {sym}: Gagal ambil data")

    if results:
        # Mengirim hasil analisis
        update.message.reply_text("\n\n".join(results), parse_mode='HTML')
    else:
        update.message.reply_text("Watchlist kosong.")

def add_stock(update: Update, context: CallbackContext):
    """Menambah saham ke daftar."""
    if not context.args:
        update.message.reply_text("Contoh: /add TLKM.JK")
        return
    
    code = context.args[0].upper()
    if ".JK" not in code: code += ".JK"
    
    if code not in watchlist:
        watchlist.append(code)
        update.message.reply_text(f"✅ {code} ditambahkan!")
    else:
        update.message.reply_text(f"ℹ️ {code} sudah ada.")

def list_watchlist(update: Update, context: CallbackContext):
    """Melihat isi watchlist."""
    msg = "📋 <b>Watchlist Saham:</b>\n" + "\n".join([f"- {s}" for s in watchlist])
    update.message.reply_text(msg, parse_mode='HTML')

if __name__ == '__main__':
    updater = Updater(TOKEN)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("scan", scan))
    dp.add_handler(CommandHandler("add", add_stock))
    dp.add_handler(CommandHandler("list", list_watchlist))

    print("Bot Berjalan...")
    # drop_pending_updates=True untuk mencegah Conflict
    updater.start_polling(drop_pending_updates=True)
    updater.idle()
