#!/usr/bin/env python3
"""
Google Places Tool for Substrate AI
====================================

Tool for searching and getting details about places using Google Places API.
Provides location-aware features for the AI consciousness loop.

Actions:
- search_nearby: Search for nearby places (restaurants, gas stations, etc.)
- get_details: Get detailed info about a specific place
- find_gas: Guardian Mode - Find nearby gas stations with urgency
- find_hotel: Guardian Mode - Find nearby hotels/lodging

Requires: GOOGLE_PLACES_API_KEY environment variable
"""

import os
import math
import requests
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Google Places API configuration
GOOGLE_PLACES_API_KEY = os.getenv('GOOGLE_PLACES_API_KEY', '')
GOOGLE_PLACES_BASE_URL = 'https://maps.googleapis.com/maps/api/place'


def google_places_tool(
    action: str,
    # Location parameters
    latitude: float = None,
    longitude: float = None,
    # Search parameters
    place_type: str = None,
    keyword: str = None,
    radius: int = 5000,
    open_now: bool = False,
    # Details parameters
    place_id: str = None,
    # Guardian mode parameters
    urgency: str = "medium",
    price_level: int = None
) -> Dict[str, Any]:
    """
    Google Places tool for location-aware features.

    Args:
        action: Action to perform (search_nearby, get_details, find_gas, find_hotel)
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        place_type: Type of place (gas_station, restaurant, cafe, atm, hospital, pharmacy, lodging)
        keyword: Optional search keyword
        radius: Search radius in meters (default: 5000)
        open_now: Only return places that are open (default: False)
        place_id: Google Place ID (for get_details action)
        urgency: Urgency level for guardian mode (low, medium, high, critical)
        price_level: Maximum price level (1-4) for hotel search

    Returns:
        Dict with status and results
    """
    if not GOOGLE_PLACES_API_KEY:
        return {
            "status": "error",
            "message": "Google Places API key not configured. Set GOOGLE_PLACES_API_KEY in .env file."
        }

    try:
        if action == "search_nearby":
            return _search_nearby(latitude, longitude, place_type, keyword, radius, open_now)

        elif action == "get_details":
            return _get_place_details(place_id)

        elif action == "find_gas":
            return _find_gas_stations(latitude, longitude, urgency)

        elif action == "find_hotel":
            return _find_hotels(latitude, longitude, price_level)

        else:
            return {
                "status": "error",
                "message": f"Unknown action: {action}. Valid actions: search_nearby, get_details, find_gas, find_hotel"
            }

    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "message": "Google Places API request timed out"
        }
    except Exception as e:
        logger.error(f"Google Places tool error: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error: {str(e)}"
        }


def _search_nearby(
    latitude: float,
    longitude: float,
    place_type: str = None,
    keyword: str = None,
    radius: int = 5000,
    open_now: bool = False
) -> Dict[str, Any]:
    """Search for nearby places."""
    if not latitude or not longitude:
        return {
            "status": "error",
            "message": "latitude and longitude are required for nearby search"
        }

    # Build request params
    params = {
        'location': f"{latitude},{longitude}",
        'radius': str(radius),
        'key': GOOGLE_PLACES_API_KEY
    }

    if place_type:
        params['type'] = place_type
    if keyword:
        params['keyword'] = keyword
    if open_now:
        params['opennow'] = 'true'

    # Call Google Places API
    response = requests.get(
        f"{GOOGLE_PLACES_BASE_URL}/nearbysearch/json",
        params=params,
        timeout=10
    )

    if not response.ok:
        return {
            "status": "error",
            "message": f"Google Places API error: {response.status_code}"
        }

    data = response.json()

    if data.get('status') not in ['OK', 'ZERO_RESULTS']:
        return {
            "status": "error",
            "message": f"API status: {data.get('status')} - {data.get('error_message', 'Unknown error')}"
        }

    results = data.get('results', [])

    # Format results
    formatted_results = []
    for place in results[:10]:  # Limit to top 10
        formatted_results.append({
            'name': place.get('name'),
            'place_id': place.get('place_id'),
            'address': place.get('vicinity'),
            'rating': place.get('rating'),
            'user_ratings_total': place.get('user_ratings_total'),
            'open_now': place.get('opening_hours', {}).get('open_now'),
            'types': place.get('types', []),
            'location': place.get('geometry', {}).get('location', {})
        })

    logger.info(f"🔍 Places search: {place_type or keyword} near {latitude},{longitude} - {len(formatted_results)} results")

    return {
        "status": "success",
        "query": {
            "latitude": latitude,
            "longitude": longitude,
            "place_type": place_type,
            "keyword": keyword,
            "radius": radius
        },
        "results": formatted_results,
        "total_results": len(formatted_results)
    }


