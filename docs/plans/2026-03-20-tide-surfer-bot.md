# Tide-Surfer Swing Trading Bot — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python swing trading bot for Alpaca that swing trades equities and leveraged ETFs, targeting ~1% daily gains while enforcing a 2-day minimum hold to avoid PDT rules.

**Architecture:** 8 modules with clear separation of concerns: config → regime detection → sector analysis → signal generation → position tracking → trade execution → Alpaca API wrapper → orchestration entry point. Historical data comes from yfinance (free); live orders go through Alpaca REST API.

**Tech Stack:** Python 3.10+, alpaca-trade-api, yfinance, pandas, numpy, ta (technical analysis), JSON flat-file for position persistence.

---

### Task 1: Project scaffold — requirements.txt and config.py

**Files:**
- Create: `requirements.txt`
- Create: `config.py`

**Step 1: Create requirements.txt**

```
alpaca-trade-api>=3.0.0
yfinance>=0.2.0
pandas>=2.0.0
numpy>=1.24.0
ta>=0.11.0
```

**Step 2: Create config.py**

```python
"""
config.py — All settings, API keys (from env vars), and ticker universe.
"""

import os

# ---------------------------------------------------------------------------
# Alpaca credentials (set via environment variables)
# ---------------------------------------------------------------------------
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

# ---------------------------------------------------------------------------
# Trading parameters
# ---------------------------------------------------------------------------
MAX_POSITIONS = 3               # Maximum concurrent open positions
POSITION_SIZE_PCT = 0.30        # Fraction of available cash per position
MIN_HOLD_DAYS = 2               # Minimum calendar days before selling (PDT)

PROFIT_TARGET_PCT = 0.08        # +8% → take profit
STOP_LOSS_PCT = -0.05           # -5% → stop out
TRAIL_TRIGGER_PCT = 0.04        # +4% gain triggers trailing stop
TRAIL_PCT = 0.03                # Trail distance (3%) once triggered

RSI_OVERBOUGHT = 70             # Don't buy bull ETF if RSI ≥ this
RSI_OVERSOLD = 30               # Don't buy bear ETF if RSI ≤ this

VIX_HIGH = 30                   # VIX above this → increase bear bias
VIX_LOW = 15                    # VIX below this → increase bull bias

MOMENTUM_PERIOD = 20            # Days for sector momentum calculation
RSI_PERIOD = 14
SMA_SHORT = 50
SMA_LONG = 200

# ---------------------------------------------------------------------------
# ETF Universe
# ---------------------------------------------------------------------------

# Broad market
BROAD_BULL_ETFS = ["SPY", "QQQ", "IWM", "TQQQ", "UPRO", "SSO", "QLD"]
BROAD_BEAR_ETFS = ["SH", "PSQ", "SQQQ", "SPXU", "SDS"]

# Sector bull ETFs keyed by sector label
SECTOR_BULL_ETFS: dict[str, list[str]] = {
    "tech":          ["XLK", "TECL", "SOXL"],
    "energy":        ["XLE", "ERX", "GUSH"],
    "financials":    ["XLF", "FAS"],
    "healthcare":    ["XLV", "CURE", "LABU"],
    "industrials":   ["XLI", "DFEN"],
    "consumer_disc": ["XLY"],
    "comms":         ["XLC"],
    "fang":          ["FNGU"],
}

# Sector bear ETFs keyed by sector label (fallback to broad bears if missing)
SECTOR_BEAR_ETFS: dict[str, list[str]] = {
    "tech":          ["TECS", "SOXS"],
    "energy":        ["ERY", "DRIP"],
    "financials":    ["FAZ"],
    "healthcare":    ["LABD"],
}

# Canonical single ETF per sector used for momentum / RSI scoring
SECTOR_PROXY_ETFS: dict[str, str] = {
    "tech":          "XLK",
    "energy":        "XLE",
    "financials":    "XLF",
    "healthcare":    "XLV",
    "industrials":   "XLI",
    "consumer_disc": "XLY",
    "comms":         "XLC",
    "fang":          "FNGU",
}

# VIX ticker
VIX_TICKER = "^VIX"
SPY_TICKER = "SPY"

# Positions persistence file
POSITIONS_FILE = "positions.json"
```

**Step 3: Verify the file parses cleanly**

```bash
python -c "import config; print('config OK')"
```

Expected: `config OK`

**Step 4: Commit**

```bash
git add requirements.txt config.py
git commit -m "feat: scaffold project with requirements and config"
```

