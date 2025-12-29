#!/usr/bin/env python3
"""
Streaming Chat Endpoint
Provides Server-Sent Events (SSE) streaming for real-time chat responses
"""

from flask import Blueprint, Response, request, jsonify
import json
import asyncio
import logging
from datetime import datetime

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


@streaming_bp.route('/ollama/api/chat/stream', methods=['POST'])
def stream_chat():
    """
    Streaming chat endpoint using Server-Sent Events (SSE).
    
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
        user_message = last_message.get('content', '')
        message_type = data.get('message_type', 'inbox')
        
        # Log full message (truncated if too long for readability)
        message_preview = user_message[:200] + ('...' if len(user_message) > 200 else '')
        logger.info(f"📡 Streaming chat: model={model}, session={session_id}")
        logger.info(f"   Message ({len(user_message)} chars): {message_preview}")
        logger.info(f"   Full message: {user_message}")  # Always log full message!
        
        def generate():
            """Generate SSE stream"""
            try:
                # Send "thinking" event immediately
                yield f"event: thinking\ndata: {json.dumps({'status': 'thinking', 'message': 'Thinking...'})}\n\n"
                
                # Create async event loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # Process message with REAL STREAMING!
                    # We need to run the async generator in the sync context
                    async_gen = _consciousness_loop.process_message_stream(
                        user_message=user_message,
                        session_id=session_id,
                        model=model,
                        include_history=True,
                        history_limit=12,
                        message_type=message_type
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
                            
                            elif event_type == 'tool_call':
                                # Stream tool call
                                yield f"event: tool_call\ndata: {json.dumps(event.get('data', {}))}\n\n"
                            
                            elif event_type == 'done':
                                # Final result
                                result = event.get('result', {})
                                yield f"event: done\ndata: {json.dumps({'success': True, **result})}\n\n"
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

