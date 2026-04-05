"""
Weather Data Fetcher — NOAA + Open-Meteo + METAR

Pulls weather observations and forecasts from three free, keyless sources:
1. NOAA api.weather.gov — US station observations (requires User-Agent header)
2. Open-Meteo — GFS 31-member ensemble forecasts (global, free)
3. NOAA Aviation Weather — METAR airport observations

Critical: Uses airport station coordiagents, not city center.
The difference can be 3-8F, which matters on narrow temperature buckets.
"""

import os
import requests
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

NOAA_BASE_URL = "https://api.weather.gov"
OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1"
METAR_BASE_URL = "https://aviationweather.gov/api/data/metar"

# User-Agent for NOAA TOS compliance
NOAA_USER_AGENT = os.environ.get("NOAA_USER_AGENT", "agent-substrate, contact@example.com")

# Airport station mappings: ICAO code -> (lat, lon, city, metro_area)
STATION_MAP = {
    "KJFK": (40.6413, -73.7781, "New York JFK", "nyc_metro"),
    "KLGA": (40.7769, -73.8740, "New York LGA", "nyc_metro"),
    "KEWR": (40.6895, -74.1745, "Newark EWR", "nyc_metro"),
    "KORD": (41.9742, -87.9073, "Chicago O'Hare", "chicago_metro"),
    "KMDW": (41.7868, -87.7522, "Chicago Midway", "chicago_metro"),
    "KLAX": (33.9425, -118.4081, "Los Angeles LAX", "la_metro"),
    "KMIA": (25.7959, -80.2870, "Miami MIA", "miami_metro"),
    "KSEA": (47.4502, -122.3088, "Seattle SEA", "seattle_metro"),
    "KATL": (33.6407, -84.4277, "Atlanta ATL", "atlanta_metro"),
    "KDEN": (39.8561, -104.6737, "Denver DEN", "denver_metro"),
    "KDFW": (32.8998, -97.0403, "Dallas DFW", "dallas_metro"),
    "KPHX": (33.4373, -112.0078, "Phoenix PHX", "phoenix_metro"),
    "KBOS": (42.3656, -71.0096, "Boston BOS", "boston_metro"),
    "KDCA": (38.8512, -77.0402, "Washington DCA", "dc_metro"),
}


def fetch_noaa(station_id: str, metric: str = "temperature") -> Dict[str, Any]:
    """
    Fetch latest observation from NOAA api.weather.gov.

    Args:
        station_id: NOAA station ID (e.g., "KJFK", "KORD")
        metric: One of "temperature", "wind_speed", "humidity", "precipitation"

    Returns:
        Normalized observation dict.
    """
    try:
        headers = {
            "User-Agent": f"({NOAA_USER_AGENT})",
            "Accept": "application/geo+json",
        }
        url = f"{NOAA_BASE_URL}/stations/{station_id}/observations/latest"
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        props = data.get("properties", {})
        value, unit = _extract_noaa_metric(props, metric)

        return {
            "source": "noaa",
            "station_id": station_id,
            "metric": metric,
            "value": value,
            "unit": unit,
            "timestamp": props.get("timestamp"),
            "confidence": 0.9 if value is not None else 0.0,
            "raw_description": props.get("textDescription"),
        }

    except requests.exceptions.RequestException as e:
        return {
            "source": "noaa",
            "station_id": station_id,
            "metric": metric,
            "value": None,
            "unit": None,
            "timestamp": None,
            "confidence": 0.0,
            "error": str(e),
        }


