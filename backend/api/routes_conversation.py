#!/usr/bin/env python3
"""
Conversation History API Routes
Provides access to the agent's complete conversation history
"""

from flask import Blueprint, jsonify, request
import logging
import asyncio
from datetime import datetime
from core.config import DEFAULT_AGENT_ID

logger = logging.getLogger(__name__)

# Create blueprint
conversation_bp = Blueprint('conversation', __name__)

# Global state manager (will be set by init function)
_state_manager = None
_consciousness_loop = None
_postgres_manager = None


def init_conversation_routes(state_manager, consciousness_loop=None, postgres_manager=None):
    """Initialize conversation routes with dependencies"""
    global _state_manager, _consciousness_loop, _postgres_manager
    _state_manager = state_manager
    _consciousness_loop = consciousness_loop
    _postgres_manager = postgres_manager


@conversation_bp.route('/api/conversation/<session_id>', methods=['GET'])
def get_conversation(session_id='default'):
    """
    Get full conversation history for a session.
    
    Args:
        session_id: Session ID (default: "default")
        
    Query params:
        limit: Max messages to return (default: 1000)
        offset: Skip N messages (default: 0)
        
    Returns:
        {
            "session_id": "default",
            "messages": [
                {"role": "user", "content": "...", "timestamp": "..."},
                {"role": "assistant", "content": "...", "timestamp": "..."}
            ],
            "total": 42
        }
    """
    try:
        limit = int(request.args.get('limit', 1000))
        offset = int(request.args.get('offset', 0))
        
        # 🏴‍☠️ POSTGRESQL-FIRST: Try PostgreSQL, fallback to SQLite
        messages = []
        
        if _postgres_manager:
            # Get agent ID from config (can be overridden via DEFAULT_AGENT_ID env var)
            agent_id = DEFAULT_AGENT_ID
            
            try:
                # Get messages from PostgreSQL
                pg_messages = _postgres_manager.get_messages(
                    agent_id=agent_id,
                    session_id=session_id,
                    limit=limit
                )
                
                # Convert to frontend format
                messages = [
                    {
                        'role': msg.role,
                        'content': msg.content,
                        'timestamp': msg.created_at.isoformat() if msg.created_at else '',
                        'tool_calls': msg.tool_calls,
                        'thinking': msg.thinking
                    }
                    for msg in pg_messages
                ]
                
                logger.info(f"📬 GET /conversation/{session_id} → {len(messages)} messages (PostgreSQL)")
            except Exception as e:
                logger.warning(f"PostgreSQL read failed, falling back to SQLite: {e}")
                # Fallback to SQLite
                if _state_manager:
                    messages = _state_manager.get_conversation(
                        session_id=session_id,
                        limit=limit
                    )
        else:
            # SQLite only
            if not _state_manager:
                return jsonify({'error': 'No database available'}), 500
            
            messages = _state_manager.get_conversation(
                session_id=session_id,
                limit=limit
            )
        
        # Apply offset
        if offset > 0:
            messages = messages[offset:]
        
        return jsonify({
            'session_id': session_id,
            'messages': messages,
            'total': len(messages)
        })
        
    except Exception as e:
        logger.error(f"Error getting conversation: {e}")
        return jsonify({'error': str(e)}), 500


@conversation_bp.route('/api/conversation/<session_id>/clear', methods=['POST'])
def clear_conversation(session_id='default'):
    """
    Clear conversation history for a session.
    
    Args:
        session_id: Session ID to clear
        
    Returns:
        {"success": true, "cleared": N}
    """
    try:
        if not _state_manager:
            return jsonify({'error': 'State manager not initialized'}), 500
        
        # Get current count
        messages = _state_manager.get_conversation(session_id=session_id, limit=10000)
        count = len(messages)
        
        # Clear messages
        _state_manager.clear_conversation(session_id=session_id)
        
        logger.warning(f"🗑️  POST /conversation/{session_id}/clear → Cleared {count} messages")
        
        return jsonify({
            'success': True,
            'cleared': count
        })
        
    except Exception as e:
        logger.error(f"Error clearing conversation: {e}")
        return jsonify({'error': str(e)}), 500


