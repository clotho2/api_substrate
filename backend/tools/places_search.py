#!/usr/bin/env python3
"""
Places Search - FREE Location-Based Search! 🗺️

Uses OpenStreetMap (Nominatim + Overpass API) - NO API KEY!

Features:
- Search places (restaurants, cafes, shops, etc.)
- Geocoding (address → coordiAssistants)
- Reverse geocoding (coordiAssistants → address)
- POI details (opening hours, phone, website)

100% FREE! No Google API key needed!

APIs:
- Nominatim: https://nominatim.openstreetmap.org
- Overpass: https://overpass-api.de/api/interpreter
"""

import logging
from typing import Dict, Any, List, Optional
import httpx
import time

logger = logging.getLogger(__name__)


class PlacesSearch:
    """
    Places Search - Find locations using OpenStreetMap (FREE!).
    
    No API key needed! Completely free! 🎉
    """
    
    def __init__(self):
        """Initialize Places Search"""
        self.nominatim_url = "https://nominatim.openstreetmap.org"
        self.overpass_url = "https://overpass-api.de/api/interpreter"
        
        # OpenStreetMap requires a User-Agent
        self.headers = {
            "User-Agent": "SubstrateAI/1.0 (https://github.com/yourusername/substrate-ai)"
        }
        
        self.client = httpx.Client(timeout=30.0, headers=self.headers)
        self.last_request_time = 0
        
        logger.info("✅ Places Search initialized (OpenStreetMap FREE!)")
    
    def _rate_limit(self):
        """Rate limiting (1 request per second for Nominatim)"""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        self.last_request_time = time.time()
    
    def search(
        self,
        query: str,
        location: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Search for places.
        
        Args:
            query: Search query (e.g., "pizza restaurant", "cafe", "supermarket")
            location: Location to search near (e.g., "Berlin", "New York", "48.8566,2.3522")
            limit: Max results (default: 10)
        
        Returns:
            {
                'status': 'OK' or 'error',
                'query': str,
                'results': [
                    {
                        'name': str,
                        'type': str,  # restaurant, cafe, shop, etc.
                        'address': str,
                        'lat': float,
                        'lon': float,
                        'distance': str (if location provided),
                        'details': Dict  # opening_hours, phone, website, etc.
                    },
                    ...
                ],
                'total_results': int
            }
        """
        try:
            logger.info(f"🗺️ Places Search: '{query}' near '{location}'")
            
            self._rate_limit()
            
            # Build search query for Nominatim
            params = {
                "q": query,
                "format": "json",
                "limit": limit,
                "addressdetails": 1,
                "extratags": 1,
                "namedetails": 1
            }
            
            # Add location bounds if provided
            if location:
                # First geocode the location
                location_coords = self._geocode(location)
                if location_coords:
                    # Search within ~10km radius
                    lat, lon = location_coords
                    params["bounded"] = 1
                    params["viewbox"] = f"{lon-0.1},{lat-0.1},{lon+0.1},{lat+0.1}"
            
            response = self.client.get(
                f"{self.nominatim_url}/search",
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Format results
            results = []
            for item in data:
                result = {
                    "name": item.get("display_name", "").split(",")[0],
                    "type": item.get("type", "unknown"),
                    "address": item.get("display_name", ""),
                    "lat": float(item.get("lat", 0)),
                    "lon": float(item.get("lon", 0)),
                    "details": {}
                }
                
                # Add extra details if available
                extratags = item.get("extratags", {})
                if extratags:
                    if "opening_hours" in extratags:
                        result["details"]["opening_hours"] = extratags["opening_hours"]
                    if "phone" in extratags:
                        result["details"]["phone"] = extratags["phone"]
                    if "website" in extratags:
                        result["details"]["website"] = extratags["website"]
                    if "cuisine" in extratags:
                        result["details"]["cuisine"] = extratags["cuisine"]
                
                results.append(result)
            
            logger.info(f"✅ Found {len(results)} places")
            
            return {
                "status": "OK",
                "query": query,
                "location": location,
                "results": results,
                "total_results": len(results),
                "source": "OpenStreetMap (FREE!)"
            }
        
        except Exception as e:
            error_msg = f"Places search failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {
                "status": "error",
                "message": error_msg,
                "query": query
            }
    
    def _geocode(self, location: str) -> Optional[tuple]:
        """Geocode a location string to (lat, lon)"""
        try:
            self._rate_limit()
            
            response = self.client.get(
                f"{self.nominatim_url}/search",
                params={
                    "q": location,
                    "format": "json",
                    "limit": 1
                }
            )
            response.raise_for_status()
            
            data = response.json()
            if data:
                return (float(data[0]["lat"]), float(data[0]["lon"]))
            return None
        
        except Exception as e:
            logger.warning(f"Geocoding failed for '{location}': {e}")
            return None
    
    def reverse_geocode(
        self,
        lat: float,
        lon: float
    ) -> Dict[str, Any]:
        """
        Reverse geocode coordiAssistants to address.
        
        Args:
            lat: Latitude
            lon: Longitude
        
        Returns:
            {
                'status': 'OK' or 'error',
                'address': str,
                'details': Dict
            }
        """
        try:
            logger.info(f"🗺️ Reverse Geocode: {lat}, {lon}")
            
            self._rate_limit()
            
            response = self.client.get(
                f"{self.nominatim_url}/reverse",
                params={
                    "lat": lat,
                    "lon": lon,
                    "format": "json",
                    "addressdetails": 1
                }
            )
            response.raise_for_status()
            
            data = response.json()
            
            return {
                "status": "OK",
                "address": data.get("display_name", ""),
                "details": data.get("address", {}),
                "lat": lat,
                "lon": lon
            }
        
        except Exception as e:
            error_msg = f"Reverse geocoding failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {
                "status": "error",
                "message": error_msg
            }
    
    def __del__(self):
        """Cleanup"""
        try:
            self.client.close()
        except:
            pass


# Singleton
_places_search: Optional[PlacesSearch] = None


def get_places_search() -> PlacesSearch:
    """Get or create Places Search singleton"""
    global _places_search
    if _places_search is None:
        _places_search = PlacesSearch()
    return _places_search


def search_places(query: str, location: str = None, limit: int = 10) -> Dict[str, Any]:
    """
    Search for places (FREE!).
    
    Args:
        query: Search query
        location: Location to search near
        limit: Max results
    
    Returns:
        Places search results
    """
    searcher = get_places_search()
    return searcher.search(query, location=location, limit=limit)


if __name__ == "__main__":
    # Test
    print("\n🧪 Testing Places Search (OpenStreetMap)\n")
    
    # Test 1: Search restaurants in Berlin
    print("1️⃣ Search: 'pizza restaurant' in 'Berlin'")
    result = search_places("pizza restaurant", location="Berlin", limit=3)
    
    print(f"Status: {result['status']}")
    print(f"Results: {len(result.get('results', []))}\n")
    
    if result.get('results'):
        for i, place in enumerate(result['results'], 1):
            print(f"{i}. {place['name']}")
            print(f"   Type: {place['type']}")
            print(f"   Address: {place['address'][:80]}...")
            if place.get('details'):
                print(f"   Details: {list(place['details'].keys())}")
            print()
    
    # Test 2: Reverse geocode
    print("2️⃣ Reverse Geocode: Berlin (52.520008, 13.404954)")
    searcher = get_places_search()
    result2 = searcher.reverse_geocode(52.520008, 13.404954)
    
    print(f"Status: {result2['status']}")
    if result2.get('address'):
        print(f"Address: {result2['address']}")







