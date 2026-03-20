# tide-surfer

A Python swing trading bot for Alpaca that rides sector momentum using leveraged ETFs.

## Overview

Tide-surfer detects the market regime (bull/bear/neutral) using SPY trend analysis and VIX, ranks sectors by momentum, then enters leveraged ETF positions in the strongest (bull) or weakest (bear) sectors. Positions are managed with profit targets, stop losses, and trailing stops, with a minimum hold period to avoid whipsaw exits.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set environment variables

```bash
export ALPACA_API_KEY=your_api_key
export ALPACA_SECRET_KEY=your_secret_key
# Optional: defaults to paper trading
export ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

### 3. Run

```bash
python main.py
```

Logs are written to both stdout and `tide-surfer.log`.

## Strategy Overview

1. **Regime Detection** (`regime.py`): Fetches 1 year of SPY data and computes SMA50/SMA200. SPY > SMA50 > SMA200 = bull; SPY < SMA50 < SMA200 = bear. VIX > 30 biases bear; VIX < 15 biases bull.

2. **Sector Ranking** (`sectors.py`): Scores each sector proxy (XLK, XLE, XLF, XLV, XLI, XLY, XLC) using 20-day momentum, RSI positioning, volume ratio, and MACD direction. Best sectors for bull plays, worst for bear.

3. **Signal Filters** (`signals.py`): Before entering, confirms RSI < 70 (bull) or > 30 (bear) and MACD histogram direction matches regime.

4. **Position Sizing**: `POSITION_SIZE_PCT` (30%) of available cash per position, up to `MAX_POSITIONS` (3) concurrent.

5. **Exit Logic**:
   - Profit target: +8%
   - Hard stop loss: -5%
   - Trailing stop: activates at +4% gain, trails 3% below peak
   - Minimum hold: 2 calendar days (prevents premature exits on noise)

## ETF Universe

### Bull ETFs

| Sector | ETFs |
|--------|------|
| Broad | TQQQ, UPRO, SSO, QLD, SPY, QQQ |
| Tech | TECL, SOXL, XLK |
| Energy | GUSH, ERX, XLE |
| Financials | FAS, XLF |
| Healthcare | LABU, CURE, XLV |
| Industrials | DFEN, XLI |
| Consumer Disc | XLY |
| Communications | XLC |
| FANG | FNGU |

### Bear ETFs

| Sector | ETFs |
|--------|------|
| Broad | SQQQ, SPXU, SDS, SH |
| Tech | TECS, SOXS |
| Energy | DRIP, ERY |
| Financials | FAZ |
| Healthcare | LABD |

## Risk Warning

This bot trades leveraged and inverse ETFs. These instruments are designed for short-term trading and can experience significant decay over time. This is for educational purposes only. Use paper trading before going live.
