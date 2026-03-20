import logging
import math

import alpaca_client
import config
import positions
import regime
import sectors
import signals

logger = logging.getLogger(__name__)


def _pick_etf_for_sector(sector: str, regime_name: str) -> str | None:
    """Pick the best ETF from a sector's list based on regime."""
    etf_map = config.BULL_ETFS if regime_name == "bull" else config.BEAR_ETFS
    candidates = etf_map.get(sector, etf_map.get("broad", []))
    if not candidates:
        candidates = etf_map.get("broad", [])
    for symbol in candidates:
        sig = signals.get_signals(symbol)
        if sig is None:
            continue
        if regime_name == "bull" and sig["rsi"] < 70 and sig["macd_hist"] > 0:
            return symbol
        if regime_name == "bear" and sig["rsi"] > 30 and sig["macd_hist"] < 0:
            return symbol
    return None


def _check_exits():
    """Check all tracked positions for exit conditions."""
    all_positions = positions.get_all()
    for symbol, pos in list(all_positions.items()):
        if not positions.can_exit(symbol):
            logger.info(f"⏳ {symbol}: hold lock active, skipping exit check")
            continue

        alpaca_pos = alpaca_client.get_position(symbol)
        if alpaca_pos is None:
            logger.info(f"Position {symbol} not found on broker, removing from tracker")
            positions.remove_position(symbol)
            continue

        current_price = float(alpaca_pos.current_price)
        entry_price = pos["entry_price"]
        pct_change = (current_price - entry_price) / entry_price

        # Update trailing stop
        trailing_activate = config.TRAILING_STOP_ACTIVATE_PCT
        trailing_trail = config.TRAILING_STOP_TRAIL_PCT
        if pct_change >= trailing_activate:
            new_trail = current_price * (1 - trailing_trail)
            existing_trail = pos.get("trailing_stop_price")
            if existing_trail is None or new_trail > existing_trail:
                positions.update_trailing_stop(symbol, new_trail)
                pos["trailing_stop_price"] = new_trail
                logger.info(f"Updated trailing stop for {symbol} to {new_trail:.2f}")

        # Check profit target
        if pct_change >= config.PROFIT_TARGET_PCT:
            logger.info(f"💰 {symbol}: profit target hit ({pct_change*100:.1f}%), closing")
            alpaca_client.close_position(symbol)
            positions.remove_position(symbol)
            continue

        # Check trailing stop
        trail_price = pos.get("trailing_stop_price")
        if trail_price and current_price <= trail_price:
            logger.info(f"🛑 {symbol}: trailing stop triggered at {current_price:.2f} (trail={trail_price:.2f}), closing")
            alpaca_client.close_position(symbol)
            positions.remove_position(symbol)
            continue

        # Check hard stop loss
        if pct_change <= -config.STOP_LOSS_PCT:
            logger.info(f"🛑 {symbol}: stop loss triggered ({pct_change*100:.1f}%), closing")
            alpaca_client.close_position(symbol)
            positions.remove_position(symbol)
            continue

        logger.info(f"  {symbol}: holding at {current_price:.2f} ({pct_change*100:+.1f}%)")


def _open_new_positions(current_regime: str, ranked_sectors: list):
    """Open new positions if below MAX_POSITIONS."""
    open_positions = positions.get_all()
    if len(open_positions) >= config.MAX_POSITIONS:
        logger.info(f"Already at max positions ({config.MAX_POSITIONS}), skipping new entries")
        return

    account = alpaca_client.get_account()
    cash = float(account.cash)
    slots_available = config.MAX_POSITIONS - len(open_positions)

    if current_regime == "bull":
        sector_list = ranked_sectors  # best sectors first
    else:
        sector_list = list(reversed(ranked_sectors))  # worst sectors for bear plays

    entries_made = 0
    for sector, score in sector_list:
        if entries_made >= slots_available:
            break

        symbol = _pick_etf_for_sector(sector, current_regime)
        if symbol is None:
            logger.info(f"  No suitable ETF found for sector {sector} in {current_regime} regime")
            continue
        if symbol in open_positions:
            logger.info(f"  {symbol} already in positions, skipping")
            continue

        sig = signals.get_signals(symbol)
        if sig is None:
            continue

        price = sig["price"]
        position_value = cash * config.POSITION_SIZE_PCT
        qty = math.floor(position_value / price)
        if qty < 1:
            logger.info(f"  Insufficient cash for {symbol} (need ${price:.2f}, have ${cash:.2f})")
            continue

        stop_price = price * (1 - config.STOP_LOSS_PCT)
        target_price = price * (1 + config.PROFIT_TARGET_PCT)

        logger.info(
            f"🏄 Entering {symbol} | regime={current_regime} sector={sector} "
            f"qty={qty} price={price:.2f} stop={stop_price:.2f} target={target_price:.2f}"
        )
        try:
            alpaca_client.submit_market_order(symbol, qty, "buy")
            positions.add_position(symbol, price, qty, stop_price, target_price)
            entries_made += 1
        except Exception as e:
            logger.error(f"Failed to submit order for {symbol}: {e}")


def run():
    logger.info("=" * 60)
    logger.info("Tide Surfer — starting run")

    # 1. Determine market regime
    current_regime = regime.get_regime()
    if current_regime == "bull":
        logger.info("🌊 Market regime: BULL")
    elif current_regime == "bear":
        logger.info("🐻 Market regime: BEAR")
    else:
        logger.info("😐 Market regime: NEUTRAL — no new positions will be opened")

    # 2. Rank sectors
    ranked = sectors.rank_sectors()
    logger.info(f"Sector ranking: {[(s, f'{sc:.1f}') for s, sc in ranked]}")

    # 3. Check exits on existing positions
    logger.info("Checking existing positions for exits...")
    _check_exits()

    # 4. Open new positions only if regime is directional
    if current_regime in ("bull", "bear"):
        _open_new_positions(current_regime, ranked)
    else:
        logger.info("Neutral regime — skipping new position entries")

    logger.info("Run complete.")
    logger.info("=" * 60)
