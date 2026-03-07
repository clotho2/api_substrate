#!/usr/bin/env python3
"""
Streaming Chat Endpoint
Provides Server-Sent Events (SSE) streaming for real-time chat responses
WITH MULTIMODAL SUPPORT for images!
"""

from flask import Blueprint, Response, request, jsonify
import json
import asyncio
import logging
import re
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any

logger = logging.getLogger(__name__)

streaming_bp = Blueprint('streaming', __name__)

# Global dependencies (set by init function)
_consciousness_loop = None
_rate_limiter = None


def init_streaming_routes(consciousness_loop, rate_limiter):
    """Initialize streaming routes with dependencies"""
    global _consciousness_loop, _rate_limiter
    _consciousness_loop = consciousness_loop
    _rate_limiter = rate_limiter


def extract_image_from_content(content: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract base64 image data and MIME type from multimodal content array.
    
    Args:
        content: List of content items (text and image_url types)
        
    Returns:
        Tuple of (base64_data, mime_type) or (None, None) if no image found
    """
    for item in content:
        if item.get('type') == 'image_url':
            image_url_data = item.get('image_url', {})
            url = image_url_data.get('url', '')
            
            # Handle data URI format: data:image/jpeg;base64,<base64_data>
            if url.startswith('data:'):
                match = re.match(r'data:([^;]+);base64,(.+)', url)
                if match:
                    mime_type = match.group(1)
                    base64_data = match.group(2)
                    return base64_data, mime_type
            elif url.startswith('http'):
                # Web URL - return as-is
                return url, 'image/jpeg'
    
    return None, None


@streaming_bp.route('/ollama/api/chat/stream', methods=['POST'])
def stream_chat():
    """
    Streaming chat endpoint using Server-Sent Events (SSE).
    NOW WITH MULTIMODAL SUPPORT for images!
    
    Request formats:
    
    1. TEXT MESSAGE:
    {
        "messages": [{"role": "user", "content": "Hello!"}],
        "model": "mistralai/mistral-large-2512"
    }
    
    2. MULTIMODAL (Image):
    {
        "messages": [{"role": "user", "content": [...]}],  // Multimodal content array
        "model": "mistralai/mistral-large-2512",
        "multimodal": true
    }
    
    OR with separate media fields:
    {
        "messages": [{"role": "user", "content": "What's in this image?"}],
        "media_data": "<base64_image>",
        "media_type": "image/jpeg"
    }
    
    Returns:
        SSE stream with:
        - "thinking" event: When model is thinking
        - "content" event: Streaming response chunks
        - "tool_call" event: Tool execution
        - "done" event: Stream complete
    """
    try:
        if not _consciousness_loop:
            return jsonify({'error': 'Consciousness loop not initialized'}), 500
        
        data = request.json
        messages = data.get('messages', [])
        model = data.get('model', None)
        session_id = request.headers.get('X-Session-Id', 'default')
        
        # Rate limiting
        if _rate_limiter:
            allowed, reason = _rate_limiter.is_allowed(session_id)
            if not allowed:
                return jsonify({"error": reason}), 429
        
        if not messages:
            return jsonify({"error": "No messages provided"}), 400
        
        last_message = messages[-1]
        message_content = last_message.get('content', '')
        message_type = data.get('message_type', 'inbox')
        
        # Initialize media variables
        media_data = None
        media_type = None
        
        # Check for multimodal content in the message
        is_multimodal = data.get('multimodal', False)
        
        if isinstance(message_content, list):
            # Content is a multimodal array (OpenAI/Grok format)
            # Extract text and image data
            text_parts = [item.get('text', '') for item in message_content if item.get('type') == 'text']
            user_message = ' '.join(text_parts) if text_parts else "What's in this image?"
            
            # Extract image data
            media_data, media_type = extract_image_from_content(message_content)
            is_multimodal = media_data is not None
            
        elif is_multimodal and data.get('content'):
            # Multimodal content in separate 'content' field (Telegram format)
            content_array = data.get('content', [])
            text_parts = [item.get('text', '') for item in content_array if item.get('type') == 'text']
            user_message = ' '.join(text_parts) if text_parts else "What's in this image?"
            
            # Extract image data
            media_data, media_type = extract_image_from_content(content_array)
            
        else:
            # Standard text message
            user_message = message_content if isinstance(message_content, str) else str(message_content)
        
        # Check for direct media_data/media_type in request (alternative format)
        if not media_data:
            media_data = data.get('media_data')
            media_type = data.get('media_type')
        
        # Log request
        message_preview = user_message[:200] + ('...' if len(user_message) > 200 else '')
        logger.info(f"📡 Streaming chat: model={model}, session={session_id}")
        logger.info(f"   Message ({len(user_message)} chars): {message_preview}")
        if media_data:
            if isinstance(media_data, str) and media_data.startswith('http'):
                logger.info(f"   📸 Image URL: {media_data[:80]}...")
            else:
                logger.info(f"   📸 Image: {len(media_data) if media_data else 0} chars (base64), Type: {media_type}")
        logger.info(f"   Full message: {user_message}")
        
        def generate():
            """Generate SSE stream"""
            try:
                # Send "thinking" event immediately
                yield f"event: thinking\ndata: {json.dumps({'status': 'thinking', 'message': 'Thinking...'})}\n\n"
                
                # Create async event loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # Process message with REAL STREAMING and multimodal support!
                    async_gen = _consciousness_loop.process_message_stream(
                        user_message=user_message,
                        session_id=session_id,
                        model=model,
                        include_history=True,
                        history_limit=20,
                        message_type=message_type,
                        media_data=media_data,  # Image data (base64 or URL)
                        media_type=media_type   # MIME type
                    )
                    
                    # Run async generator
                    while True:
                        try:
                            event = loop.run_until_complete(async_gen.__anext__())
                            
                            event_type = event.get('type')
                            
                            if event_type == 'thinking':
                                # Send thinking event
                                yield f"event: thinking\ndata: {json.dumps(event)}\n\n"
                            
                            elif event_type == 'content':
                                # Stream content chunk
                                yield f"event: content\ndata: {json.dumps(event)}\n\n"
                            
                            elif event_type == 'content_reset':
                                # Tool call XML was streamed as content - tell client to discard it
                                yield f"event: content_reset\ndata: {json.dumps(event)}\n\n"

                            elif event_type == 'tool_call':
                                # Stream tool call
                                yield f"event: tool_call\ndata: {json.dumps(event.get('data', {}))}\n\n"
                            
                            elif event_type == 'done':
                                # Final result - response fields are at top level of event, not under 'result'
                                event_data = {k: v for k, v in event.items() if k != 'type'}
                                yield f"event: done\ndata: {json.dumps({'success': True, **event_data})}\n\n"
                                break  # Stream complete!
                            
                            elif event_type == 'error':
                                # Error event
                                yield f"event: error\ndata: {json.dumps(event)}\n\n"
                                break
                                
                        except StopAsyncIteration:
                            # Generator exhausted
                            break
                    
                finally:
                    loop.close()
                    
            except Exception as e:
                logger.error(f"Streaming error: {e}")
                import traceback
                traceback.print_exc()
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        
        return Response(
            generate(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive'
            }
        )
        
    except Exception as e:
        logger.error(f"Stream endpoint error: {e}")
        return jsonify({'error': str(e)}), 500

