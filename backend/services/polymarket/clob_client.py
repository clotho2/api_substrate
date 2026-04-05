"""
CLOB Client — Polymarket Order Execution (Paper + Live)

Paper mode (default): Logs orders to the position tracker DB but skips
actual CLOB API execution.

Live mode: Uses py-clob-client for real order execution on Polygon.
Requires POLYMARKET_PRIVATE_KEY, POLYMARKET_API_KEY, etc.
Records all live trades to the position tracker DB for dashboard/tracking.

Follows the PaperBroker/LiveBroker pattern from RiekertQuant/polymarket-weather-bot-poc.
"""

import os
from typing import Dict, Any, Optional

PAPER_MODE = os.environ.get("POLYMARKET_PAPER_MODE", "true").lower() == "true"
CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon


def _get_clob_client():
    """
    Initialize and return an authenticated ClobClient.
    Reusable across live order, balance check, and cancel operations.
    """
    private_key = os.environ.get("POLYMARKET_PRIVATE_KEY", "")
    api_key = os.environ.get("POLYMARKET_API_KEY", "")

    if not private_key or not api_key:
        return None, "Live trading requires POLYMARKET_PRIVATE_KEY and POLYMARKET_API_KEY."

    try:
        from py_clob_client.client import ClobClient

        client = ClobClient(
            CLOB_HOST,
            key=private_key,
            chain_id=CHAIN_ID,
        )
        creds = client.create_or_derive_api_creds()
        client.set_api_creds(creds)
        return client, None
    except ImportError:
        return None, "py-clob-client not installed. Run: pip install py-clob-client>=0.19.0"
    except Exception as e:
        return None, f"CLOB client initialization failed: {str(e)}"


def place_order(
    market_id: str,
    token_id: str,
    side: str,
    price: float,
    size_usdc: float,
    question: str = "",
    model_p: float = None,
    market_p: float = None,
    edge: float = None,
    ev_per_dollar: float = None,
    kelly_fraction: float = None,
    consensus_score: float = None,
    source_count: int = None,
    city: str = None,
    metro_area: str = None,
    metric: str = None,
    threshold: float = None,
    comparison: str = None,
    station_id: str = None,
    stop_loss_price: float = None,
) -> Dict[str, Any]:
    """
    Place an order — either paper or live depending on POLYMARKET_PAPER_MODE.
    Both modes record trades in the position tracker DB.
    """
    trade_metadata = dict(
        model_p=model_p,
        market_p=market_p,
        edge=edge,
        ev_per_dollar=ev_per_dollar,
        kelly_fraction=kelly_fraction,
        consensus_score=consensus_score,
        source_count=source_count,
        city=city,
        metro_area=metro_area,
        metric=metric,
        threshold=threshold,
        comparison=comparison,
        station_id=station_id,
        stop_loss_price=stop_loss_price,
    )

    if PAPER_MODE:
        return _paper_order(
            market_id=market_id,
            token_id=token_id,
            side=side,
            price=price,
            size_usdc=size_usdc,
            question=question,
            **trade_metadata,
        )
    else:
        return _live_order(
            market_id=market_id,
            token_id=token_id,
            side=side,
            price=price,
            size_usdc=size_usdc,
            question=question,
            **trade_metadata,
        )


def get_orderbook(token_id: str) -> Dict[str, Any]:
    """Fetch the order book for a token from the CLOB API (no auth needed)."""
    try:
        import requests
        resp = requests.get(
            f"{CLOB_HOST}/book",
            params={"token_id": token_id},
            timeout=15,
        )
        resp.raise_for_status()
        return {"status": "OK", "orderbook": resp.json()}
    except Exception as e:
        return {"status": "error", "message": f"Orderbook fetch failed: {str(e)}"}


def _paper_order(
    market_id: str,
    token_id: str,
    side: str,
    price: float,
    size_usdc: float,
    question: str = "",
    **trade_metadata,
) -> Dict[str, Any]:
    """
    Paper trade: record in position tracker DB without executing on CLOB.
    """
    from services.polymarket.position_tracker import record_trade

    result = record_trade(
        market_id=market_id,
        question=question,
        side=side,
        size_usdc=size_usdc,
        entry_price=price,
        model_p=trade_metadata.get("model_p", 0),
        market_p=trade_metadata.get("market_p", 0),
        edge=trade_metadata.get("edge", 0),
        ev_per_dollar=trade_metadata.get("ev_per_dollar", 0),
        kelly_fraction=trade_metadata.get("kelly_fraction", 0),
        consensus_score=trade_metadata.get("consensus_score", 0),
        source_count=trade_metadata.get("source_count", 0),
        city=trade_metadata.get("city"),
        metro_area=trade_metadata.get("metro_area"),
        metric=trade_metadata.get("metric"),
        threshold=trade_metadata.get("threshold"),
        comparison=trade_metadata.get("comparison"),
        station_id=trade_metadata.get("station_id"),
        stop_loss_price=trade_metadata.get("stop_loss_price"),
        paper_trade=True,
    )

    if result["status"] == "OK":
        result["execution_type"] = "paper"
        result["message"] = f"[PAPER] {result['message']}"

    return result