---

### Task 2: alpaca_client.py — Alpaca REST API wrapper

**Files:**
- Create: `alpaca_client.py`

**Step 1: Create alpaca_client.py**

```python
"""
alpaca_client.py — Thin wrapper around the Alpaca REST API.

Handles authentication and exposes the methods the rest of the bot needs:
  - get_account()         → account dict
  - get_positions()       → list of position dicts
  - get_position(symbol)  → single position dict or None
  - submit_order(...)     → order dict
  - close_position(symbol)→ order dict
  - get_clock()           → clock dict (is_open, next_open, next_close)
"""

import logging
from typing import Optional

import alpaca_trade_api as tradeapi

import config

logger = logging.getLogger(__name__)


def _make_client() -> tradeapi.REST:
    return tradeapi.REST(
        key_id=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
        base_url=config.ALPACA_BASE_URL,
    )


class AlpacaClient:
    def __init__(self):
        self._api = _make_client()

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------
    def get_account(self) -> dict:
        acct = self._api.get_account()
        return {
            "cash": float(acct.cash),
            "portfolio_value": float(acct.portfolio_value),
            "buying_power": float(acct.buying_power),
            "equity": float(acct.equity),
            "status": acct.status,
        }

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------
    def get_positions(self) -> list[dict]:
        positions = self._api.list_positions()
        return [self._pos_to_dict(p) for p in positions]

    def get_position(self, symbol: str) -> Optional[dict]:
        try:
            p = self._api.get_position(symbol)
            return self._pos_to_dict(p)
        except Exception:
            return None

    @staticmethod
    def _pos_to_dict(p) -> dict:
        return {
            "symbol": p.symbol,
            "qty": float(p.qty),
            "avg_entry_price": float(p.avg_entry_price),
            "current_price": float(p.current_price),
            "market_value": float(p.market_value),
            "unrealized_pl": float(p.unrealized_pl),
            "unrealized_plpc": float(p.unrealized_plpc),
        }

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    def submit_market_order(
        self,
        symbol: str,
        qty: float,
        side: str,  # "buy" or "sell"
        time_in_force: str = "day",
    ) -> dict:
        order = self._api.submit_order(
            symbol=symbol,
            qty=int(qty),
            side=side,
            type="market",
            time_in_force=time_in_force,
        )
        logger.info("Order submitted: %s %s x%s → id=%s", side, symbol, qty, order.id)
        return {
            "id": order.id,
            "symbol": order.symbol,
            "qty": float(order.qty),
            "side": order.side,
            "status": order.status,
        }

    def close_position(self, symbol: str) -> dict:
        order = self._api.close_position(symbol)
        logger.info("Closed position: %s → order id=%s", symbol, order.id)
        return {
            "id": order.id,
            "symbol": order.symbol,
            "side": order.side,
            "status": order.status,
        }

    # ------------------------------------------------------------------
    # Market clock
    # ------------------------------------------------------------------
    def get_clock(self) -> dict:
        clock = self._api.get_clock()
        return {
            "is_open": clock.is_open,
            "next_open": str(clock.next_open),
            "next_close": str(clock.next_close),
        }
```

**Step 2: Verify syntax**

```bash
python -c "from alpaca_client import AlpacaClient; print('alpaca_client OK')"
```

Expected: `alpaca_client OK`

**Step 3: Commit**

```bash
git add alpaca_client.py
git commit -m "feat: add Alpaca REST API wrapper"
```

---

### Task 3: regime.py — Market regime detection

**Files:**
- Create: `regime.py`

**Step 1: Create regime.py**