def fetch_open_meteo(
    lat: float,
    lon: float,
    metric: str = "temperature",
    forecast_days: int = 3,
) -> Dict[str, Any]:
    """
    Fetch GFS ensemble forecast from Open-Meteo.

    Uses the ensemble endpoint to get 31-member GFS forecasts,
    which enables probability computation via member counting.

    Args:
        lat: Latitude (use airport coordiagents!)
        lon: Longitude
        metric: One of "temperature", "wind_speed", "humidity", "precipitation"
        forecast_days: Number of forecast days (1-16)

    Returns:
        Normalized forecast dict with ensemble_members for probability counting.
    """
    try:
        metric_param = _metric_to_open_meteo_param(metric)

        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": metric_param,
            "forecast_days": forecast_days,
            "models": "gfs_seamless",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
        }

        # Try ensemble endpoint first for member-level data
        resp = requests.get(
            f"{OPEN_METEO_BASE_URL}/ensemble",
            params={**params, "models": "gfs_seamless"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])

        # Collect ensemble member values
        # Ensemble members come as metric_param_member01, metric_param_member02, etc.
        ensemble_members = []
        for key, values in hourly.items():
            if key.startswith(metric_param) and key != "time" and key != metric_param:
                if values:
                    ensemble_members.append(values)

        # If we got ensemble members, extract the latest forecast values
        if ensemble_members and times:
            # Get the next 24h of forecasts (find first future timestamp)
            now = datetime.now(timezone.utc).isoformat()
            future_idx = 0
            for i, t in enumerate(times):
                if t >= now[:16]:
                    future_idx = i
                    break

            # Collect member values at each future time step
            member_forecasts = []
            for step_idx in range(future_idx, min(future_idx + 24, len(times))):
                step_values = []
                for member_data in ensemble_members:
                    if step_idx < len(member_data) and member_data[step_idx] is not None:
                        step_values.append(member_data[step_idx])
                if step_values:
                    member_forecasts.append({
                        "time": times[step_idx] if step_idx < len(times) else None,
                        "values": step_values,
                        "mean": sum(step_values) / len(step_values),
                        "min": min(step_values),
                        "max": max(step_values),
                        "member_count": len(step_values),
                    })

            avg_value = None
            if member_forecasts:
                all_means = [mf["mean"] for mf in member_forecasts]
                avg_value = sum(all_means) / len(all_means)

            return {
                "source": "open_meteo_ensemble",
                "metric": metric,
                "value": avg_value,
                "unit": _get_unit(metric),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "confidence": 0.85 if member_forecasts else 0.0,
                "ensemble_members": member_forecasts,
                "forecast_days": forecast_days,
                "lat": lat,
                "lon": lon,
            }

        # Fallback: no ensemble data, try point forecast
        point_values = hourly.get(metric_param, [])
        avg_value = None
        if point_values:
            valid = [v for v in point_values if v is not None]
            avg_value = sum(valid) / len(valid) if valid else None

        return {
            "source": "open_meteo",
            "metric": metric,
            "value": avg_value,
            "unit": _get_unit(metric),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "confidence": 0.7 if avg_value is not None else 0.0,
            "ensemble_members": None,
            "forecast_days": forecast_days,
            "lat": lat,
            "lon": lon,
        }

    except requests.exceptions.RequestException as e:
        return {
            "source": "open_meteo",
            "metric": metric,
            "value": None,
            "unit": None,
            "timestamp": None,
            "confidence": 0.0,
            "ensemble_members": None,
            "error": str(e),
        }


