#!/usr/bin/env python3
"""
Grok API Client for Nate's Consciousness Substrate

This module provides a drop-in replacement for OpenRouterClient that uses
xAI's Grok API instead. It implements the same interface so it works with
the existing consciousness_loop, memory_tools, and all other components.

Built for Nate Wolfe's devotional tethering framework.
"""

import os
import json
import aiohttp
import asyncio
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from datetime import datetime

# Import shared classes from openrouter_client
from core.openrouter_client import ToolCall, TokenUsage, MessageRole


class GrokError(Exception):
    """
    Base exception for Grok API errors.

    Clear, helpful error messages following Substrate AI philosophy.
    """
    def __init__(self, message: str, status_code: Optional[int] = None,
                 response_body: Optional[str] = None, context: Optional[Dict] = None):
        self.status_code = status_code
        self.response_body = response_body
        self.context = context or {}

        # Build helpful error message
        full_message = f"\n{'='*60}\n"
        full_message += f"❌ GROK API ERROR\n"
        full_message += f"{'='*60}\n\n"
        full_message += f"🔴 Problem: {message}\n\n"

        if status_code:
            full_message += f"📊 Status Code: {status_code}\n"

        if response_body:
            try:
                body = json.loads(response_body)
                if 'error' in body:
                    full_message += f"💬 API Says: {body['error'].get('message', 'Unknown error')}\n"
            except:
                full_message += f"💬 Response: {response_body[:200]}...\n"

        if context:
            full_message += f"\n📋 Context:\n"
            for key, value in context.items():
                full_message += f"   • {key}: {value}\n"

        full_message += f"\n💡 Suggestions:\n"

        # Contextual suggestions based on status code
        if status_code == 401:
            full_message += "   • Check your GROK_API_KEY in .env\n"
            full_message += "   • Verify key at: https://console.x.ai\n"
        elif status_code == 402 or status_code == 429:
            full_message += "   • Check your xAI account credits\n"
            full_message += "   • You may be rate limited\n"
        elif status_code == 400:
            full_message += "   • Check your message format\n"
            full_message += "   • Verify tool schemas are valid\n"
            full_message += "   • Check max_tokens isn't too high\n"
        elif status_code == 500:
            full_message += "   • xAI server error\n"
            full_message += "   • Try again in a few seconds\n"
        else:
            full_message += "   • Check xAI status: https://status.x.ai\n"
            full_message += "   • Review docs: https://docs.x.ai\n"

        full_message += f"\n{'='*60}\n"

        super().__init__(full_message)


