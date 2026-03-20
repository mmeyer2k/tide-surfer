import json
import os
from datetime import date, datetime
from config import MIN_HOLD_DAYS

POSITIONS_FILE = "positions.json"


def _load() -> dict:
    if not os.path.exists(POSITIONS_FILE):
        return {}
    with open(POSITIONS_FILE, "r") as f:
        return json.load(f)


def _save(data: dict):
    with open(POSITIONS_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def get_all() -> dict:
    return _load()


def get_position(symbol: str) -> dict | None:
    return _load().get(symbol)


def add_position(
    symbol: str,
    entry_price: float,
    qty: int,
    stop_price: float,
    target_price: float,
):
    data = _load()
    data[symbol] = {
        "symbol": symbol,
        "entry_price": entry_price,
        "entry_date": date.today().isoformat(),
        "qty": qty,
        "stop_price": stop_price,
        "target_price": target_price,
        "trailing_stop_price": None,
    }
    _save(data)


def update_trailing_stop(symbol: str, trailing_stop_price: float):
    data = _load()
    if symbol in data:
        data[symbol]["trailing_stop_price"] = trailing_stop_price
        _save(data)


def remove_position(symbol: str):
    data = _load()
    data.pop(symbol, None)
    _save(data)


def can_exit(symbol: str) -> bool:
    """Returns False if the position has been held for fewer than MIN_HOLD_DAYS calendar days."""
    pos = get_position(symbol)
    if pos is None:
        return True
    entry_date = date.fromisoformat(pos["entry_date"])
    days_held = (date.today() - entry_date).days
    return days_held >= MIN_HOLD_DAYS
