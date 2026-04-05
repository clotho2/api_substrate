"""
Risk Manager — Trade Validation + Quarter Kelly Sizing + Metro Correlation Guard

Validates every trade against multiple risk rules before allowing execution:
1. EV threshold (MIN_EDGE)
2. Model consensus minimum (MIN_CONSENSUS)
3. Metro area correlation (max 1 open position per metro)
4. Price bounds (0.10 - 0.90)
5. Bankroll limits (Quarter Kelly, capped at MAX_BANKROLL_PCT)
6. Daily loss circuit breaker
7. Stop-loss at -20%

Returns approved/rejected with reason and recommended size.
"""

import os
import math
from typing import Dict, Any, Optional

# Load config with defaults
MIN_EDGE = float(os.environ.get("POLYMARKET_MIN_EDGE", "0.06"))
MIN_CONSENSUS = float(os.environ.get("POLYMARKET_MIN_CONSENSUS", "0.65"))
MAX_BANKROLL_PCT = float(os.environ.get("POLYMARKET_MAX_BANKROLL_PCT", "2"))
MAX_PER_METRO = int(os.environ.get("POLYMARKET_MAX_PER_METRO", "1"))
MIN_PRICE = float(os.environ.get("POLYMARKET_MIN_PRICE", "0.10"))
MAX_PRICE = float(os.environ.get("POLYMARKET_MAX_PRICE", "0.90"))
MAX_TRADE_USDC = 100.0  # Hard cap per trade (from weather bot benchmarks)
LIVE_MAX_USDC = float(os.environ.get("POLYMARKET_LIVE_MAX_USDC", "25"))  # Live trading hard cap
DAILY_LOSS_LIMIT = -300.0  # Circuit breaker
STOP_LOSS_PCT = 0.20  # -20% stop loss
KELLY_FRACTION = 0.25  # Quarter Kelly


# Metropolitan area groupings
METRO_AREAS = {
    "nyc_metro": ["KJFK", "KLGA", "KEWR"],
    "chicago_metro": ["KORD", "KMDW"],
    "la_metro": ["KLAX"],
    "miami_metro": ["KMIA"],
    "seattle_metro": ["KSEA"],
    "atlanta_metro": ["KATL"],
    "denver_metro": ["KDEN"],
    "dallas_metro": ["KDFW"],
    "phoenix_metro": ["KPHX"],
    "boston_metro": ["KBOS"],
    "dc_metro": ["KDCA"],
}

# Reverse lookup: station -> metro area
_STATION_TO_METRO = {}
for metro, stations in METRO_AREAS.items():
    for station in stations:
        _STATION_TO_METRO[station] = metro


def get_metro_area(station_id: str = None, city: str = None) -> Optional[str]:
    """Map a station ID or city name to its metropolitan area."""
    if station_id:
        return _STATION_TO_METRO.get(station_id)
    if city:
        city_lower = city.lower()
        city_to_metro = {
            "new york": "nyc_metro", "nyc": "nyc_metro", "manhattan": "nyc_metro",
            "newark": "nyc_metro", "jfk": "nyc_metro",
            "chicago": "chicago_metro", "midway": "chicago_metro",
            "los angeles": "la_metro", "la": "la_metro",
            "miami": "miami_metro",
            "seattle": "seattle_metro",
            "atlanta": "atlanta_metro",
            "denver": "denver_metro",
            "dallas": "dallas_metro",
            "phoenix": "phoenix_metro",
            "boston": "boston_metro",
            "washington": "dc_metro", "dc": "dc_metro",
        }
        for name, metro in city_to_metro.items():
            if name in city_lower:
                return metro
    return None


def calculate_ev(model_p: float, market_p: float) -> float:
    """
    Expected value per dollar wagered.
    EV = P_true * (1 - P_market) - (1 - P_true) * P_market
    """
    return model_p * (1.0 - market_p) - (1.0 - model_p) * market_p