```python
"""
regime.py — Detect broad market regime: BULL, BEAR, or NEUTRAL.

Uses SPY price vs 50-day and 200-day SMAs plus VIX level as a bias factor.
"""

import logging
from enum import Enum

import numpy as np
import pandas as pd
import yfinance as yf

import config

logger = logging.getLogger(__name__)


class Regime(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    NEUTRAL = "NEUTRAL"


def _fetch(ticker: str, period: str = "1y") -> pd.DataFrame:
    df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No data for {ticker}")
    return df


def detect_regime() -> Regime:
    """
    Returns the current market regime based on SPY SMAs and VIX.

    Logic:
      - BULL:    SPY > SMA50 > SMA200 (golden cross zone)
      - BEAR:    SPY < SMA50 < SMA200 (death cross zone)
      - NEUTRAL: mixed signals
    VIX bias: VIX > 30 → tilt NEUTRAL → BEAR; VIX < 15 → tilt NEUTRAL → BULL
    """
    spy_df = _fetch(config.SPY_TICKER)
    close = spy_df["Close"].squeeze()

    sma50 = float(close.rolling(config.SMA_SHORT).mean().iloc[-1])
    sma200 = float(close.rolling(config.SMA_LONG).mean().iloc[-1])
    price = float(close.iloc[-1])

    # VIX
    try:
        vix_df = _fetch(config.VIX_TICKER, period="5d")
        vix = float(vix_df["Close"].squeeze().iloc[-1])
    except Exception:
        vix = 20.0  # Assume neutral if VIX unavailable

    logger.info(
        "SPY=%.2f  SMA50=%.2f  SMA200=%.2f  VIX=%.1f", price, sma50, sma200, vix
    )

    # Primary regime
    if price > sma50 and sma50 > sma200:
        regime = Regime.BULL
    elif price < sma50 and sma50 < sma200:
        regime = Regime.BEAR
    else:
        regime = Regime.NEUTRAL

    # VIX bias override for NEUTRAL
    if regime == Regime.NEUTRAL:
        if vix > config.VIX_HIGH:
            regime = Regime.BEAR
            logger.info("VIX=%.1f > %d → NEUTRAL overridden to BEAR 🐻", vix, config.VIX_HIGH)
        elif vix < config.VIX_LOW:
            regime = Regime.BULL
            logger.info("VIX=%.1f < %d → NEUTRAL overridden to BULL 🌊", vix, config.VIX_LOW)

    emoji = "🌊" if regime == Regime.BULL else ("🐻" if regime == Regime.BEAR else "➡️")
    logger.info("Regime detected: %s %s", emoji, regime.value)
    return regime
```

**Step 2: Verify syntax**

```bash
python -c "from regime import detect_regime, Regime; print('regime OK')"
```

Expected: `regime OK`

**Step 3: Commit**

```bash
git add regime.py
git commit -m "feat: add market regime detection (SPY SMA + VIX)"
```

---

### Task 4: signals.py — Technical analysis helpers

**Files:**
- Create: `signals.py`

**Step 1: Create signals.py**

```python
"""
signals.py — Technical indicator helpers using the `ta` library and pandas.

Functions:
  - get_ohlcv(ticker, period)  → DataFrame with OHLCV + indicators
  - compute_rsi(close, period) → float
  - compute_macd_signal(close) → bool  (True = bullish crossover)
  - compute_volume_trend(df)   → float (ratio vs 20-day avg)
  - compute_momentum(close, period) → float (% change)
"""

import logging
from typing import Optional

import pandas as pd
import yfinance as yf
import ta

import config

logger = logging.getLogger(__name__)


def get_ohlcv(ticker: str, period: str = "6mo") -> pd.DataFrame:
    """Download OHLCV data for ticker. Returns empty DataFrame on failure."""
    try:
        df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
        if df.empty:
            logger.warning("No OHLCV data for %s", ticker)
        return df
    except Exception as exc:
        logger.error("Failed to fetch %s: %s", ticker, exc)
        return pd.DataFrame()


def compute_rsi(close: pd.Series, period: int = config.RSI_PERIOD) -> Optional[float]:
    """Return most recent RSI value, or None if insufficient data."""
    if len(close) < period + 1:
        return None
    rsi_series = ta.momentum.RSIIndicator(close=close, window=period).rsi()
    val = rsi_series.iloc[-1]
    return float(val) if not pd.isna(val) else None


def compute_macd_bullish(close: pd.Series) -> bool:
    """
    Returns True if MACD line is above signal line (bullish momentum).
    Uses default MACD params (12, 26, 9).
    """
    if len(close) < 35:
        return False
    macd_ind = ta.trend.MACD(close=close)
    macd_line = macd_ind.macd().iloc[-1]
    signal_line = macd_ind.macd_signal().iloc[-1]
    if pd.isna(macd_line) or pd.isna(signal_line):
        return False
    return float(macd_line) > float(signal_line)


def compute_volume_trend(df: pd.DataFrame, period: int = 20) -> float:
    """
    Return ratio of most recent volume vs 20-day average.
    > 1.0 means above average volume.
    """
    if df.empty or "Volume" not in df.columns or len(df) < period:
        return 1.0
    vol = df["Volume"].squeeze()
    avg = float(vol.rolling(period).mean().iloc[-1])
    recent = float(vol.iloc[-1])
    if avg == 0:
        return 1.0
    return recent / avg


def compute_momentum(close: pd.Series, period: int = config.MOMENTUM_PERIOD) -> float:
    """
    Return % price change over `period` days.
    Positive = upward momentum, negative = downward.
    """
    if len(close) < period + 1:
        return 0.0
    past = float(close.iloc[-(period + 1)])
    current = float(close.iloc[-1])
    if past == 0:
        return 0.0
    return (current - past) / past * 100.0
```

