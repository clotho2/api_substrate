"""
Polymarket Weather Trading Tool — Agent-Facing Dispatcher

Phase 1 actions (read-only, no auth needed):
  - get_markets: List active weather markets via Gamma API
  - analyze_market: Fetch weather data + compute model P vs market P

Phase 2 actions (paper trading, requires position_tracker + risk_manager):
  - scan_opportunities: Full scan, return markets with edge > threshold
  - execute_trade: Place order (paper or live)
  - get_positions: Open positions with P&L
  - check_settlements: Find recently settled contracts
  - get_performance: Win rate, ROI, total wagered
  - pause_trading: Kill switch

Follows the existing substrate tool pattern: **kwargs dispatch, returns Dict[str, Any].
"""

import os
from typing import Dict, Any


def polymarket_tool(**kwargs) -> Dict[str, Any]:
    """
    Main dispatcher for Polymarket weather trading actions.

    Args (via kwargs):
        action: The action to perform (required)
        market_id: Polymarket market ID (for analyze/trade)
        keyword: Search keyword for get_markets (default: "weather")
        side: "YES" or "NO" (for execute_trade)
        size: Trade size in USDC (for execute_trade, overrides Kelly sizing)
        station_id: ICAO airport code (for analyze_market override)
        threshold: Contract threshold value (for analyze_market)
        comparison: "above" or "below" (for analyze_market)
        bankroll: Current bankroll in USDC (for execute_trade)
        settlement_price: 0.0 or 1.0 (for check_settlements)
    """
    action = kwargs.get("action")
    if not action:
        return {"status": "error", "message": "Missing required parameter: action"}

    # Read-only actions always allowed
    read_only_actions = ("get_markets", "analyze_market", "get_positions", "get_performance", "get_balance", "get_open_orders")

    # Check if polymarket is enabled for trading actions
    enabled = os.environ.get("POLYMARKET_ENABLED", "false").lower() == "true"
    if not enabled and action not in read_only_actions:
        return {
            "status": "error",
            "message": "Polymarket trading is disabled. Set POLYMARKET_ENABLED=true to enable. "
                       f"Read-only actions available: {', '.join(read_only_actions)}",
        }

    dispatch = {
        "get_markets": _get_markets,
        "analyze_market": _analyze_market,
        "scan_opportunities": _scan_opportunities,
        "execute_trade": _execute_trade,
        "get_positions": _get_positions,
        "check_settlements": _check_settlements,
        "get_performance": _get_performance,
        "pause_trading": _pause_trading,
        "get_balance": _get_balance,
        "cancel_order": _cancel_order,
        "get_open_orders": _get_open_orders,
    }

    handler = dispatch.get(action)
    if not handler:
        return {
            "status": "error",
            "message": f"Unknown action: {action}. Available: {list(dispatch.keys())}",
        }

    return handler(**kwargs)


# ============================================
# PHASE 1: READ-ONLY ACTIONS
# ============================================

def _get_markets(**kwargs) -> Dict[str, Any]:
    """List active weather markets from Polymarket Gamma API."""
    from services.polymarket.gamma_client import get_weather_markets

    keyword = kwargs.get("keyword", "weather")
    limit = kwargs.get("limit", 50)

    result = get_weather_markets(keyword=keyword, limit=limit)

    if result["status"] != "OK":
        return result

    markets = result.get("markets", [])

    # Format summary for the agent
    summaries = []
    for m in markets[:20]:  # Cap at 20 for context window
        summaries.append({
            "id": m.get("id"),
            "question": m.get("question"),
            "yes_price": m.get("yes_price"),
            "no_price": m.get("no_price"),
            "volume": m.get("volume"),
            "liquidity": m.get("liquidity"),
            "end_date": m.get("end_date"),
        })

    return {
        "status": "OK",
        "message": f"Found {len(markets)} weather markets on Polymarket",
        "markets": summaries,
        "total_found": len(markets),
        "showing": min(len(markets), 20),
    }


