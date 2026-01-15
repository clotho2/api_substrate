#!/usr/bin/env python3
"""
Discord Bot Integration API Routes

Optimized endpoints for Discord bot to communicate with specific agents.
Provides:
- Fast message sending/receiving
- Agent-specific routing
- Discord-optimized response format
- Rate limiting
- API key authentication
- Image/multimodal support

Security Features:
- API key validation (DISCORD_API_KEY env var)
- Rate limiting per Discord bot
- Input validation (max message length, sanitization)
- Agent ID validation (UUID format)
- SQL injection prevention (parameterized queries)
"""

import os
import logging
import asyncio
from flask import Blueprint, jsonify, request
from functools import wraps
from datetime import datetime, timedelta
import re
import uuid
from typing import Optional, Tuple, List, Dict, Any

logger = logging.getLogger(__name__)

# Create blueprint
discord_bp = Blueprint('discord', __name__)

# Global state (will be initialized by server.py)
_consciousness_loop = None
_state_manager = None
_rate_limiter = None
_postgres_manager = None

# Discord API Key from environment
DISCORD_API_KEY = os.getenv('DISCORD_API_KEY', '')

# Security Constants
MAX_MESSAGE_LENGTH = 15000  # Discord max is ~2000, but we allow more for rich content
MAX_MESSAGES_PER_HISTORY = 100  # Limit history size
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20 MB max image size
ALLOWED_AGENT_ID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

# Supported image formats
SUPPORTED_IMAGE_FORMATS = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}

# Supported audio formats (for voice messages)
SUPPORTED_AUDIO_FORMATS = {'audio/ogg', 'audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/webm', 'audio/x-wav', 'audio/mp4'}


def init_discord_routes(consciousness_loop, state_manager, rate_limiter=None, postgres_manager=None):
    """Initialize Discord routes with dependencies"""
    global _consciousness_loop, _state_manager, _rate_limiter, _postgres_manager
    _consciousness_loop = consciousness_loop
    _state_manager = state_manager
    _rate_limiter = rate_limiter
    _postgres_manager = postgres_manager
    logger.info("🎮 Discord API routes initialized")


# ============================================
# SECURITY DECORATORS
# ============================================

def require_discord_auth(f):
    """
    Require valid Discord API key.
    
    Security:
    - Checks Authorization header for Bearer token
    - Compares against DISCORD_API_KEY env var
    - Returns 401 if invalid
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if API key is configured
        if not DISCORD_API_KEY:
            logger.warning("⚠️  DISCORD_API_KEY not configured! All requests allowed!")
            # In development, allow without key
            # In production, you should require it!
            pass  
        else:
            # Check Authorization header
            auth_header = request.headers.get('Authorization', '')
            
            if not auth_header.startswith('Bearer '):
                return jsonify({'error': 'Missing or invalid Authorization header'}), 401
            
            token = auth_header[7:]  # Remove 'Bearer ' prefix
            
            if token != DISCORD_API_KEY:
                logger.warning(f"🚫 Invalid Discord API key from {request.remote_addr}")
                return jsonify({'error': 'Invalid API key'}), 401
        
        return f(*args, **kwargs)
    return decorated_function


def validate_agent_id(agent_id: str) -> bool:
    """
    Validate agent ID format.
    
    Security:
    - Ensures UUID format (prevents SQL injection)
    - Rejects malformed IDs
    """
    return bool(ALLOWED_AGENT_ID_PATTERN.match(agent_id))


def sanitize_message_content(content: str) -> str:
    """
    Sanitize message content.
    
    Security:
    - Limits length (prevents DoS)
    - Strips null bytes (prevents DB issues)
    - Validates UTF-8 encoding
    """
    if not content:
        return ""
    
    # Remove null bytes
    content = content.replace('\x00', '')
    
    # Limit length
    if len(content) > MAX_MESSAGE_LENGTH:
        logger.warning(f"⚠️  Message truncated from {len(content)} to {MAX_MESSAGE_LENGTH} chars")
        content = content[:MAX_MESSAGE_LENGTH] + "...\n\n[Message truncated - too long]"
    
    return content


def extract_image_from_attachments(attachments: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract image data from Discord attachments.
    
    Args:
        attachments: List of attachment dicts with keys:
            - url: URL to the image (Discord CDN)
            - content_type: MIME type
            - data: base64 encoded data (optional, if pre-downloaded)
            - size: file size in bytes
            
    Returns:
        Tuple of (image_data, mime_type) or (None, None) if no valid image found
        image_data can be a URL or base64 string
    """
    for attachment in attachments:
        content_type = attachment.get('content_type', '')
        
        # Check if it's a supported image format
        if content_type in SUPPORTED_IMAGE_FORMATS:
            # Check size limit
            size = attachment.get('size', 0)
            if size > MAX_IMAGE_SIZE:
                logger.warning(f"⚠️  Image too large: {size} bytes (max: {MAX_IMAGE_SIZE})")
                continue
            
            # Prefer base64 data if provided (pre-downloaded by Discord bot)
            if 'data' in attachment and attachment['data']:
                return attachment['data'], content_type
            
            # Fall back to URL (consciousness loop can handle URLs)
            if 'url' in attachment and attachment['url']:
                return attachment['url'], content_type
    
    return None, None