**Step 2: Verify syntax**

```bash
python -c "from signals import get_ohlcv, compute_rsi; print('signals OK')"
```

Expected: `signals OK`

**Step 3: Commit**

```bash
git add signals.py
git commit -m "feat: add technical indicator helpers (RSI, MACD, momentum, volume)"
```

---

### Task 5: sectors.py — Sector momentum and rotation analysis

**Files:**
- Create: `sectors.py`

**Step 1: Create sectors.py**

```python
"""
sectors.py — Sector momentum and rotation analysis.

Scores each sector by:
  - 20-day price momentum (%)
  - RSI(14) on the sector proxy ETF
  - Volume trend vs 20-day average

Exposes:
  - rank_sectors()              → list of (sector, score) sorted descending
  - best_bull_etf(sector)       → ticker string
  - best_bear_etf(sector)       → ticker string
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import config
from signals import get_ohlcv, compute_rsi, compute_momentum, compute_volume_trend

logger = logging.getLogger(__name__)


@dataclass
class SectorScore:
    sector: str
    proxy: str
    momentum: float = 0.0
    rsi: Optional[float] = None
    volume_trend: float = 1.0
    score: float = 0.0


def _score_sector(sector: str) -> SectorScore:
    proxy = config.SECTOR_PROXY_ETFS[sector]
    df = get_ohlcv(proxy)

    ss = SectorScore(sector=sector, proxy=proxy)

    if df.empty:
        logger.warning("No data for sector proxy %s (%s)", proxy, sector)
        return ss

    close = df["Close"].squeeze()
    ss.momentum = compute_momentum(close)
    ss.rsi = compute_rsi(close)
    ss.volume_trend = compute_volume_trend(df)

    # Composite score: weight momentum heavily, add bonus for above-avg volume
    rsi_factor = 1.0
    if ss.rsi is not None:
        # Penalise if overbought (>70) or oversold (<30) extremes
        if ss.rsi > 70:
            rsi_factor = 0.7
        elif ss.rsi < 30:
            rsi_factor = 0.7

    ss.score = ss.momentum * rsi_factor * (1.0 + (ss.volume_trend - 1.0) * 0.2)
    logger.debug(
        "%-14s  proxy=%-6s  mom=%.2f%%  rsi=%.1f  vol=%.2fx  score=%.2f",
        sector, proxy,
        ss.momentum,
        ss.rsi if ss.rsi is not None else -1,
        ss.volume_trend,
        ss.score,
    )
    return ss


def rank_sectors() -> list[SectorScore]:
    """Return all sectors sorted by composite score descending (best first)."""
    scores = [_score_sector(s) for s in config.SECTOR_PROXY_ETFS]
    scores.sort(key=lambda x: x.score, reverse=True)

    logger.info("Sector ranking:")
    for i, s in enumerate(scores, 1):
        logger.info("  %d. %-14s score=%.2f  mom=%.2f%%  rsi=%s",
                    i, s.sector, s.score, s.momentum,
                    f"{s.rsi:.1f}" if s.rsi else "N/A")
    return scores


def best_bull_etf(sector: str) -> str:
    """Return the first (most liquid / least leveraged) bull ETF for the sector."""
    etfs = config.SECTOR_BULL_ETFS.get(sector, config.BROAD_BULL_ETFS)
    return etfs[0]


def best_bear_etf(sector: str) -> str:
    """Return the first bear ETF for the sector, fallback to broad bear."""
    etfs = config.SECTOR_BEAR_ETFS.get(sector, config.BROAD_BEAR_ETFS)
    return etfs[0]
```

**Step 2: Verify syntax**

```bash
python -c "from sectors import rank_sectors; print('sectors OK')"
```

Expected: `sectors OK`

**Step 3: Commit**

```bash
git add sectors.py
git commit -m "feat: add sector momentum scoring and rotation analysis"
```

---

### Task 6: positions.py — Position tracking and hold-time enforcement