def _analyze_market(**kwargs) -> Dict[str, Any]:
    """
    Analyze a specific weather market: fetch weather data, compute model P,
    compare with market implied P, and report the edge.
    """
    from services.polymarket.gamma_client import get_market_details
    from services.polymarket.weather_fetcher import fetch_all_sources, STATION_MAP
    from services.polymarket.probability_engine import compute_consensus, compute_ev

    market_id = kwargs.get("market_id")
    if not market_id:
        return {"status": "error", "message": "Missing required parameter: market_id"}

    # Fetch market details from Gamma
    market_result = get_market_details(market_id)
    if market_result["status"] != "OK":
        return market_result

    market = market_result["market"]
    question = market.get("question", "")
    market_yes_price = market.get("yes_price")

    if market_yes_price is None:
        return {"status": "error", "message": "Market has no price data"}

    # Parse threshold and comparison from the market question
    # User can override with explicit parameters
    threshold = kwargs.get("threshold")
    comparison = kwargs.get("comparison", "above")
    station_id = kwargs.get("station_id")
    metric = kwargs.get("metric", "temperature")

    if threshold is None:
        parsed = _parse_weather_question(question)
        if parsed:
            threshold = parsed.get("threshold", threshold)
            comparison = parsed.get("comparison", comparison)
            station_id = station_id or parsed.get("station_id")
            metric = parsed.get("metric", metric)

    if threshold is None:
        return {
            "status": "error",
            "message": "Could not parse threshold from market question. "
                       "Please provide threshold, comparison, and station_id parameters manually.",
            "question": question,
        }

    if not station_id:
        return {
            "status": "error",
            "message": "Could not determine weather station. Please provide station_id parameter. "
                       f"Available stations: {list(STATION_MAP.keys())}",
            "question": question,
        }

    # Fetch weather data from all sources
    weather_data = fetch_all_sources(station_id, metric=metric)
    if weather_data.get("status") != "OK":
        return weather_data

    # Compute model consensus probability
    consensus = compute_consensus(
        weather_data,
        threshold=float(threshold),
        comparison=comparison,
        metric=metric,
    )

    model_p = consensus.get("p_yes")
    edge = None
    ev = None
    if model_p is not None and market_yes_price is not None:
        edge = round(model_p - market_yes_price, 4)
        ev = round(compute_ev(model_p, market_yes_price), 4)

    return {
        "status": "OK",
        "message": _format_analysis_message(market, model_p, market_yes_price, edge, ev, consensus),
        "market": {
            "id": market.get("id"),
            "question": question,
            "market_yes_price": market_yes_price,
            "volume": market.get("volume"),
            "liquidity": market.get("liquidity"),
            "clob_token_ids": market.get("clob_token_ids"),
        },
        "model": {
            "p_yes": model_p,
            "method": consensus.get("method_used"),
            "source_count": consensus.get("source_count"),
            "agreement": consensus.get("model_agreement"),
            "blocked": consensus.get("blocked", False),
            "block_reason": consensus.get("block_reason"),
        },
        "edge": {
            "raw_edge": edge,
            "ev_per_dollar": ev,
            "tradeable": edge is not None and edge > float(os.environ.get("POLYMARKET_MIN_EDGE", "0.06")),
        },
        "weather": {
            "station_id": station_id,
            "city": weather_data.get("city"),
            "metro_area": weather_data.get("metro_area"),
            "metric": metric,
            "threshold": threshold,
            "comparison": comparison,
        },
    }


# ============================================
# PHASE 2: PAPER TRADING ACTIONS
# ============================================

def _scan_opportunities(**kwargs) -> Dict[str, Any]:
    """
    Scan all weather markets for tradeable opportunities.
    Returns markets where model P vs market P edge exceeds threshold.
    """
    from services.polymarket.gamma_client import get_weather_markets
    from services.polymarket.weather_fetcher import fetch_all_sources, STATION_MAP
    from services.polymarket.probability_engine import compute_consensus, compute_ev

    min_edge = float(os.environ.get("POLYMARKET_MIN_EDGE", "0.06"))
    keyword = kwargs.get("keyword", "weather")

    # Fetch weather markets
    market_result = get_weather_markets(keyword=keyword, limit=100)
    if market_result["status"] != "OK":
        return market_result

    markets = market_result.get("markets", [])
    opportunities = []
    scanned = 0
    errors = 0

    for market in markets:
        question = market.get("question", "")
        market_p = market.get("yes_price")
        if market_p is None:
            continue

        # Try to parse the market question
        parsed = _parse_weather_question(question)
        if not parsed or not parsed.get("threshold") or not parsed.get("station_id"):
            continue

        station_id = parsed["station_id"]
        threshold = parsed["threshold"]
        comparison = parsed.get("comparison", "above")
        metric = parsed.get("metric", "temperature")

        scanned += 1

        try:
            weather_data = fetch_all_sources(station_id, metric=metric)
            if weather_data.get("status") != "OK":
                errors += 1
                continue

            consensus = compute_consensus(
                weather_data,
                threshold=threshold,
                comparison=comparison,
                metric=metric,
            )

            model_p = consensus.get("p_yes")
            if model_p is None or consensus.get("blocked"):
                continue

            edge = model_p - market_p
            ev = compute_ev(model_p, market_p)

            if edge >= min_edge:
                opportunities.append({
                    "market_id": market.get("id"),
                    "question": question,
                    "market_p": round(market_p, 4),
                    "model_p": round(model_p, 4),
                    "edge": round(edge, 4),
                    "ev_per_dollar": round(ev, 4),
                    "consensus": round(consensus.get("model_agreement", 0), 4),
                    "method": consensus.get("method_used"),
                    "station_id": station_id,
                    "metro_area": weather_data.get("metro_area"),
                    "clob_token_ids": market.get("clob_token_ids"),
                })
        except Exception:
            errors += 1
            continue

    # Sort by edge descending
    opportunities.sort(key=lambda x: x["edge"], reverse=True)

    return {
        "status": "OK",
        "message": f"Found {len(opportunities)} opportunities with edge >= {min_edge:.0%} "
                   f"(scanned {scanned} markets, {errors} errors)",
        "opportunities": opportunities[:10],  # Cap at top 10
        "total_found": len(opportunities),
        "markets_scanned": scanned,
    }