@conversation_bp.route('/api/conversation/<session_id>/summarize', methods=['POST'])
def trigger_summary(session_id='default'):
    """
    Manually trigger conversation summary generation.
    
    This allows users to create summaries on-demand, not just when
    context window is >80% full.
    
    Args:
        session_id: Session ID to summarize
        
    Returns:
        {
            "success": true,
            "summary_id": 123,
            "message_count": 150,
            "from_timestamp": "...",
            "to_timestamp": "..."
        }
    """
    try:
        if not _state_manager:
            return jsonify({'error': 'State manager not initialized'}), 500
        
        if not _consciousness_loop:
            return jsonify({'error': 'Consciousness loop not initialized'}), 500
        
        logger.info(f"📝 POST /conversation/{session_id}/summarize → Manual summary trigger")
        
        # Get all messages since last summary
        latest_summary = _state_manager.get_latest_summary(session_id)
        
        if latest_summary:
            from_timestamp = datetime.fromisoformat(latest_summary['to_timestamp'])
            logger.info(f"   Last summary: {latest_summary['created_at']}")
            logger.info(f"   Summarizing messages after: {latest_summary['to_timestamp']}")
        else:
            from_timestamp = None
            logger.info(f"   No previous summary - summarizing ALL messages")
        
        # Get messages to summarize
        all_messages = _state_manager.get_conversation(session_id=session_id, limit=100000)
        
        # Filter by timestamp if needed
        messages_to_summarize = []
        for msg in all_messages:
            if from_timestamp and msg.timestamp <= from_timestamp:
                continue  # Skip already summarized
            
            messages_to_summarize.append({
                'role': msg.role,
                'content': msg.content,
                'timestamp': msg.timestamp.isoformat() if hasattr(msg.timestamp, 'isoformat') else str(msg.timestamp)
            })
        
        if not messages_to_summarize:
            return jsonify({
                'success': False,
                'error': 'No new messages to summarize',
                'message': 'All messages have already been summarized'
            }), 400
        
        logger.info(f"📝 Summarizing {len(messages_to_summarize)} messages...")
        
        # Generate summary using consciousness loop's summary generator
        from core.summary_generator import SummaryGenerator
        
        generator = SummaryGenerator(state_manager=_state_manager)
        summary_result = generator.generate_summary(
            messages=messages_to_summarize,
            session_id=session_id
        )
        
        # Save summary to DB
        from_ts = datetime.fromisoformat(summary_result['from_timestamp'])
        to_ts = datetime.fromisoformat(summary_result['to_timestamp'])
        
        summary_id = _state_manager.save_summary(
            session_id=session_id,
            summary=summary_result['summary'],
            from_timestamp=from_ts,
            to_timestamp=to_ts,
            message_count=summary_result['message_count'],
            token_count=summary_result['token_count']
        )
        
        # CRITICAL: Also add as SYSTEM MESSAGE to conversation!
        # This way the agent can see it in context!
        import uuid
        summary_msg_id = f"msg-{uuid.uuid4()}"
        _state_manager.add_message(
            message_id=summary_msg_id,
            session_id=session_id,
            role='system',
            content=summary_result['summary'],
            message_type='system'  # Mark as system message (not inbox!)
        )
        logger.info(f"✅ Summary added as system message (id: {summary_msg_id})")
        
        # Save to Archive Memory
        try:
            from tools.memory_tools import MemoryTools
            memory_tools = MemoryTools(_state_manager)
            
            archive_text = f"""📅 Chat Zusammenfassung ({from_ts.strftime('%d.%m.%Y %H:%M')} - {to_ts.strftime('%d.%m.%Y %H:%M')})

{summary_result['summary']}

---
📊 Stats: {summary_result['message_count']} Nachrichten zusammengefasst"""
            
            memory_tools.add_to_archive(
                content=archive_text,
                metadata={
                    'type': 'conversation_summary',
                    'session_id': session_id,
                    'summary_id': summary_id,
                    'from_timestamp': summary_result['from_timestamp'],
                    'to_timestamp': summary_result['to_timestamp'],
                    'message_count': summary_result['message_count']
                }
            )
            logger.info(f"✅ Summary saved to Archive Memory!")
        except Exception as e:
            logger.warning(f"⚠️  Failed to save to Archive: {e}")
        
        # Save summary as System Message in messages table!
        import uuid
        summary_content = f"""📝 **ZUSAMMENFASSUNG** (Manuell erstellt)

**Zeitraum:** {from_ts.strftime('%d.%m.%Y %H:%M')} - {to_ts.strftime('%d.%m.%Y %H:%M')}  
**Nachrichten:** {summary_result['message_count']}

{summary_result['summary']}

---
📊 Diese Zusammenfassung umfasst {summary_result['message_count']} Nachrichten vom {from_ts.strftime('%d.%m.%Y %H:%M')} bis {to_ts.strftime('%d.%m.%Y %H:%M')}.

💾 Vollständige Details: `search_archive()` oder `read_archive()`"""
        
        summary_msg_id = f"msg-{uuid.uuid4()}"
        _state_manager.add_message(
            message_id=summary_msg_id,
            session_id=session_id,
            role="system",
            content=summary_content,
            message_type="system"
        )
        logger.info(f"✅ Summary saved to DB as system message (id: {summary_msg_id})")
        
        return jsonify({
            'success': True,
            'summary_id': summary_id,
            'message_id': summary_msg_id,
            'message_count': summary_result['message_count'],
            'from_timestamp': summary_result['from_timestamp'],
            'to_timestamp': summary_result['to_timestamp'],
            'token_count': summary_result['token_count']
        })
        
    except Exception as e:
        logger.error(f"Error triggering summary: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