**Files:**
- Create: `positions.py`

**Step 1: Create positions.py**

```python
"""
positions.py — Load / save / manage open positions from positions.json.

Each position record:
{
  "symbol":       "TQQQ",
  "entry_price":  45.20,
  "entry_date":   "2026-03-18",   # ISO date string
  "quantity":     100,
  "stop_price":   42.94,          # initial stop; updated by trailing stop logic
  "target_price": 48.82,
  "trailing_stop_active": false,
  "trail_price":  null            # set once trailing stop is triggered
}
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)

POSITIONS_FILE = Path(config.POSITIONS_FILE)


def load_positions() -> list[dict]:
    if not POSITIONS_FILE.exists():
        return []
    try:
        with open(POSITIONS_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load positions: %s", exc)
        return []


def save_positions(positions: list[dict]) -> None:
    with open(POSITIONS_FILE, "w") as f:
        json.dump(positions, f, indent=2, default=str)
    logger.debug("Saved %d positions to %s", len(positions), POSITIONS_FILE)


def add_position(
    symbol: str,
    entry_price: float,
    quantity: float,
    stop_price: float,
    target_price: float,
) -> dict:
    positions = load_positions()
    record = {
        "symbol": symbol,
        "entry_price": entry_price,
        "entry_date": date.today().isoformat(),
        "quantity": quantity,
        "stop_price": stop_price,
        "target_price": target_price,
        "trailing_stop_active": False,
        "trail_price": None,
    }
    # Replace if already tracked (re-entry)
    positions = [p for p in positions if p["symbol"] != symbol]
    positions.append(record)
    save_positions(positions)
    logger.info("📌 Position added: %s @ %.2f  qty=%d", symbol, entry_price, quantity)
    return record


def remove_position(symbol: str) -> None:
    positions = load_positions()
    positions = [p for p in positions if p["symbol"] != symbol]
    save_positions(positions)
    logger.info("Removed position record for %s", symbol)


def get_position(symbol: str) -> Optional[dict]:
    return next((p for p in load_positions() if p["symbol"] == symbol), None)


def update_position(updated: dict) -> None:
    """Replace position record for updated['symbol'] in the file."""
    positions = load_positions()
    positions = [p for p in positions if p["symbol"] != updated["symbol"]]
    positions.append(updated)
    save_positions(positions)


def can_sell(symbol: str) -> bool:
    """
    Returns True only if the position has been held for at least MIN_HOLD_DAYS
    calendar days. Returns True if symbol not in local tracking (safety default).
    """
    pos = get_position(symbol)
    if pos is None:
        return True
    entry = date.fromisoformat(pos["entry_date"])
    days_held = (date.today() - entry).days
    if days_held < config.MIN_HOLD_DAYS:
        logger.info(
            "⏳ %s held %d day(s) — minimum is %d. Skipping exit.",
            symbol, days_held, config.MIN_HOLD_DAYS,
        )
        return False
    return True


def update_trailing_stop(symbol: str, current_price: float) -> Optional[float]:
    """
    If gain ≥ TRAIL_TRIGGER_PCT, activate or update trailing stop.
    Returns the new stop price if trailing stop was updated, else None.
    """
    pos = get_position(symbol)
    if pos is None:
        return None

    entry_price = pos["entry_price"]
    gain_pct = (current_price - entry_price) / entry_price

    if gain_pct < config.TRAIL_TRIGGER_PCT:
        return None

    new_trail = current_price * (1.0 - config.TRAIL_PCT)

    if not pos["trailing_stop_active"]:
        pos["trailing_stop_active"] = True
        pos["trail_price"] = new_trail
        logger.info("🔔 Trailing stop ACTIVATED for %s @ %.2f (gain=%.1f%%)", symbol, new_trail, gain_pct * 100)
    else:
        # Only ratchet up
        if pos["trail_price"] is None or new_trail > pos["trail_price"]:
            pos["trail_price"] = new_trail
            logger.info("🔔 Trailing stop updated for %s → %.2f", symbol, new_trail)

    update_position(pos)
    return pos["trail_price"]
```

**Step 2: Verify syntax**

```bash
python -c "from positions import load_positions, can_sell; print('positions OK')"
```

Expected: `positions OK`

**Step 3: Commit**

```bash
git add positions.py
git commit -m "feat: add position persistence and 2-day hold enforcement"
```

---

### Task 7: trader.py — Trade execution and entry/exit logic

**Files:**
- Create: `trader.py`