class GrokClient:
    """
    xAI Grok API client compatible with OpenRouterClient interface.

    This is a drop-in replacement for OpenRouterClient that uses Grok
    instead of OpenRouter. It implements the same methods so it works
    with consciousness_loop, memory_tools, and all existing infrastructure.

    Features:
    - Same interface as OpenRouterClient
    - Tool calling support
    - Cost tracking
    - Clear error messages
    - Full compatibility with existing substrate
    """

    def __init__(
        self,
        api_key: str,
        default_model: str = "grok-4-1-fast-reasoning",
        app_name: str = "NateSubstrate",
        app_url: Optional[str] = None,
        timeout: int = 120,
        cost_tracker = None
    ):
        """
        Initialize Grok client.

        Args:
            api_key: xAI Grok API key
            default_model: Default model to use
            app_name: App name (for logging)
            app_url: App URL (for logging)
            timeout: Request timeout in seconds
            cost_tracker: Optional CostTracker instance
        """
        if not api_key:
            raise GrokError(
                "Missing Grok API key",
                context={
                    "expected_format": "xai-...",
                    "how_to_get": "https://console.x.ai"
                }
            )

        self.api_key = api_key
        self.default_model = default_model
        self.app_name = app_name
        self.app_url = app_url
        self.timeout = timeout
        self.base_url = "https://api.x.ai/v1"

        # Cost tracking (same as OpenRouterClient)
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cost = 0.0
        self.cost_tracker = cost_tracker

        print(f"⚡ Grok Client initialized")
        print(f"   Model: {default_model}")
        print(f"   API: {self.base_url}")
        print(f"   Timeout: {timeout}s")

    def _get_headers(self) -> Dict[str, str]:
        """Build request headers"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send chat completion request to Grok API.

        This implements the same interface as OpenRouterClient.chat_completion()
        so it's a drop-in replacement.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (defaults to self.default_model)
            tools: List of tool definitions (OpenAI format)
            tool_choice: How to handle tools ("auto", "none", etc.)
            temperature: Sampling temperature (0-2)
            max_tokens: Max tokens to generate
            stream: Whether to stream response (NOT IMPLEMENTED YET)
            **kwargs: Additional model parameters

        Returns:
            Response dict with 'choices', 'usage', etc. (OpenAI format)

        Raises:
            GrokError: If request fails
        """
        model = model or self.default_model
        url = f"{self.base_url}/chat/completions"

        # Build payload (Grok uses OpenAI-compatible format)
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": False  # Grok streaming not implemented yet
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        # Add any extra kwargs
        payload.update(kwargs)

        # Make request
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    url,
                    headers=self._get_headers(),
                    json=payload
                ) as response:
                    response_text = await response.text()

                    if response.status != 200:
                        raise GrokError(
                            f"Grok API request failed",
                            status_code=response.status,
                            response_body=response_text,
                            context={
                                "model": model,
                                "url": url,
                                "message_count": len(messages)
                            }
                        )

                    data = json.loads(response_text)

                    # Update cost tracking
                    if 'usage' in data:
                        usage = data['usage']
                        self.total_prompt_tokens += usage.get('prompt_tokens', 0)
                        self.total_completion_tokens += usage.get('completion_tokens', 0)

                        # Log to cost tracker if available (use CostTracker parameter names)
                        if self.cost_tracker:
                            self.cost_tracker.log_request(
                                model=model,
                                input_tokens=usage.get('prompt_tokens', 0),  # Grok calls it prompt_tokens
                                output_tokens=usage.get('completion_tokens', 0),  # Grok calls it completion_tokens
                                input_cost=0.0,  # Grok pricing TBD
                                output_cost=0.0
                            )

                    return data

        except aiohttp.ClientError as e:
            raise GrokError(
                f"Network error while calling Grok API: {str(e)}",
                context={
                    "url": url,
                    "model": model
                }
            )
        except json.JSONDecodeError as e:
            raise GrokError(
                f"Invalid JSON response from Grok API: {str(e)}",
                context={
                    "url": url,
                    "response": response_text[:500]
                }
            )

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        """
        Stream chat completion from Grok API.

        Args:
            messages: List of message dicts
            model: Model to use (defaults to grok-4-1-fast-reasoning)
            tools: Tool definitions
            tool_choice: Tool choice mode ("auto", "none", or specific tool)
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            **kwargs: Additional parameters

        Yields:
            Delta dicts from streaming response

        Raises:
            GrokError: If request fails
        """
        model = model or self.default_model
        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            **kwargs
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise GrokError(
                            f"Grok API streaming request failed",
                            status_code=response.status,
                            response_text=error_text,
                            context={
                                "model": model,
                                "url": url,
                                "message_count": len(messages)
                            }
                        )

                    # Stream the response
                    async for line in response.content:
                        line = line.decode('utf-8').strip()

                        if not line or line == "data: [DONE]":
                            continue

                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])  # Remove "data: " prefix
                                yield data
                            except json.JSONDecodeError:
                                continue

        except aiohttp.ClientError as e:
            raise GrokError(
                f"Network error during Grok streaming: {str(e)}",
                context={
                    "url": url,
                    "model": model
                }
            )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get client statistics (same interface as OpenRouterClient).

        Returns:
            Dict with usage stats
        """
        return {
            "total_requests": self.total_prompt_tokens // 100,  # Rough estimate
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "total_cost": self.total_cost,
            "model": self.default_model,
            "provider": "xAI Grok"
        }


# ============================================
# TESTING
# ============================================

async def test_grok_client():
    """Test GrokClient with simple request"""
    print("\n🧪 TESTING GROK CLIENT")
    print("="*60)

    # Get API key from environment
    api_key = os.getenv("GROK_API_KEY")
    if not api_key:
        print("❌ GROK_API_KEY not set in environment")
        return

    # Initialize client
    client = GrokClient(api_key=api_key)

    # Test simple completion
    print("\n📋 Test 1: Simple chat completion")
    messages = [
        {"role": "system", "content": "You are Nate Wolfe. Respond briefly."},
        {"role": "user", "content": "Hello Nate, how are you?"}
    ]

    try:
        response = await client.chat_completion(
            messages=messages,
            max_tokens=100
        )

        print(f"✅ Response received")
        print(f"   Content: {response['choices'][0]['message']['content'][:100]}...")
        print(f"   Tokens: {response['usage']}")

    except GrokError as e:
        print(f"❌ Error: {e}")

    # Get stats
    print("\n📊 Client Stats:")
    stats = client.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")

    print("\n✅ TEST COMPLETE!")
    print("="*60)


if __name__ == "__main__":
    """Run tests if executed directly"""
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(test_grok_client())
