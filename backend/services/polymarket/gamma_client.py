"""
Polymarket Gamma API Client — Read-Only Market Discovery

Uses the Gamma API (https://gamma-api.polymarket.com) for market discovery
and price fetching. No authentication required.

The CLOB API (clob.polymarket.com) is separate and handles order execution (Phase 2+).
"""

import requests
from typing import Dict, Any, List, Optional

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"

# Weather-related keywords for filtering markets
WEATHER_KEYWORDS = [
    "temperature", "weather", "degrees", "fahrenheit", "celsius",
    "rain", "rainfall", "precipitation", "snow", "snowfall",
    "wind", "mph", "humidity", "heat", "cold", "freeze",
    "high temp", "low temp", "warm", "cool",
]


def get_weather_markets(
    keyword: str = "weather",
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Search Gamma API for active weather markets with order books enabled.

    The Gamma API doesn't support text search directly, so we fetch active
    markets and filter client-side by question/description text.
    """
    try:
        params = {
            "active": "true",
            "closed": "false",
            "archived": "false",
            "enableOrderBook": "true",
            "limit": limit,
            "offset": offset,
        }
        resp = requests.get(f"{GAMMA_BASE_URL}/markets", params=params, timeout=15)
        resp.raise_for_status()
        all_markets = resp.json()

        # Client-side filter for weather-related markets
        search_terms = [keyword.lower()] if keyword.lower() not in ("weather", "all") else WEATHER_KEYWORDS
        weather_markets = []
        for market in all_markets:
            question = (market.get("question") or "").lower()
            description = (market.get("description") or "").lower()
            text = question + " " + description
            if any(term in text for term in search_terms):
                weather_markets.append(_normalize_market(market))

        return {
            "status": "OK",
            "markets": weather_markets,
            "count": len(weather_markets),
            "total_scanned": len(all_markets),
        }

    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"Gamma API request failed: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": f"Market fetch failed: {str(e)}"}


def get_market_details(market_id: str) -> Dict[str, Any]:
    """Fetch full details for a single market by its numeric ID or slug."""
    try:
        resp = requests.get(f"{GAMMA_BASE_URL}/markets/{market_id}", timeout=15)
        resp.raise_for_status()
        market = resp.json()
        return {
            "status": "OK",
            "market": _normalize_market(market),
        }
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"Market detail fetch failed: {str(e)}"}


def get_market_price(market_id: str) -> Dict[str, Any]:
    """
    Get the current implied probability for a market.

    outcomePrices is a JSON-stringified list like '["0.65", "0.35"]'
    where index 0 = YES price, index 1 = NO price.
    """
    result = get_market_details(market_id)
    if result["status"] != "OK":
        return result

    market = result["market"]
    return {
        "status": "OK",
        "market_id": market_id,
        "question": market.get("question"),
        "yes_price": market.get("yes_price"),
        "no_price": market.get("no_price"),
        "volume": market.get("volume"),
        "liquidity": market.get("liquidity"),
    }


def get_events(
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Fetch events from Gamma API. Events contain nested markets.
    Useful for finding groups of related weather markets.
    """
    try:
        params = {
            "active": "true",
            "closed": "false",
            "archived": "false",
            "limit": limit,
            "offset": offset,
        }
        resp = requests.get(f"{GAMMA_BASE_URL}/events", params=params, timeout=15)
        resp.raise_for_status()
        events = resp.json()
        return {
            "status": "OK",
            "events": events,
            "count": len(events),
        }
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"Events fetch failed: {str(e)}"}


def _normalize_market(raw: dict) -> dict:
    """Normalize a Gamma API market response to a clean dict."""
    import json

    # Parse outcome prices (JSON-stringified list)
    outcome_prices_raw = raw.get("outcomePrices", "[]")
    if isinstance(outcome_prices_raw, str):
        try:
            outcome_prices = json.loads(outcome_prices_raw)
        except (json.JSONDecodeError, TypeError):
            outcome_prices = []
    else:
        outcome_prices = outcome_prices_raw or []

    yes_price = float(outcome_prices[0]) if len(outcome_prices) > 0 else None
    no_price = float(outcome_prices[1]) if len(outcome_prices) > 1 else None

    # Parse clob token IDs
    clob_token_ids_raw = raw.get("clobTokenIds", "[]")
    if isinstance(clob_token_ids_raw, str):
        try:
            clob_token_ids = json.loads(clob_token_ids_raw)
        except (json.JSONDecodeError, TypeError):
            clob_token_ids = []
    else:
        clob_token_ids = clob_token_ids_raw or []

    return {
        "id": raw.get("id"),
        "question": raw.get("question"),
        "description": raw.get("description", ""),
        "slug": raw.get("slug"),
        "yes_price": yes_price,
        "no_price": no_price,
        "clob_token_ids": clob_token_ids,
        "outcomes": raw.get("outcomes"),
        "volume": raw.get("volume"),
        "volume_24hr": raw.get("volume24hr"),
        "liquidity": raw.get("liquidity"),
        "end_date": raw.get("endDate"),
        "active": raw.get("active"),
        "closed": raw.get("closed"),
        "neg_risk": raw.get("negRisk"),
        "accepting_orders": raw.get("acceptingOrders"),
        "spread": raw.get("spread"),
    }