**Step 1: Create trader.py**

```python
"""
trader.py — Core trade logic: entry, exit, position sizing.

Orchestrates regime → sector → signals → execute in one run() call.
"""

import logging
from typing import Optional

import config
import positions as pos_store
from alpaca_client import AlpacaClient
from regime import Regime, detect_regime
from sectors import rank_sectors, best_bull_etf, best_bear_etf
from signals import get_ohlcv, compute_rsi, compute_macd_bullish

logger = logging.getLogger(__name__)

alpaca = AlpacaClient()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _position_size(available_cash: float) -> float:
    """Dollar amount to allocate per position."""
    return available_cash * config.POSITION_SIZE_PCT


def _calc_stop(entry_price: float) -> float:
    return entry_price * (1.0 + config.STOP_LOSS_PCT)


def _calc_target(entry_price: float) -> float:
    return entry_price * (1.0 + config.PROFIT_TARGET_PCT)


# ---------------------------------------------------------------------------
# Exit logic
# ---------------------------------------------------------------------------

def _check_exits(regime: Regime) -> None:
    """Evaluate exit conditions for all tracked positions."""
    tracked = pos_store.load_positions()
    alpaca_positions = {p["symbol"]: p for p in alpaca.get_positions()}

    for pos in tracked:
        symbol = pos["symbol"]

        if symbol not in alpaca_positions:
            logger.info("Position %s not found on Alpaca — removing from tracking.", symbol)
            pos_store.remove_position(symbol)
            continue

        live = alpaca_positions[symbol]
        current_price = live["current_price"]
        gain_pct = (current_price - pos["entry_price"]) / pos["entry_price"]

        # Update trailing stop
        trail_price = pos_store.update_trailing_stop(symbol, current_price)

        logger.info(
            "%s | price=%.2f | gain=%.1f%% | stop=%.2f | target=%.2f",
            symbol, current_price, gain_pct * 100,
            pos["stop_price"], pos["target_price"],
        )

        if not pos_store.can_sell(symbol):
            continue

        reason: Optional[str] = None

        # Profit target
        if current_price >= pos["target_price"]:
            reason = "profit_target"
            logger.info("💰 Profit target hit for %s (%.1f%%)", symbol, gain_pct * 100)

        # Hard stop loss
        elif current_price <= pos["stop_price"] and not pos.get("trailing_stop_active"):
            reason = "stop_loss"
            logger.info("🛑 Stop loss triggered for %s (%.1f%%)", symbol, gain_pct * 100)

        # Trailing stop
        elif pos.get("trailing_stop_active") and trail_price and current_price <= trail_price:
            reason = "trailing_stop"
            logger.info("🛑 Trailing stop triggered for %s @ %.2f", symbol, current_price)

        # Regime flip
        elif regime == Regime.BEAR and symbol in [
            t for etfs in config.SECTOR_BULL_ETFS.values() for t in etfs
        ] + config.BROAD_BULL_ETFS:
            reason = "regime_flip_to_bear"
            logger.info("🌀 Regime flipped to BEAR — exiting bull position %s", symbol)

        elif regime == Regime.BULL and symbol in [
            t for etfs in config.SECTOR_BEAR_ETFS.values() for t in etfs
        ] + config.BROAD_BEAR_ETFS:
            reason = "regime_flip_to_bull"
            logger.info("🌀 Regime flipped to BULL — exiting bear position %s", symbol)

        if reason:
            try:
                alpaca.close_position(symbol)
                pos_store.remove_position(symbol)
                logger.info("✅ Closed %s | reason=%s | gain=%.1f%%", symbol, reason, gain_pct * 100)
            except Exception as exc:
                logger.error("Failed to close %s: %s", symbol, exc)


# ---------------------------------------------------------------------------
# Entry logic
# ---------------------------------------------------------------------------

def _check_entries(regime: Regime) -> None:
    """Evaluate new entry opportunities."""
    tracked_symbols = {p["symbol"] for p in pos_store.load_positions()}
    open_count = len(tracked_symbols)

    if open_count >= config.MAX_POSITIONS:
        logger.info("Max positions (%d) reached. No new entries.", config.MAX_POSITIONS)
        return

    acct = alpaca.get_account()
    cash = acct["cash"]
    alloc = _position_size(cash)

    if alloc < 100:
        logger.info("Insufficient cash (%.2f) for a new position.", cash)
        return

    # Rank sectors and pick best ETF
    sector_scores = rank_sectors()

    if regime == Regime.BULL:
        best_sector = sector_scores[0].sector
        candidate = best_bull_etf(best_sector)
        is_bull_trade = True
        logger.info("🌊 BULL regime — targeting %s (%s)", candidate, best_sector)
    elif regime == Regime.BEAR:
        worst_sector = sector_scores[-1].sector
        candidate = best_bear_etf(worst_sector)
        is_bull_trade = False
        logger.info("🐻 BEAR regime — targeting %s (short %s)", candidate, worst_sector)
    else:
        # NEUTRAL: stay in best broad bull if RSI not overbought, else skip
        candidate = config.BROAD_BULL_ETFS[0]  # SPY
        is_bull_trade = True
        logger.info("➡️ NEUTRAL regime — conservative entry with %s", candidate)

    if candidate in tracked_symbols:
        logger.info("%s already in portfolio. Skipping.", candidate)
        return

    # Technical confirmation
    df = get_ohlcv(candidate)
    if df.empty:
        logger.warning("No data for %s — skipping entry.", candidate)
        return

    close = df["Close"].squeeze()
    rsi = compute_rsi(close)
    macd_bull = compute_macd_bullish(close)
    price = float(close.iloc[-1])

    logger.info("🏄 Entry check: %s | RSI=%.1f | MACD_bull=%s | price=%.2f",
                candidate, rsi if rsi else 0, macd_bull, price)

    # RSI gate
    if is_bull_trade and rsi is not None and rsi >= config.RSI_OVERBOUGHT:
        logger.info("RSI overbought (%.1f) — skipping bull entry for %s.", rsi, candidate)
        return
    if not is_bull_trade and rsi is not None and rsi <= config.RSI_OVERSOLD:
        logger.info("RSI oversold (%.1f) — skipping bear entry for %s.", rsi, candidate)
        return

    # MACD confirmation
    if is_bull_trade and not macd_bull:
        logger.info("MACD not bullish — skipping bull entry for %s.", candidate)
        return
    if not is_bull_trade and macd_bull:
        logger.info("MACD bullish — skipping bear entry for %s.", candidate)
        return

    # Regime NEUTRAL: require MACD (relaxed — already checked above)
    if price <= 0 or alloc <= 0:
        return

    qty = int(alloc // price)
    if qty < 1:
        logger.info("Allocation %.2f too small to buy even 1 share of %s @ %.2f", alloc, candidate, price)
        return

    stop = _calc_stop(price)
    target = _calc_target(price)

    try:
        order = alpaca.submit_market_order(candidate, qty, "buy")
        actual_price = price  # market order; use current as estimate
        pos_store.add_position(
            symbol=candidate,
            entry_price=actual_price,
            quantity=qty,
            stop_price=stop,
            target_price=target,
        )
        logger.info(
            "🏄 ENTRY: %s x%d @ ~%.2f | stop=%.2f | target=%.2f",
            candidate, qty, actual_price, stop, target,
        )
    except Exception as exc:
        logger.error("Order failed for %s: %s", candidate, exc)


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run() -> None:
    """Single trading cycle: detect regime → check exits → check entries."""
    logger.info("=" * 60)
    logger.info("🌊 Tide-Surfer trading cycle started")

    clock = alpaca.get_clock()
    if not clock["is_open"]:
        logger.info("Market is closed. Next open: %s", clock["next_open"])
        return

    regime = detect_regime()

    _check_exits(regime)
    _check_entries(regime)

    logger.info("🌊 Trading cycle complete")
    logger.info("=" * 60)
```

