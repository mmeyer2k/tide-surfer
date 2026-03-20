import logging
from config import SECTOR_PROXIES
from signals import get_signals

logger = logging.getLogger(__name__)


def _score_sector(symbol: str) -> float:
    """Score a sector proxy symbol. Higher = stronger momentum."""
    sig = get_signals(symbol)
    if sig is None:
        return 0.0

    score = 0.0
    score += sig["momentum_pct"] * 0.5
    rsi = sig["rsi"]
    if 40 <= rsi <= 65:
        score += 10.0
    elif rsi > 70:
        score -= 5.0
    elif rsi < 30:
        score -= 5.0
    if sig["volume_ratio"] > 1.2:
        score += 5.0
    if sig["macd_hist"] > 0:
        score += 5.0

    return score


def rank_sectors() -> list[tuple[str, float]]:
    """
    Score every sector proxy and return ranked list of (sector_name, score),
    best sector first (highest score).
    """
    scores = []
    for sector, symbol in SECTOR_PROXIES.items():
        try:
            score = _score_sector(symbol)
            scores.append((sector, score))
            logger.debug(f"Sector {sector} ({symbol}): score={score:.2f}")
        except Exception as e:
            logger.warning(f"Failed to score sector {sector}: {e}")
            scores.append((sector, 0.0))

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores
