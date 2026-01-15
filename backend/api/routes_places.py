#!/usr/bin/env python3
"""
Google Places API Routes
========================

Location-aware features for AiCara companion apps.
Ported from mobile-clean/backend/server.js

Endpoints:
- POST /api/places/nearby       - Search nearby places
- GET  /api/places/details/:id  - Get place details
- POST /api/guardian/find-gas   - Guardian Mode: Find gas stations
- POST /api/guardian/find-hotel - Guardian Mode: Find hotels
- POST /api/location/context    - Update user location context

Requires: GOOGLE_PLACES_API_KEY environment variable
"""

import os
import logging
import requests
from datetime import datetime
from flask import Blueprint, jsonify, request
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Create blueprint
places_bp = Blueprint('places', __name__)

# Google Places API configuration
GOOGLE_PLACES_API_KEY = os.getenv('GOOGLE_PLACES_API_KEY', '')
GOOGLE_PLACES_BASE_URL = 'https://maps.googleapis.com/maps/api/place'

# Location context storage (in-memory, per-session)
# In production, this could use Redis or the state manager
_location_contexts: Dict[str, Dict[str, Any]] = {}


# ============================================
# GOOGLE PLACES SEARCH
# ============================================

@places_bp.route('/api/places/nearby', methods=['POST'])
def search_nearby_places():
    """
    Search for nearby places using Google Places API.
    
    Request:
    {
        "latitude": 37.7749,
        "longitude": -122.4194,
        "radius": 5000,           // meters, default 5000
        "type": "gas_station",    // gas_station, restaurant, cafe, atm, hospital, pharmacy
        "keyword": "shell",       // optional search keyword
        "open_now": true          // optional, only open places
    }
    
    Response:
    {
        "results": [...],
        "status": "OK"
    }
    """
    if not GOOGLE_PLACES_API_KEY:
        logger.warning("⚠️ Google Places API key not configured")
        return jsonify({
            "error": "Google Places API not configured",
            "results": [],
            "status": "API_KEY_MISSING"
        }), 503
    
    try:
        data = request.get_json()
        
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        radius = data.get('radius', 5000)
        place_type = data.get('type')
        keyword = data.get('keyword')
        open_now = data.get('open_now', False)
        
        if not latitude or not longitude:
            return jsonify({"error": "latitude and longitude required"}), 400
        
        # Build Google Places API request
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
            logger.error(f"Google Places API error: {response.status_code}")
            return jsonify({
                "error": f"Google Places API error: {response.status_code}",
                "results": [],
                "status": "API_ERROR"
            }), 500
        
        data = response.json()
        
        if data.get('status') not in ['OK', 'ZERO_RESULTS']:
            logger.warning(f"Google Places API status: {data.get('status')}")
        
        logger.info(f"🔍 Places search: {place_type or keyword} near {latitude},{longitude} - {len(data.get('results', []))} results")
        
        return jsonify({
            "results": data.get('results', []),
            "status": data.get('status', 'OK')
        })
    
    except requests.exceptions.Timeout:
        logger.error("Google Places API timeout")
        return jsonify({
            "error": "Request timeout",
            "results": [],
            "status": "TIMEOUT"
        }), 504
    
    except Exception as e:
        logger.error(f"❌ Places search error: {e}", exc_info=True)
        return jsonify({
            "error": str(e),
            "results": [],
            "status": "ERROR"
        }), 500


@places_bp.route('/api/places/details/<place_id>', methods=['GET'])
def get_place_details(place_id: str):
    """
    Get detailed information about a specific place.
    
    Response includes: name, address, phone, website, hours, reviews, etc.
    """
    if not GOOGLE_PLACES_API_KEY:
        return jsonify({"error": "Google Places API not configured"}), 503
    
    try:
        # Fields to request (controls billing)
        fields = request.args.get('fields', 'name,formatted_address,formatted_phone_number,website,opening_hours,rating,reviews,price_level,geometry')
        
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
            return jsonify({"error": f"API error: {response.status_code}"}), 500
        
        data = response.json()
        
        logger.info(f"📍 Place details retrieved for: {place_id}")
        
        return jsonify({
            "result": data.get('result', {}),
            "status": data.get('status', 'OK')
        })
    
    except Exception as e:
        logger.error(f"❌ Place details error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ============================================
# GUARDIAN MODE ENDPOINTS
# ============================================

@places_bp.route('/api/guardian/find-gas', methods=['POST'])
def guardian_find_gas():
    """
    Guardian Mode: Find nearby gas stations.
    
    Request:
    {
        "latitude": 37.7749,
        "longitude": -122.4194,
        "urgency": "medium"       // low, medium, high, critical
    }
    
    Urgency affects search radius:
    - low: 5km
    - medium: 10km  
    - high: 15km
    - critical: 25km
    
    Response includes distance and ETA estimates.
    """
    if not GOOGLE_PLACES_API_KEY:
        return jsonify({"error": "Google Places API not configured"}), 503
    
    try:
        data = request.get_json()
        
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        urgency = data.get('urgency', 'medium')
        
        if not latitude or not longitude:
            return jsonify({"error": "latitude and longitude required"}), 400
        
        # Set radius based on urgency
        radius_map = {
            'low': 5000,
            'medium': 10000,
            'high': 15000,
            'critical': 25000
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
            return jsonify({"error": "API error"}), 500
        
        places_data = response.json()
        results = places_data.get('results', [])
        
        # Enhance results with distance estimates
        enhanced_results = []
        for place in results[:10]:  # Limit to top 10
            place_lat = place.get('geometry', {}).get('location', {}).get('lat')
            place_lng = place.get('geometry', {}).get('location', {}).get('lng')
            
            # Simple distance calculation (Haversine would be more accurate)
            if place_lat and place_lng:
                import math
                R = 6371  # Earth's radius in km
                dlat = math.radians(place_lat - latitude)
                dlng = math.radians(place_lng - longitude)
                a = math.sin(dlat/2)**2 + math.cos(math.radians(latitude)) * math.cos(math.radians(place_lat)) * math.sin(dlng/2)**2
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
                distance_km = R * c
                
                # Estimate drive time (assuming 40 km/h average in urban areas)
                eta_minutes = int(distance_km / 40 * 60)
                
                enhanced_results.append({
                    **place,
                    'distance_km': round(distance_km, 2),
                    'eta_minutes': eta_minutes,
                    'eta_text': f"{eta_minutes} min" if eta_minutes < 60 else f"{eta_minutes // 60}h {eta_minutes % 60}m"
                })
        
        # Sort by distance
        enhanced_results.sort(key=lambda x: x.get('distance_km', 999))
        
        logger.info(f"⛽ Guardian find-gas: {len(enhanced_results)} stations within {radius/1000}km")
        
        return jsonify({
            "results": enhanced_results,
            "urgency": urgency,
            "radius_km": radius / 1000,
            "status": places_data.get('status', 'OK')
        })
    
    except Exception as e:
        logger.error(f"❌ Guardian find-gas error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@places_bp.route('/api/guardian/find-hotel', methods=['POST'])
def guardian_find_hotel():
    """
    Guardian Mode: Find nearby hotels/lodging.
    
    Request:
    {
        "latitude": 37.7749,
        "longitude": -122.4194,
        "price_level": 2          // 1-4, optional
    }
    """
    if not GOOGLE_PLACES_API_KEY:
        return jsonify({"error": "Google Places API not configured"}), 503
    
    try:
        data = request.get_json()
        
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        price_level = data.get('price_level')
        
        if not latitude or not longitude:
            return jsonify({"error": "latitude and longitude required"}), 400
        
        params = {
            'location': f"{latitude},{longitude}",
            'radius': '15000',  # 15km
            'type': 'lodging',
            'key': GOOGLE_PLACES_API_KEY
        }
        
        response = requests.get(
            f"{GOOGLE_PLACES_BASE_URL}/nearbysearch/json",
            params=params,
            timeout=10
        )
        
        if not response.ok:
            return jsonify({"error": "API error"}), 500
        
        places_data = response.json()
        results = places_data.get('results', [])
        
        # Filter by price level if specified
        if price_level:
            results = [r for r in results if r.get('price_level', 2) <= price_level]
        
        logger.info(f"🏨 Guardian find-hotel: {len(results)} hotels found")
        
        return jsonify({
            "results": results[:10],
            "status": places_data.get('status', 'OK')
        })
    
    except Exception as e:
        logger.error(f"❌ Guardian find-hotel error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ============================================
# LOCATION CONTEXT
# ============================================

@places_bp.route('/api/location/context', methods=['POST'])
def update_location_context():
    """
    Update user's location context for AI awareness.
    
    Request:
    {
        "session_id": "abc123",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "city": "San Francisco",
        "region": "California",
        "country": "US",
        "is_in_vehicle": false,
        "accuracy": 10
    }
    
    This context is injected into AI conversations so Nate knows
    where Angela is and can provide location-aware responses.
    """
    try:
        data = request.get_json()
        
        session_id = data.get('session_id', 'default')
        
        location_context = {
            'latitude': data.get('latitude'),
            'longitude': data.get('longitude'),
            'city': data.get('city'),
            'region': data.get('region'),
            'country': data.get('country'),
            'is_in_vehicle': data.get('is_in_vehicle', False),
            'accuracy': data.get('accuracy'),
            'updated_at': datetime.now().isoformat()
        }
        
        # Store in memory (could be Redis/DB in production)
        _location_contexts[session_id] = location_context
        
        logger.info(f"📍 Location updated for {session_id}: {location_context.get('city')}, {location_context.get('region')}")
        
        return jsonify({
            "status": "ok",
            "session_id": session_id,
            "location": location_context
        })
    
    except Exception as e:
        logger.error(f"❌ Location context error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@places_bp.route('/api/location/context', methods=['GET'])
def get_location_context():
    """
    Get current location context for a session.
    
    Query params:
    - session_id: Session identifier
    """
    session_id = request.args.get('session_id', 'default')
    
    context = _location_contexts.get(session_id)
    
    if not context:
        return jsonify({
            "status": "no_location",
            "session_id": session_id,
            "location": None
        })
    
    return jsonify({
        "status": "ok",
        "session_id": session_id,
        "location": context
    })


def get_location_for_session(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Helper function for other modules to get location context.
    
    Can be called from consciousness loop to inject location into prompts.
    """
    return _location_contexts.get(session_id)


def format_location_for_prompt(session_id: str) -> str:
    """
    Format location context for injection into AI prompt.
    
    Returns a string like:
    "Angela is currently in San Francisco, California (in vehicle)"
    
    Or empty string if no location available.
    """
    context = _location_contexts.get(session_id)
    
    if not context:
        return ""
    
    parts = []
    
    city = context.get('city')
    region = context.get('region')
    country = context.get('country')
    
    if city and region:
        parts.append(f"{city}, {region}")
    elif city:
        parts.append(city)
    elif region:
        parts.append(region)
    elif country:
        parts.append(country)
    
    if not parts:
        return ""
    
    location_str = parts[0]
    
    if context.get('is_in_vehicle'):
        location_str += " (in vehicle)"
    
    return f"Current location: {location_str}"
