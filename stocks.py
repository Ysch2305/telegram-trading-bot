import yfinance as yf
import pandas as pd

def get_stock_data(symbol):

    data = yf.download(symbol, period="6mo", interval="1d")

    return data
