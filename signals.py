import yfinance as yf
import pandas as pd
import ta


def get_signals(symbol: str) -> dict:
    """
    Compute technical signals for a given symbol.
    Returns dict with rsi, macd_signal, momentum_pct, volume_ratio.
    Returns None if data is insufficient.
    """
    data = yf.download(symbol, period="3mo", interval="1d", progress=False)
    if data.empty or len(data) < 30:
        return None

    close = data["Close"].squeeze()
    volume = data["Volume"].squeeze()

    rsi_series = ta.momentum.RSIIndicator(close=close, window=14).rsi()
    rsi = rsi_series.iloc[-1]

    macd = ta.trend.MACD(close=close)
    macd_line = macd.macd().iloc[-1]
    macd_signal_line = macd.macd_signal().iloc[-1]
    macd_hist = macd_line - macd_signal_line

    momentum_pct = (close.iloc[-1] / close.iloc[-20] - 1) * 100 if len(close) >= 20 else 0.0

    vol_avg_20 = volume.iloc[-21:-1].mean()
    volume_ratio = float(volume.iloc[-1]) / float(vol_avg_20) if vol_avg_20 > 0 else 1.0

    return {
        "rsi": float(rsi),
        "macd_hist": float(macd_hist),
        "macd_line": float(macd_line),
        "macd_signal_line": float(macd_signal_line),
        "momentum_pct": float(momentum_pct),
        "volume_ratio": float(volume_ratio),
        "price": float(close.iloc[-1]),
    }
