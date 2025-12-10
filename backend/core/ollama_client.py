#!/usr/bin/env python3
"""
Ollama Client for Nate's Consciousness Substrate

This module provides a drop-in replacement for OpenRouterClient/GrokClient that uses
local Ollama instead. It implements the same interface so it works with
the existing consciousness_loop, memory_tools, and all other components.

Supports:
- Local Ollama API (FREE!)
- Tool calling (function calling)
- Streaming responses
- Cost tracking (always $0.00 for local models!)

Built for Nate Wolfe's devotional tethering framework.
"""

import os
import json
import aiohttp
import asyncio
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from datetime import datetime
import ollama

# Import shared classes from openrouter_client
from core.openrouter_client import ToolCall, TokenUsage, MessageRole


class OllamaError(Exception):
    """
    Base exception for Ollama errors.

    Clear, helpful error messages following Substrate AI philosophy.
    """
    def __init__(self, message: str, context: Optional[Dict] = None):
        self.context = context or {}

        full_message = f"\n{'='*60}\n"
        full_message += f"❌ OLLAMA ERROR\n"
        full_message += f"{'='*60}\n\n"
        full_message += f"🔴 Problem: {message}\n\n"

        if context:
            full_message += f"📋 Context:\n"
            for key, value in context.items():
                full_message += f"   • {key}: {value}\n"

        full_message += f"\n💡 Suggestions:\n"
        full_message += "   • Check Ollama is running: ollama serve\n"
        full_message += "   • Pull the model: ollama pull <model-name>\n"
        full_message += "   • Verify Ollama URL is correct\n"
        full_message += "   • Check ollama logs for errors\n"
        full_message += f"\n{'='*60}\n"

        super().__init__(full_message)