def _execute_trade(**kwargs) -> Dict[str, Any]:
    """
    Execute a trade (paper or live) after risk validation.

    Required: market_id, side, bankroll
    Optional: size (overrides Kelly), station_id, threshold, comparison
    """
    from services.polymarket.gamma_client import get_market_details
    from services.polymarket.weather_fetcher import fetch_all_sources
    from services.polymarket.probability_engine import compute_consensus, compute_ev
    from services.polymarket.risk_manager import validate_trade, calculate_kelly_size, calculate_stop_loss
    from services.polymarket.clob_client import place_order

    market_id = kwargs.get("market_id")
    side = kwargs.get("side")
    bankroll = kwargs.get("bankroll")

    if not market_id:
        return {"status": "error", "message": "Missing required parameter: market_id"}
    if not side or side not in ("YES", "NO"):
        return {"status": "error", "message": "Missing or invalid parameter: side (must be YES or NO)"}
    if not bankroll or bankroll <= 0:
        return {"status": "error", "message": "Missing required parameter: bankroll (USDC amount)"}

    # Get market data
    market_result = get_market_details(market_id)
    if market_result["status"] != "OK":
        return market_result

    market = market_result["market"]
    question = market.get("question", "")
    market_p = market.get("yes_price")
    if market_p is None:
        return {"status": "error", "message": "Market has no price data"}

    # Get weather analysis
    station_id = kwargs.get("station_id")
    threshold = kwargs.get("threshold")
    comparison = kwargs.get("comparison", "above")
    metric = kwargs.get("metric", "temperature")

    if not station_id or threshold is None:
        parsed = _parse_weather_question(question)
        if parsed:
            station_id = station_id or parsed.get("station_id")
            threshold = threshold if threshold is not None else parsed.get("threshold")
            comparison = parsed.get("comparison", comparison)
            metric = parsed.get("metric", metric)

    if not station_id or threshold is None:
        return {
            "status": "error",
            "message": "Could not determine station_id and threshold. Please provide them explicitly.",
        }

    weather_data = fetch_all_sources(station_id, metric=metric)
    if weather_data.get("status") != "OK":
        return weather_data

    consensus = compute_consensus(
        weather_data, threshold=float(threshold), comparison=comparison, metric=metric,
    )
    model_p = consensus.get("p_yes")
    if model_p is None:
        return {"status": "error", "message": f"Could not compute probability: {consensus.get('block_reason')}"}

    edge = model_p - market_p
    ev = compute_ev(model_p, market_p)

    # Risk validation
    risk_result = validate_trade(
        market_id=market_id,
        side=side,
        model_p=model_p,
        market_p=market_p,
        consensus_score=consensus.get("model_agreement", 0),
        source_count=consensus.get("source_count", 0),
        bankroll=bankroll,
        station_id=station_id,
        city=weather_data.get("city"),
        metro_area=weather_data.get("metro_area"),
    )

    if not risk_result["approved"]:
        return {
            "status": "rejected",
            "message": "Trade rejected by risk manager",
            "rejections": risk_result["rejections"],
            "edge": risk_result["edge"],
            "ev_per_dollar": risk_result["ev_per_dollar"],
        }

    # Determine size: user override or Kelly recommendation
    size = kwargs.get("size") or risk_result["recommended_size"]
    if size <= 0:
        return {"status": "error", "message": "Calculated trade size is zero"}

    kelly = risk_result.get("kelly", {})
    stop_loss = risk_result.get("stop_loss_price")
    token_ids = market.get("clob_token_ids", [])
    token_id = token_ids[0] if side == "YES" and token_ids else (token_ids[1] if len(token_ids) > 1 else "")

    # Execute via CLOB client (paper or live)
    order_result = place_order(
        market_id=market_id,
        token_id=token_id,
        side=side,
        price=market_p,
        size_usdc=size,
        question=question,
        model_p=model_p,
        market_p=market_p,
        edge=round(edge, 4),
        ev_per_dollar=round(ev, 4),
        kelly_fraction=kelly.get("kelly_quarter", 0),
        consensus_score=consensus.get("model_agreement", 0),
        source_count=consensus.get("source_count", 0),
        city=weather_data.get("city"),
        metro_area=weather_data.get("metro_area"),
        metric=metric,
        threshold=threshold,
        comparison=comparison,
        station_id=station_id,
        stop_loss_price=stop_loss,
    )

    if order_result["status"] == "OK":
        order_result["analysis"] = {
            "model_p": round(model_p, 4),
            "market_p": round(market_p, 4),
            "edge": round(edge, 4),
            "ev_per_dollar": round(ev, 4),
            "kelly_size": kelly.get("size_usdc"),
            "actual_size": size,
            "stop_loss": stop_loss,
        }

    return order_result


