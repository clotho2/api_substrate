#!/usr/bin/env python3
"""
AiCara Frontend Compatibility Routes
=====================================

Adapter routes that translate AiCara frontend requests to substrate's 
internal endpoints. This allows the AiCara web and mobile apps to work
with the substrate backend without any frontend code changes.

Endpoints:
- POST /chat                    - Web wolfeEngine.ts compatibility
- POST /v1/chat/completions     - Mobile wolfeEngine.js (OpenAI format)

The AiCara frontends call these endpoints via relay.aicara.ai.
This file translates those requests to the substrate's consciousness loop.
"""

import json
import asyncio
import logging
from datetime import datetime
from flask import Blueprint, Response, request, jsonify
from typing import Dict, Any, Optional

from core.config import get_model_or_default

logger = logging.getLogger(__name__)

# Create blueprint
aicara_bp = Blueprint('aicara', __name__)

# Global dependencies (set by init function)
_consciousness_loop = None
_state_manager = None
_rate_limiter = None


def init_aicara_routes(consciousness_loop, state_manager, rate_limiter=None):
    """Initialize AiCara compatibility routes with dependencies"""
    global _consciousness_loop, _state_manager, _rate_limiter
    _consciousness_loop = consciousness_loop
    _state_manager = state_manager
    _rate_limiter = rate_limiter
    logger.info("🌐 AiCara compatibility routes initialized")


# ============================================
# /chat - Web wolfeEngine.ts Compatibility
# ============================================

