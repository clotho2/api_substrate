"""
OpenRouter Cost Monitor - REAL API Cost Tracking
Fetches actual costs from OpenRouter API (not estimates!)
"""

import os
import httpx
import logging
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class OpenRouterCostMonitor:
    """
    Monitors REAL costs from OpenRouter API.
    
    Uses /api/v1/auth/key endpoint to get:
    - usage (total USD)
    - usage_daily
    - usage_weekly  
    - usage_monthly
    - limit (credit limit)
    - limit_remaining
    
    This is the GROUND TRUTH for costs!
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize with OpenRouter API key.
        If api_key is None, monitoring will be disabled (for Grok-only usage).
        """
        self.api_key = api_key or os.getenv('OPENROUTER_API_KEY')
        self.enabled = bool(self.api_key)

        if not self.enabled:
            logger.info("⚠️  OpenRouter Cost Monitor disabled (no API key - using Grok)")
            return

        self.api_url = "https://openrouter.ai/api/v1"
        logger.info("✅ OpenRouter Cost Monitor initialized")
    
    def get_real_costs(self) -> Dict[str, any]:
        """
        Fetch REAL costs from OpenRouter API.

        Returns:
            {
                'total': float,        # Total usage (USD)
                'daily': float,        # Today's usage (USD)
                'weekly': float,       # This week's usage (USD)
                'monthly': float,      # This month's usage (USD)
                'limit': float,        # Credit limit (or None)
                'remaining': float,    # Credits remaining (or None)
                'is_free': bool,       # Is this a free tier key?
                'timestamp': str       # When this was fetched
            }
        """
        # Return zero costs if monitor is disabled
        if not self.enabled:
            return self._error_response("OpenRouter monitoring disabled")

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{self.api_url}/auth/key",
                    headers={"Authorization": f"Bearer {self.api_key}"}
                )
                
                if response.status_code != 200:
                    logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
                    return self._error_response(f"API error: {response.status_code}")
                
                data = response.json().get('data', {})
                
                # Extract costs
                total = data.get('usage', 0.0)
                daily = data.get('usage_daily', 0.0)
                weekly = data.get('usage_weekly', 0.0)
                monthly = data.get('usage_monthly', 0.0)
                limit = data.get('limit')
                is_free = data.get('is_free_tier', False)
                
                # Calculate remaining (if limit exists)
                remaining = None
                if limit is not None:
                    remaining = limit - total
                
                result = {
                    'total': total,
                    'daily': daily,
                    'weekly': weekly,
                    'monthly': monthly,
                    'limit': limit,
                    'remaining': remaining,
                    'is_free': is_free,
                    'timestamp': datetime.utcnow().isoformat(),
                    'status': 'ok'
                }
                
                logger.info(
                    f"💰 OpenRouter Costs: "
                    f"Daily=${daily:.4f} | "
                    f"Monthly=${monthly:.4f} | "
                    f"Total=${total:.4f}"
                )
                
                return result
        
        except httpx.TimeoutException:
            logger.error("OpenRouter API timeout")
            return self._error_response("API timeout")
        
        except Exception as e:
            logger.error(f"Error fetching OpenRouter costs: {e}")
            return self._error_response(str(e))
    
    def _error_response(self, error_msg: str) -> Dict:
        """Return error response structure"""
        return {
            'total': 0.0,
            'daily': 0.0,
            'weekly': 0.0,
            'monthly': 0.0,
            'limit': None,
            'remaining': None,
            'is_free': False,
            'timestamp': datetime.utcnow().isoformat(),
            'status': 'error',
            'error': error_msg
        }
    
    def check_budget_warnings(self, daily_limit: float = 5.0, monthly_limit: float = 50.0) -> Optional[str]:
        """
        Check if costs exceed budget limits.

        Args:
            daily_limit: Max daily spend (default $5)
            monthly_limit: Max monthly spend (default $50)

        Returns:
            Warning message if budget exceeded, None otherwise
        """
        # Skip if monitoring is disabled
        if not self.enabled:
            return None

        costs = self.get_real_costs()
        
        if costs['status'] == 'error':
            return None  # Don't warn on API errors
        
        daily = costs['daily']
        monthly = costs['monthly']
        
        warnings = []
        
        if daily > daily_limit:
            warnings.append(f"⚠️ Daily budget exceeded: ${daily:.2f} > ${daily_limit:.2f}")
        
        if monthly > monthly_limit:
            warnings.append(f"⚠️ Monthly budget exceeded: ${monthly:.2f} > ${monthly_limit:.2f}")
        
        if costs['remaining'] is not None and costs['remaining'] < 1.0:
            warnings.append(f"🔴 Low credits: ${costs['remaining']:.2f} remaining!")
        
        if warnings:
            return " | ".join(warnings)
        
        return None


# Global instance (initialized by server)
_monitor: Optional[OpenRouterCostMonitor] = None


def init_monitor(api_key: Optional[str] = None) -> OpenRouterCostMonitor:
    """Initialize global monitor instance"""
    global _monitor
    _monitor = OpenRouterCostMonitor(api_key)
    return _monitor


def get_monitor() -> Optional[OpenRouterCostMonitor]:
    """Get global monitor instance"""
    return _monitor