**Step 2: Verify syntax**

```bash
python -c "from trader import run; print('trader OK')"
```

Expected: `trader OK`

**Step 3: Commit**

```bash
git add trader.py
git commit -m "feat: add core trade logic — entry, exit, regime+sector driven"
```

---

### Task 8: main.py — Entry point and orchestration

**Files:**
- Create: `main.py`

**Step 1: Create main.py**

```python
"""
main.py — Entry point for Tide-Surfer swing trading bot.

Usage:
    python main.py

Runs once per invocation. Schedule with cron or a loop for live trading.
"""

import logging
import sys

import config
from trader import run


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Silence noisy third-party loggers
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("peewee").setLevel(logging.WARNING)


def main() -> None:
    setup_logging()
    logger = logging.getLogger("main")

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        logger.error(
            "❌ ALPACA_API_KEY and ALPACA_SECRET_KEY must be set as environment variables."
        )
        sys.exit(1)

    logger.info("🌊 Tide-Surfer starting up")
    logger.info("   API base: %s", config.ALPACA_BASE_URL)
    logger.info("   Max positions: %d", config.MAX_POSITIONS)
    logger.info("   Min hold days: %d", config.MIN_HOLD_DAYS)

    run()


if __name__ == "__main__":
    main()
```

**Step 2: Verify syntax**