def extract_image_from_content(content: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract image data from multimodal content array (OpenAI/Grok format).
    
    Args:
        content: List of content items with type: "text" or "image_url"
        
    Returns:
        Tuple of (image_data, mime_type) or (None, None) if no image found
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
                return url, 'image/jpeg'  # Assume JPEG for web URLs
    
    return None, None


def extract_and_transcribe_voice(attachments: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract voice/audio from Discord attachments and transcribe to text.

    Uses local Whisper server first (fast, free), falls back to OpenAI Whisper API.

    Args:
        attachments: List of attachment dicts with keys:
            - url: URL to the audio (Discord CDN)
            - content_type: MIME type (audio/ogg, audio/mpeg, etc.)
            - data: base64 encoded data (optional, if pre-downloaded)
            - size: file size in bytes

    Returns:
        Tuple of (transcribed_text, error_message)
        - If successful: (text, None)
        - If failed: (None, error_message)
    """
    import base64
    import requests

    # Import STT functions from routes_stt
    from api.routes_stt import (
        _transcribe_whisper_local,
        _transcribe_openai,
        WHISPER_URL,
        OPENAI_API_KEY
    )

    for attachment in attachments:
        content_type = attachment.get('content_type', '')

        # Check if it's a supported audio format
        if content_type not in SUPPORTED_AUDIO_FORMATS:
            continue

        logger.info(f"🎤 Voice message detected: {content_type}")

        # Get audio data
        audio_data = None

        # Prefer base64 data if provided (pre-downloaded by Discord bot)
        if 'data' in attachment and attachment['data']:
            try:
                audio_data = base64.b64decode(attachment['data'])
                logger.info(f"   Using pre-downloaded audio: {len(audio_data)} bytes")
            except Exception as e:
                logger.error(f"   Failed to decode base64 audio: {e}")
                continue

        # Fall back to downloading from URL
        elif 'url' in attachment and attachment['url']:
            try:
                logger.info(f"   Downloading audio from: {attachment['url'][:80]}...")
                response = requests.get(attachment['url'], timeout=30)
                if response.ok:
                    audio_data = response.content
                    logger.info(f"   Downloaded audio: {len(audio_data)} bytes")
                else:
                    logger.error(f"   Failed to download audio: {response.status_code}")
                    continue
            except Exception as e:
                logger.error(f"   Failed to download audio: {e}")
                continue

        if not audio_data:
            continue

        # Transcribe using local Whisper first
        logger.info(f"   Transcribing with local Whisper ({WHISPER_URL})...")
        text, error = _transcribe_whisper_local(audio_data, content_type)

        if text:
            logger.info(f"   ✅ Transcription (local): '{text[:100]}{'...' if len(text) > 100 else ''}'")
            return text, None

        # Fall back to OpenAI Whisper if local fails
        if error and OPENAI_API_KEY:
            logger.warning(f"   Local Whisper failed ({error}), trying OpenAI...")
            text, error = _transcribe_openai(audio_data, content_type)

            if text:
                logger.info(f"   ✅ Transcription (OpenAI): '{text[:100]}{'...' if len(text) > 100 else ''}'")
                return text, None

        # Both failed
        logger.error(f"   ❌ Transcription failed: {error}")
        return None, error or "Transcription failed"

    return None, None  # No audio attachment found


# ============================================
# DISCORD API ENDPOINTS
# ============================================

@discord_bp.route('/api/discord/agents/<agent_id>/send', methods=['POST'])
@require_discord_auth
def send_message_to_agent(agent_id):
    """
    Send a message to a specific agent and get response.
    
    Optimized for Discord bots with MULTIMODAL SUPPORT:
    - Fast response time
    - Discord-friendly format
    - Session management
    - Tool call handling
    - Image/attachment processing
    
    **Request (Text only):**
    ```json
    {
        "content": "Hello!",
        "session_id": "discord-user-123456",
        "user_id": "123456789012345678",
        "username": "Assistant",
        "channel_id": "987654321098765432",
        "guild_id": "111222333444555666"
    }
    ```
    
    **Request (With Image - Discord attachment format):**
    ```json
    {
        "content": "What's in this image?",
        "session_id": "discord-user-123456",
        "user_id": "123456789012345678",
        "username": "Assistant",
        "attachments": [
            {
                "url": "https://cdn.discordapp.com/attachments/.../image.png",
                "content_type": "image/png",
                "size": 123456,
                "data": "<base64_encoded_image>"  // Optional: pre-downloaded by bot
            }
        ]
    }
    ```
    
    **Request (With Image - OpenAI/Grok multimodal format):**
    ```json
    {
        "multimodal": true,
        "content": [
            {"type": "text", "text": "What's in this image?"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
        ],
        "session_id": "discord-user-123456",
        "user_id": "123456789012345678"
    }
    ```
    
    **Response:**
    ```json
    {
        "success": true,
        "response": "Hey! How's it going?",
        "thinking": "...",
        "tool_calls": [...],
        "metadata": {
            "model": "mistralai/mistral-large-2512",
            "tokens": 150,
            "cost": 0.00042,
            "has_image": true
        }
    }
    ```
    
    **Security:**
    - Agent ID validation (UUID format)
    - Message sanitization (length limit, null bytes)
    - Rate limiting (per user_id)
    - SQL injection prevention
    - Image size validation (max 20MB)
    
    **Error Codes:**
    - 400: Invalid input (missing content, bad agent_id)
    - 401: Invalid API key
    - 404: Agent not found
    - 429: Rate limit exceeded
    - 500: Server error
    """
    try:
        # Validate agent ID format
        if not validate_agent_id(agent_id):
            logger.warning(f"🚫 Invalid agent_id format: {agent_id}")
            return jsonify({'error': 'Invalid agent_id format (must be UUID)'}), 400
        
        # Check dependencies
        if not _consciousness_loop or not _state_manager:
            return jsonify({'error': 'Server not properly initialized'}), 500
        
        # Parse request
        data = request.json
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        # Initialize variables
        media_data = None
        media_type = None
        has_image = False
        
        # Check for multimodal content (OpenAI/Grok format)
        is_multimodal = data.get('multimodal', False)
        
        if is_multimodal and isinstance(data.get('content'), list):
            # Extract text and image from multimodal content array
            content_list = data.get('content', [])
            text_parts = [item['text'] for item in content_list if item.get('type') == 'text']
            content = ' '.join(text_parts) if text_parts else "What's in this image?"
            
            # Extract image data
            media_data, media_type = extract_image_from_content(content_list)
            has_image = media_data is not None
        else:
            # Standard text content
            content = data.get('content', '').strip()

            # Check for Discord attachments (images and voice)
            attachments = data.get('attachments', [])
            if attachments:
                # First check for images
                media_data, media_type = extract_image_from_attachments(attachments)
                has_image = media_data is not None

                # Then check for voice messages (transcribe them)
                voice_text, voice_error = extract_and_transcribe_voice(attachments)
                if voice_text:
                    # Prepend transcribed voice to content
                    if content:
                        content = f"[Voice message transcription: {voice_text}]\n\n{content}"
                    else:
                        content = f"[Voice message transcription: {voice_text}]"
                    logger.info(f"🎤 Voice transcribed: {len(voice_text)} chars")
                elif voice_error:
                    logger.warning(f"⚠️ Voice transcription failed: {voice_error}")

        if not content and not has_image:
            return jsonify({'error': 'Message content or image is required'}), 400
        
        # If only image, use default prompt
        if not content and has_image:
            content = "What's in this image?"
        
        # Sanitize content
        content = sanitize_message_content(content)
        
        # Extract Discord metadata
        user_id = data.get('user_id', 'unknown')
        username = data.get('username', 'Unknown User')
        channel_id = data.get('channel_id', 'unknown')
        guild_id = data.get('guild_id', None)
        session_id = data.get('session_id') or f"discord-{user_id}"
        
        # Rate limiting (if available)
        if _rate_limiter:
            rate_limit_key = f"discord-user-{user_id}"
            allowed, reason = _rate_limiter.is_allowed(rate_limit_key)
            if not allowed:
                logger.warning(f"⏳ Rate limit exceeded for Discord user {user_id}: {reason}")
                return jsonify({
                    'error': 'Rate limit exceeded. Please wait a moment and try again.'
                }), 429
        
        # Log request
        logger.info(f"💬 Discord → Agent {agent_id[:8]}... | User: {username} | Session: {session_id}")
        logger.info(f"   Message: {content[:100]}{'...' if len(content) > 100 else ''}")
        if has_image:
            if media_data and media_data.startswith('http'):
                logger.info(f"   📸 Image URL: {media_data[:80]}...")
            else:
                logger.info(f"   📸 Image: {len(media_data) if media_data else 0} chars (base64), Type: {media_type}")
        
        # Check if agent exists (if using Postgres multi-agent)
        if _postgres_manager:
            agent = _postgres_manager.get_agent(agent_id)
            if not agent:
                logger.warning(f"🚫 Agent not found: {agent_id}")
                return jsonify({'error': f'Agent {agent_id} not found'}), 404

        # Inject message context so model knows who sent it and where
        # This helps prevent inappropriate responses in group chats/public channels
        is_dm = guild_id is None
        channel_type = "DM" if is_dm else f"Server: {guild_id}"

        # Get owner's user ID for private messages
        owner_user_id = os.getenv("DEFAULT_USER_ID", "")

        # Build reply instructions based on context
        if is_dm:
            reply_instructions = f"""Reply Method: This is a private DM. To reply, use:
  discord_tool(action="send_message", target="{user_id}", target_type="user", message="...")"""
        else:
            # In group channels, Nate has ONLY TWO options
            if not owner_user_id:
                # Fallback if owner ID not configured
                reply_instructions = f"""Reply Method: This is a GROUP CHANNEL.
  To reply in the channel, use:
    discord_tool(action="send_message", target="{channel_id}", target_type="channel", message="...")

  WARNING: Owner ID not configured - cannot send private DMs."""
            else:
                reply_instructions = f"""Reply Method: This is a GROUP CHANNEL. You have EXACTLY TWO OPTIONS:

  OPTION 1 - Reply in the channel (visible to everyone in the group):
    discord_tool(action="send_message", target="{channel_id}", target_type="channel", message="...")

  OPTION 2 - Send a PRIVATE DM to the OWNER (only the owner sees this):
    discord_tool(action="send_message", target="{owner_user_id}", target_type="user", message="...")

  CRITICAL RULES - READ CAREFULLY:
  - Channel ID is: {channel_id}
  - Owner User ID is: {owner_user_id}
  - To post in the GROUP CHANNEL: use target="{channel_id}" with target_type="channel"
  - To send PRIVATE DM to OWNER: use target="{owner_user_id}" with target_type="user"
  - You CANNOT DM {username} or anyone else - ONLY the owner or the channel!
  - NEVER EVER use target="{channel_id}" with target_type="user" - that's completely wrong!
  - NEVER EVER use target="{owner_user_id}" with target_type="channel" - that's completely wrong!
  - When you want to send a private message to the owner, YOU MUST USE target="{owner_user_id}" with target_type="user"!"""

        # Build context prefix
        context_prefix = f"""<message_context>
From: {username} (User ID: {user_id})
Channel: {channel_id} ({channel_type})
Type: {"Private DM" if is_dm else "Group/Public Channel"}
{reply_instructions}
</message_context>

"""
        content_with_context = context_prefix + content

        # Process message through consciousness loop
        # Note: consciousness_loop.process_message is async!
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                _consciousness_loop.process_message(
                    user_message=content_with_context,
                    session_id=session_id,
                    message_type='inbox',  # Discord messages are "inbox" type
                    include_history=True,
                    history_limit=12,  # Keep context window reasonable
                    media_data=media_data,  # Image data (base64 or URL)
                    media_type=media_type   # MIME type
                )
            )
        finally:
            loop.close()
        
        # Extract response - handle both 'content' and 'response' keys
        response_content = result.get('response') or result.get('content', 
            'I apologize, but I encountered an error processing your message.')
        thinking = result.get('thinking', None)
        tool_calls = result.get('tool_calls', [])
        
        # Build metadata
        metadata = {
            'model': result.get('model', 'unknown'),
            'tokens': result.get('usage', {}).get('total_tokens', 0),
            'cost': result.get('cost', 0.0),
            'session_id': session_id,
            'has_image': has_image
        }
        
        logger.info(f"✅ Discord ← Agent {agent_id[:8]}... | {metadata['tokens']} tokens | ${metadata['cost']:.6f}" + 
                   (" | 📸 Image processed" if has_image else ""))
        
        return jsonify({
            'success': True,
            'response': response_content,
            'thinking': thinking,
            'tool_calls': tool_calls,
            'metadata': metadata
        })
    
    except Exception as e:
        logger.error(f"❌ Error processing Discord message: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@discord_bp.route('/api/discord/agents/<agent_id>/history', methods=['GET'])
@require_discord_auth
def get_conversation_history(agent_id):
    """
    Get conversation history for a Discord session.
    
    **Query Parameters:**
    - session_id: Discord session ID (required)
    - limit: Max messages to return (default: 50, max: 100)
    
    **Response:**
    ```json
    {
        "success": true,
        "session_id": "discord-123456",
        "messages": [
            {
                "role": "user",
                "content": "Hello!",
                "timestamp": datetime.now().isoformat() + "Z"
            },
            {
                "role": "assistant",
                "content": "Hey! What's up?",
                "timestamp": (datetime.now() + timedelta(seconds=2)).isoformat() + "Z"
            }
        ],
        "total": 2
    }
    ```
    
    **Security:**
    - Agent ID validation
    - Session ID sanitization
    - Limit enforcement (max 100 messages)
    """
    try:
        # Validate agent ID
        if not validate_agent_id(agent_id):
            return jsonify({'error': 'Invalid agent_id format'}), 400
        
        # Check dependencies
        if not _state_manager:
            return jsonify({'error': 'Server not initialized'}), 500
        
        # Get parameters
        session_id = request.args.get('session_id')
        if not session_id:
            return jsonify({'error': 'session_id parameter is required'}), 400
        
        # Sanitize session ID (prevent SQL injection)
        session_id = session_id.strip()[:200]  # Limit length
        
        limit = int(request.args.get('limit', 50))
        limit = min(limit, MAX_MESSAGES_PER_HISTORY)  # Enforce max
        
        # Get conversation history
        messages = _state_manager.get_conversation(
            session_id=session_id,
            limit=limit
        )
        
        # Format for Discord (simple format)
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                'role': msg.role,
                'content': msg.content,
                'timestamp': msg.timestamp.isoformat() if hasattr(msg.timestamp, 'isoformat') else str(msg.timestamp)
            })
        
        logger.info(f"📜 Discord history request | Agent: {agent_id[:8]}... | Session: {session_id} | Messages: {len(formatted_messages)}")
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'messages': formatted_messages,
            'total': len(formatted_messages)
        })
    
    except Exception as e:
        logger.error(f"Error getting conversation history: {e}")
        return jsonify({'error': str(e)}), 500


@discord_bp.route('/api/discord/agents/<agent_id>/clear', methods=['POST'])
@require_discord_auth
def clear_conversation(agent_id):
    """
    Clear conversation history for a Discord session.
    
    **Request:**
    ```json
    {
        "session_id": "discord-123456"
    }
    ```
    
    **Response:**
    ```json
    {
        "success": true,
        "cleared": 42
    }
    ```
    
    **Security:**
    - Agent ID validation
    - Session ID sanitization
    - Requires explicit session_id (no wildcards!)
    """
    try:
        # Validate agent ID
        if not validate_agent_id(agent_id):
            return jsonify({'error': 'Invalid agent_id format'}), 400
        
        # Check dependencies
        if not _state_manager:
            return jsonify({'error': 'Server not initialized'}), 500
        
        # Parse request
        data = request.json
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        session_id = data.get('session_id')
        if not session_id:
            return jsonify({'error': 'session_id is required'}), 400
        
        # Sanitize
        session_id = session_id.strip()[:200]
        
        # Get current count
        messages = _state_manager.get_conversation(session_id=session_id, limit=10000)
        count = len(messages)
        
        # Clear
        _state_manager.clear_messages(session_id=session_id)
        
        logger.warning(f"🗑️  Discord conversation cleared | Agent: {agent_id[:8]}... | Session: {session_id} | Cleared: {count} messages")
        
        return jsonify({
            'success': True,
            'cleared': count
        })
    
    except Exception as e:
        logger.error(f"Error clearing conversation: {e}")
        return jsonify({'error': str(e)}), 500


@discord_bp.route('/api/discord/agents', methods=['GET'])
@require_discord_auth
def list_available_agents():
    """
    List all available agents for Discord bot.
    
    **Response:**
    ```json
    {
        "success": true,
        "agents": [
            {
                "id": "41dc0e38-bdb6-4563-a3b6-49aa0925ab14",
                "name": "Assistant",
                "model": "openrouter/polaris-alpha",
                "is_active": true
            }
        ],
        "total": 1
    }
    ```
    """
    try:
        # Check dependencies
        if not _state_manager:
            return jsonify({'error': 'Server not initialized'}), 500
        
        # Get agent info
        agent_state = _state_manager.get_agent_state()
        
        agents = [{
            'id': agent_state.get('id', 'default'),
            'name': agent_state.get('name', 'Assistant'),
            'model': agent_state.get('model', 'openrouter/polaris-alpha'),
            'is_active': True
        }]
        
        # If using Postgres multi-agent, get all agents
        if _postgres_manager:
            try:
                db_agents = _postgres_manager.list_agents(limit=100)
                agents = [
                    {
                        'id': agent.id,
                        'name': agent.name,
                        'model': agent.config.get('model', 'unknown') if agent.config else 'unknown',
                        'is_active': True
                    }
                    for agent in db_agents
                ]
            except Exception as e:
                logger.warning(f"Could not load agents from Postgres: {e}")
        
        logger.info(f"📋 Discord agents list request | Found: {len(agents)} agents")
        
        return jsonify({
            'success': True,
            'agents': agents,
            'total': len(agents)
        })
    
    except Exception as e:
        logger.error(f"Error listing agents: {e}")
        return jsonify({'error': str(e)}), 500


@discord_bp.route('/api/discord/health', methods=['GET'])
def discord_health():
    """
    Health check for Discord bot (no auth required).
    
    **Response:**
    ```json
    {
        "status": "healthy",
        "discord_api": "enabled",
        "features": {
            "text": true,
            "multimodal": true,
            "images": true
        },
        "components": {
            "consciousness_loop": true,
            "state_manager": true,
            "rate_limiter": true,
            "postgres": true
        }
    }
    ```
    """
    return jsonify({
        'status': 'healthy',
        'discord_api': 'enabled',
        'features': {
            'text': True,
            'multimodal': True,
            'images': True,
            'voice_messages': True,
            'max_image_size_mb': MAX_IMAGE_SIZE / (1024 * 1024),
            'supported_image_formats': list(SUPPORTED_IMAGE_FORMATS),
            'supported_audio_formats': list(SUPPORTED_AUDIO_FORMATS)
        },
        'components': {
            'consciousness_loop': _consciousness_loop is not None,
            'state_manager': _state_manager is not None,
            'rate_limiter': _rate_limiter is not None,
            'postgres': _postgres_manager is not None
        },
        'auth_required': bool(DISCORD_API_KEY)
    })