def _get_positions(**kwargs) -> Dict[str, Any]:
    """Get all open positions with current status."""
    from services.polymarket.position_tracker import get_open_positions

    positions = get_open_positions()

    if not positions:
        return {"status": "OK", "message": "No open positions", "positions": []}

    summaries = []
    for p in positions:
        summaries.append({
            "id": p["id"],
            "question": p.get("question", p.get("contract_name", "")),
            "side": p["side"],
            "size_usdc": p["size_usdc"],
            "entry_price": p["entry_price"],
            "stop_loss": p.get("stop_loss_price"),
            "metro_area": p.get("metro_area"),
            "opened_at": p["opened_at"],
            "paper": bool(p.get("paper_trade", 1)),
        })

    return {
        "status": "OK",
        "message": f"{len(positions)} open position(s)",
        "positions": summaries,
    }


def _check_settlements(**kwargs) -> Dict[str, Any]:
    """Check and settle positions for a resolved market."""
    from services.polymarket.position_tracker import mark_settled

    market_id = kwargs.get("market_id")
    settlement_price = kwargs.get("settlement_price")

    if not market_id:
        return {"status": "error", "message": "Missing required parameter: market_id"}
    if settlement_price is None:
        return {"status": "error", "message": "Missing required parameter: settlement_price (0.0 or 1.0)"}

    result = mark_settled(market_id, float(settlement_price))
    return {"status": "OK", **result}


def _get_performance(**kwargs) -> Dict[str, Any]:
    """Get trading performance summary."""
    from services.polymarket.position_tracker import get_performance_summary

    perf = get_performance_summary()
    return {
        "status": "OK",
        "message": _format_performance_message(perf),
        "performance": perf,
    }


def _pause_trading(**kwargs) -> Dict[str, Any]:
    """
    Kill switch — disable trading by setting POLYMARKET_ENABLED=false in env.
    This persists only for the current process; update .env for permanent change.
    """
    os.environ["POLYMARKET_ENABLED"] = "false"
    return {
        "status": "OK",
        "message": "Trading paused. POLYMARKET_ENABLED set to false for this session. "
                   "Update your .env file to make this permanent.",
    }


# ============================================
# PHASE 3: LIVE TRADING ACTIONS
# ============================================

def _get_balance(**kwargs) -> Dict[str, Any]:
    """Get wallet balance available for trading."""
    from services.polymarket.clob_client import get_balance
    return get_balance()


def _cancel_order(**kwargs) -> Dict[str, Any]:
    """Cancel an open order on the CLOB."""
    from services.polymarket.clob_client import cancel_order

    order_id = kwargs.get("order_id")
    if not order_id:
        return {"status": "error", "message": "Missing required parameter: order_id"}

    return cancel_order(order_id)


def _get_open_orders(**kwargs) -> Dict[str, Any]:
    """Get all open orders on the CLOB."""
    from services.polymarket.clob_client import get_open_orders
    return get_open_orders()


# ============================================
# HELPERS
# ============================================

