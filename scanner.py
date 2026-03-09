from stocks import get_stock_data
from indicator import ema, rsi, macd, volume_spike
from strategy import calculate_score, generate_signal


def analyze_stock(symbol):

    try:

        data = get_stock_data(symbol)

        if data is None or data.empty:
            return {
                "symbol": symbol,
                "price": 0,
                "rsi": 0,
                "score": 0,
                "signal": "NO DATA"
            }

        data['EMA20'] = ema(data['Close'], 20)
        data['EMA50'] = ema(data['Close'], 50)
        data['EMA200'] = ema(data['Close'], 200)

        data['RSI'] = rsi(data['Close'])

        macd_line, signal_line, hist = macd(data['Close'])

        data['MACD'] = macd_line
        data['SIGNAL'] = signal_line

        data['VOLUME_SPIKE'] = volume_spike(data['Volume'])

        score = calculate_score(data)

        signal = generate_signal(score)

        price = round(data['Close'].iloc[-1], 2)
        rsi_value = round(data['RSI'].iloc[-1], 2)

        return {
            "symbol": symbol,
            "price": price,
            "rsi": rsi_value,
            "score": score,
            "signal": signal
        }

    except Exception as e:

        return {
            "symbol": symbol,
            "price": 0,
            "rsi": 0,
            "score": 0,
            "signal": "ERROR"
        }
