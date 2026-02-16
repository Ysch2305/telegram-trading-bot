import os
import yfinance as yf
import pandas as pd
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import logging

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
watchlist = ["BUMI.JK", "BBCA.JK", "BUVA.JK", "BBRI.JK", "BMRI.JK", "ANTM.JK"]

def analyze_symbol(sym, df):
    if len(df) < 50:
        return None
    
    close = df["Close"]
    volume = df["Volume"]
    
    # 1. Indikator EMA
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    
    # 2. Indikator RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = (-delta).clip(lower=0).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1]))
    
    # 3. Indikator Volume (Cek jika di atas rata-rata 20 hari)
    avg_vol = volume.rolling(window=20).mean().iloc[-1]
    current_vol = volume.iloc[-1]
    vol_status = "Tinggi 📈" if current_vol > avg_vol else "Rendah 📉"
    
    current_price = close.iloc[-1]
    
    # 4. Hitung Target Harga (Sederhana: TP 5%, SL 3%)
    tp_price = current_price * 1.05
    sl_price = current_price * 0.97
    
    # Logika Sinyal
    if ema20 > ema50 and rsi > 55:
        status = "BUY 🟢"
        reason = f"Tren Bullish, Vol: {vol_status}"
        trade_plan = f"🎯 TP: {tp_price:,.0f}\n🛑 SL: {sl_price:,.0f}"
    elif ema20 < ema50 and rsi < 45:
        status = "SELL 🔴"
        reason = f"Tren Bearish, Vol: {vol_status}"
        trade_plan = "⚠️ Segera amankan modal."
    else:
        status = "HOLD 🟡"
        reason = f"Sideways/Bimbang, Vol: {vol_status}"
        trade_plan = "⌛ Tunggu konfirmasi tren."
        
    return {
        "status": status,
        "price": current_price,
        "reason": reason,
        "plan": trade_plan
    }

def scan(update: Update, context: CallbackContext):
    update.message.reply_text("🔎 Menganalisis dengan Volume & Trade Plan...")
    results = []
    
    for sym in watchlist:
        try:
            df = yf.download(sym, period="3mo", interval="1d", progress=False)
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            res = analyze_symbol(sym, df)
            clean_sym = sym.replace('.JK','')
            
            results.append(
                f"<b>{clean_sym}</b> | Rp{res['price']:,.0f}\n"
                f"Sinyal: {res['status']}\n"
                f"Analisa: {res['reason']}\n"
                f"{res['plan']}"
            )
        except:
            results.append(f"❌ {sym}: Gagal")

    if results:
        update.message.reply_text("\n\n".join(results), parse_mode='HTML')

# Fungsi start, add, list tetap sama seperti sebelumnya
def start(update: Update, context: CallbackContext):
    update.message.reply_text("👋 <b>SwingWatchBit Pro Aktif!</b>\n\n/scan - Analisis Lengkap\n/add - Tambah Saham\n/list - Cek Watchlist", parse_mode='HTML')

def add_stock(update: Update, context: CallbackContext):
    if not context.args: return
    code = context.args[0].upper()
    if ".JK" not in code: code += ".JK"
    if code not in watchlist: watchlist.append(code); update.message.reply_text(f"✅ {code} Added")

def list_watchlist(update: Update, context: CallbackContext):
    update.message.reply_text("📋 <b>Watchlist:</b>\n" + "\n".join(watchlist), parse_mode='HTML')

if __name__ == '__main__':
    updater = Updater(TOKEN)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("scan", scan))
    dp.add_handler(CommandHandler("add", add_stock))
    dp.add_handler(CommandHandler("list", list_watchlist))
    updater.start_polling(drop_pending_updates=True)
    updater.idle()