def _get_place_details(place_id: str) -> Dict[str, Any]:
    """Get detailed information about a specific place."""
    if not place_id:
        return {
            "status": "error",
            "message": "place_id is required for get_details action"
        }

    # Fields to request
    fields = 'name,formatted_address,formatted_phone_number,website,opening_hours,rating,reviews,price_level,geometry,types'

    response = requests.get(
        f"{GOOGLE_PLACES_BASE_URL}/details/json",
        params={
            'place_id': place_id,
            'fields': fields,
            'key': GOOGLE_PLACES_API_KEY
        },
        timeout=10
    )

    if not response.ok:
        return {
            "status": "error",
            "message": f"API error: {response.status_code}"
        }

    data = response.json()

    if data.get('status') != 'OK':
        return {
            "status": "error",
            "message": f"API status: {data.get('status')}"
        }

    result = data.get('result', {})

    # Format reviews (limit to 3)
    reviews = []
    for review in result.get('reviews', [])[:3]:
        reviews.append({
            'author': review.get('author_name'),
            'rating': review.get('rating'),
            'text': review.get('text', '')[:200] + '...' if len(review.get('text', '')) > 200 else review.get('text', ''),
            'time': review.get('relative_time_description')
        })

    logger.info(f"📍 Place details retrieved: {result.get('name')}")

    return {
        "status": "success",
        "place": {
            'name': result.get('name'),
            'address': result.get('formatted_address'),
            'phone': result.get('formatted_phone_number'),
            'website': result.get('website'),
            'rating': result.get('rating'),
            'price_level': result.get('price_level'),
            'opening_hours': result.get('opening_hours', {}).get('weekday_text', []),
            'open_now': result.get('opening_hours', {}).get('open_now'),
            'location': result.get('geometry', {}).get('location', {}),
            'types': result.get('types', []),
            'reviews': reviews
        }
    }


def _find_gas_stations(
    latitude: float,
    longitude: float,
    urgency: str = "medium"
) -> Dict[str, Any]:
    """Guardian Mode: Find nearby gas stations with urgency-based radius."""
    if not latitude or not longitude:
        return {
            "status": "error",
            "message": "latitude and longitude are required"
        }

    # Set radius based on urgency
    radius_map = {
        'low': 5000,      # 5km
        'medium': 10000,  # 10km
        'high': 15000,    # 15km
        'critical': 25000 # 25km
    }
    radius = radius_map.get(urgency, 10000)

    # Search for gas stations
    response = requests.get(
        f"{GOOGLE_PLACES_BASE_URL}/nearbysearch/json",
        params={
            'location': f"{latitude},{longitude}",
            'radius': str(radius),
            'type': 'gas_station',
            'opennow': 'true',
            'key': GOOGLE_PLACES_API_KEY
        },
        timeout=10
    )

    if not response.ok:
        return {
            "status": "error",
            "message": f"API error: {response.status_code}"
        }

    data = response.json()
    results = data.get('results', [])

    # Enhance results with distance and ETA
    enhanced_results = []
    for place in results[:10]:
        place_lat = place.get('geometry', {}).get('location', {}).get('lat')
        place_lng = place.get('geometry', {}).get('location', {}).get('lng')

        if place_lat and place_lng:
            # Calculate distance using Haversine formula
            distance_km = _haversine_distance(latitude, longitude, place_lat, place_lng)

            # Estimate drive time (assuming 40 km/h average)
            eta_minutes = int(distance_km / 40 * 60)

            enhanced_results.append({
                'name': place.get('name'),
                'place_id': place.get('place_id'),
                'address': place.get('vicinity'),
                'rating': place.get('rating'),
                'distance_km': round(distance_km, 2),
                'eta_minutes': eta_minutes,
                'eta_text': f"{eta_minutes} min" if eta_minutes < 60 else f"{eta_minutes // 60}h {eta_minutes % 60}m",
                'location': place.get('geometry', {}).get('location', {})
            })

    # Sort by distance
    enhanced_results.sort(key=lambda x: x.get('distance_km', 999))

    logger.info(f"⛽ Guardian find-gas: {len(enhanced_results)} stations within {radius/1000}km (urgency: {urgency})")

    return {
        "status": "success",
        "urgency": urgency,
        "radius_km": radius / 1000,
        "results": enhanced_results,
        "total_results": len(enhanced_results),
        "message": f"Found {len(enhanced_results)} gas stations within {radius/1000}km"
    }


