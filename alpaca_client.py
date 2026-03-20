import alpaca_trade_api as tradeapi
import config


_api = None


def get_api():
    global _api
    if _api is None:
        _api = tradeapi.REST(
            config.ALPACA_API_KEY,
            config.ALPACA_SECRET_KEY,
            config.ALPACA_BASE_URL,
            api_version="v2",
        )
    return _api


def get_account():
    return get_api().get_account()


def get_positions():
    return get_api().list_positions()


def get_position(symbol):
    try:
        return get_api().get_position(symbol)
    except Exception:
        return None


def submit_market_order(symbol, qty, side):
    return get_api().submit_order(
        symbol=symbol,
        qty=qty,
        side=side,
        type="market",
        time_in_force="day",
    )


def close_position(symbol):
    return get_api().close_position(symbol)
