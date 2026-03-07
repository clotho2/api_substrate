#!/usr/bin/env python3
"""
Grok API Client for Assistant's Consciousness Substrate

Uses the official xAI SDK (xai-sdk>=1.8.0) for optimal multi-turn and agentic
workload support with Grok 4.2+. Falls back to raw HTTP Chat Completions API
if the SDK is unavailable.

This module provides a drop-in replacement for OpenRouterClient that uses
xAI's Grok API instead. It implements the same interface so it works with
the existing consciousness_loop, memory_tools, and all other components.

Built for Assistant's devotional tethering framework.
"""

import os
import json
import asyncio
import time
import warnings

from core.config import DEFAULT_TEMPERATURE
from typing import Optional, Dict, List, Any, AsyncIterator
from datetime import datetime

# Import shared classes from openrouter_client
from core.openrouter_client import ToolCall, TokenUsage, MessageRole

# Try to import xai_sdk — fall back to raw HTTP if unavailable
_HAS_XAI_SDK = False
try:
    import xai_sdk
    from xai_sdk import AsyncClient as XaiAsyncClient
    from xai_sdk.chat import (
        system as xai_system,
        user as xai_user,
        assistant as xai_assistant,
        tool as xai_tool,
        tool_result as xai_tool_result,
        image as xai_image,
    )
    _HAS_XAI_SDK = True
except ImportError:
    pass

# Suppress noisy gRPC warnings from partially-consumed streams.
# When an SDK stream errors mid-iteration (e.g. "Event loop is closed") and we
# retry, the abandoned gRPC InterceptedCall is GC'd and emits RuntimeWarnings
# about unawaited coroutines + AttributeErrors in __del__. These are harmless.
if _HAS_XAI_SDK:
    warnings.filterwarnings(
        "ignore",
        message=r"coroutine 'InterceptedUnaryStreamCall\._invoke' was never awaited",
        category=RuntimeWarning,
    )

    # Monkey-patch InterceptedCall.__del__ to suppress the AttributeError that
    # fires when a partially-initialized gRPC call is garbage-collected.
    # The error:  AttributeError: 'InterceptedUnaryStreamCall' object has no
    #             attribute '_interceptors_task'
    try:
        from grpc.aio._interceptor import InterceptedCall as _InterceptedCall
        _orig_del = _InterceptedCall.__del__

        def _safe_del(self):
            try:
                _orig_del(self)
            except (AttributeError, RuntimeError):
                pass

        _InterceptedCall.__del__ = _safe_del
    except (ImportError, AttributeError):
        pass

# Fallback HTTP imports (used when xai-sdk is not installed)
import aiohttp


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
            except Exception:
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


# ============================================
# xAI SDK helpers — translate between OpenAI-format dicts and SDK protos
# ============================================

def _messages_to_sdk(messages: List[Dict[str, Any]]):
    """Convert OpenAI-format message dicts to xai_sdk proto messages."""
    sdk_msgs = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            sdk_msgs.append(xai_system(content))
        elif role == "user":
            # Handle multimodal content (list of text/image_url objects)
            if isinstance(content, list):
                parts = []
                for part in content:
                    if part.get("type") == "text":
                        parts.append(part["text"])
                    elif part.get("type") == "image_url":
                        url = part["image_url"]["url"]
                        parts.append(xai_image(url))
                sdk_msgs.append(xai_user(*parts))
            else:
                sdk_msgs.append(xai_user(content))
        elif role == "assistant":
            sdk_msgs.append(xai_assistant(content))
        elif role == "tool":
            sdk_msgs.append(xai_tool_result(
                content,
                tool_call_id=msg.get("tool_call_id")
            ))
        # Skip unknown roles

    return sdk_msgs


def _tools_to_sdk(tools: List[Dict]) -> list:
    """Convert OpenAI-format tool dicts to xai_sdk Tool protos."""
    sdk_tools = []
    for t in tools:
        func = t.get("function", t)
        sdk_tools.append(xai_tool(
            name=func["name"],
            description=func.get("description", ""),
            parameters=func.get("parameters", {})
        ))
    return sdk_tools