def _live_order(
    market_id: str,
    token_id: str,
    side: str,
    price: float,
    size_usdc: float,
    question: str = "",
    **trade_metadata,
) -> Dict[str, Any]:
    """
    Live order execution via py-clob-client.
    Records all live trades to position_tracker DB for dashboard/tracking.
    """
    # Enforce live trading hard cap
    live_max = float(os.environ.get("POLYMARKET_LIVE_MAX_USDC", "25"))
    if size_usdc > live_max:
        return {
            "status": "error",
            "message": f"Trade size ${size_usdc:.2f} exceeds live cap ${live_max:.2f}. "
                       f"Adjust POLYMARKET_LIVE_MAX_USDC to increase.",
        }

    client, error = _get_clob_client()
    if error:
        return {"status": "error", "message": error}

    try:
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY, SELL

        clob_side = BUY if side == "YES" else SELL
        shares = size_usdc / price if price > 0 else 0

        order_args = OrderArgs(
            price=price,
            size=shares,
            side=clob_side,
            token_id=token_id,
        )

        signed_order = client.create_order(order_args)
        response = client.post_order(signed_order, OrderType.GTC)

        # Record the live trade in position tracker DB
        from services.polymarket.position_tracker import record_trade

        db_result = record_trade(
            market_id=market_id,
            question=question,
            side=side,
            size_usdc=size_usdc,
            entry_price=price,
            model_p=trade_metadata.get("model_p", 0),
            market_p=trade_metadata.get("market_p", 0),
            edge=trade_metadata.get("edge", 0),
            ev_per_dollar=trade_metadata.get("ev_per_dollar", 0),
            kelly_fraction=trade_metadata.get("kelly_fraction", 0),
            consensus_score=trade_metadata.get("consensus_score", 0),
            source_count=trade_metadata.get("source_count", 0),
            city=trade_metadata.get("city"),
            metro_area=trade_metadata.get("metro_area"),
            metric=trade_metadata.get("metric"),
            threshold=trade_metadata.get("threshold"),
            comparison=trade_metadata.get("comparison"),
            station_id=trade_metadata.get("station_id"),
            stop_loss_price=trade_metadata.get("stop_loss_price"),
            paper_trade=False,
        )

        return {
            "status": "OK",
            "execution_type": "live",
            "position_id": db_result.get("position_id"),
            "order_response": response,
            "trade": {
                "market_question": question,
                "side": side,
                "price": price,
                "size": size_usdc,
                "shares": round(shares, 4),
                "paper_trade": False,
            },
            "message": f"[LIVE] Order placed: {side} ${size_usdc:.2f} @ {price:.4f} ({shares:.2f} shares)",
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Live order execution failed: {str(e)}",
        }


def get_balance() -> Dict[str, Any]:
    """
    Get the USDC balance available for trading on Polymarket.
    Uses the CLOB API to check the wallet's allowance/balance.
    """
    if PAPER_MODE:
        return {
            "status": "OK",
            "mode": "paper",
            "message": "Paper mode — no real balance. Set bankroll manually.",
        }

    client, error = _get_clob_client()
    if error:
        return {"status": "error", "message": error}

    try:
        # py-clob-client exposes get_balance_allowance for the connected wallet
        balance_data = client.get_balance_allowance()
        return {
            "status": "OK",
            "mode": "live",
            "balance": balance_data,
            "message": f"Wallet balance: {balance_data}",
        }
    except AttributeError:
        # Fallback: some versions don't have get_balance_allowance
        return {
            "status": "OK",
            "mode": "live",
            "message": "Balance check not available in this py-clob-client version. "
                       "Check your wallet balance directly on Polymarket.",
        }
    except Exception as e:
        return {"status": "error", "message": f"Balance check failed: {str(e)}"}


def cancel_order(order_id: str) -> Dict[str, Any]:
    """Cancel an open order on the CLOB."""
    if PAPER_MODE:
        return {"status": "OK", "message": "Paper mode — no orders to cancel."}

    client, error = _get_clob_client()
    if error:
        return {"status": "error", "message": error}

    try:
        response = client.cancel(order_id)
        return {
            "status": "OK",
            "message": f"Order {order_id} cancelled",
            "response": response,
        }
    except Exception as e:
        return {"status": "error", "message": f"Cancel failed: {str(e)}"}


def get_open_orders() -> Dict[str, Any]:
    """Get all open orders on the CLOB."""
    if PAPER_MODE:
        return {"status": "OK", "mode": "paper", "orders": [], "message": "Paper mode — no CLOB orders."}

    client, error = _get_clob_client()
    if error:
        return {"status": "error", "message": error}

    try:
        orders = client.get_orders()
        return {
            "status": "OK",
            "mode": "live",
            "orders": orders,
            "message": f"{len(orders) if isinstance(orders, list) else 'Unknown'} open order(s)",
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to fetch orders: {str(e)}"}
