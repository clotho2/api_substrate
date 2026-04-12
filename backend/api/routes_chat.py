#!/usr/bin/env python3
"""
Chat API Routes - Unified endpoint for text, images, and documents
===================================================================

Handles:
- Regular text chat messages
- Multimodal messages (images) with full image processing support
- Document/file attachments

Designed for Telegram bot integration but works with any client.
"""

from flask import Blueprint, jsonify, request
import logging
import asyncio
import base64
import os
import tempfile
from datetime import datetime
import uuid
import re
from typing import Optional, Tuple

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


def extract_image_from_content(content: list) -> Tuple[Optional[str], Optional[str]]:
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
                # Parse data URI: data:<mime_type>;base64,<data>
                match = re.match(r'data:([^;]+);base64,(.+)', url)
                if match:
                    mime_type = match.group(1)
                    base64_data = match.group(2)
                    return base64_data, mime_type
            elif url.startswith('http'):
                # Web URL - return as-is (consciousness loop handles URLs)
                return url, 'image/jpeg'  # Assume JPEG for web URLs
    
    return None, None


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
        # Use unified session ID so Agent has full conversation context across all interfaces
        session_id = data.get('session_id', 'nate_conversation')
        stream = data.get('stream', False)

        # 📍 Extract and store location context from mobile/web clients
        location_data = data.get('location')
        if location_data and isinstance(location_data, dict):
            from api.routes_places import _location_contexts
            from datetime import datetime
            _location_contexts[session_id] = {
                'latitude': location_data.get('latitude'),
                'longitude': location_data.get('longitude'),
                'city': location_data.get('city'),
                'region': location_data.get('region'),
                'country': location_data.get('country'),
                'is_in_vehicle': location_data.get('is_in_vehicle', False),
                'speed': location_data.get('speed'),
                'accuracy': location_data.get('accuracy'),
                'updated_at': datetime.now().isoformat(),
            }
            logger.info(f"📍 Location from /api/chat: {location_data.get('city')}, {location_data.get('region')} (session={session_id})")

        # Rate limiting
        if _rate_limiter:
            allowed, reason = _rate_limiter.is_allowed(session_id)
            if not allowed:
                return jsonify({"error": reason}), 429

        # Determine message type and prepare user message
        is_multimodal = data.get('multimodal', False)
        has_attachment = 'attachment' in data

        # Initialize media variables
        media_data = None
        media_type = None

        if is_multimodal:
            # MULTIMODAL MESSAGE (IMAGE)
            content = data.get('content', [])

            if not content:
                return jsonify({"error": "No content provided for multimodal message"}), 400

            # Extract text for logging and processing
            text_parts = [item['text'] for item in content if item.get('type') == 'text']
            user_message_text = ' '.join(text_parts) if text_parts else "What's in this image?"

            # Extract image data from content array
            media_data, media_type = extract_image_from_content(content)
            
            image_count = sum(1 for item in content if item.get('type') == 'image_url')
            
            logger.info(f"📸 POST /api/chat (multimodal) session={session_id}")
            logger.info(f"   Text: {user_message_text}")
            logger.info(f"   Images: {image_count}")
            if media_data:
                if media_data.startswith('http'):
                    logger.info(f"   Image URL: {media_data[:100]}...")
                else:
                    logger.info(f"   Image Data: {len(media_data)} chars (base64), Type: {media_type}")

            # Build message in standard format (image handled separately via media_data)
            user_message = {
                "role": "user",
                "content": user_message_text
            }

        elif has_attachment:
            # DOCUMENT ATTACHMENT
            # Accept caller's message verbatim — empty is fine. The mobile
            # composer no longer fabricates a fallback prompt; Agent is smart
            # enough to react to a file landing in the conversation.
            message = data.get('message', '') or ''
            attachment = data.get('attachment', {})

            filename = attachment.get('filename', 'document')
            mime_type = (attachment.get('mime_type') or 'application/octet-stream').lower()
            content_data = attachment.get('content', '') or ''

            logger.info(f"📎 POST /api/chat (attachment) session={session_id}")
            logger.info(f"   Message: {message[:200] if message else '(no caption)'}")
            logger.info(f"   File: {filename} ({mime_type})")

            # Decode the base64 payload from the mobile client. Some callers
            # send raw text; tolerate that gracefully.
            raw_bytes: Optional[bytes] = None
            try:
                raw_bytes = base64.b64decode(content_data, validate=False)
            except Exception as decode_err:
                logger.warning(f"   Could not base64-decode attachment: {decode_err}")
                raw_bytes = content_data.encode('utf-8', errors='replace') if isinstance(content_data, str) else None

            file_size = len(raw_bytes) if raw_bytes else 0
            logger.info(f"   Decoded size: {file_size} bytes")

            # Cap injected file content so we don't blow the model context.
            MAX_FILE_CHARS = 50_000

            def _looks_textlike(mt: str, fname: str) -> bool:
                if mt.startswith('text/'):
                    return True
                if mt in {
                    'application/json',
                    'application/xml',
                    'application/javascript',
                    'application/x-javascript',
                    'application/x-yaml',
                    'application/yaml',
                    'application/x-sh',
                    'application/x-python',
                    'application/x-toml',
                    'application/sql',
                }:
                    return True
                lowered = (fname or '').lower()
                code_exts = (
                    '.txt', '.md', '.markdown', '.json', '.yaml', '.yml', '.toml',
                    '.xml', '.html', '.htm', '.css', '.scss', '.less',
                    '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs',
                    '.py', '.rb', '.go', '.rs', '.java', '.kt', '.swift',
                    '.c', '.h', '.cpp', '.hpp', '.cc', '.cs', '.php',
                    '.sh', '.bash', '.zsh', '.fish', '.ps1',
                    '.sql', '.csv', '.tsv', '.log', '.ini', '.cfg', '.conf', '.env',
                )
                return lowered.endswith(code_exts)

            file_text: Optional[str] = None
            extraction_note = ''

            if raw_bytes is not None and _looks_textlike(mime_type, filename):
                try:
                    decoded = raw_bytes.decode('utf-8', errors='replace')
                    if len(decoded) > MAX_FILE_CHARS:
                        file_text = decoded[:MAX_FILE_CHARS]
                        extraction_note = (
                            f"\n\n[truncated — showing first {MAX_FILE_CHARS} of {len(decoded)} characters]"
                        )
                    else:
                        file_text = decoded
                except Exception as text_err:
                    logger.warning(f"   Text decode failed: {text_err}")

            elif raw_bytes is not None and mime_type == 'application/pdf':
                # Extract PDF text inline via PyMuPDF (already a dep via read_pdf tool)
                try:
                    import fitz  # type: ignore
                    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_pdf:
                        tmp_pdf.write(raw_bytes)
                        tmp_pdf_path = tmp_pdf.name
                    try:
                        pdf_doc = fitz.open(tmp_pdf_path)
                        pages_text = []
                        total_pages = len(pdf_doc)
                        for page_num, page in enumerate(pdf_doc, start=1):
                            pages_text.append(f"--- Page {page_num} ---\n{page.get_text()}")
                        pdf_doc.close()
                        joined = '\n\n'.join(pages_text)
                        if len(joined) > MAX_FILE_CHARS:
                            file_text = joined[:MAX_FILE_CHARS]
                            extraction_note = (
                                f"\n\n[truncated — showing first {MAX_FILE_CHARS} of {len(joined)} characters "
                                f"across {total_pages} pages]"
                            )
                        else:
                            file_text = joined
                            extraction_note = f"\n\n[extracted from {total_pages} page(s)]"
                    finally:
                        try:
                            os.unlink(tmp_pdf_path)
                        except Exception:
                            pass
                except Exception as pdf_err:
                    logger.warning(f"   PDF extraction failed: {pdf_err}")
                    file_text = None
                    extraction_note = f"\n\n[PDF text extraction failed: {pdf_err}]"

            # Build the enhanced message that goes to the model.
            caption_block = message.strip() if message else ''
            header = f"[Attached file: {filename} ({mime_type}, {file_size} bytes)]"

            if file_text is not None:
                fenced = f"```\n{file_text}{extraction_note}\n```"
                if caption_block:
                    enhanced_message = f"{caption_block}\n\n{header}\n{fenced}"
                else:
                    enhanced_message = f"{header}\n{fenced}"
            else:
                # Binary or otherwise unreadable — be honest about why
                fallback = (
                    f"{header}\n"
                    f"(This file type isn't text-readable on the server, "
                    f"so I can see it was attached but can't read the contents directly.)"
                )
                if caption_block:
                    enhanced_message = f"{caption_block}\n\n{fallback}"
                else:
                    enhanced_message = fallback

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

        # 📍 Prepend a <message_context> block with current location metadata so
        # the AI receives it as part of the incoming message (not just the
        # system prompt, which can go stale across turns).
        from api.routes_places import build_location_context_block
        location_block = build_location_context_block(session_id)
        if location_block and user_message_text:
            user_message_text = location_block + user_message_text
            if isinstance(user_message.get('content'), str):
                user_message['content'] = location_block + user_message['content']
            logger.info(f"📍 Location metadata prepended to user message ({len(location_block)} chars)")

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
                # Call consciousness loop with full conversation (including image data!)
                result = loop.run_until_complete(
                    _process_message_async(
                        user_message_text=user_message_text,
                        session_id=session_id,
                        conversation_history=conversation_history,
                        is_multimodal=is_multimodal,
                        media_data=media_data,
                        media_type=media_type
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
    is_multimodal: bool = False,
    media_data: Optional[str] = None,
    media_type: Optional[str] = None
):
    """
    Process message through consciousness loop asynchronously.

    Args:
        user_message_text: Text content for logging/storage
        session_id: Session identifier
        conversation_history: Full conversation with current message
        is_multimodal: Whether this is a multimodal request
        media_data: Base64 encoded image data or URL (for multimodal)
        media_type: MIME type of the image (e.g., 'image/jpeg')

    Returns:
        {"response": "...", "message_id": "..."}
    """
    try:
        # Generate message ID
        message_id = f"msg-{uuid.uuid4()}"

        # Save user message to state
        # Ensure content is a string (convert arrays/dicts to JSON string if needed)
        user_content_str = user_message_text if isinstance(user_message_text, str) else str(user_message_text)
        
        # Add indicator if image was included
        if media_data:
            storage_content = f"{user_content_str} [Image attached]"
        else:
            storage_content = user_content_str

        _state_manager.add_message(
            message_id=message_id,
            session_id=session_id,
            role='user',
            content=storage_content,
            message_type='inbox',
            tool_calls=None  # Explicitly pass None for tool_calls
        )

        # Process through consciousness loop with full multimodal support
        # Pass media_data and media_type so the image can be processed by the model
        result = await _consciousness_loop.process_message(
            user_message=user_message_text,
            session_id=session_id,
            model=None,  # Use default model from environment
            include_history=True,
            history_limit=24,
            message_type='inbox',
            media_data=media_data,  # Image data (base64 or URL)
            media_type=media_type   # MIME type (e.g., 'image/jpeg')
        )

        # Extract the actual response text from the result
        # consciousness_loop returns a dict with 'response', 'model', 'usage', etc.
        if isinstance(result, dict):
            response_text = result.get('response', str(result))
            tool_calls_data = result.get('tool_calls', [])
        else:
            response_text = str(result)
            tool_calls_data = []

        # Save assistant response
        response_id = f"msg-{uuid.uuid4()}"
        _state_manager.add_message(
            message_id=response_id,
            session_id=session_id,
            role='assistant',
            content=response_text,
            message_type='inbox',
            tool_calls=tool_calls_data if tool_calls_data else None
        )

        return {
            "response": response_text,
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