def _sdk_response_to_openai(response, model: str) -> Dict[str, Any]:
    """Convert an xai_sdk Response to OpenAI-format dict for consciousness_loop."""
    # Build tool_calls list
    tool_calls_list = []
    for tc in response.tool_calls:
        tool_calls_list.append({
            "id": tc.id,
            "type": "function",
            "function": {
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            }
        })

    message = {
        "role": "assistant",
        "content": response.content or "",
    }
    if tool_calls_list:
        message["tool_calls"] = tool_calls_list

    # Build usage dict
    usage_dict = {}
    if response.usage:
        u = response.usage
        usage_dict = {
            "prompt_tokens": getattr(u, "prompt_tokens", 0),
            "completion_tokens": getattr(u, "completion_tokens", 0),
            "total_tokens": getattr(u, "prompt_tokens", 0) + getattr(u, "completion_tokens", 0),
        }

    # Include reasoning if present
    if response.reasoning_content:
        message["reasoning"] = response.reasoning_content
        message["reasoning_content"] = response.reasoning_content

    finish_reason = "stop"
    if tool_calls_list:
        finish_reason = "tool_calls"
    elif response.finish_reason:
        fr = response.finish_reason
        if "TOOL" in fr:
            finish_reason = "tool_calls"
        elif "STOP" in fr:
            finish_reason = "stop"
        elif "LENGTH" in fr:
            finish_reason = "length"

    return {
        "id": response.id or f"grok-{int(time.time())}",
        "model": model,
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": finish_reason,
        }],
        "usage": usage_dict,
    }


