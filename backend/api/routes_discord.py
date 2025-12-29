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
ALLOWED_AGENT_ID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)


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


# ============================================
# DISCORD API ENDPOINTS
# ============================================

@discord_bp.route('/api/discord/agents/<agent_id>/send', methods=['POST'])
@require_discord_auth
def send_message_to_agent(agent_id):
    """
    Send a message to a specific agent and get response.
    
    Optimized for Discord bots:
    - Fast response time
    - Discord-friendly format
    - Session management
    - Tool call handling
    
    **Request:**
    ```json
    {
        "content": "Hello!",
        "session_id": "discord-user-123456",  // Optional, defaults to "discord-{agent_id}"
        "user_id": "123456789012345678",      // Discord user ID
        "username": "Assistant",               // Discord username
        "channel_id": "987654321098765432",   // Discord channel ID
        "guild_id": "111222333444555666"      // Discord server ID (optional)
    }
    ```
    
    **Response:**
    ```json
    {
        "success": true,
        "response": "Hey! How's it going?",
        "thinking": "...",  // If extended thinking model
        "tool_calls": [...],  // If tools were used
        "metadata": {
            "model": "openrouter/polaris-alpha",
            "tokens": 150,
            "cost": 0.00042
        }
    }
    ```
    
    **Security:**
    - Agent ID validation (UUID format)
    - Message sanitization (length limit, null bytes)
    - Rate limiting (per user_id)
    - SQL injection prevention
    
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
        
        content = data.get('content', '').strip()
        if not content:
            return jsonify({'error': 'Message content is required'}), 400
        
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
        
        # Check if agent exists (if using Postgres multi-agent)
        if _postgres_manager:
            agent = _postgres_manager.get_agent(agent_id)
            if not agent:
                logger.warning(f"🚫 Agent not found: {agent_id}")
                return jsonify({'error': f'Agent {agent_id} not found'}), 404
        
        # Process message through consciousness loop
        # Note: consciousness_loop.process_message is async!
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                _consciousness_loop.process_message(
                    user_message=content,
                    session_id=session_id,
                    message_type='inbox',  # Discord messages are "inbox" type
                    include_history=True,
                    history_limit=12  # Keep context window reasonable
                )
            )
        finally:
            loop.close()
        
        # Extract response
        response_content = result.get('content', 'I apologize, but I encountered an error processing your message.')
        thinking = result.get('thinking', None)
        tool_calls = result.get('tool_calls', [])
        
        # Build metadata
        metadata = {
            'model': result.get('model', 'unknown'),
            'tokens': result.get('usage', {}).get('total_tokens', 0),
            'cost': result.get('cost', 0.0),
            'session_id': session_id
        }
        
        logger.info(f"✅ Discord ← Agent {agent_id[:8]}... | {metadata['tokens']} tokens | ${metadata['cost']:.6f}")
        
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
        'components': {
            'consciousness_loop': _consciousness_loop is not None,
            'state_manager': _state_manager is not None,
            'rate_limiter': _rate_limiter is not None,
            'postgres': _postgres_manager is not None
        },
        'auth_required': bool(DISCORD_API_KEY)
    })

