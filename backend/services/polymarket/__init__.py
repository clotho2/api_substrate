"""
Polymarket Weather Trading Service

Provides weather data fetching, probability computation, risk management,
position tracking, and market interaction for trading weather contracts
on Polymarket.

Phase 1: Read-only market intelligence (gamma_client, weather_fetcher, probability_engine)
Phase 2: Paper trading (risk_manager, position_tracker, clob_client)
Phase 3: Live execution with real keys
"""

from services.polymarket.gamma_client import (
    get_weather_markets,
    get_market_details,
    get_market_price,
)
from services.polymarket.weather_fetcher import (
    fetch_noaa,
    fetch_open_meteo,
    fetch_metar,
    fetch_all_sources,
    list_stations,
    STATION_MAP,
)
from services.polymarket.probability_engine import (
    compute_consensus,
    compute_ev,
    gaussian_probability,
)
from services.polymarket.risk_manager import (
    validate_trade,
    calculate_kelly_size,
    calculate_ev as risk_calculate_ev,
    get_metro_area,
)
from services.polymarket.position_tracker import (
    record_trade,
    close_position,
    mark_settled,
    get_open_positions,
    get_open_by_metro,
    get_performance_summary,
    get_dashboard_data,
)
from services.polymarket.clob_client import (
    place_order,
    get_orderbook,
    get_balance,
    cancel_order,
    get_open_orders,
)

__all__ = [
    # Gamma API
    "get_weather_markets",
    "get_market_details",
    "get_market_price",
    # Weather data
    "fetch_noaa",
    "fetch_open_meteo",
    "fetch_metar",
    "fetch_all_sources",
    "list_stations",
    "STATION_MAP",
    # Probability
    "compute_consensus",
    "compute_ev",
    "gaussian_probability",
    # Risk management
    "validate_trade",
    "calculate_kelly_size",
    "risk_calculate_ev",
    "get_metro_area",
    # Position tracking
    "record_trade",
    "close_position",
    "mark_settled",
    "get_open_positions",
    "get_open_by_metro",
    "get_performance_summary",
    "get_dashboard_data",
    # CLOB client
    "place_order",
    "get_orderbook",
    "get_balance",
    "cancel_order",
    "get_open_orders",
]
