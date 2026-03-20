import os

ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

BULL_ETFS = {
    "broad": ["TQQQ", "UPRO", "SSO", "QLD", "SPY", "QQQ"],
    "tech": ["TECL", "SOXL", "XLK"],
    "energy": ["GUSH", "ERX", "XLE"],
    "financials": ["FAS", "XLF"],
    "healthcare": ["LABU", "CURE", "XLV"],
    "industrials": ["DFEN", "XLI"],
    "consumer_disc": ["XLY"],
    "comms": ["XLC"],
    "fang": ["FNGU"],
}

BEAR_ETFS = {
    "broad": ["SQQQ", "SPXU", "SDS", "SH"],
    "tech": ["TECS", "SOXS"],
    "energy": ["DRIP", "ERY"],
    "financials": ["FAZ"],
    "healthcare": ["LABD"],
}

SECTOR_PROXIES = {
    "tech": "XLK",
    "energy": "XLE",
    "financials": "XLF",
    "healthcare": "XLV",
    "industrials": "XLI",
    "consumer_disc": "XLY",
    "comms": "XLC",
}

MAX_POSITIONS = 3
POSITION_SIZE_PCT = 0.30
PROFIT_TARGET_PCT = 0.08
STOP_LOSS_PCT = 0.05
TRAILING_STOP_ACTIVATE_PCT = 0.04
TRAILING_STOP_TRAIL_PCT = 0.03
MIN_HOLD_DAYS = 2