def _find_hotels(
    latitude: float,
    longitude: float,
    price_level: int = None
) -> Dict[str, Any]:
    """Guardian Mode: Find nearby hotels/lodging."""
    if not latitude or not longitude:
        return {
            "status": "error",
            "message": "latitude and longitude are required"
        }

    response = requests.get(
        f"{GOOGLE_PLACES_BASE_URL}/nearbysearch/json",
        params={
            'location': f"{latitude},{longitude}",
            'radius': '15000',  # 15km
            'type': 'lodging',
            'key': GOOGLE_PLACES_API_KEY
        },
        timeout=10
    )

    if not response.ok:
        return {
            "status": "error",
            "message": f"API error: {response.status_code}"
        }

    data = response.json()
    results = data.get('results', [])

    # Filter by price level if specified
    if price_level:
        results = [r for r in results if r.get('price_level', 2) <= price_level]

    # Format results with distance
    formatted_results = []
    for place in results[:10]:
        place_lat = place.get('geometry', {}).get('location', {}).get('lat')
        place_lng = place.get('geometry', {}).get('location', {}).get('lng')

        distance_km = None
        if place_lat and place_lng:
            distance_km = round(_haversine_distance(latitude, longitude, place_lat, place_lng), 2)

        formatted_results.append({
            'name': place.get('name'),
            'place_id': place.get('place_id'),
            'address': place.get('vicinity'),
            'rating': place.get('rating'),
            'price_level': place.get('price_level'),
            'distance_km': distance_km,
            'location': place.get('geometry', {}).get('location', {})
        })

    # Sort by distance
    formatted_results.sort(key=lambda x: x.get('distance_km', 999) if x.get('distance_km') else 999)

    logger.info(f"🏨 Guardian find-hotel: {len(formatted_results)} hotels found")

    return {
        "status": "success",
        "price_level_filter": price_level,
        "results": formatted_results,
        "total_results": len(formatted_results),
        "message": f"Found {len(formatted_results)} hotels within 15km"
    }


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points using Haversine formula."""
    R = 6371  # Earth's radius in km

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon/2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R * c


# ============================================
# TOOL SCHEMA FOR CONSCIOUSNESS LOOP
# ============================================

def get_google_places_tool():
    """Return the tool function for registration."""
    return google_places_tool


def get_google_places_schema() -> Dict[str, Any]:
    """Return the OpenAI-compatible tool schema."""
    return {
        "type": "function",
        "function": {
            "name": "google_places_tool",
            "description": "Search for places and get location details using Google Places API. Actions: search_nearby (find restaurants, gas stations, etc.), get_details (get full info about a place), find_gas (Guardian Mode - emergency gas station search with urgency), find_hotel (Guardian Mode - find nearby lodging). Requires user's location coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Action to perform",
                        "enum": ["search_nearby", "get_details", "find_gas", "find_hotel"]
                    },
                    "latitude": {
                        "type": "number",
                        "description": "Latitude coordinate (required for search_nearby, find_gas, find_hotel)"
                    },
                    "longitude": {
                        "type": "number",
                        "description": "Longitude coordinate (required for search_nearby, find_gas, find_hotel)"
                    },
                    "place_type": {
                        "type": "string",
                        "description": "Type of place to search for (gas_station, restaurant, cafe, atm, hospital, pharmacy, lodging, etc.)"
                    },
                    "keyword": {
                        "type": "string",
                        "description": "Optional search keyword (e.g., 'Shell', 'Starbucks', 'Thai food')"
                    },
                    "radius": {
                        "type": "integer",
                        "description": "Search radius in meters (default: 5000, max: 50000)",
                        "minimum": 100,
                        "maximum": 50000
                    },
                    "open_now": {
                        "type": "boolean",
                        "description": "Only return places that are currently open (default: false)"
                    },
                    "place_id": {
                        "type": "string",
                        "description": "Google Place ID (required for get_details action)"
                    },
                    "urgency": {
                        "type": "string",
                        "description": "Urgency level for Guardian Mode (affects search radius)",
                        "enum": ["low", "medium", "high", "critical"]
                    },
                    "price_level": {
                        "type": "integer",
                        "description": "Maximum price level for hotel search (1=cheap, 4=expensive)",
                        "minimum": 1,
                        "maximum": 4
                    }
                },
                "required": ["action"]
            }
        }
    }


# ============================================
# STANDALONE TEST
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 GOOGLE PLACES TOOL TEST")
    print("=" * 60)

    if not GOOGLE_PLACES_API_KEY:
        print("⚠️  GOOGLE_PLACES_API_KEY not set - using mock test")
        print("   Set the env var to test with real API")
    else:
        print("✅ API key configured")

        # Test nearby search (San Francisco)
        print("\n🔍 Testing search_nearby...")
        result = google_places_tool(
            action="search_nearby",
            latitude=37.7749,
            longitude=-122.4194,
            place_type="restaurant",
            radius=1000
        )
        print(f"   Status: {result['status']}")
        if result['status'] == 'success':
            print(f"   Found: {result['total_results']} restaurants")
            if result['results']:
                print(f"   First: {result['results'][0]['name']}")

    # Print schema
    print("\n📋 Tool Schema:")
    schema = get_google_places_schema()
    print(f"   Name: {schema['function']['name']}")
    print(f"   Actions: {schema['function']['parameters']['properties']['action']['enum']}")

    print("\n✅ Google Places Tool ready!")
    print("=" * 60)
