import yfinance as yf
import pandas as pd


def get_regime() -> str:
    """
    Determine market regime based on SPY trend and VIX level.
    Returns: 'bull', 'bear', or 'neutral'
    """
    spy = yf.download("SPY", period="1y", interval="1d", progress=False)
    if spy.empty or len(spy) < 200:
        return "neutral"

    close = spy["Close"].squeeze()
    sma50 = close.rolling(50).mean().iloc[-1]
    sma200 = close.rolling(200).mean().iloc[-1]
    spy_price = close.iloc[-1]

    vix_data = yf.download("^VIX", period="5d", interval="1d", progress=False)
    vix = vix_data["Close"].squeeze().iloc[-1] if not vix_data.empty else 20.0

    bull_trend = spy_price > sma50 > sma200
    bear_trend = spy_price < sma50 < sma200

    if vix > 30:
        if bull_trend:
            return "neutral"
        return "bear"

    if vix < 15:
        if bear_trend:
            return "neutral"
        if bull_trend:
            return "bull"

    if bull_trend:
        return "bull"
    if bear_trend:
        return "bear"
    return "neutral"
