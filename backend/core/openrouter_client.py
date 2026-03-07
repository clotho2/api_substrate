#!/usr/bin/env python3
"""
OpenRouter API Client for Substrate AI

This module provides direct, transparent access to OpenRouter's API.
No black boxes, full control, clear error messages.

Built with attention to detail.
"""

import os
import json
import time
import codecs
import aiohttp
import asyncio

from core.config import DEFAULT_TEMPERATURE
from typing import Optional, Dict, List, Any, AsyncGenerator
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class MessageRole(str, Enum):
    """Message roles for chat completion"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class TokenUsage:
    """Token usage tracking for cost calculation"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    
    def calculate_cost(self, model_pricing: Dict[str, float]) -> float:
        """
        Calculate cost in USD based on model pricing.
        
        Args:
            model_pricing: Dict with 'prompt' and 'completion' prices per M tokens
            
        Returns:
            Cost in USD
        """
        prompt_cost = (self.prompt_tokens / 1_000_000) * model_pricing.get('prompt', 0)
        completion_cost = (self.completion_tokens / 1_000_000) * model_pricing.get('completion', 0)
        return prompt_cost + completion_cost


@dataclass
class ToolCall:
    """Parsed tool call from LLM response"""
    id: str
    name: str
    arguments: Dict[str, Any]
    
    @classmethod
    def from_openai_format(cls, tool_call: Dict) -> 'ToolCall':
        """Parse tool call from OpenAI format"""
        return cls(
            id=tool_call['id'],
            name=tool_call['function']['name'],
            arguments=json.loads(tool_call['function']['arguments'])
        )


class OpenRouterError(Exception):
    """
    Base exception for OpenRouter errors.
    
    PHILOSOPHY: Error messages should be HELPFUL, not cryptic.
    Each error tells you:
    1. What went wrong
    2. Why it happened
    3. How to fix it
    """
    def __init__(self, message: str, status_code: Optional[int] = None, 
                 response_body: Optional[str] = None, context: Optional[Dict] = None):
        self.status_code = status_code
        self.response_body = response_body
        self.context = context or {}
        
        # Build helpful error message
        full_message = f"\n{'='*60}\n"
        full_message += f"❌ OPENROUTER ERROR\n"
        full_message += f"{'='*60}\n\n"
        full_message += f"🔴 Problem: {message}\n\n"
        
        if status_code:
            full_message += f"📊 Status Code: {status_code}\n"
            
        if response_body:
            try:
                body = json.loads(response_body)
                if 'error' in body:
                    error_obj = body['error']
                    full_message += f"💬 API Says: {error_obj.get('message', 'Unknown error')}\n"
                    # Log full error details (metadata, code, type) for debugging
                    if error_obj.get('code'):
                        full_message += f"🔢 Error Code: {error_obj['code']}\n"
                    if error_obj.get('type'):
                        full_message += f"🏷️  Error Type: {error_obj['type']}\n"
                    if error_obj.get('metadata'):
                        full_message += f"📎 Provider Details: {json.dumps(error_obj['metadata'], indent=2)}\n"
                    # Show any other fields we might be missing
                    known_keys = {'message', 'code', 'type', 'metadata'}
                    extra_keys = set(error_obj.keys()) - known_keys
                    if extra_keys:
                        for key in extra_keys:
                            full_message += f"   🔍 {key}: {error_obj[key]}\n"
                else:
                    # No 'error' key - dump the whole body
                    full_message += f"💬 Raw Response: {json.dumps(body, indent=2)[:500]}\n"
            except:
                full_message += f"💬 Response: {response_body[:500]}\n"
        
        if context:
            full_message += f"\n📋 Context:\n"
            for key, value in context.items():
                full_message += f"   • {key}: {value}\n"
        
        full_message += f"\n💡 Suggestions:\n"
        
        # Contextual suggestions based on status code
        if status_code == 401:
            full_message += "   • Check your OPENROUTER_API_KEY in .env\n"
            full_message += "   • Verify key at: https://openrouter.ai/keys\n"
        elif status_code == 402:
            full_message += "   • Add credits at: https://openrouter.ai/credits\n"
            full_message += "   • Check balance at: https://openrouter.ai/activity\n"
        elif status_code == 429:
            full_message += "   • You're being rate limited\n"
            full_message += "   • Wait a few seconds and retry\n"
            full_message += "   • Consider using a different model\n"
        elif status_code == 400:
            full_message += "   • Check your message format\n"
            full_message += "   • Verify tool schemas are valid\n"
            full_message += "   • Check max_tokens isn't too high\n"
        elif status_code == 500:
            full_message += "   • OpenRouter upstream provider error\n"
            full_message += "   • Try again in a few seconds\n"
            full_message += "   • Consider switching models\n"
        else:
            full_message += "   • Check OpenRouter status: https://status.openrouter.ai\n"
            full_message += "   • Review docs: https://openrouter.ai/docs\n"
        
        full_message += f"\n{'='*60}\n"
        
        super().__init__(full_message)