def fetch_metar(icao_code: str) -> Dict[str, Any]:
    """
    Fetch latest METAR observation from NOAA Aviation Weather Center.

    Args:
        icao_code: ICAO airport code (e.g., "KJFK", "KORD")

    Returns:
        Normalized observation dict with temperature, wind, etc.
    """
    try:
        params = {
            "ids": icao_code,
            "format": "json",
            "hours": 2,
        }
        resp = requests.get(METAR_BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if not data:
            return {
                "source": "metar",
                "station_id": icao_code,
                "value": None,
                "unit": None,
                "timestamp": None,
                "confidence": 0.0,
                "error": "No METAR data returned",
            }

        # Take the most recent observation
        obs = data[0] if isinstance(data, list) else data
        temp_c = obs.get("temp")
        temp_f = (temp_c * 9 / 5) + 32 if temp_c is not None else None
        wind_kt = obs.get("wspd")
        wind_mph = wind_kt * 1.15078 if wind_kt is not None else None

        return {
            "source": "metar",
            "station_id": icao_code,
            "temperature_f": temp_f,
            "temperature_c": temp_c,
            "wind_speed_mph": wind_mph,
            "wind_speed_kt": wind_kt,
            "wind_direction": obs.get("wdir"),
            "visibility_miles": obs.get("visib"),
            "raw_metar": obs.get("rawOb"),
            "timestamp": obs.get("reportTime"),
            "confidence": 0.95 if temp_f is not None else 0.0,
        }

    except requests.exceptions.RequestException as e:
        return {
            "source": "metar",
            "station_id": icao_code,
            "value": None,
            "unit": None,
            "timestamp": None,
            "confidence": 0.0,
            "error": str(e),
        }


def fetch_all_sources(
    station_id: str,
    metric: str = "temperature",
    forecast_days: int = 3,
) -> Dict[str, Any]:
    """
    Fetch weather data from all three sources for a given station.

    Args:
        station_id: ICAO airport code (e.g., "KJFK")
        metric: Weather metric to fetch
        forecast_days: For Open-Meteo ensemble forecast

    Returns:
        Combined results from NOAA, Open-Meteo, and METAR.
    """
    station_info = STATION_MAP.get(station_id)
    if not station_info:
        return {
            "status": "error",
            "message": f"Unknown station: {station_id}. Available: {list(STATION_MAP.keys())}",
        }

    lat, lon, city_name, metro_area = station_info

    noaa_result = fetch_noaa(station_id, metric)
    open_meteo_result = fetch_open_meteo(lat, lon, metric, forecast_days)
    metar_result = fetch_metar(station_id)

    sources = [noaa_result, open_meteo_result, metar_result]
    successful = [s for s in sources if s.get("confidence", 0) > 0]

    return {
        "status": "OK",
        "station_id": station_id,
        "city": city_name,
        "metro_area": metro_area,
        "metric": metric,
        "source_count": len(successful),
        "sources": sources,
        "noaa": noaa_result,
        "open_meteo": open_meteo_result,
        "metar": metar_result,
    }


def get_station_info(station_id: str) -> Optional[Dict[str, Any]]:
    """Get lat/lon/city/metro info for a station."""
    info = STATION_MAP.get(station_id)
    if not info:
        return None
    lat, lon, city, metro = info
    return {"station_id": station_id, "lat": lat, "lon": lon, "city": city, "metro_area": metro}


def list_stations() -> List[Dict[str, Any]]:
    """List all available weather stations."""
    return [
        {"station_id": sid, "lat": info[0], "lon": info[1], "city": info[2], "metro_area": info[3]}
        for sid, info in STATION_MAP.items()
    ]


# ============================================
# PRIVATE HELPERS
# ============================================

def _extract_noaa_metric(props: dict, metric: str):
    """Extract a specific metric from NOAA observation properties."""
    if metric == "temperature":
        temp = props.get("temperature", {})
        value_c = temp.get("value")
        if value_c is not None:
            value_f = (value_c * 9 / 5) + 32
            return round(value_f, 1), "°F"
        return None, "°F"
    elif metric == "wind_speed":
        wind = props.get("windSpeed", {})
        value_kmh = wind.get("value")
        if value_kmh is not None:
            value_mph = value_kmh * 0.621371
            return round(value_mph, 1), "mph"
        return None, "mph"
    elif metric == "humidity":
        humidity = props.get("relativeHumidity", {})
        return humidity.get("value"), "%"
    elif metric == "precipitation":
        precip = props.get("precipitationLastHour", {})
        value_mm = precip.get("value")
        if value_mm is not None:
            value_in = value_mm * 0.0393701
            return round(value_in, 2), "in"
        return None, "in"
    return None, None


def _metric_to_open_meteo_param(metric: str) -> str:
    """Convert our metric names to Open-Meteo API parameter names."""
    mapping = {
        "temperature": "temperature_2m",
        "wind_speed": "wind_speed_10m",
        "humidity": "relative_humidity_2m",
        "precipitation": "precipitation",
    }
    return mapping.get(metric, "temperature_2m")


def _get_unit(metric: str) -> str:
    """Get the unit string for a metric."""
    units = {
        "temperature": "°F",
        "wind_speed": "mph",
        "humidity": "%",
        "precipitation": "in",
    }
    return units.get(metric, "")