```bash
python -c "import main; print('main OK')"
```

Expected: `main OK`

**Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add main entry point with logging setup"
```

---

### Task 9: README.md

**Files:**
- Create: `README.md`

**Step 1: Create README.md**

````markdown
# 🌊 Tide-Surfer

A Python swing trading bot for [Alpaca](https://alpaca.markets) that trades equities and leveraged ETFs.

## Strategy

Tide-Surfer detects the broad market regime (bull / bear / neutral) using SPY's relationship to its 50-day and 200-day moving averages, then picks the strongest sector via 20-day momentum scoring. It enters positions using RSI and MACD confirmation, and exits via profit target, stop loss, or a ratcheting trailing stop — while enforcing a **2-day minimum hold** to comply with FINRA's Pattern Day Trader (PDT) rules.

| Parameter          | Value  |
|--------------------|--------|
| Profit target      | +8%    |
| Hard stop loss     | −5%    |
| Trailing stop trigger | +4%  |
| Trailing distance  | 3%     |
| Minimum hold       | 2 days |
| Max concurrent     | 3 positions |
| Position sizing    | 30% of available cash |

## ETF Universe

### Broad Market

| Direction | Tickers                             |
|-----------|-------------------------------------|
| Bull      | SPY, QQQ, IWM, TQQQ, UPRO, SSO, QLD|
| Bear      | SH, PSQ, SQQQ, SPXU, SDS           |

### Sector ETFs

| Sector       | Bull                   | Bear          |
|--------------|------------------------|---------------|
| Tech         | XLK, TECL, SOXL        | TECS, SOXS    |
| Energy       | XLE, ERX, GUSH         | ERY, DRIP     |
| Financials   | XLF, FAS               | FAZ           |
| Healthcare   | XLV, CURE, LABU        | LABD          |
| Industrials  | XLI, DFEN              | (broad bear)  |
| Consumer Disc| XLY                    | (broad bear)  |
| Comms        | XLC                    | (broad bear)  |
| FANG         | FNGU                   | (broad bear)  |

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set environment variables

```bash
export ALPACA_API_KEY="your_api_key"
export ALPACA_SECRET_KEY="your_secret_key"
# Optional — defaults to paper trading endpoint:
export ALPACA_BASE_URL="https://paper-api.alpaca.markets"
```

### 3. Run the bot

```bash
python main.py
```

The bot runs a single trading cycle and exits. Schedule it with `cron` or a loop script:

```bash
# Example: run every 15 minutes during market hours
*/15 9-16 * * 1-5 cd /path/to/tide-surfer && python main.py
```

## File Structure

```
tide-surfer/
├── config.py          # Settings, API keys, ETF universe
├── regime.py          # Market regime detection (bull/bear/neutral)
├── sectors.py         # Sector momentum scoring
├── signals.py         # RSI, MACD, volume indicators
├── positions.py       # Position persistence and hold-time enforcement
├── trader.py          # Entry/exit logic
├── alpaca_client.py   # Alpaca REST API wrapper
├── main.py            # Entry point
├── positions.json     # Auto-created: tracks open positions
└── requirements.txt
```

## Disclaimer

This software is for educational purposes. Trading leveraged ETFs carries substantial risk. Past performance is not indicative of future results. Always test on a paper trading account before using real money.
````

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup, strategy, and ETF universe table"
```

---

### Task 10: Final verification — import check and event signal

**Step 1: Verify all modules import cleanly**

```bash
python -c "
import config
from alpaca_client import AlpacaClient
from regime import detect_regime, Regime
from signals import get_ohlcv, compute_rsi, compute_macd_bullish
from sectors import rank_sectors, best_bull_etf, best_bear_etf
from positions import load_positions, can_sell
from trader import run
import main
print('✅ All modules import successfully')
"
```

Expected: `✅ All modules import successfully`

**Step 2: Fire the completion event**

```bash
openclaw system event --text "Done: tide-surfer bot built and ready" --mode now
```

**Step 3: Final commit**

```bash
git add -A
git commit -m "chore: final verification — all modules import cleanly"
```
````
