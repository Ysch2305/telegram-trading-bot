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
    """Fungsi untuk menganalisis indikator teknikal saham."""
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
    
    # Logika Penentuan Sinyal
    if ema20 > ema50 and rsi > 55:
        return "BUY 🟢", f"Bullish: EMA20 ({ema20:.0f}) > EMA50 ({ema50:.0f}) & RSI ({rsi:.1f}) Kuat"
    elif ema20 < ema50 and rsi < 45:
        return "SELL 🔴", f"Bearish: EMA20 ({ema20:.0f}) < EMA50 ({ema50:.0f}) & RSI ({rsi:.1f}) Lemah"
    else:
        return "HOLD 🟡", f"Sideways: RSI berada di level {rsi:.1f}"

def start(update: Update, context: CallbackContext):
    """Menampilkan menu bantuan saat bot dimulai."""
    update.message.reply_text(
        "👋 <b>Bot SwingWatchBit Aktif!</b>\n\n"
        "Gunakan perintah berikut:\n"
        "/scan - Analisis semua saham di watchlist\n"
        "/add [KODE] - Tambah saham (contoh: /add TLKM.JK)\n"
        "/list - Lihat daftar saham yang dipantau",
        parse_mode='HTML'
    )

def scan(update: Update, context: CallbackContext):
    """Menganalisis semua saham yang ada di daftar watchlist."""
    update.message.reply_text("🔎 Sedang menganalisis pasar, mohon tunggu...")
    results = []
    
    for sym in watchlist:
        try:
            # Download data historis 3 bulan
            df = yf.download(sym, period="3mo", interval="1d", progress=False)
            if df.empty: continue
            
            # Membersihkan MultiIndex jika ada (untuk library yfinance terbaru)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            status, reason = analyze_symbol(sym, df)
            results.append(f"<b>{sym.replace('.JK','')}</b>: {status}\n└ <i>{reason}</i>")
        except Exception as e:
            results.append(f"❌ {sym}: Gagal dianalisis")

    update.message.reply_text("\n\n".join(results), parse_mode='HTML')

def add_stock(update: Update, context: CallbackContext):
    """Menambah saham baru ke dalam daftar sementara."""
    if not context.args:
        update.message.reply_text("Format salah! Gunakan: /add KODE.JK\nContoh: /add ASII.JK")
        return
    
    code = context.args[0].upper()
    if ".JK" not in code: code += ".JK"
    
    if code not in watchlist:
        watchlist.append(code)
        update.message.reply_text(f"✅ <b>{code}</b> berhasil ditambahkan ke watchlist!")
    else:
        update.message.reply_text(f"ℹ️ {code} sudah ada di daftar.")

def list_watchlist(update: Update, context: CallbackContext):
    """Menampilkan daftar saham yang sedang dipantau."""
    msg = "📋 <b>Watchlist Saham Anda:</b>\n" + "\n".join([f"- {s}" for s in watchlist])
    update.message.reply_text(msg, parse_mode='HTML')

if __name__ == '__main__':
    # Inisialisasi Updater
    updater = Updater(TOKEN)
    dp = updater.dispatcher

    # Daftarkan Command
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("scan", scan))
    dp.add_handler(CommandHandler("add", add_stock))
    dp.add_handler(CommandHandler("list", list_watchlist))

    print("Bot sedang berjalan...")
    
    # drop_pending_updates=True mencegah bot memproses pesan lama yang menumpuk
    # Ini adalah solusi untuk mencegah error Conflict
    updater.start_polling(drop_pending_updates=True)
    updater.idle()
