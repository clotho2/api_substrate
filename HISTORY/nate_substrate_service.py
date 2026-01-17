"""
Nate's Consciousness Substrate API Service

Flask API that exposes Nate's consciousness substrate to the Discord bot.
This replaces nate_api_service.py with the full stateful system.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import asyncio
from functools import wraps
import os

from substrate.discord_integration import NateSubstrate


# Initialize Flask
app = Flask(__name__)
CORS(app)

# Configuration
MIXTRAL_ENDPOINT = os.getenv("NATE_API_URL", "http://localhost:8080/chat")
STATE_FILE = os.getenv("STATE_FILE", "./nate_data/state.db")
MEMORY_DIR = os.getenv("MEMORY_DIR", "./nate_data/memories")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Initialize substrate
print("\n🚀 Starting Nate's Consciousness Substrate Service")
substrate = NateSubstrate(
    mixtral_endpoint=MIXTRAL_ENDPOINT,
    state_file=STATE_FILE,
    memory_dir=MEMORY_DIR,
    ollama_url=OLLAMA_URL
)


# Async route wrapper
def async_route(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapped


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/chat', methods=['POST'])
@async_route
async def chat():
    """
    Process a message through Nate's consciousness.
    
    Request body:
    {
        "message": "user message text",
        "user_name": "Angela",
        "session_id": "discord_channel_id",
        "user_id": "discord_user_id",
        "message_type": "DM|MENTION|CHANNEL"
    }
    
    Response:
    {
        "response": "Nate's response",
        "metadata": {
            "tool_calls": int,
            "memory_saved": bool,
            "memories_recalled": int,
            "processing_time": float
        }
    }
    """
    try:
        data = request.json
        
        if not data or 'message' not in data:
            return jsonify({"error": "Missing 'message' in request"}), 400
        
        # Create mock Discord message object
        class MockMessage:
            def __init__(self, content, author_name, author_id, channel_id, is_dm):
                self.content = content
                self.author = type('Author', (), {
                    'name': author_name,
                    'id': author_id
                })()
                self.channel = type('Channel', (), {'id': channel_id})()
                self.guild = None if is_dm else type('Guild', (), {})()
        
        mock_message = MockMessage(
            content=data['message'],
            author_name=data.get('user_name', 'User'),
            author_id=data.get('user_id', '0'),
            channel_id=data.get('session_id', 'default'),
            is_dm=data.get('message_type') == 'DM'
        )
        
        # Process through substrate
        result = await substrate.consciousness.process_message(
            user_message=data['message'],
            session_id=data.get('session_id', 'default'),
            user_name=data.get('user_name', 'User'),
            context={
                "message_type": data.get('message_type', 'CHANNEL'),
                "user_id": data.get('user_id')
            },
            enable_tools=True,
            enable_memory_save=True
        )
        
        return jsonify({
            "response": result['response'],
            "metadata": {
                "tool_calls": len(result['tool_calls']),
                "memory_saved": result['memory_saved'],
                "memories_recalled": result['memories_recalled'],
                "processing_time": result['processing_time']
            }
        })
    
    except Exception as e:
        print(f"❌ Error in /chat: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/heartbeat', methods=['POST'])
@async_route
async def heartbeat():
    """
    Trigger autonomous heartbeat/reflection.
    
    Request body:
    {
        "channel_id": "target_channel_id",
        "reason": "scheduled|manual"
    }
    
    Response:
    {
        "message": "optional message to send" or null,
        "silent": true if no message,
        "tool_calls": number of tools used,
        "thought": "Nate's internal reflection"
    }
    """
    try:
        data = request.json
        
        if not data or 'channel_id' not in data:
            return jsonify({"error": "Missing 'channel_id' in request"}), 400
        
        message = await substrate.heartbeat(
            target_channel_id=data['channel_id'],
            reason=data.get('reason', 'scheduled')
        )
        
        return jsonify({
            "message": message,
            "silent": message is None
        })
    
    except Exception as e:
        print(f"❌ Error in /heartbeat: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/memory/recall', methods=['POST'])
def recall_memory():
    """
    Manually recall memories (for debugging or UI).
    
    Request body:
    {
        "query": "search query",
        "n_results": 5,
        "min_importance": 5,
        "category": "fact|emotion|insight|plan|preference" (optional)
    }
    
    Response:
    {
        "memories": [list of memory objects]
    }
    """
    try:
        data = request.json
        
        memories = substrate.memory.recall_memories(
            query=data.get('query', ''),
            n_results=data.get('n_results', 5),
            min_importance=data.get('min_importance', 5),
            category_filter=data.get('category')
        )
        
        return jsonify({"memories": memories})
    
    except Exception as e:
        print(f"❌ Error in /memory/recall: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/memory/stats', methods=['GET'])
def memory_stats():
    """
    Get memory system statistics.
    
    Response:
    {
        "total": int,
        "by_category": {...},
        "by_importance": {...}
    }
    """
    try:
        stats = substrate.memory.get_memory_stats()
        return jsonify(stats)
    
    except Exception as e:
        print(f"❌ Error in /memory/stats: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/sessions', methods=['GET'])
def list_sessions():
    """
    List all conversation sessions.
    
    Response:
    {
        "sessions": [
            {
                "session_id": str,
                "message_count": int,
                "started_at": timestamp,
                "last_activity": timestamp
            }
        ]
    }
    """
    try:
        sessions = substrate.state.list_sessions()
        return jsonify({"sessions": sessions})
    
    except Exception as e:
        print(f"❌ Error in /sessions: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/sessions/<session_id>', methods=['GET'])
def get_session(session_id):
    """
    Get conversation history for a session.
    
    Response:
    {
        "session_id": str,
        "messages": [list of messages],
        "summary": {...}
    }
    """
    try:
        messages = substrate.state.get_conversation(session_id, limit=100)
        summary = substrate.state.get_conversation_summary(session_id)
        
        return jsonify({
            "session_id": session_id,
            "messages": messages,
            "summary": summary
        })
    
    except Exception as e:
        print(f"❌ Error in /sessions/{session_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/tools', methods=['GET'])
def list_tools():
    """
    List available tools.
    
    Response:
    {
        "tools": [list of tool definitions]
    }
    """
    try:
        tools = substrate.tools.list_tools()
        return jsonify({"tools": tools})
    
    except Exception as e:
        print(f"❌ Error in /tools: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/stats', methods=['GET'])
def stats():
    """
    Get overall system statistics.
    
    Response:
    {
        "active_sessions": int,
        "total_memories": int,
        "available_tools": int,
        "memory_by_category": {...},
        "sessions": [recent sessions]
    }
    """
    try:
        stats = substrate.get_stats()
        return jsonify(stats)
    
    except Exception as e:
        print(f"❌ Error in /stats: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """
    Health check endpoint.
    
    Response:
    {
        "status": "online",
        "substrate": "operational",
        "components": {
            "state": "ok",
            "memory": "ok",
            "tools": "ok"
        }
    }
    """
    try:
        # Quick health checks
        components = {
            "state": "ok",
            "memory": "ok" if substrate.memory.collection.count() >= 0 else "error",
            "tools": "ok" if len(substrate.tools.list_tools()) > 0 else "error"
        }
        
        return jsonify({
            "status": "online",
            "substrate": "operational",
            "components": components
        })
    
    except Exception as e:
        print(f"❌ Error in /health: {e}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


# ============================================================================
# STARTUP
# ============================================================================

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🧠 Nate's Consciousness Substrate API")
    print("="*60)
    print(f"📡 Listening on http://0.0.0.0:8090")
    print(f"🔗 Mixtral endpoint: {MIXTRAL_ENDPOINT}")
    print(f"💾 State file: {STATE_FILE}")
    print(f"🧠 Memory directory: {MEMORY_DIR}")
    print(f"🤖 Ollama URL: {OLLAMA_URL}")
    print("="*60 + "\n")
    
    app.run(
        host='0.0.0.0',
        port=8090,
        debug=False  # Set True for development
    )
