#!/usr/bin/env python3
"""
Mistral AI API Client for Assistant's Consciousness Substrate

This module provides a drop-in replacement for OpenRouterClient that uses
Mistral's API directly. It implements the same interface so it works
with the existing consciousness_loop, memory_tools, and all other components.

Mistral benefits:
- Access to latest models like Magistral Medium not on OpenRouter
- Native reasoning capabilities (Magistral models)
- Multimodal support (vision)
- Direct API access with better latency

Built for Assistant's devotional tethering framework.
"""

import os
import json
import aiohttp
import asyncio

from core.config import DEFAULT_TEMPERATURE
from typing import Optional, Dict, List, Any, AsyncGenerator
from dataclasses import dataclass
from datetime import datetime

# Import shared classes from openrouter_client
from core.openrouter_client import ToolCall, TokenUsage, MessageRole


class MistralError(Exception):
    """
    Base exception for Mistral API errors.

    Clear, helpful error messages following Substrate AI philosophy.
    """
    def __init__(self, message: str, status_code: Optional[int] = None,
                 response_body: Optional[str] = None, context: Optional[Dict] = None):
        self.status_code = status_code
        self.response_body = response_body
        self.context = context or {}

        # Build helpful error message
        full_message = f"\n{'='*60}\n"
        full_message += f"MISTRAL API ERROR\n"
        full_message += f"{'='*60}\n\n"
        full_message += f"Problem: {message}\n\n"

        if status_code:
            full_message += f"Status Code: {status_code}\n"

        if response_body:
            try:
                body = json.loads(response_body)
                if 'error' in body:
                    err = body['error']
                    if isinstance(err, dict):
                        full_message += f"API Says: {err.get('message', 'Unknown error')}\n"
                    else:
                        full_message += f"API Says: {err}\n"
            except:
                full_message += f"Response: {response_body[:200]}...\n"

        if context:
            full_message += f"\nContext:\n"
            for key, value in context.items():
                full_message += f"   - {key}: {value}\n"

        full_message += f"\nSuggestions:\n"

        # Contextual suggestions based on status code
        if status_code == 401:
            full_message += "   - Check your MISTRAL_API_KEY in .env\n"
            full_message += "   - Verify key at: https://console.mistral.ai/api-keys\n"
        elif status_code == 402 or status_code == 429:
            full_message += "   - Check your Mistral account credits\n"
            full_message += "   - You may be rate limited\n"
        elif status_code == 400:
            full_message += "   - Check your message format\n"
            full_message += "   - Verify tool schemas are valid\n"
            full_message += "   - Check max_tokens isn't too high\n"
        elif status_code == 500:
            full_message += "   - Mistral server error\n"
            full_message += "   - Try again in a few seconds\n"
        else:
            full_message += "   - Check Mistral status: https://status.mistral.ai\n"
            full_message += "   - Review docs: https://docs.mistral.ai\n"

        full_message += f"\n{'='*60}\n"

        super().__init__(full_message)