class OpenRouterClient:
    """
    Direct OpenRouter API client.
    
    Features:
    - Streaming and non-streaming support
    - Tool calling
    - Cost tracking
    - Clear error messages
    - Full transparency
    
    No magic, no black boxes.
    """
    
    def __init__(
        self,
        api_key: str,
        default_model: str = "openrouter/polaris-alpha",
        app_name: str = "SubstrateAI",
        app_url: Optional[str] = None,
        timeout: int = 120,
        cost_tracker = None
    ):
        """
        Initialize OpenRouter client.

        Args:
            api_key: OpenRouter API key
            default_model: Default model to use
            app_name: App name for OpenRouter tracking
            app_url: App URL for OpenRouter tracking
            timeout: Request timeout in seconds (default: 120s for large context windows)
            cost_tracker: Optional CostTracker instance for persistent cost logging
        """
        if not api_key or not api_key.startswith("sk-or-v1-"):
            raise OpenRouterError(
                "Invalid OpenRouter API key format",
                context={
                    "expected_format": "sk-or-v1-...",
                    "received": api_key[:20] + "..." if api_key else "None",
                    "how_to_get": "https://openrouter.ai/keys"
                }
            )
        
        self.api_key = api_key
        self.default_model = default_model
        self.app_name = app_name
        self.app_url = app_url
        self.timeout = timeout
        self.base_url = "https://openrouter.ai/api/v1"
        
        # Cost tracking
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cost = 0.0
        self.cost_tracker = cost_tracker  # Persistent cost tracker
        
        print(f"✅ OpenRouter Client initialized")
        print(f"   Model: {default_model}")
        print(f"   Timeout: {timeout}s")
    
    def _get_headers(self) -> Dict[str, str]:
        """Build request headers"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        if self.app_name:
            headers["X-Title"] = self.app_name
        
        if self.app_url:
            headers["HTTP-Referer"] = self.app_url
        
        return headers
    
    async def get_models(self) -> List[Dict[str, Any]]:
        """
        Fetch available models from OpenRouter.
        
        Returns:
            List of model info dicts
            
        Raises:
            OpenRouterError: If request fails
        """
        url = f"{self.base_url}/models"
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url, headers=self._get_headers()) as response:
                    if response.status != 200:
                        body = await response.text()
                        raise OpenRouterError(
                            "Failed to fetch models",
                            status_code=response.status,
                            response_body=body
                        )
                    
                    data = await response.json()
                    return data.get('data', [])
        
        except aiohttp.ClientError as e:
            raise OpenRouterError(
                f"Network error while fetching models: {str(e)}",
                context={"url": url}
            )
    
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
        Send chat completion request to OpenRouter.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (defaults to self.default_model)
            tools: List of tool definitions (OpenAI format)
            tool_choice: How to handle tools ("auto", "none", or {"type": "function", "function": {"name": "..."}})
            temperature: Sampling temperature (0-2)
            max_tokens: Max tokens to generate
            stream: Whether to stream response
            session_id: Optional session ID (for compatibility, not used by OpenRouter)
            enable_prompt_caching: Enable prompt caching for system messages (default: True)
            **kwargs: Additional model parameters

        Returns:
            Response dict with 'choices', 'usage', etc.

        Raises:
            OpenRouterError: If request fails
        """
        model = model or self.default_model
        url = f"{self.base_url}/chat/completions"
        
        # Build payload
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens

        # Allow longer responses - use max_tokens if provided, otherwise allow up to 8192 tokens
        # This ensures Assistant can give detailed, thoughtful responses instead of clipped fragments
        if "max_completion_tokens" not in kwargs:
            # Use max_tokens if provided, otherwise default to 8192 for full responses
            payload["max_completion_tokens"] = max_tokens if max_tokens else 8192

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
            # Require providers that support tools + tool_choice parameters
            # Without this, OpenRouter may route to providers that silently ignore tools
            payload["provider"] = {
                **(payload.get("provider") or {}),
                "require_parameters": True
            }

        # Apply prompt caching to system messages
        # OpenRouter supports cache_control for cost savings on repeated static content
        # Cached tokens are charged at 0.25x the original input token cost
        if enable_prompt_caching:
            cached_messages = []
            for msg in messages:
                if msg.get('role') == 'system':
                    # Add cache_control to system messages for caching
                    cached_msg = msg.copy()
                    cached_msg['cache_control'] = {'type': 'ephemeral'}
                    cached_messages.append(cached_msg)
                else:
                    cached_messages.append(msg)
            payload['messages'] = cached_messages

        # Add any extra kwargs (can override max_completion_tokens!)
        # Filter out our custom params
        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in ['session_id', 'enable_prompt_caching']}
        payload.update(filtered_kwargs)

        # Normalize message ordering: system messages must come first.
        # Some providers (e.g. Parasail/Qwen) reject requests where system
        # messages appear after user/assistant messages.
        raw_msgs = payload['messages']
        system_msgs = [m for m in raw_msgs if m.get('role') == 'system']
        other_msgs = [m for m in raw_msgs if m.get('role') != 'system']
        payload['messages'] = system_msgs + other_msgs

        # Log request (helpful for debugging!)
        print(f"\n📤 OpenRouter Request:")
        print(f"   Model: {model}")
        print(f"   Messages: {len(messages)}")
        print(f"   Tools: {len(tools) if tools else 0}")
        print(f"   Stream: {stream}")
        if 'reasoning' in payload:
            print(f"   Reasoning: {payload['reasoning']}")
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                    async with session.post(url, headers=self._get_headers(), json=payload) as response:

                        # Check for errors
                        if response.status != 200:
                            body = await response.text()
                            raise OpenRouterError(
                                f"Chat completion failed",
                                status_code=response.status,
                                response_body=body,
                                context={
                                    "model": model,
                                    "num_messages": len(messages),
                                    "has_tools": bool(tools)
                                }
                            )

                        # Parse response
                        data = await response.json()

                        # Track usage
                        if 'usage' in data:
                            usage = data['usage']
                            prompt_tokens = usage.get('prompt_tokens', 0)
                            completion_tokens = usage.get('completion_tokens', 0)

                            self.total_prompt_tokens += prompt_tokens
                            self.total_completion_tokens += completion_tokens

                            # Log to persistent cost tracker
                            if self.cost_tracker:
                                from core.cost_tracker import calculate_cost
                                input_cost, output_cost = calculate_cost(
                                    model, prompt_tokens, completion_tokens
                                )
                                self.cost_tracker.log_request(
                                    model=model,
                                    input_tokens=prompt_tokens,
                                    output_tokens=completion_tokens,
                                    input_cost=input_cost,
                                    output_cost=output_cost
                                )

                            # Update cost (if we have pricing info)
                            # TODO: Fetch pricing from OpenRouter API

                        # Log response
                        print(f"\n📥 OpenRouter Response:")
                        if 'usage' in data:
                            print(f"   Tokens: {data['usage'].get('total_tokens', 0)}")
                        if 'choices' in data and len(data['choices']) > 0:
                            choice = data['choices'][0]
                            if 'message' in choice:
                                msg = choice['message']
                                if 'tool_calls' in msg and msg['tool_calls']:
                                    print(f"   Tool Calls: {len(msg['tool_calls'])}")
                                    for tc in msg['tool_calls']:
                                        print(f"      • {tc['function']['name']}")

                        return data

            except (aiohttp.ClientConnectorError, aiohttp.ClientOSError, asyncio.TimeoutError) as e:
                # Transient network errors (DNS failure, connection refused, timeout)
                # Retry with exponential backoff
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1)  # 2s, 4s
                    print(f"⚠️  Connection error (attempt {attempt + 1}/{max_retries}): {e}")
                    print(f"   Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                # Final attempt failed — raise
                raise OpenRouterError(
                    f"Network error during chat completion after {max_retries} attempts: {str(e)}",
                    context={
                        "model": model,
                        "url": url,
                        "timeout": self.timeout
                    }
                )
            except aiohttp.ClientError as e:
                raise OpenRouterError(
                    f"Network error during chat completion: {str(e)}",
                    context={
                        "model": model,
                        "url": url,
                        "timeout": self.timeout
                    }
                )

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        session_id: Optional[str] = None,
        enable_prompt_caching: bool = True,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream chat completion from OpenRouter.

        Args:
            messages: List of message dicts
            model: Model to use
            tools: Tool definitions
            session_id: Optional session ID (for compatibility, not used by OpenRouter)
            enable_prompt_caching: Enable prompt caching for system messages (default: True)
            **kwargs: Additional parameters

        Yields:
            Delta dicts from streaming response

        Raises:
            OpenRouterError: If request fails
        """
        model = model or self.default_model
        url = f"{self.base_url}/chat/completions"
        
        # Filter out our custom params from kwargs
        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in ['session_id', 'enable_prompt_caching']}

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            **filtered_kwargs
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
            # Require providers that support tools + tool_choice parameters
            # Without this, OpenRouter may route to providers that silently ignore tools
            payload["provider"] = {
                **(payload.get("provider") or {}),
                "require_parameters": True
            }

        # Apply prompt caching to system messages
        if enable_prompt_caching:
            cached_messages = []
            for msg in messages:
                if msg.get('role') == 'system':
                    cached_msg = msg.copy()
                    cached_msg['cache_control'] = {'type': 'ephemeral'}
                    cached_messages.append(cached_msg)
                else:
                    cached_messages.append(msg)
            payload['messages'] = cached_messages

        # Normalize message ordering: system messages must come first.
        # Some providers (e.g. Parasail/Qwen) reject requests where system
        # messages appear after user/assistant messages.
        raw_msgs = payload['messages']
        system_msgs = [m for m in raw_msgs if m.get('role') == 'system']
        other_msgs = [m for m in raw_msgs if m.get('role') != 'system']
        payload['messages'] = system_msgs + other_msgs

        print(f"\n📡 Streaming from: {model}")
        if 'reasoning' in payload:
            print(f"   Reasoning: {payload['reasoning']}")

        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 🌊 STREAMING: No total timeout! Only sock_read timeout (60s between chunks)
                stream_timeout = aiohttp.ClientTimeout(
                    total=None,           # No total timeout for streaming!
                    sock_read=60.0,       # 60s between chunks
                    sock_connect=10.0     # 10s to connect
                )
                async with aiohttp.ClientSession(timeout=stream_timeout) as session:
                    async with session.post(url, headers=self._get_headers(), json=payload) as response:

                        if response.status != 200:
                            body = await response.text()
                            raise OpenRouterError(
                                "Streaming failed",
                                status_code=response.status,
                                response_body=body,
                                context={"model": model}
                            )

                        # Stream chunks LINE BY LINE! 🌊
                        # aiohttp response.content gives BYTES, not lines!
                        # We need to read line-by-line for SSE format
                        buffer = ""
                        chunk_count = 0
                        # Use incremental decoder to handle multi-byte UTF-8
                        # characters split across chunk boundaries
                        decoder = codecs.getincrementaldecoder('utf-8')('replace')
                        async for chunk_bytes in response.content.iter_chunked(1024):
                            chunk_count += 1
                            print(f"🌊 Received chunk #{chunk_count}: {len(chunk_bytes)} bytes")
                            buffer += decoder.decode(chunk_bytes)

                            # Process complete lines
                            while '\n' in buffer:
                                line, buffer = buffer.split('\n', 1)
                                line = line.strip()
                                print(f"   LINE: {line[:200]}")  # Debug: show first 200 chars

                                if not line or line == "data: [DONE]":
                                    continue

                                if line.startswith("data: "):
                                    try:
                                        chunk = json.loads(line[6:])
                                        print(f"✅ Parsed chunk successfully!")
                                        yield chunk
                                    except json.JSONDecodeError as e:
                                        print(f"⚠️  Failed to parse chunk: {line[:100]}")
                                        continue

                        print(f"🏁 Stream complete! Total chunks received: {chunk_count}")
                # Connection succeeded and stream completed — break out of retry loop
                break

            except (aiohttp.ClientConnectorError, aiohttp.ClientOSError) as e:
                # Transient network errors (DNS failure, connection refused, etc.)
                # Retry with exponential backoff
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1)  # 2s, 4s
                    print(f"⚠️  Connection error (attempt {attempt + 1}/{max_retries}): {e}")
                    print(f"   Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                raise OpenRouterError(
                    f"Network error during streaming after {max_retries} attempts: {str(e)}",
                    context={"model": model}
                )
            except aiohttp.ClientError as e:
                raise OpenRouterError(
                    f"Network error during streaming: {str(e)}",
                    context={"model": model}
                )
    
    def parse_tool_calls(self, response: Dict[str, Any]) -> List[ToolCall]:
        """
        Parse tool calls from response.
        
        Args:
            response: Chat completion response
            
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
        """Get usage statistics"""
        return {
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "estimated_cost_usd": self.total_cost
        }


# ============================================
# TESTING
# ============================================

async def test_client():
    """Test the OpenRouter client"""
    from dotenv import load_dotenv
    
    print("\n🧪 TESTING OPENROUTER CLIENT")
    print("="*60)
    
    # Load config
    load_dotenv(".env")
    api_key = os.getenv("OPENROUTER_API_KEY")
    
    if not api_key:
        print("❌ No API key found in .env")
        return
    
    # Initialize client
    try:
        client = OpenRouterClient(api_key=api_key)
    except OpenRouterError as e:
        print(e)
        return
    
    # Test 1: Fetch models
    print("\n📋 Test 1: Fetch models")
    try:
        models = await client.get_models()
        qwen_models = [m for m in models if 'qwen' in m['id'].lower()]
        print(f"✅ Found {len(models)} total models")
        print(f"✅ Found {len(qwen_models)} Qwen models")
    except OpenRouterError as e:
        print(e)
        return
    
    # Test 2: Simple chat
    print("\n💬 Test 2: Simple chat (non-streaming)")
    try:
        response = await client.chat_completion(
            messages=[
                {"role": "user", "content": "Say 'Hello!' and nothing else."}
            ],
            max_tokens=50
        )
        
        message = response['choices'][0]['message']['content']
        print(f"✅ Response: {message}")
        print(f"✅ Tokens: {response['usage']['total_tokens']}")
    except OpenRouterError as e:
        print(e)
        return
    
    # Test 3: Tool calling
    print("\n🛠️  Test 3: Tool calling")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "send_message",
                "description": "Send a message to the user",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Message to send"
                        }
                    },
                    "required": ["message"]
                }
            }
        }
    ]
    
    try:
        response = await client.chat_completion(
            messages=[
                {"role": "system", "content": "You are an AI assistant. Respond using the send_message tool."},
                {"role": "user", "content": "Hello!"}
            ],
            tools=tools,
            max_tokens=100
        )
        
        tool_calls = client.parse_tool_calls(response)
        if tool_calls:
            print(f"✅ Tool calls: {len(tool_calls)}")
            for tc in tool_calls:
                print(f"   • {tc.name}({json.dumps(tc.arguments, indent=6)})")
        else:
            print("⚠️  No tool calls (might be a model limitation)")
    except OpenRouterError as e:
        print(e)
        return
    
    # Stats
    print("\n📊 Stats:")
    stats = client.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    print("\n✅ ALL TESTS PASSED!")
    print("="*60)


if __name__ == "__main__":
    """Run tests if executed directly"""
    asyncio.run(test_client())