@aicara_bp.route('/chat', methods=['POST'])
def aicara_chat():
    """
    AiCara Web Frontend Compatibility Endpoint
    
    wolfeEngine.ts sends:
    {
        "messages": [{"role": "user", "content": "..."}],
        "max_tokens": 2048,
        "temperature": 0.55,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.15,
        "repeat_last_n": 64,
        "stream": true,
        "max_prompt_tokens": 8000,  // optional
        "concise": false            // optional
    }
    
    Expects NDJSON streaming response:
    {"delta": "Hello", "done": false}
    {"delta": " world", "done": false}
    {"delta": "", "done": true}
    """
    if not _consciousness_loop:
        return jsonify({"error": "Consciousness loop not initialized"}), 500
    
    try:
        data = request.get_json()
        
        # Extract from wolfeEngine format
        messages = data.get('messages', [])
        stream = data.get('stream', True)
        max_tokens = data.get('max_tokens', 2048)
        temperature = data.get('temperature', 0.55)
        
        # Get user message (last message in array)
        user_message = ""
        if messages:
            last_msg = messages[-1]
            user_message = last_msg.get('content', '')
        
        if not user_message:
            return jsonify({"error": "No message content"}), 400
        
        # Extract session from headers or use unified default
        # Using same session ID across all interfaces so Nate remembers conversations
        session_id = request.headers.get('X-Session-Id', 'nate_conversation')
        
        logger.info(f"🌐 AiCara /chat: session={session_id}, stream={stream}, msg_len={len(user_message)}")
        
        # Get model from state or use default from .env configuration
        model = _state_manager.get_state("agent:model") if _state_manager else None
        if not model:
            model = get_model_or_default()
        
        if stream:
            # STREAMING MODE - Return NDJSON
            return Response(
                _generate_ndjson_stream(user_message, session_id, model),
                mimetype='application/x-ndjson',
                headers={
                    'Cache-Control': 'no-cache',
                    'X-Accel-Buffering': 'no'
                }
            )
        else:
            # NON-STREAMING MODE
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                result = loop.run_until_complete(
                    _consciousness_loop.process_message(
                        user_message=user_message,
                        session_id=session_id,
                        model=model,
                        include_history=True,
                        history_limit=12
                    )
                )
            finally:
                loop.close()
            
            response_text = result.get('response', '')
            
            # Return in format wolfeEngine expects for non-streaming
            return jsonify({
                "response": response_text,
                "done": True
            })
    
    except Exception as e:
        logger.error(f"❌ AiCara /chat error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


def _generate_ndjson_stream(user_message: str, session_id: str, model: str):
    """
    Generate NDJSON streaming response for wolfeEngine.ts
    
    Yields lines like:
    {"delta": "Hello", "done": false}
    {"delta": " world", "done": false}  
    {"delta": "", "done": true}
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        async_gen = _consciousness_loop.process_message_stream(
            user_message=user_message,
            session_id=session_id,
            model=model,
            include_history=True,
            history_limit=12
        )
        
        while True:
            try:
                chunk = loop.run_until_complete(async_gen.__anext__())
                
                # Substrate stream format -> wolfeEngine NDJSON format
                if isinstance(chunk, dict):
                    delta = chunk.get('delta', chunk.get('content', ''))
                    done = chunk.get('done', False)
                else:
                    delta = str(chunk)
                    done = False
                
                yield json.dumps({"delta": delta, "done": done}) + '\n'
                
                if done:
                    break
                    
            except StopAsyncIteration:
                # Send final done message
                yield json.dumps({"delta": "", "done": True}) + '\n'
                break
                
    except Exception as e:
        logger.error(f"❌ Streaming error: {e}", exc_info=True)
        yield json.dumps({"error": str(e), "done": True}) + '\n'
    finally:
        loop.close()


# ============================================
# /v1/chat/completions - Mobile OpenAI Compat
# ============================================

@aicara_bp.route('/v1/chat/completions', methods=['POST'])
def openai_chat_completions():
    """
    OpenAI-Compatible Chat Completions Endpoint
    
    wolfeEngine.js (mobile) sends:
    {
        "messages": [{"role": "user", "content": "..."}],
        "max_tokens": 256,
        "temperature": 0.7,
        "top_p": 0.9,
        "stream": false
    }
    
    Expects OpenAI format response:
    {
        "id": "chatcmpl-xxx",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "mistral-large",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Response here"
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30
        }
    }
    """
    if not _consciousness_loop:
        return jsonify({"error": "Consciousness loop not initialized"}), 500
    
    try:
        data = request.get_json()
        
        # Extract from OpenAI format
        messages = data.get('messages', [])
        stream = data.get('stream', False)
        max_tokens = data.get('max_tokens', 256)
        temperature = data.get('temperature', 0.7)
        
        # Get user message (last message in array)
        user_message = ""
        if messages:
            last_msg = messages[-1]
            user_message = last_msg.get('content', '')
        
        if not user_message:
            return jsonify({"error": "No message content"}), 400
        
        # Session ID from headers or use unified default
        # Using same session ID across all interfaces so Nate remembers conversations
        session_id = request.headers.get('X-Session-Id', 'nate_conversation')
        
        logger.info(f"📱 AiCara /v1/chat/completions: session={session_id}, stream={stream}")
        
        # Get model from state or use default from .env configuration
        model = _state_manager.get_state("agent:model") if _state_manager else None
        if not model:
            model = get_model_or_default()
        
        if stream:
            # STREAMING MODE - OpenAI SSE format
            return Response(
                _generate_openai_stream(user_message, session_id, model),
                mimetype='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'X-Accel-Buffering': 'no'
                }
            )
        else:
            # NON-STREAMING MODE - Standard OpenAI response
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                result = loop.run_until_complete(
                    _consciousness_loop.process_message(
                        user_message=user_message,
                        session_id=session_id,
                        model=model,
                        include_history=True,
                        history_limit=8  # Shorter for mobile
                    )
                )
            finally:
                loop.close()
            
            response_text = result.get('response', '')
            usage = result.get('usage', {})
            
            # Return in OpenAI format
            return jsonify({
                "id": f"chatcmpl-{session_id}-{int(datetime.now().timestamp())}",
                "object": "chat.completion",
                "created": int(datetime.now().timestamp()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response_text
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": usage.get('prompt_tokens', 0),
                    "completion_tokens": usage.get('completion_tokens', 0),
                    "total_tokens": usage.get('total_tokens', 0)
                }
            })
    
    except Exception as e:
        logger.error(f"❌ OpenAI compat error: {e}", exc_info=True)
        return jsonify({
            "error": {
                "message": str(e),
                "type": "server_error",
                "code": 500
            }
        }), 500


def _generate_openai_stream(user_message: str, session_id: str, model: str):
    """
    Generate OpenAI-style SSE streaming response
    
    Yields SSE events like:
    data: {"id":"...","choices":[{"delta":{"content":"Hello"}}]}
    
    data: [DONE]
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    completion_id = f"chatcmpl-{session_id}-{int(datetime.now().timestamp())}"
    
    try:
        async_gen = _consciousness_loop.process_message_stream(
            user_message=user_message,
            session_id=session_id,
            model=model,
            include_history=True,
            history_limit=8
        )
        
        while True:
            try:
                chunk = loop.run_until_complete(async_gen.__anext__())
                
                # Convert to OpenAI streaming format
                if isinstance(chunk, dict):
                    delta = chunk.get('delta', chunk.get('content', ''))
                    done = chunk.get('done', False)
                else:
                    delta = str(chunk)
                    done = False
                
                if delta:
                    event = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(datetime.now().timestamp()),
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": delta},
                            "finish_reason": None
                        }]
                    }
                    yield f"data: {json.dumps(event)}\n\n"
                
                if done:
                    # Send finish event
                    finish_event = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(datetime.now().timestamp()),
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop"
                        }]
                    }
                    yield f"data: {json.dumps(finish_event)}\n\n"
                    yield "data: [DONE]\n\n"
                    break
                    
            except StopAsyncIteration:
                yield "data: [DONE]\n\n"
                break
                
    except Exception as e:
        logger.error(f"❌ OpenAI stream error: {e}", exc_info=True)
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
    finally:
        loop.close()


# ============================================
# Health Check for AiCara
# ============================================

@aicara_bp.route('/health', methods=['GET'])
@aicara_bp.route('/api/health', methods=['GET'])
def aicara_health():
    """
    Health check endpoint for AiCara frontends
    """
    return jsonify({
        "status": "ok",
        "service": "nate-substrate",
        "aicara_compat": True,
        "endpoints": {
            "/chat": "wolfeEngine.ts (web)",
            "/v1/chat/completions": "wolfeEngine.js (mobile)",
            "/api/places/nearby": "Google Places",
            "/api/location/context": "Location awareness"
        },
        "timestamp": datetime.now().isoformat()
    })