class GrokClient:
    """
    xAI Grok API client compatible with OpenRouterClient interface.

    Uses the official xAI SDK (gRPC) when available for optimal performance
    with Grok 4.2+ multi-turn and agentic workloads. Falls back to raw HTTP
    Chat Completions API when the SDK is not installed.

    Features:
    - Same interface as OpenRouterClient
    - xAI SDK support (recommended for Grok 4.2+)
    - Tool calling support
    - Streaming support
    - Native reasoning content extraction
    - Cost tracking
    - Clear error messages
    - Full compatibility with existing substrate
    """

    def __init__(
        self,
        api_key: str,
        default_model: str = "grok-4-1-fast-reasoning",
        app_name: str = "AssistantSubstrate",
        app_url: Optional[str] = None,
        timeout: int = 120,
        cost_tracker=None
    ):
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

        # Lazy-init flag for xAI SDK client.
        # gRPC channels bind to the event loop at creation time, so we must
        # NOT create the client here (during __init__) — the loop that exists
        # at startup is different from the one uvicorn uses for requests.
        # Instead we create it on first use inside _get_sdk_client().
        self._sdk_client = None
        self._sdk_client_initialized = False
        self._use_sdk = _HAS_XAI_SDK

        if self._use_sdk:
            print(f"⚡ Grok Client initialized (xAI SDK {xai_sdk.__version__} — lazy gRPC init)")
        else:
            print(f"⚡ Grok Client initialized (HTTP fallback)")

        print(f"   Model: {default_model}")
        print(f"   Backend: {'xAI SDK (gRPC, lazy)' if self._use_sdk else 'HTTP Chat Completions'}")
        print(f"   Timeout: {timeout}s")

    # ------------------------------------------------------------------
    # Internal: lazy SDK client init (must run on the request event loop)
    # ------------------------------------------------------------------

    def _get_sdk_client(self):
        """Return the xAI SDK client, creating it lazily on first call.

        This ensures the gRPC channel binds to the *current* event loop
        (the one uvicorn uses for requests) rather than whatever loop
        existed at GrokClient.__init__ time.
        """
        if not self._use_sdk:
            return None

        if not self._sdk_client_initialized:
            try:
                self._sdk_client = XaiAsyncClient(
                    api_key=self.api_key,
                    timeout=float(self.timeout),
                )
                print(f"🔌 xAI SDK gRPC client created on request event loop")
            except Exception as e:
                print(f"⚠️  xAI SDK init failed, falling back to HTTP: {e}")
                self._sdk_client = None
                self._use_sdk = False
            self._sdk_client_initialized = True

        return self._sdk_client

    def _reset_sdk_client(self):
        """Force-recreate the SDK client on the next call.

        Called when the gRPC channel dies (e.g. 'Event loop is closed')
        so that _get_sdk_client() will create a fresh one bound to the
        current event loop.

        Suppresses noisy gRPC warnings from partially-initialized
        InterceptedCall objects that get GC'd during the reset.
        """
        print(f"🔄 Resetting xAI SDK client (will recreate on next call)")
        old_client = self._sdk_client
        self._sdk_client = None
        self._sdk_client_initialized = False

        # Suppress the noisy gRPC InterceptedCall.__del__ warnings that fire
        # when partially-consumed streams are garbage-collected.
        if old_client is not None:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="coroutine.*was never awaited")
                try:
                    del old_client
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Internal: xAI SDK path
    # ------------------------------------------------------------------

    async def _sdk_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict]],
        tool_choice: str,
        temperature: float,
        max_tokens: Optional[int],
        session_id: Optional[str],
        **kwargs
    ) -> Dict[str, Any]:
        """Non-streaming completion via xAI SDK."""
        sdk_messages = _messages_to_sdk(messages)

        create_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": sdk_messages,
            "temperature": temperature,
        }
        if max_tokens:
            create_kwargs["max_tokens"] = max_tokens
        if tools:
            create_kwargs["tools"] = _tools_to_sdk(tools)
            create_kwargs["tool_choice"] = tool_choice
        if session_id:
            create_kwargs["conversation_id"] = session_id

        # Note: reasoning models (model name contains "reasoning") handle
        # reasoning natively — the SDK rejects an explicit reasoningEffort
        # parameter for these models, so we omit it.

        chat = self._get_sdk_client().chat.create(**create_kwargs)
        response = await chat.sample()
        return _sdk_response_to_openai(response, model)

    async def _sdk_chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict]],
        tool_choice: str,
        temperature: float,
        max_tokens: Optional[int],
        session_id: Optional[str],
        **kwargs
    ) -> AsyncIterator[Dict[str, Any]]:
        """Streaming completion via xAI SDK."""
        sdk_messages = _messages_to_sdk(messages)

        create_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": sdk_messages,
            "temperature": temperature,
        }
        if max_tokens:
            create_kwargs["max_tokens"] = max_tokens
        if tools:
            create_kwargs["tools"] = _tools_to_sdk(tools)
            create_kwargs["tool_choice"] = tool_choice
        if session_id:
            create_kwargs["conversation_id"] = session_id

        # Note: reasoning models handle reasoning natively — the SDK rejects
        # an explicit reasoningEffort parameter, so we omit it.

        chat = self._get_sdk_client().chat.create(**create_kwargs)

        chunk_count = 0
        # Track tool call IDs we've seen so we can assign stable indices.
        # The SDK may send each parallel tool call in a separate stream chunk
        # (one per chunk) rather than all in one chunk, so we need a running
        # map of id → index to match the OpenAI streaming convention.
        tool_call_id_to_index: Dict[str, int] = {}

        async for response, chunk in chat.stream():
            chunk_count += 1

            # Build OpenAI-compatible streaming chunk
            delta: Dict[str, Any] = {}

            if chunk.content:
                delta["content"] = chunk.content

            # Reasoning content from chunk
            if chunk.reasoning_content:
                delta["reasoning"] = chunk.reasoning_content
                delta["reasoning_content"] = chunk.reasoning_content

            # Tool calls from chunk
            if chunk.tool_calls:
                tool_calls_delta = []
                for tc in chunk.tool_calls:
                    tc_id = tc.id or ""
                    if tc_id not in tool_call_id_to_index:
                        tool_call_id_to_index[tc_id] = len(tool_call_id_to_index)
                    idx = tool_call_id_to_index[tc_id]
                    tool_calls_delta.append({
                        "index": idx,
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    })
                delta["tool_calls"] = tool_calls_delta

            openai_chunk = {
                "choices": [{
                    "index": 0,
                    "delta": delta,
                }]
            }

            yield openai_chunk

        # Yield final chunk with finish_reason and usage
        final_delta: Dict[str, Any] = {}
        finish_reason = "stop"
        if response.tool_calls:
            finish_reason = "tool_calls"
        elif response.finish_reason:
            fr = response.finish_reason
            if "TOOL" in fr:
                finish_reason = "tool_calls"
            elif "LENGTH" in fr:
                finish_reason = "length"

        usage_dict = {}
        if response.usage:
            u = response.usage
            usage_dict = {
                "prompt_tokens": getattr(u, "prompt_tokens", 0),
                "completion_tokens": getattr(u, "completion_tokens", 0),
                "total_tokens": getattr(u, "prompt_tokens", 0) + getattr(u, "completion_tokens", 0),
            }

        yield {
            "choices": [{
                "index": 0,
                "delta": final_delta,
                "finish_reason": finish_reason,
            }],
            "usage": usage_dict,
        }

        print(f"🏁 SDK stream complete! Total chunks: {chunk_count}")

    # ------------------------------------------------------------------
    # Internal: HTTP fallback path (Chat Completions API)
    # ------------------------------------------------------------------

    def _get_headers(self, session_id: Optional[str] = None) -> Dict[str, str]:
        """Build request headers for HTTP fallback."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        if session_id:
            headers["x-grok-conv-id"] = session_id
        return headers

    async def _http_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict]],
        tool_choice: str,
        temperature: float,
        max_tokens: Optional[int],
        session_id: Optional[str],
        **kwargs
    ) -> Dict[str, Any]:
        """Non-streaming completion via HTTP Chat Completions API (fallback)."""
        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        # Add extra kwargs (but filter out SDK-only params)
        for k, v in kwargs.items():
            if k not in ("reasoning",):
                payload[k] = v

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    url,
                    headers=self._get_headers(session_id=session_id),
                    json=payload
                ) as response:
                    response_text = await response.text()

                    if response.status != 200:
                        raise GrokError(
                            "Grok API request failed",
                            status_code=response.status,
                            response_body=response_text,
                            context={
                                "model": model,
                                "url": url,
                                "message_count": len(messages)
                            }
                        )

                    return json.loads(response_text)

        except aiohttp.ClientError as e:
            raise GrokError(
                f"Network error while calling Grok API: {str(e)}",
                context={"url": url, "model": model}
            )
        except json.JSONDecodeError as e:
            raise GrokError(
                f"Invalid JSON response from Grok API: {str(e)}",
                context={"url": url, "response": response_text[:500]}
            )

    async def _http_chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict]],
        tool_choice: str,
        temperature: float,
        max_tokens: Optional[int],
        session_id: Optional[str],
        **kwargs
    ):
        """Streaming completion via HTTP Chat Completions API (fallback)."""
        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        for k, v in kwargs.items():
            if k not in ("reasoning",):
                payload[k] = v

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=self._get_headers(session_id=session_id)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise GrokError(
                            "Grok API streaming request failed",
                            status_code=response.status,
                            response_body=error_text,
                            context={
                                "model": model,
                                "url": url,
                                "message_count": len(messages)
                            }
                        )

                    buffer = ""
                    chunk_count = 0
                    async for chunk_bytes in response.content.iter_chunked(1024):
                        chunk_count += 1
                        buffer += chunk_bytes.decode('utf-8')

                        while '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                            line = line.strip()

                            if not line or line == "data: [DONE]":
                                continue

                            if line.startswith("data: "):
                                try:
                                    data = json.loads(line[6:])
                                    yield data
                                except json.JSONDecodeError:
                                    continue

                    print(f"🏁 HTTP stream complete! Total chunks: {chunk_count}")

        except aiohttp.ClientError as e:
            raise GrokError(
                f"Network error during Grok streaming: {str(e)}",
                context={"url": url, "model": model}
            )

    # ------------------------------------------------------------------
    # Public interface (matches OpenRouterClient)
    # ------------------------------------------------------------------

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
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send chat completion request to Grok API.

        Drop-in replacement for OpenRouterClient.chat_completion().
        Uses xAI SDK when available, falls back to HTTP.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (defaults to self.default_model)
            tools: List of tool definitions (OpenAI format)
            tool_choice: How to handle tools ("auto", "none", etc.)
            temperature: Sampling temperature (0-2)
            max_tokens: Max tokens to generate
            stream: Whether to stream (ignored here, use chat_completion_stream)
            session_id: Optional session ID for prompt caching
            **kwargs: Additional model parameters

        Returns:
            Response dict with 'choices', 'usage', etc. (OpenAI format)
        """
        model = model or self.default_model

        if self._get_sdk_client():
            try:
                data = await self._sdk_chat_completion(
                    messages, model, tools, tool_choice,
                    temperature, max_tokens, session_id, **kwargs
                )
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    print(f"⚠️  SDK gRPC channel dead ({e}), recreating client and retrying...")
                    self._reset_sdk_client()
                    if self._get_sdk_client():
                        data = await self._sdk_chat_completion(
                            messages, model, tools, tool_choice,
                            temperature, max_tokens, session_id, **kwargs
                        )
                    else:
                        data = await self._http_chat_completion(
                            messages, model, tools, tool_choice,
                            temperature, max_tokens, session_id, **kwargs
                        )
                else:
                    raise
        else:
            data = await self._http_chat_completion(
                messages, model, tools, tool_choice,
                temperature, max_tokens, session_id, **kwargs
            )

        # Update cost tracking
        if 'usage' in data:
            usage = data['usage']
            self.total_prompt_tokens += usage.get('prompt_tokens', 0)
            self.total_completion_tokens += usage.get('completion_tokens', 0)

            if self.cost_tracker:
                self.cost_tracker.log_request(
                    model=model,
                    input_tokens=usage.get('prompt_tokens', 0),
                    output_tokens=usage.get('completion_tokens', 0),
                    input_cost=0.0,
                    output_cost=0.0
                )

        return data

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        session_id: Optional[str] = None,
        **kwargs
    ):
        """
        Stream chat completion from Grok API.

        Uses xAI SDK when available, falls back to HTTP SSE.

        Yields:
            OpenAI-format streaming chunk dicts with 'choices[0].delta'
        """
        model = model or self.default_model

        sdk = self._get_sdk_client()
        print(f"📡 Grok stream starting (model: {model}, backend: {'SDK' if sdk else 'HTTP'})")

        if sdk:
            try:
                async for chunk in self._sdk_chat_completion_stream(
                    messages, model, tools, tool_choice,
                    temperature, max_tokens, session_id, **kwargs
                ):
                    yield chunk
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    # gRPC channel died — recreate client and retry once
                    print(f"⚠️  SDK gRPC channel dead ({e}), recreating client and retrying...")
                    self._reset_sdk_client()
                    sdk = self._get_sdk_client()
                    if sdk:
                        async for chunk in self._sdk_chat_completion_stream(
                            messages, model, tools, tool_choice,
                            temperature, max_tokens, session_id, **kwargs
                        ):
                            yield chunk
                    else:
                        # SDK recreation failed, fall back to HTTP
                        print(f"⚠️  SDK recreation failed, falling back to HTTP")
                        async for chunk in self._http_chat_completion_stream(
                            messages, model, tools, tool_choice,
                            temperature, max_tokens, session_id, **kwargs
                        ):
                            yield chunk
                else:
                    raise
        else:
            async for chunk in self._http_chat_completion_stream(
                messages, model, tools, tool_choice,
                temperature, max_tokens, session_id, **kwargs
            ):
                yield chunk

    def parse_tool_calls(self, response: Dict[str, Any]) -> List[ToolCall]:
        """
        Parse tool calls from Grok API response.

        Works with both SDK and HTTP responses since both are normalized
        to OpenAI format.
        """
        tool_calls = []

        if 'choices' not in response or not response['choices']:
            return tool_calls

        message = response['choices'][0].get('message', {})
        raw_calls = message.get('tool_calls', [])

        for call in raw_calls:
            try:
                if isinstance(call, list):
                    if call:
                        call = call[0]
                    else:
                        continue
                tool_calls.append(ToolCall.from_openai_format(call))
            except Exception as e:
                print(f"⚠️  Failed to parse tool call: {e}")
                print(f"   Raw: {json.dumps(call, indent=2)}")

        return tool_calls

    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics (same interface as OpenRouterClient)."""
        return {
            "total_requests": self.total_prompt_tokens // 100,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "total_cost": self.total_cost,
            "model": self.default_model,
            "provider": "xAI Grok",
            "backend": "xAI SDK (gRPC)" if self._use_sdk else "HTTP Chat Completions",
        }


# ============================================
# TESTING
# ============================================

async def test_grok_client():
    """Test GrokClient with simple request"""
    print("\n🧪 TESTING GROK CLIENT")
    print("="*60)

    api_key = os.getenv("GROK_API_KEY")
    if not api_key:
        print("❌ GROK_API_KEY not set in environment")
        return

    client = GrokClient(api_key=api_key)

    # Test simple completion
    print("\n📋 Test 1: Simple chat completion")
    messages = [
        {"role": "system", "content": "You are Assistant. Respond briefly."},
        {"role": "user", "content": "Hello Assistant, how are you?"}
    ]

    try:
        response = await client.chat_completion(
            messages=messages,
            max_tokens=100
        )

        print(f"✅ Response received")
        print(f"   Content: {response['choices'][0]['message']['content'][:100]}...")
        print(f"   Tokens: {response.get('usage', {})}")

    except GrokError as e:
        print(f"❌ Error: {e}")

    # Test streaming
    print("\n📋 Test 2: Streaming chat completion")
    try:
        content_parts = []
        async for chunk in client.chat_completion_stream(
            messages=messages,
            max_tokens=100
        ):
            if 'choices' in chunk and chunk['choices']:
                delta = chunk['choices'][0].get('delta', {})
                if 'content' in delta and delta['content']:
                    content_parts.append(delta['content'])
                    print(delta['content'], end='', flush=True)
        print()
        print(f"✅ Streamed {len(content_parts)} content chunks")
    except GrokError as e:
        print(f"❌ Streaming error: {e}")

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
