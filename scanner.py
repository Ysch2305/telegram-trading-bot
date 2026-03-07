import yfinance as yf
from stocks import IDX_STOCKS

def breakout_scan():

    breakout = []

    for stock in IDX_STOCKS:

        try:

            df = yf.download(stock, period="3mo", progress=False)

            if len(df) < 20:
                continue

            high20 = df["High"].rolling(20).max()

            close = df["Close"].iloc[-1]

            if close > high20.iloc[-2]:

                breakout.append(stock)

        except:
            continue

    return breakout
