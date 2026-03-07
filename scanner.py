import yfinance as yf
import pandas as pd
from stocks import stocks

def scan_market():

    results = []

    for symbol in stocks:

        try:

            df = yf.download(symbol, period="3mo", interval="1d")

            if len(df) < 30:
                continue

            df["MA20"] = df["Close"].rolling(20).mean()
            df["MA50"] = df["Close"].rolling(50).mean()

            volume_today = df["Volume"].iloc[-1]
            volume_avg = df["Volume"].rolling(20).mean().iloc[-1]

            close = df["Close"].iloc[-1]
            ma20 = df["MA20"].iloc[-1]
            ma50 = df["MA50"].iloc[-1]

            volume_spike = volume_today > volume_avg * 2
            breakout = close > df["High"].rolling(20).max().iloc[-2]

            score = 0

            if close > ma20:
                score += 1

            if close > ma50:
                score += 1

            if volume_spike:
                score += 2

            if breakout:
                score += 3

            if score >= 3:

                results.append({
                    "symbol": symbol,
                    "price": round(close,2),
                    "score": score,
                    "volume_spike": volume_spike,
                    "breakout": breakout
                })

        except:
            pass

    results = sorted(results, key=lambda x: x["score"], reverse=True)

    return results