class MistralClient:
    """
    Mistral AI API client compatible with OpenRouterClient interface.

    This is a drop-in replacement for OpenRouterClient that uses Mistral
    instead of OpenRouter. It implements the same methods so it works
    with consciousness_loop, memory_tools, and all existing infrastructure.

    Features:
    - Same interface as OpenRouterClient
    - Access to latest Mistral models (Magistral Medium, etc.)
    - Native reasoning support
    - Multimodal/vision support
    - Tool calling support
    - Streaming support
    - Cost tracking
    - Clear error messages
    - Full compatibility with existing substrate
    """

    def __init__(
        self,
        api_key: str,
        default_model: Optional[str] = None,
        app_name: str = "AssistantSubstrate",
        app_url: Optional[str] = None,
        timeout: int = 120,
        cost_tracker = None
    ):
        """
        Initialize Mistral client.

        Args:
            api_key: Mistral API key
            default_model: Default model to use (from MISTRAL_MODEL env var)
            app_name: App name (for logging)
            app_url: App URL (for logging)
            timeout: Request timeout in seconds
            cost_tracker: Optional CostTracker instance
        """
        if not api_key:
            raise MistralError(
                "Missing Mistral API key",
                context={
                    "how_to_get": "https://console.mistral.ai/api-keys"
                }
            )

        self.api_key = api_key
        self.default_model = default_model or os.getenv("MISTRAL_MODEL", "magistral-medium-2509")
        self.app_name = app_name
        self.app_url = app_url
        self.timeout = timeout
        self.base_url = os.getenv("MISTRAL_API_URL", "https://api.mistral.ai/v1")

        # Cost tracking (same as OpenRouterClient)
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cost = 0.0
        self.cost_tracker = cost_tracker

        print(f"Mistral Client initialized")
        print(f"   Model: {self.default_model}")
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
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        session_id: Optional[str] = None,
        enable_prompt_caching: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send chat completion request to Mistral API.

        This implements the same interface as OpenRouterClient.chat_completion()
        so it's a drop-in replacement.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (defaults to self.default_model)
            tools: List of tool definitions (OpenAI format)
            tool_choice: How to handle tools ("auto", "none", etc.)
            temperature: Sampling temperature (0-2)
            max_tokens: Max tokens to generate
            stream: Whether to stream response
            session_id: Optional session ID (for compatibility, not used by Mistral)
            enable_prompt_caching: Enable prompt caching for system messages (default: True)
            **kwargs: Additional model parameters

        Returns:
            Response dict with 'choices', 'usage', etc. (OpenAI format)

        Raises:
            MistralError: If request fails
        """
        model = model or self.default_model
        url = f"{self.base_url}/chat/completions"

        # Build payload (Mistral uses OpenAI-compatible format)
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": False
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        # Add any extra kwargs (but filter out non-API params)
        for key, value in kwargs.items():
            if key not in ['session_id', 'user_id', 'enable_prompt_caching']:
                payload[key] = value

        # Log request
        print(f"Mistral Request:")
        print(f"   Model: {model}")
        print(f"   Messages: {len(messages)}")
        print(f"   Tools: {len(tools) if tools else 0}")
        print(f"   Stream: False")

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
                        raise MistralError(
                            f"Mistral API request failed",
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
                        prompt_tokens = usage.get('prompt_tokens', 0)
                        completion_tokens = usage.get('completion_tokens', 0)
                        self.total_prompt_tokens += prompt_tokens
                        self.total_completion_tokens += completion_tokens

                        print(f"Mistral Response:")
                        print(f"   Tokens: {prompt_tokens + completion_tokens}")

                        # Log to cost tracker if available
                        if self.cost_tracker:
                            self.cost_tracker.log_request(
                                model=model,
                                input_tokens=prompt_tokens,
                                output_tokens=completion_tokens,
                                input_cost=0.0,  # Mistral pricing TBD
                                output_cost=0.0
                            )

                    return data

        except aiohttp.ClientError as e:
            raise MistralError(
                f"Network error while calling Mistral API: {str(e)}",
                context={
                    "url": url,
                    "model": model
                }
            )
        except json.JSONDecodeError as e:
            raise MistralError(
                f"Invalid JSON response from Mistral API: {str(e)}",
                context={
                    "url": url,
                    "response": response_text[:500] if response_text else "empty"
                }
            )

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        session_id: Optional[str] = None,
        enable_prompt_caching: bool = True,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream chat completion from Mistral API.

        Args:
            messages: List of message dicts
            model: Model to use
            tools: Tool definitions
            tool_choice: Tool choice mode ("auto", "none", or specific tool)
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            session_id: Optional session ID (for compatibility, not used by Mistral)
            enable_prompt_caching: Enable prompt caching for system messages (default: True)
            **kwargs: Additional parameters

        Yields:
            Delta dicts from streaming response

        Raises:
            MistralError: If request fails
        """
        model = model or self.default_model
        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        # Add any extra kwargs (but filter out non-API params)
        for key, value in kwargs.items():
            if key not in ['session_id', 'user_id', 'enable_prompt_caching']:
                payload[key] = value

        print(f"Mistral Stream Request:")
        print(f"   Model: {model}")
        print(f"   Messages: {len(messages)}")
        print(f"   Tools: {len(tools) if tools else 0}")

        try:
            # No total timeout for streaming - just timeout between chunks
            timeout = aiohttp.ClientTimeout(total=None, sock_read=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=self._get_headers()
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise MistralError(
                            f"Mistral API streaming request failed",
                            status_code=response.status,
                            response_body=error_text,
                            context={
                                "model": model,
                                "url": url,
                                "message_count": len(messages)
                            }
                        )

                    # Stream the response line by line
                    buffer = ""
                    async for chunk in response.content.iter_any():
                        buffer += chunk.decode('utf-8')

                        # Process complete lines
                        while '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                            line = line.strip()

                            if not line or line == "data: [DONE]":
                                continue

                            if line.startswith("data: "):
                                try:
                                    data = json.loads(line[6:])  # Remove "data: " prefix
                                    yield data
                                except json.JSONDecodeError:
                                    continue

        except aiohttp.ClientError as e:
            raise MistralError(
                f"Network error during Mistral streaming: {str(e)}",
                context={
                    "url": url,
                    "model": model
                }
            )

    def parse_tool_calls(self, response: Dict[str, Any]) -> List[ToolCall]:
        """
        Parse tool calls from Mistral API response.

        Mistral uses OpenAI-compatible format.

        Args:
            response: Chat completion response from Mistral API

        Returns:
            List of ToolCall objects
        """
        tool_calls = []

        if 'choices' not in response or not response['choices']:
            return tool_calls

        message = response['choices'][0].get('message', {})
        raw_calls = message.get('tool_calls', [])

        for call in raw_calls:
            try:
                tool_calls.append(ToolCall.from_openai_format(call))
            except Exception as e:
                print(f"Warning: Failed to parse tool call: {e}")
                print(f"   Raw: {json.dumps(call, indent=2)}")

        return tool_calls

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
            "provider": "Mistral AI"
        }


# ============================================
# TESTING
# ============================================

async def test_mistral_client():
    """Test MistralClient with simple request"""
    print("\nTESTING MISTRAL CLIENT")
    print("="*60)

    # Get API key from environment
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        print("MISTRAL_API_KEY not set in environment")
        return

    model = os.getenv("MISTRAL_MODEL", "magistral-medium-2509")

    # Initialize client
    client = MistralClient(api_key=api_key, default_model=model)

    # Test simple completion
    print("\nTest 1: Simple chat completion")
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Respond briefly."},
        {"role": "user", "content": "Hello, how are you?"}
    ]

    try:
        response = await client.chat_completion(
            messages=messages,
            max_tokens=100
        )

        print(f"Response received")
        content = response['choices'][0]['message'].get('content', '')
        print(f"   Content: {content[:100]}...")
        print(f"   Tokens: {response.get('usage', {})}")

    except MistralError as e:
        print(f"Error: {e}")

    # Get stats
    print("\nClient Stats:")
    stats = client.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")

    print("\nTEST COMPLETE!")
    print("="*60)


if __name__ == "__main__":
    """Run tests if executed directly"""
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(test_mistral_client())