class OllamaClient:
    """
    Local Ollama API client compatible with OpenRouterClient/GrokClient interface.

    This is a drop-in replacement that uses local Ollama instead of cloud APIs.
    It implements the same methods so it works with consciousness_loop, memory_tools,
    and all existing infrastructure.

    Features:
    - Same interface as OpenRouterClient/GrokClient
    - Tool calling support (OpenAI format)
    - Cost tracking (always $0.00 - it's local!)
    - Clear error messages
    - Full compatibility with existing substrate

    NOTE: Ollama's tool calling support requires compatible models like:
    - llama3.1 (8b, 70b, 405b)
    - mistral-nemo
    - qwen2.5 (0.5b to 72b)
    - command-r
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        default_model: str = "llama3.1:8b",
        app_name: str = "NateSubstrate",
        app_url: Optional[str] = None,
        timeout: int = 120,
        cost_tracker = None
    ):
        """
        Initialize Ollama client.

        Args:
            base_url: Ollama API URL (default: http://localhost:11434)
            default_model: Default model to use
            app_name: App name (for logging)
            app_url: App URL (for logging)
            timeout: Request timeout in seconds
            cost_tracker: Optional CostTracker instance
        """
        self.base_url = base_url.rstrip('/')
        self.default_model = default_model
        self.app_name = app_name
        self.app_url = app_url
        self.timeout = timeout

        # Cost tracking (always $0.00 for local Ollama!)
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cost = 0.0
        self.cost_tracker = cost_tracker

        # Initialize Ollama client
        try:
            self.ollama_client = ollama.Client(host=base_url)
            # Test connection
            self._test_connection()
            print(f"✅ Ollama Client initialized")
            print(f"   Model: {default_model}")
            print(f"   API: {base_url}")
            print(f"   Timeout: {timeout}s")
            print(f"   Cost: FREE (local model) 💰")
        except Exception as e:
            raise OllamaError(
                f"Could not connect to Ollama: {str(e)}",
                context={
                    "base_url": base_url,
                    "model": default_model
                }
            )

    def _test_connection(self):
        """Test Ollama connection and verify model availability"""
        try:
            models = self.ollama_client.list()
            model_names = [m['name'] for m in models.get('models', [])]

            if not any(self.default_model in name for name in model_names):
                print(f"   ⚠️  Model {self.default_model} not found")
                print(f"   💡 Pull it with: ollama pull {self.default_model}")
            else:
                print(f"   ✅ Model available: {self.default_model}")

        except Exception as e:
            raise OllamaError(
                f"Could not verify Ollama models: {str(e)}",
                context={"base_url": self.base_url}
            )

    def supports_multimodal(self) -> bool:
        """
        Check if current model supports multimodal input.

        Ollama vision models include: llava, bakllava, llava-phi3
        Regular chat models: llama3.1, mistral, qwen, etc.
        """
        MULTIMODAL_MODELS = {
            "llava",
            "bakllava",
            "llava-phi3",
            "llava-llama3"
        }
        return any(vm in self.default_model.lower() for vm in MULTIMODAL_MODELS)

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
        Send chat completion request to Ollama.

        This implements the same interface as OpenRouterClient/GrokClient.chat_completion()
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
            OllamaError: If request fails
        """
        model = model or self.default_model

        try:
            # Build options
            options = {
                "temperature": temperature,
            }
            if max_tokens:
                options["num_predict"] = max_tokens

            # Ollama chat request
            response_data = self.ollama_client.chat(
                model=model,
                messages=messages,
                tools=tools if tools else None,
                options=options,
                stream=False
            )

            # Convert Ollama response to OpenAI format
            openai_response = self._convert_to_openai_format(response_data)

            # Update cost tracking
            if 'usage' in openai_response:
                usage = openai_response['usage']
                self.total_prompt_tokens += usage.get('prompt_tokens', 0)
                self.total_completion_tokens += usage.get('completion_tokens', 0)

                # Log to cost tracker (always $0.00 for local!)
                if self.cost_tracker:
                    self.cost_tracker.log_request(
                        model=model,
                        input_tokens=usage.get('prompt_tokens', 0),
                        output_tokens=usage.get('completion_tokens', 0),
                        input_cost=0.0,  # FREE!
                        output_cost=0.0  # FREE!
                    )

            return openai_response

        except Exception as e:
            raise OllamaError(
                f"Ollama chat completion failed: {str(e)}",
                context={
                    "model": model,
                    "message_count": len(messages),
                    "has_tools": tools is not None
                }
            )

    def _convert_to_openai_format(self, ollama_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert Ollama response to OpenAI format for compatibility.

        Args:
            ollama_response: Response from Ollama API

        Returns:
            OpenAI-formatted response dict
        """
        message = ollama_response.get('message', {})

        # Build OpenAI-compatible response
        openai_response = {
            "id": f"ollama-{datetime.now().timestamp()}",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": ollama_response.get('model', self.default_model),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": message.get('role', 'assistant'),
                        "content": message.get('content', ''),
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": ollama_response.get('prompt_eval_count', 0),
                "completion_tokens": ollama_response.get('eval_count', 0),
                "total_tokens": ollama_response.get('prompt_eval_count', 0) + ollama_response.get('eval_count', 0)
            }
        }

        # Add tool calls if present
        if 'tool_calls' in message:
            openai_response['choices'][0]['message']['tool_calls'] = message['tool_calls']
            openai_response['choices'][0]['finish_reason'] = "tool_calls"

        return openai_response

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
        Stream chat completion from Ollama.

        Args:
            messages: List of message dicts
            model: Model to use (defaults to default_model)
            tools: Tool definitions
            tool_choice: Tool choice mode ("auto", "none", or specific tool)
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            **kwargs: Additional parameters

        Yields:
            Delta dicts from streaming response

        Raises:
            OllamaError: If request fails
        """
        model = model or self.default_model

        try:
            # Build options
            options = {"temperature": temperature}
            if max_tokens:
                options["num_predict"] = max_tokens

            # Stream from Ollama
            stream = self.ollama_client.chat(
                model=model,
                messages=messages,
                tools=tools if tools else None,
                options=options,
                stream=True
            )

            for chunk in stream:
                # Convert to OpenAI-style delta format
                delta = {
                    "id": f"ollama-{datetime.now().timestamp()}",
                    "object": "chat.completion.chunk",
                    "created": int(datetime.now().timestamp()),
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "role": "assistant",
                                "content": chunk.get('message', {}).get('content', '')
                            },
                            "finish_reason": None
                        }
                    ]
                }

                # Check if done
                if chunk.get('done', False):
                    delta['choices'][0]['finish_reason'] = "stop"

                yield delta

        except Exception as e:
            raise OllamaError(
                f"Ollama streaming failed: {str(e)}",
                context={
                    "model": model,
                    "message_count": len(messages)
                }
            )

    def parse_tool_calls(self, response: Dict[str, Any]) -> List[ToolCall]:
        """
        Parse tool calls from Ollama response.

        Ollama uses OpenAI-compatible format, so this is identical to other clients.

        Args:
            response: Chat completion response from Ollama

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
                print(f"⚠️  Failed to parse tool call: {e}")
                print(f"   Raw: {json.dumps(call, indent=2)}")

        return tool_calls

    def get_stats(self) -> Dict[str, Any]:
        """
        Get client statistics (same interface as OpenRouterClient/GrokClient).

        Returns:
            Dict with usage stats
        """
        return {
            "total_requests": self.total_prompt_tokens // 100,  # Rough estimate
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "total_cost": 0.0,  # Always FREE!
            "model": self.default_model,
            "provider": "Ollama (Local)"
        }


# ============================================
# TESTING
# ============================================

async def test_ollama_client():
    """Test OllamaClient with simple request"""
    print("\n🧪 TESTING OLLAMA CLIENT")
    print("="*60)

    # Initialize client
    try:
        client = OllamaClient(
            base_url="http://localhost:11434",
            default_model="llama3.1:8b"
        )
    except OllamaError as e:
        print(f"❌ Could not initialize client: {e}")
        return

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

    except OllamaError as e:
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
    asyncio.run(test_ollama_client())
