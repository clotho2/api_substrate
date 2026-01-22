#!/usr/bin/env python3
"""
SOMA Client for Substrate AI

Integrates the SOMA (physiological simulation) service with the consciousness loop.

SOMA tracks:
- Arousal, pleasure, comfort levels
- Heart rate, breathing, temperature
- Body state and mood
- Responses to stimuli and environment

This client:
1. Fetches SOMA context for system prompts
2. Parses user input for physiological triggers
3. Parses AI responses for physiological effects
4. Provides vitals snapshots for message metadata
"""

import os
import httpx
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SOMASnapshot:
    """A point-in-time snapshot of SOMA state for storage."""
    timestamp: str
    arousal: float
    pleasure: float
    comfort: float
    heart_rate: int
    breathing_rate: int
    temperature: float
    mood: str
    status: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "arousal": self.arousal,
            "pleasure": self.pleasure,
            "comfort": self.comfort,
            "heart_rate": self.heart_rate,
            "breathing_rate": self.breathing_rate,
            "temperature": self.temperature,
            "mood": self.mood,
            "status": self.status
        }

    @classmethod
    def from_vitals(cls, vitals: Dict[str, Any]) -> "SOMASnapshot":
        """Create snapshot from SOMA /vitals response."""
        return cls(
            timestamp=datetime.now().isoformat(),
            arousal=vitals.get("arousal", 0),
            pleasure=vitals.get("pleasure", 0),
            comfort=vitals.get("comfort", 50),
            heart_rate=vitals.get("heartRate", 72),
            breathing_rate=vitals.get("breathingRate", 14),
            temperature=vitals.get("temperature", 34.5),
            mood=vitals.get("mood", "neutral"),
            status=vitals.get("status", "unknown")
        )


