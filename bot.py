import os
import yfinance as yf
import pandas as pd
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import logging

# Setup Logging agar kita bisa pantau error di Railway
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Ambil Token dari Environment Variable Railway
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Daftar saham awal (Default Watchlist)
watchlist = ["BUMI.JK", "BBCA.JK", "BUVA.JK", "BBRI.JK", "BMRI.JK", "ANTM.JK"]

def analyze_symbol(sym, df):
    """Logika Analisis dengan penjelasan yang mudah dipahami."""
    if len(df) < 50:
        return "DATA KURANG", "Butuh riwayat harga minimal 50 hari."
    
    close = df["Close"]
    
    # Menghitung EMA (Tren Harga)
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    
    # Menghitung RSI (Tenaga Beli)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = (-delta).clip(lower=0).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1]))
    
    # Penentuan Sinyal dan Penjelasan Deskriptif
    if ema20 > ema50 and rsi > 55:
        return "BUY 🟢", "Tren menguat (Bullish) & tenaga beli sangat besar."
    elif ema20 < ema50 and rsi < 45:
        return "SELL 🔴", "Tren melemah (Bearish) & harga cenderung turun."
    else:
        # Penjelasan tambahan untuk kondisi bimbang (Hold)
        if ema20 > ema50:
            return "HOLD 🟡", "Tren naik tapi tenaga beli mulai jenuh/lemah."
        else:
            return "HOLD 🟡", "Pasar sedang bimbang atau bergerak menyamping (Sideways)."

def start(update: Update, context: CallbackContext):
    """Menampilkan pesan sambutan dan daftar perintah."""
    update.message.reply_text(
        "👋 <b>Bot SwingWatchBit Aktif!</b>\n\n"
        "Gunakan perintah berikut:\n"
        "/scan - Cek sinyal semua saham di watchlist\n"
        "/add [KODE] - Tambah saham (contoh: /add TLKM.JK)\n"
        "/list - Lihat daftar saham yang dipantau",
        parse_mode='HTML'
    )

def scan(update: Update, context: CallbackContext):
    """Proses scan semua saham di watchlist."""
    update.message.reply_text("🔎 Sedang menganalisis pasar, mohon tunggu...")
    results = []
    
    for sym in watchlist:
        try:
            # Ambil data 3 bulan terakhir
            df = yf.download(sym, period="3mo", interval="1d", progress=False)
            if df.empty: continue
            
            # Bersihkan format data jika perlu
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            status, reason = analyze_symbol(sym, df)
            clean_sym = sym.replace('.JK','')
            
            results.append(f"<b>{clean_sym}</b>: {status}\n└ <i>{reason}</i>")
        except Exception as e:
            logging.error(f"Gagal scan {sym}: {e}")
            results.append(f"❌ {sym}: Gagal dianalisis")

    if results:
        update.message.reply_text("\n\n".join(results), parse_mode='HTML')
    else:
        update.message.reply_text("Wah, watchlist kamu kosong nih.")

def add_stock(update: Update, context: CallbackContext):
    """Menambah saham baru ke watchlist."""
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
    """Melihat daftar saham yang sedang dipantau."""
    msg = "📋 <b>Watchlist Saham Anda:</b>\n\n" + "\n".join([f"- {s}" for s in watchlist])
    update.message.reply_text(msg, parse_mode='HTML')

if __name__ == '__main__':
    if not TOKEN:
        print("Error: Variabel TELEGRAM_BOT_TOKEN tidak ditemukan di Railway!")
    else:
        updater = Updater(TOKEN)
        dp = updater.dispatcher

        # MENDAFTARKAN PERINTAH AGAR BISA DIGUNAKAN
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("scan", scan))
        dp.add_handler(CommandHandler("add", add_stock))
        dp.add_handler(CommandHandler("list", list_watchlist))

        print("Bot SwingWatchBit sedang berjalan...")
        
        # Mencegah conflict dengan menghapus update yang tertunda
        updater.start_polling(drop_pending_updates=True)
        updater.idle()
