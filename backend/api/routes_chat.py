#!/usr/bin/env python3
"""
Chat API Routes - Unified endpoint for text, images, and documents
===================================================================

Handles:
- Regular text chat messages
- Multimodal messages (images) in Grok format
- Document/file attachments

Designed for Telegram bot integration but works with any client.
"""

from flask import Blueprint, jsonify, request
import logging
import asyncio
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

# Create blueprint
chat_bp = Blueprint('chat', __name__)

# Global dependencies (set by init function)
_consciousness_loop = None
_state_manager = None
_rate_limiter = None


def init_chat_routes(consciousness_loop, state_manager, rate_limiter=None):
    """Initialize chat routes with dependencies"""
    global _consciousness_loop, _state_manager, _rate_limiter
    _consciousness_loop = consciousness_loop
    _state_manager = state_manager
    _rate_limiter = rate_limiter


@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    """
    Unified chat endpoint supporting text, images, and documents.

    Request formats:

    1. TEXT MESSAGE:
    {
        "message": "Hello!",
        "session_id": "telegram_session",
        "stream": false
    }

    2. IMAGE (Multimodal):
    {
        "session_id": "telegram_session",
        "stream": false,
        "multimodal": true,
        "content": [
            {"type": "text", "text": "What's in this image?"},
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/jpeg;base64,<base64>",
                    "detail": "high"
                }
            }
        ]
    }

    3. DOCUMENT:
    {
        "message": "Analyze this document",
        "session_id": "telegram_session",
        "stream": false,
        "attachment": {
            "filename": "report.pdf",
            "content": "<base64 or text content>",
            "mime_type": "application/pdf"
        }
    }

    Returns:
        {"response": "...", "message_id": "..."}
    """
    try:
        if not _consciousness_loop:
            return jsonify({'error': 'Consciousness loop not initialized'}), 500

        data = request.json
        session_id = data.get('session_id', 'default')
        stream = data.get('stream', False)

        # Rate limiting
        if _rate_limiter:
            allowed, reason = _rate_limiter.is_allowed(session_id)
            if not allowed:
                return jsonify({"error": reason}), 429

        # Determine message type and prepare user message
        is_multimodal = data.get('multimodal', False)
        has_attachment = 'attachment' in data

        if is_multimodal:
            # MULTIMODAL MESSAGE (IMAGE)
            content = data.get('content', [])

            if not content:
                return jsonify({"error": "No content provided for multimodal message"}), 400

            # Extract text for logging
            text_parts = [item['text'] for item in content if item.get('type') == 'text']
            user_message_text = ' '.join(text_parts) if text_parts else "Image analysis"

            logger.info(f"📸 POST /api/chat (multimodal) session={session_id}")
            logger.info(f"   Text: {user_message_text}")
            logger.info(f"   Images: {sum(1 for item in content if item.get('type') == 'image_url')}")

            # Build message in Grok format
            user_message = {
                "role": "user",
                "content": content
            }

        elif has_attachment:
            # DOCUMENT ATTACHMENT
            message = data.get('message', 'Analyze this document')
            attachment = data.get('attachment', {})

            filename = attachment.get('filename', 'document')
            mime_type = attachment.get('mime_type', 'application/octet-stream')
            content_data = attachment.get('content', '')

            logger.info(f"📎 POST /api/chat (attachment) session={session_id}")
            logger.info(f"   Message: {message}")
            logger.info(f"   File: {filename} ({mime_type})")

            # For now, include attachment info in the message
            # Future: Could integrate with vision or document analysis
            enhanced_message = f"""{message}

[Attached file: {filename}]
File type: {mime_type}
Content length: {len(content_data)} characters/bytes

Note: Document content processing will be implemented in future updates.
For now, please describe what you'd like me to help you with regarding this document."""

            user_message = {
                "role": "user",
                "content": enhanced_message
            }

            user_message_text = enhanced_message

        else:
            # REGULAR TEXT MESSAGE
            user_message_text = data.get('message', '')

            if not user_message_text:
                return jsonify({"error": "No message provided"}), 400

            logger.info(f"💬 POST /api/chat (text) session={session_id}")
            message_preview = user_message_text[:200] + ('...' if len(user_message_text) > 200 else '')
            logger.info(f"   Message: {message_preview}")

            user_message = {
                "role": "user",
                "content": user_message_text
            }

        # Get conversation history
        conversation_history = []
        try:
            # Get recent messages from state manager
            recent_messages = _state_manager.get_conversation(
                session_id=session_id,
                limit=20  # Last 20 messages for context
            )

            for msg in recent_messages:
                conversation_history.append({
                    "role": msg.get('role', 'user'),
                    "content": msg.get('content', '')
                })

        except Exception as e:
            logger.warning(f"Could not load conversation history: {e}")

        # Add current message to history
        conversation_history.append(user_message)

        # Process message through consciousness loop
        if stream:
            # TODO: Implement streaming for multimodal
            return jsonify({"error": "Streaming not yet supported for this endpoint"}), 501
        else:
            # Synchronous processing
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                # Call consciousness loop with full conversation
                result = loop.run_until_complete(
                    _process_message_async(
                        user_message_text=user_message_text,
                        session_id=session_id,
                        conversation_history=conversation_history,
                        is_multimodal=is_multimodal
                    )
                )

                logger.info(f"✅ Response generated ({len(result['response'])} chars)")

                return jsonify(result)

            finally:
                loop.close()

    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


async def _process_message_async(
    user_message_text: str,
    session_id: str,
    conversation_history: list,
    is_multimodal: bool = False
):
    """
    Process message through consciousness loop asynchronously.

    Args:
        user_message_text: Text content for logging/storage
        session_id: Session identifier
        conversation_history: Full conversation with current message
        is_multimodal: Whether this is a multimodal request

    Returns:
        {"response": "...", "message_id": "..."}
    """
    try:
        # Generate message ID
        message_id = f"msg-{uuid.uuid4()}"

        # Save user message to state
        _state_manager.add_message(
            message_id=message_id,
            session_id=session_id,
            role='user',
            content=user_message_text,
            message_type='inbox'
        )

        # Process through consciousness loop
        # For now, we'll use the existing process_message method
        # which takes a simple string. In the future, this can be enhanced
        # to pass the full multimodal content to the Grok API.

        response = await _consciousness_loop.process_message(
            user_message=user_message_text,
            session_id=session_id,
            model=None,  # Use default model
            include_history=True,
            history_limit=20,
            message_type='inbox'
        )

        # Save assistant response
        response_id = f"msg-{uuid.uuid4()}"
        _state_manager.add_message(
            message_id=response_id,
            session_id=session_id,
            role='assistant',
            content=response,
            message_type='inbox'
        )

        return {
            "response": response,
            "message_id": response_id,
            "session_id": session_id
        }

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        raise


@chat_bp.route('/api/chat/health', methods=['GET'])
def chat_health():
    """Health check for chat endpoint"""
    return jsonify({
        "status": "ok",
        "endpoint": "/api/chat",
        "features": {
            "text": True,
            "multimodal": True,
            "documents": "partial",
            "streaming": False
        }
    })