def calculate_kelly_size(
    model_p: float,
    market_p: float,
    bankroll: float,
) -> Dict[str, Any]:
    """
    Calculate Quarter Kelly position size.

    Full Kelly: f* = (p * b - q) / b
    where p = model probability, q = 1 - p, b = odds = (1/market_p) - 1

    We use 0.25 * Kelly (Quarter Kelly) for safety.
    Result is capped at MAX_BANKROLL_PCT and MAX_TRADE_USDC.
    """
    if market_p <= 0 or market_p >= 1:
        return {"size_usdc": 0, "kelly_full": 0, "kelly_quarter": 0, "reason": "Invalid market price"}

    b = (1.0 / market_p) - 1.0  # Decimal odds
    if b <= 0:
        return {"size_usdc": 0, "kelly_full": 0, "kelly_quarter": 0, "reason": "Non-positive odds"}

    q = 1.0 - model_p
    kelly_full = (model_p * b - q) / b

    if kelly_full <= 0:
        return {
            "size_usdc": 0,
            "kelly_full": round(kelly_full, 6),
            "kelly_quarter": 0,
            "reason": "Negative Kelly — no edge",
        }

    kelly_quarter = kelly_full * KELLY_FRACTION
    size_pct = min(kelly_quarter * 100, MAX_BANKROLL_PCT)

    # Apply per-trade cap — use the stricter of general cap vs live cap
    paper_mode = os.environ.get("POLYMARKET_PAPER_MODE", "true").lower() == "true"
    effective_cap = MAX_TRADE_USDC if paper_mode else min(MAX_TRADE_USDC, LIVE_MAX_USDC)
    size_usdc = min(bankroll * size_pct / 100, effective_cap)

    return {
        "size_usdc": round(size_usdc, 2),
        "kelly_full": round(kelly_full, 6),
        "kelly_quarter": round(kelly_quarter, 6),
        "bankroll_pct": round(size_pct, 4),
        "capped_by": "live_max" if (not paper_mode and size_usdc >= LIVE_MAX_USDC) else (
            "max_trade" if size_usdc >= MAX_TRADE_USDC else (
                "bankroll_pct" if size_pct >= MAX_BANKROLL_PCT else "kelly"
            )
        ),
    }


def calculate_stop_loss(entry_price: float, side: str) -> float:
    """Calculate stop-loss price for a position."""
    if side == "YES":
        return max(0.01, entry_price * (1 - STOP_LOSS_PCT))
    else:
        return min(0.99, entry_price * (1 + STOP_LOSS_PCT))


def validate_trade(
    market_id: str,
    side: str,
    model_p: float,
    market_p: float,
    consensus_score: float,
    source_count: int,
    bankroll: float,
    station_id: str = None,
    city: str = None,
    metro_area: str = None,
) -> Dict[str, Any]:
    """
    Validate a proposed trade against all risk rules.

    Returns approved/rejected with reason and recommended size.
    """
    from services.polymarket.position_tracker import get_open_by_metro, get_daily_pnl

    rejections = []

    # 1. EV threshold
    ev = calculate_ev(model_p, market_p)
    edge = model_p - market_p
    if edge < MIN_EDGE:
        rejections.append(f"Insufficient edge: {edge:.4f} < {MIN_EDGE} minimum")

    # 2. Consensus threshold
    if consensus_score < MIN_CONSENSUS:
        rejections.append(f"Low consensus: {consensus_score:.2f} < {MIN_CONSENSUS} minimum")

    # 3. Source count
    if source_count < 2:
        rejections.append(f"Insufficient data sources: {source_count}/2 minimum")

    # 4. Price bounds
    trade_price = market_p  # We're buying at market price
    if trade_price < MIN_PRICE:
        rejections.append(f"Price too low: {trade_price:.2f} < {MIN_PRICE} minimum")
    if trade_price > MAX_PRICE:
        rejections.append(f"Price too high: {trade_price:.2f} > {MAX_PRICE} maximum")

    # 5. Metro area correlation guard
    resolved_metro = metro_area or get_metro_area(station_id=station_id, city=city)
    if resolved_metro:
        open_in_metro = get_open_by_metro(resolved_metro)
        if len(open_in_metro) >= MAX_PER_METRO:
            rejections.append(
                f"Metro correlation limit: {len(open_in_metro)}/{MAX_PER_METRO} "
                f"open positions in {resolved_metro}"
            )

    # 6. Daily loss circuit breaker
    daily_pnl = get_daily_pnl()
    if daily_pnl <= DAILY_LOSS_LIMIT:
        rejections.append(f"Daily loss circuit breaker: ${daily_pnl:.2f} exceeds ${DAILY_LOSS_LIMIT:.2f} limit")

    # 7. Calculate position size
    kelly = calculate_kelly_size(model_p, market_p, bankroll)
    recommended_size = kelly["size_usdc"]

    if recommended_size <= 0:
        rejections.append(f"Kelly sizing: no position recommended ({kelly.get('reason', 'negative Kelly')})")

    # Compute stop loss
    stop_loss = calculate_stop_loss(market_p, side)

    if rejections:
        return {
            "approved": False,
            "rejections": rejections,
            "rejection_count": len(rejections),
            "edge": round(edge, 4),
            "ev_per_dollar": round(ev, 4),
            "recommended_size": 0,
            "metro_area": resolved_metro,
        }

    return {
        "approved": True,
        "recommended_size": recommended_size,
        "kelly": kelly,
        "edge": round(edge, 4),
        "ev_per_dollar": round(ev, 4),
        "stop_loss_price": round(stop_loss, 4),
        "metro_area": resolved_metro,
        "daily_pnl": round(daily_pnl, 2),
    }