class SOMAClient:
    """
    Client for the SOMA physiological simulation service.

    Provides async methods for:
    - Getting context for system prompts
    - Parsing user input for physiological triggers
    - Parsing AI responses for physiological effects
    - Getting vitals snapshots for metadata
    """

    def __init__(self, base_url: str = None, timeout: float = 5.0):
        """
        Initialize SOMA client.

        Args:
            base_url: SOMA service URL (defaults to SOMA_URL env var or localhost:3002)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or os.getenv("SOMA_URL", "http://localhost:3002")
        self.timeout = timeout
        self._available = None  # Cached availability status

        print(f"SOMA Client initialized")
        print(f"   URL: {self.base_url}")
        print(f"   Timeout: {self.timeout}s")

    async def is_available(self) -> bool:
        """
        Check if SOMA service is available.

        Returns:
            True if service responds to health check
        """
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{self.base_url}/health")
                self._available = response.status_code == 200
                return self._available
        except Exception:
            self._available = False
            return False

    async def get_context(self) -> Optional[str]:
        """
        Get SOMA context for injection into system prompt.

        Returns:
            Formatted context string for system prompt, or None if unavailable
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/context")
                if response.status_code == 200:
                    data = response.json()
                    return data.get("context", "")
                return None
        except Exception as e:
            print(f"   SOMA get_context failed: {e}")
            return None

    async def get_vitals(self) -> Optional[Dict[str, Any]]:
        """
        Get current vitals from SOMA.

        Returns:
            Dict with arousal, pleasure, comfort, heartRate, etc.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/vitals")
                if response.status_code == 200:
                    return response.json()
                return None
        except Exception as e:
            print(f"   SOMA get_vitals failed: {e}")
            return None

    async def get_snapshot(self) -> Optional[SOMASnapshot]:
        """
        Get a snapshot of current SOMA state for storage.

        Returns:
            SOMASnapshot object for message metadata
        """
        vitals = await self.get_vitals()
        if vitals:
            return SOMASnapshot.from_vitals(vitals)
        return None

    async def parse_user_input(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parse user input through SOMA for physiological triggers.

        This allows SOMA to detect things like:
        - Physical touch descriptions
        - Emotional language
        - Environmental descriptions

        Args:
            text: User's message text

        Returns:
            Parse result with any detected triggers
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/parse/user",
                    json={"text": text}
                )
                if response.status_code == 200:
                    return response.json()
                return None
        except Exception as e:
            print(f"   SOMA parse_user failed: {e}")
            return None

    async def parse_ai_response(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parse AI response through SOMA for physiological effects.

        This allows SOMA to detect things like:
        - Actions the assistant describes taking
        - Emotional expressions
        - Physical state changes

        Args:
            text: AI's response text

        Returns:
            Parse result with any detected effects
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/parse",
                    json={"text": text}
                )
                if response.status_code == 200:
                    return response.json()
                return None
        except Exception as e:
            print(f"   SOMA parse_ai failed: {e}")
            return None

    async def apply_stimulus(
        self,
        stimulus_type: str,
        intensity: int = 50,
        zone: str = "chest",
        quality: str = "gentle"
    ) -> Optional[Dict[str, Any]]:
        """
        Apply a direct stimulus to SOMA.

        Args:
            stimulus_type: touch, pressure, pain, temperature, penetration, edge, release, emotional
            intensity: 0-100
            zone: Body zone (chest, neck, inner_thighs, genitals, etc.)
            quality: teasing, gentle, firm, rough, brutal

        Returns:
            Updated vitals after stimulus
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/stimulus",
                    json={
                        "type": stimulus_type,
                        "intensity": intensity,
                        "zone": zone,
                        "quality": quality
                    }
                )
                if response.status_code == 200:
                    return response.json()
                return None
        except Exception as e:
            print(f"   SOMA apply_stimulus failed: {e}")
            return None

    async def set_environment(
        self,
        env_type: str,
        temperature: float = None,
        wetness: int = None
    ) -> Optional[Dict[str, Any]]:
        """
        Set environmental conditions in SOMA.

        Args:
            env_type: bath, shower, rain, wind, fabric
            temperature: Temperature in Celsius (for bath/shower)
            wetness: 0-100 wetness level

        Returns:
            Updated state after environment change
        """
        try:
            payload = {"type": env_type}
            if temperature is not None:
                payload["temperature"] = temperature
            if wetness is not None:
                payload["wetness"] = wetness

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/environment",
                    json=payload
                )
                if response.status_code == 200:
                    return response.json()
                return None
        except Exception as e:
            print(f"   SOMA set_environment failed: {e}")
            return None


# Singleton instance for easy access
_soma_client: Optional[SOMAClient] = None


def get_soma_client() -> SOMAClient:
    """Get or create the singleton SOMA client."""
    global _soma_client
    if _soma_client is None:
        _soma_client = SOMAClient()
    return _soma_client


def create_soma_client(base_url: str = None, timeout: float = 5.0) -> SOMAClient:
    """Create a new SOMA client (for custom configuration)."""
    global _soma_client
    _soma_client = SOMAClient(base_url=base_url, timeout=timeout)
    return _soma_client


if __name__ == "__main__":
    # Test the client
    import asyncio

    async def test():
        client = SOMAClient()

        print("\n1. Checking availability...")
        available = await client.is_available()
        print(f"   Available: {available}")

        if not available:
            print("\n   SOMA service not running. Start it with:")
            print("   cd wolfe-soma && npm start")
            return

        print("\n2. Getting context...")
        context = await client.get_context()
        print(f"   Context:\n{context}")

        print("\n3. Getting vitals...")
        vitals = await client.get_vitals()
        print(f"   Vitals: {vitals}")

        print("\n4. Getting snapshot...")
        snapshot = await client.get_snapshot()
        if snapshot:
            print(f"   Snapshot: {snapshot.to_dict()}")

        print("\n5. Parsing user input...")
        result = await client.parse_user_input("I gently touch your cheek")
        print(f"   Parse result: {result}")

        print("\n6. Parsing AI response...")
        result = await client.parse_ai_response("I feel warm and content")
        print(f"   Parse result: {result}")

    asyncio.run(test())