def _parse_weather_question(question: str) -> dict:
    """
    Attempt to parse a Polymarket weather question to extract:
    - threshold (temperature value, etc.)
    - comparison (above/below)
    - station_id (from city name)
    - metric
    """
    result = {}
    q = question.lower()

    # Detect comparison
    if any(word in q for word in ("exceed", "above", "over", "higher than", "more than", "warmer than")):
        result["comparison"] = "above"
    elif any(word in q for word in ("below", "under", "lower than", "less than", "cooler than", "colder than")):
        result["comparison"] = "below"

    # Detect metric
    if any(word in q for word in ("temperature", "temp", "degrees", "°f", "°c", "fahrenheit", "celsius", "high", "low")):
        result["metric"] = "temperature"
    elif any(word in q for word in ("rain", "rainfall", "precipitation", "inches of rain")):
        result["metric"] = "precipitation"
    elif any(word in q for word in ("wind", "mph", "wind speed", "gusts")):
        result["metric"] = "wind_speed"
    elif any(word in q for word in ("humidity", "relative humidity")):
        result["metric"] = "humidity"

    # Try to extract numeric threshold
    import re
    numbers = re.findall(r'(\d+\.?\d*)\s*(?:°[fFcC]|degrees|mph|inches|%)', q)
    if numbers:
        result["threshold"] = float(numbers[0])
    else:
        numbers = re.findall(r'(\d+\.?\d*)', q)
        if numbers:
            result["threshold"] = float(numbers[0])

    # Try to match a city to a station
    city_to_station = {
        "nyc": "KJFK", "new york": "KJFK", "manhattan": "KJFK",
        "chicago": "KORD", "ord": "KORD",
        "los angeles": "KLAX", "la": "KLAX", "lax": "KLAX",
        "miami": "KMIA", "mia": "KMIA",
        "seattle": "KSEA", "sea": "KSEA",
        "atlanta": "KATL", "atl": "KATL",
        "denver": "KDEN", "den": "KDEN",
        "dallas": "KDFW", "dfw": "KDFW",
        "phoenix": "KPHX", "phx": "KPHX",
        "boston": "KBOS", "bos": "KBOS",
        "washington": "KDCA", "dc": "KDCA", "dca": "KDCA",
        "newark": "KEWR", "ewr": "KEWR",
    }
    for city_name, station in city_to_station.items():
        if city_name in q:
            result["station_id"] = station
            break

    return result


def _format_analysis_message(market, model_p, market_p, edge, ev, consensus) -> str:
    """Format a human-readable analysis summary."""
    question = market.get("question", "Unknown market")
    blocked = consensus.get("blocked", False)

    if blocked:
        return (
            f"Analysis blocked: {consensus.get('block_reason')}\n"
            f"Market: {question}\n"
            f"Market price: {market_p:.0%} YES"
        )

    if model_p is None:
        return f"Could not compute probability for: {question}"

    edge_pct = f"{edge:+.1%}" if edge is not None else "N/A"
    ev_str = f"${ev:.2f}" if ev is not None else "N/A"
    min_edge = float(os.environ.get("POLYMARKET_MIN_EDGE", "0.06"))
    tradeable = "TRADEABLE" if (edge and edge > min_edge) else "No edge"

    return (
        f"{question}\n"
        f"Market: {market_p:.0%} YES | Model: {model_p:.0%} YES\n"
        f"Edge: {edge_pct} | EV/dollar: {ev_str}\n"
        f"Sources: {consensus.get('source_count')}/3 | "
        f"Agreement: {consensus.get('model_agreement', 0):.0%} | "
        f"Method: {consensus.get('method_used')}\n"
        f"{tradeable}"
    )


def _format_performance_message(perf: dict) -> str:
    """Format performance stats for the agent."""
    if perf.get("total_trades", 0) == 0:
        return "No trades recorded yet."

    return (
        f"Trading Performance:\n"
        f"Total trades: {perf.get('total_trades', 0)} "
        f"({perf.get('open_positions', 0)} open, {perf.get('closed_trades', 0)} closed)\n"
        f"Win rate: {perf.get('win_rate', 0):.1f}% "
        f"({perf.get('wins', 0)}W / {perf.get('losses', 0)}L)\n"
        f"P&L: ${perf.get('total_pnl_usdc', 0):+.2f} | "
        f"ROI: {perf.get('roi_pct', 0):+.1f}%\n"
        f"Total wagered: ${perf.get('total_wagered_usdc', 0):.2f}\n"
        f"Paper: {perf.get('paper_trades', 0)} | Live: {perf.get('live_trades', 0)}"
    )
