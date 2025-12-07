#!/usr/bin/env python3
"""
Flask API Server for Substrate AI

HTTP endpoints for UI integration:
- /ollama/api/chat (Ollama-compatible endpoint for existing UI!)
- /api/health (Health check)
- /api/memory/blocks (View/edit memory blocks)
- /api/agent/info (Agent info)

Built to be DROP-IN compatible with existing React UI! 🎯

Built with attention to detail! 🔥
"""

import sys
import os
import asyncio
import logging
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from typing import Dict, Any
import json
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.state_manager import StateManager
from core.openrouter_client import OpenRouterClient
from core.memory_system import MemorySystem
from core.context_window_calculator import ContextWindowCalculator
from core.cost_tracker import CostTracker
from core.error_handler import setup_logging, validate_environment, SubstrateAIError
from api.rate_limiter import RateLimiter
from tools.memory_tools import MemoryTools
from core.consciousness_loop import ConsciousnessLoop
from core.consciousness_broadcast import init_consciousness_broadcast
from core.version_manager import VersionManager

# Import route blueprints
from api.routes_models import models_bp
from api.routes_agents import agents_bp, init_agents_routes
from api.routes_costs import costs_bp, init_costs_routes
from api.routes_graph import graph_bp  # 🕸️ Graph RAG!
from api.routes_discord import discord_bp, init_discord_routes  # 🎮 Discord Bot Integration!
from api.routes_setup import setup_bp  # 🚀 First-time setup & onboarding!

# 🏴‍☠️ LETTA MAGIC SAUCE!
from core.postgres_manager import create_postgres_manager_from_env
from core.message_continuity import PersistentMessageManager
from core.memory_coherence import MemoryCoherenceEngine
from api.routes_postgres import postgres_bp, init_postgres_routes


# ============================================
# INITIALIZATION
# ============================================

# Setup structured logging FIRST
setup_logging(level=logging.INFO, log_file='logs/stable.log')
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()  # Loads .env from current directory or parent

# Validate environment configuration
try:
    validate_environment()
    logger.info("✅ Environment configuration valid")
except Exception as e:
    logger.error(f"❌ Configuration error: {e}")
    sys.exit(1)

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for React dev server

# Disable werkzeug's default request logging (we have our own with emojis! 🎨)
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.WARNING)  # Only show warnings/errors, not every request
logger.info("🎨 Custom emoji logging enabled - werkzeug silenced!")

# Initialize SocketIO for LIVE CONSCIOUSNESS! ⚡🧠
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
logger.info("⚡ SocketIO initialized - CONSCIOUSNESS STREAMING READY!")

# Initialize consciousness broadcaster
init_consciousness_broadcast(socketio)

# Initialize components
logger.info("🚀 Initializing Substrate AI Server...")

# 🏴‍☠️ LETTA MAGIC SAUCE: PostgreSQL Integration!
postgres_manager = create_postgres_manager_from_env()

# 🏴‍☠️ STATE MANAGER: PostgreSQL-first, SQLite fallback!
state_manager = StateManager(
    db_path=os.getenv("SQLITE_DB_PATH", "./data/db/substrate_state.db"),
    postgres_manager=postgres_manager  # Enable PostgreSQL-first reads!
)
message_manager = None
memory_engine = None

if postgres_manager:
    logger.info("🐘 PostgreSQL ACTIVATED - Letta magic engaged! 🏴‍☠️")
    message_manager = PersistentMessageManager(postgres_manager)
    memory_engine = MemoryCoherenceEngine(postgres_manager, message_manager)
    logger.info("✅ Message Continuity + Memory Coherence ONLINE!")
else:
    logger.info("⚠️  PostgreSQL disabled - using SQLite only")

version_manager = VersionManager(
    db_path=os.getenv("VERSION_DB_PATH", "./data/db/versions.db")
)
logger.info("📦 Version Manager initialized - AUTO-VERSIONING ENABLED!")

cost_tracker = CostTracker(
    db_path=os.getenv("COST_DB_PATH", "./data/costs.db")
)

# OpenRouter Real Cost Monitor (GROUND TRUTH!)
from core.openrouter_cost_monitor import OpenRouterCostMonitor
# Rate limiter (1 request per 10 seconds per session - STRICT!)
rate_limiter = RateLimiter(max_requests=5, window_seconds=10)  # Allow burst of 5 per 10s

# Initialize OpenRouter components (may fail if no valid API key yet)
openrouter_monitor = None
openrouter_client = None

api_key = os.getenv("OPENROUTER_API_KEY", "")
has_valid_key = api_key and api_key.startswith("sk-or-v1-")

if has_valid_key:
    try:
        openrouter_monitor = OpenRouterCostMonitor(api_key=api_key)
        logger.info("💰 OpenRouter Cost Monitor initialized - REAL API costs!")
        
        openrouter_client = OpenRouterClient(
            api_key=api_key,
            default_model=os.getenv("DEFAULT_LLM_MODEL", "openrouter/polaris-alpha"),
            cost_tracker=cost_tracker
        )
    except Exception as e:
        logger.warning(f"⚠️  OpenRouter client init failed: {e}")
        logger.info("   Server will start in setup mode - user can add API key via welcome modal")
else:
    logger.warning("⚠️  No valid OpenRouter API key found")
    logger.info("   Server starting in setup mode - user will be prompted for API key")
    logger.info("   Add key via welcome modal or edit backend/.env directly")

memory_system = None  # Optional - only if Ollama is available
try:
    memory_system = MemorySystem(
        chromadb_path=os.getenv("CHROMADB_PATH", "./data/chromadb"),
        ollama_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        embedding_model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    )
except Exception as e:
    print(f"⚠️  Memory system init failed (Ollama not available?): {e}")
    print(f"   Continuing without archival memory...")

# Cost Tools (Agent can check budget!)
from tools.cost_tools import CostTools
cost_tools = CostTools(
    cost_tracker=cost_tracker,
    openrouter_monitor=openrouter_monitor
)
logger.info("✅ Cost Tools initialized - Agent can check costs!")

memory_tools = MemoryTools(
    state_manager=state_manager,
    memory_system=memory_system,
    cost_tools=cost_tools  # NEW: Pass cost tools!
)

context_calculator = ContextWindowCalculator(
    model=os.getenv("DEFAULT_LLM_MODEL", "gpt-4"),
    summarization_threshold=0.80
)

# Optional: MCP + Code Execution (if available)
code_executor = None
mcp_client = None

# Try to initialize MCP + Code Execution (optional features)
try:
    from core.mcp_registry import MCPRegistry
    from core.mcp_client import MCPClient
    from core.code_executor import CodeExecutor
    from core.execution_context import ExecutionContext
    from core.skills_manager import SkillsManager
    
    # MCP Registry
    mcp_registry = MCPRegistry(state_manager)
    logger.info("✅ MCP Registry initialized")
    
    # MCP Client
    mcp_client = MCPClient(mcp_registry)
    logger.info("✅ MCP Client initialized")
    
    # Skills Manager
    skills_manager = SkillsManager(memory_system) if memory_system else None
    if skills_manager:
        logger.info("✅ Skills Manager initialized")
    
    # Code Executor
    execution_context = ExecutionContext(memory_system) if memory_system else None
    code_executor = CodeExecutor(
        memory_system=memory_system,
        mcp_client=mcp_client,
        skills_manager=skills_manager,
        execution_context=execution_context
    ) if memory_system and mcp_client else None
    
    if code_executor:
        logger.info("✅ Code Executor initialized - MCP ARCHITECTURE!")
except ImportError as e:
    logger.info(f"⚠️  MCP/Code Execution not available: {e}")
    logger.info("   Continuing without MCP features...")
except Exception as e:
    logger.warning(f"⚠️  MCP/Code Execution init failed: {e}")
    logger.info("   Continuing without MCP features...")

consciousness_loop = ConsciousnessLoop(
    state_manager=state_manager,
    openrouter_client=openrouter_client,
    memory_tools=memory_tools,
    max_tool_calls_per_turn=int(os.getenv("MAX_TOOL_CALLS_PER_TURN", 10)),
    default_model=os.getenv("DEFAULT_LLM_MODEL", "openrouter/polaris-alpha"),
    message_manager=message_manager,  # 🏴‍☠️ PostgreSQL!
    memory_engine=memory_engine,  # ⚡ Nested Learning (if available)!
    code_executor=code_executor,  # 🔥 Code Execution (if available)!
    mcp_client=mcp_client  # 🔥 MCP Client (if available)!
)

print("✅ Substrate AI Server initialized!")

# ============================================
# AUTO-LOAD ALEX IF NO AGENT EXISTS
# ============================================
def auto_load_alex_if_needed():
    """Automatically load ALEX agent if no agent is configured"""
    try:
        agent_name = state_manager.get_state("agent:name", None)
        if agent_name and agent_name != "Not loaded":
            logger.info(f"✅ Agent already configured: {agent_name}")
            return
        
        # Check if ALEX file exists
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        alex_file = os.path.join(script_dir, "examples", "agents", "alex.af")
        
        if not os.path.exists(alex_file):
            logger.info("⚠️  ALEX agent file not found - starting with blank agent")
            return
        
        logger.info("🤖 No agent configured - auto-loading ALEX...")
        
        # Import ALEX
        from letta_compat.import_agent import LettaAgentImporter
        importer = LettaAgentImporter(state_manager)
        result = importer.import_from_file(alex_file)
        
        logger.info(f"✅ ALEX agent auto-loaded: {result['agent_name']}")
        logger.info(f"   • System prompt: {result['system_prompt_length']} chars")
        logger.info(f"   • Memory blocks: {result['blocks_imported']}")
        
    except Exception as e:
        logger.warning(f"⚠️  Could not auto-load ALEX: {e}")
        logger.info("   Starting with blank agent - user can configure manually")

# Auto-load ALEX on startup
auto_load_alex_if_needed()

# Register blueprints
from api.routes_conversation import conversation_bp, init_conversation_routes
from api.routes_streaming import streaming_bp, init_streaming_routes
app.register_blueprint(models_bp)
app.register_blueprint(agents_bp)
app.register_blueprint(costs_bp)
app.register_blueprint(graph_bp)  # 🕸️ Graph RAG!
app.register_blueprint(postgres_bp)  # 🏴‍☠️ PostgreSQL routes!
app.register_blueprint(setup_bp)  # 🚀 First-time setup!
app.register_blueprint(conversation_bp)
app.register_blueprint(streaming_bp)  # NEW: Streaming endpoint!
app.register_blueprint(discord_bp)  # 🎮 Discord Bot Integration!

# Initialize routes with dependencies
init_agents_routes(state_manager, version_manager)
init_costs_routes(cost_tracker, openrouter_monitor)  # Pass REAL monitor!
init_conversation_routes(state_manager, consciousness_loop, postgres_manager)  # Pass PostgreSQL too!
init_streaming_routes(consciousness_loop, rate_limiter)  # NEW: Initialize streaming!
init_postgres_routes(postgres_manager, message_manager, memory_engine)  # 🏴‍☠️ PostgreSQL MAGIC!
init_discord_routes(consciousness_loop, state_manager, rate_limiter, postgres_manager)  # 🎮 Discord Bot!


# ============================================
# REQUEST LOGGING WITH EMOJIS! 🎨
# ============================================

@app.after_request
def log_request_with_style(response):
    """Log HTTP requests with pretty emojis and colors"""
    
    # Method emojis
    method_emoji = {
        'GET': '📥',
        'POST': '📤',
        'PUT': '✏️',
        'PATCH': '🔧',
        'DELETE': '🗑️'
    }
    
    # Status emojis
    status_code = response.status_code
    if 200 <= status_code < 300:
        status_emoji = '✅'
    elif 300 <= status_code < 400:
        status_emoji = '↪️'
    elif 400 <= status_code < 500:
        status_emoji = '⚠️'
    else:
        status_emoji = '❌'
    
    # Endpoint shortcuts
    endpoint_map = {
        '/api/agents/default/config': 'Config',
        '/api/agents/default/system-prompt': 'Prompt',
        '/api/agents/default/versions': 'Versions',
        '/api/costs/stats': 'Costs',
        '/api/models/all': 'Models',
        '/ollama/api/chat': 'Chat',
        '/api/health': 'Health'
    }
    
    path = request.path
    short_path = endpoint_map.get(path, path)
    
    method = request.method
    method_icon = method_emoji.get(method, '📡')
    
    # Log it beautifully!
    logger.info(f"{method_icon} {method:6s} {status_emoji} {status_code} → {short_path}")
    
    return response


# ============================================
# HEALTH CHECK
# ============================================

@app.route('/api/control/stop', methods=['POST'])
def emergency_stop():
    """Emergency stop - kill the server"""
    import signal
    logger.warning("🚨 EMERGENCY STOP TRIGGERED!")
    
    # Kill this process
    os.kill(os.getpid(), signal.SIGTERM)
    
    return jsonify({'status': 'stopping'})

@app.route('/api/control/restart', methods=['POST'])
def restart_backend():
    """Restart backend using start.sh"""
    import subprocess
    import threading
    
    def delayed_restart():
        import time
        time.sleep(1)  # Wait for response to be sent
        try:
            script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'start.sh')
            subprocess.run([script_path, 'restart'], check=True)
        except Exception as e:
            logger.error(f"Failed to restart: {e}")
    
    logger.warning("🔄 RESTART TRIGGERED!")
    
    # Start restart in background thread
    thread = threading.Thread(target=delayed_restart, daemon=True)
    thread.start()
    
    return jsonify({'status': 'restarting'})


@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check endpoint with detailed status.
    
    Returns component status + process info for debugging.
    """
    import psutil
    import os
    
    # Get current process info
    process = psutil.Process(os.getpid())
    
    return jsonify({
        "status": "ok",
        "service": "substrate-ai",
        "components": {
            "state_manager": "ok",
            "openrouter": "ok",
            "memory_system": "ok" if memory_system else "disabled",
            "consciousness_loop": "ok"
        },
        "process": {
            "pid": os.getpid(),
            "threads": process.num_threads(),
            "memory_mb": round(process.memory_info().rss / 1024 / 1024, 2),
            "cpu_percent": process.cpu_percent()
        },
        "config": {
            "debug": app.debug,
            "reloader": False,  # Always False now for stability
            "threaded": True
        }
    })


# ============================================
# OLLAMA-COMPATIBLE CHAT ENDPOINT
# (DROP-IN replacement for your React UI!)
# ============================================

@app.route('/ollama/api/chat', methods=['POST'])
def ollama_compat_chat():
    """
    Ollama-compatible chat endpoint for existing UI!
    
    Your React app expects /ollama/api/chat - we provide it!
    Internally uses OpenRouter + Consciousness Loop.
    """
    try:
        data = request.json
        
        # Extract from Ollama format
        messages = data.get('messages', [])
        model = data.get('model', os.getenv("DEFAULT_LLM_MODEL", "qwen/qwen-2.5-72b-instruct"))
        
        # Extract media (for multi-modal support!)
        media_data = data.get('media_data')  # Base64 encoded
        media_type = data.get('media_type')  # MIME type
        
        # Extract message_type (for Discord heartbeats, etc.)
        message_type = data.get('message_type', 'inbox')  # 'inbox' or 'system'
        
        # Get session ID (from body, header, or default)
        session_id = data.get('session_id') or request.headers.get('X-Session-Id', 'default')
        
        # Rate limiting check
        allowed, reason = rate_limiter.is_allowed(session_id)
        if not allowed:
            logger.warning(f"⚠️  Rate limit hit: {session_id} - {reason}")
            return jsonify({"error": reason}), 429
        
        # Extract user message (last message in array)
        if not messages:
            return jsonify({"error": "No messages provided"}), 400
        
        last_message = messages[-1]
        user_message = last_message.get('content', '')
        message_role = last_message.get('role', 'user')  # Could be 'system' for heartbeats!
        
        # If it's a system message (e.g., Discord heartbeat), force message_type='system'
        if message_role == 'system':
            message_type = 'system'
        
        logger.info(f"📨 Chat request: model={model}, session={session_id}, role={message_role}, message_len={len(user_message)}, type={message_type}, has_media={'YES ✨' if media_data else 'No'}")
        if media_data:
            logger.info(f"   🎨 Media Type: {media_type}, Data Length: {len(media_data)} chars")
        logger.debug(f"   Full message: {user_message}")
        logger.debug(f"   All messages in request: {len(messages)}")
        
        # 🌊 Check if streaming is requested
        stream_requested = data.get('stream', False)
        
        # Process through consciousness loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 🌊 STREAMING MODE
            if stream_requested:
                logger.info("🌊 Streaming mode enabled")
                
                def generate_stream():
                    """SSE streaming generator"""
                    try:
                        async_gen = consciousness_loop.process_message_stream(
                            user_message=user_message,
                            session_id=session_id,
                            model=model,
                            include_history=True,
                            history_limit=20,
                            message_type=message_type
                        )
                        
                        # Run async generator in sync context
                        while True:
                            try:
                                chunk = loop.run_until_complete(async_gen.__anext__())
                                # Send as newline-delimited JSON (Ollama format)
                                yield json.dumps(chunk) + '\n'
                            except StopAsyncIteration:
                                break
                        
                    except Exception as e:
                        logger.error(f"❌ Streaming error: {e}", exc_info=True)
                        yield json.dumps({'error': str(e)}) + '\n'
                    finally:
                        loop.close()
                
                return Response(generate_stream(), mimetype='application/x-ndjson')
            
            # 📦 NON-STREAMING MODE (traditional)
            else:
                logger.info("📦 Non-streaming mode")
                result = loop.run_until_complete(
                    consciousness_loop.process_message(
                        user_message=user_message,
                        session_id=session_id,
                        model=model,
                        include_history=True,
                        history_limit=20,  # 15-30 for continuity (recommended)
                        media_data=media_data,  # Multi-modal support!
                        media_type=media_type,
                        message_type=message_type  # inbox or system
                    )
                )
        except Exception as e:
            logger.error(f"❌ Processing error: {e}", exc_info=True)
            loop.close()
            raise
        finally:
            if not stream_requested:
                loop.close()
        
        # For streaming, we already returned above
        # Check if we got a response (non-streaming only)
        if not result or not result.get('response'):
            logger.error(f"⚠️  No response from consciousness loop! Result: {result}")
            return jsonify({
                "error": "No response generated",
                "model": "error",
                "message": {
                    "role": "assistant",
                    "content": "Sorry, I couldn't generate a response. Please try again."
                }
            }), 500
        
        # Return in Ollama format (for UI compatibility!)
        # BUT - enhanced with Letta-style structured data! 💜
        response = {
            "model": model,
            "created_at": datetime.now().isoformat() + "Z",
            "message": {
                "role": "assistant",
                "content": result['response']
            },
            "done": True,
            "done_reason": "stop",
            # Letta-style structured data for frontend!
            "thinking": result.get('thinking'),  # <think> tags extracted
            "tool_calls": result.get('tool_calls', []),  # Tool execution history
            "reasoning_time": result.get('reasoning_time', 0),  # Time spent thinking
            "usage": result.get('usage'),  # Token usage and cost info!
            # Ollama compatibility fields
            "total_duration": 0,
            "load_duration": 0,
            "prompt_eval_count": 0,
            "eval_count": 0,
            "eval_duration": 0
        }
        
        logger.info(f"✅ Response sent: {len(result['response'])} chars, {len(result.get('tool_calls', []))} tool calls, thinking={'YES' if result.get('thinking') else 'NO'}")
        
        return jsonify(response)
    
    except Exception as e:
        logger.error(f"❌ Chat endpoint error: {e}", exc_info=True)
        return jsonify({
            "error": str(e),
            "model": "error",
            "message": {
                "role": "assistant",
                "content": f"Sorry, I encountered an error: {str(e)}"
            }
        }), 500


@app.route('/ollama/api/chat/stream', methods=['POST'])
def ollama_compat_chat_stream():
    """
    Dedicated streaming endpoint (Frontend calls this!)
    """
    try:
        data = request.json
        
        # Extract from Ollama format
        messages = data.get('messages', [])
        model = data.get('model', os.getenv("DEFAULT_LLM_MODEL", "qwen/qwen-2.5-72b-instruct"))
        session_id = data.get('session_id') or request.headers.get('X-Session-Id', 'default')
        message_type = data.get('message_type', 'inbox')
        
        # Rate limiting check
        allowed, reason = rate_limiter.is_allowed(session_id)
        if not allowed:
            logger.warning(f"⚠️  Rate limit hit: {session_id} - {reason}")
            return jsonify({"error": reason}), 429
        
        # Extract user message
        if not messages:
            return jsonify({"error": "No messages provided"}), 400
        
        last_message = messages[-1]
        user_message = last_message.get('content', '')
        message_role = last_message.get('role', 'user')
        
        if message_role == 'system':
            message_type = 'system'
        
        logger.info(f"🌊 STREAMING Chat request: model={model}, session={session_id}, message_len={len(user_message)}")
        
        # Create async event loop for streaming
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        def generate_sse():
            """Server-Sent Events generator"""
            try:
                # Send "thinking" event immediately
                yield f"event: thinking\ndata: {json.dumps({'status': 'thinking', 'message': 'Thinking...'})}\n\n"
                
                # Create async generator
                async_gen = consciousness_loop.process_message_stream(
                    user_message=user_message,
                    session_id=session_id,
                    model=model,
                    include_history=True,
                    history_limit=20,
                    message_type=message_type
                )
                
                # Stream chunks
                while True:
                    try:
                        chunk = loop.run_until_complete(async_gen.__anext__())
                        # Send as SSE format: event: type\ndata: {...}\n\n
                        event_type = chunk.get('type', 'content')
                        yield f"event: {event_type}\ndata: {json.dumps(chunk)}\n\n"
                    except StopAsyncIteration:
                        break
                
                logger.info("✅ Stream complete")
                
            except Exception as e:
                logger.error(f"❌ Streaming error: {e}", exc_info=True)
                # Send error event
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
                # ALWAYS send "done" event so frontend doesn't hang!
                yield f"event: done\ndata: {json.dumps({{'response': f'Error: {str(e)}', 'thinking': None, 'reasoning_time': 0, 'usage': None}})}\n\n"
            finally:
                loop.close()
        
        return Response(generate_sse(), mimetype='text/event-stream')
    
    except Exception as e:
        logger.error(f"❌ Stream endpoint error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ============================================
# AGENT INFO
# ============================================

@app.route('/api/agent/info', methods=['GET'])
def get_agent_info():
    """Get agent information"""
    try:
        blocks = state_manager.list_blocks(include_hidden=False)
        
        return jsonify({
            "name": state_manager.get_state("agent:name", "Assistant"),
            "model": os.getenv("DEFAULT_LLM_MODEL", "qwen/qwen-2.5-72b-instruct"),
            "system_prompt_length": len(state_manager.get_state("agent:system_prompt", "")),
            "memory_blocks": len(blocks),
            "blocks": [
                {
                    "label": b.label,
                    "type": b.block_type.value,
                    "size": len(b.content),
                    "limit": b.limit,
                    "read_only": b.read_only,
                    "description": b.description
                }
                for b in blocks
            ],
            "imported_at": state_manager.get_state("agent:imported_at", "Never"),
            "source_file": state_manager.get_state("agent:source_file", "Unknown")
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================
# MEMORY BLOCKS
# ============================================

@app.route('/api/memory/blocks', methods=['GET'])
def list_memory_blocks():
    """List all memory blocks"""
    try:
        blocks = state_manager.list_blocks(include_hidden=False)
        
        return jsonify({
            "blocks": [b.to_dict() for b in blocks]
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/memory/blocks/<label>', methods=['GET'])
def get_memory_block(label: str):
    """Get a specific memory block"""
    try:
        block = state_manager.get_block(label)
        
        if not block:
            return jsonify({"error": f"Block '{label}' not found"}), 404
        
        return jsonify(block.to_dict())
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/memory/blocks/<label>', methods=['PUT'])
def update_memory_block(label: str):
    """Update a memory block (human editing!)"""
    try:
        data = request.json
        new_content = data.get('content')
        
        if not new_content:
            return jsonify({"error": "No content provided"}), 400
        
        # Update with check_read_only=False (human can edit read-only blocks!)
        block = state_manager.update_block(label, new_content, check_read_only=False)
        
        return jsonify({
            "status": "ok",
            "block": block.to_dict()
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================
# CONVERSATION HISTORY
# ============================================

@app.route('/api/conversation/<session_id>', methods=['GET'])
def get_conversation(session_id: str):
    """Get conversation history"""
    try:
        limit = request.args.get('limit', 50, type=int)
        messages = state_manager.get_conversation(session_id, limit=limit)
        
        return jsonify({
            "session_id": session_id,
            "messages": [m.to_dict() for m in messages]
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================
# CONTEXT WINDOW USAGE
# ============================================

@app.route('/api/context/usage', methods=['GET'])
def get_context_usage():
    """Get context window usage for token counter UI"""
    try:
        session_id = request.args.get('session_id', 'default')
        
        # Get agent data
        system_prompt = state_manager.get_state("agent:system_prompt", "")
        memory_blocks = state_manager.list_blocks(include_hidden=False)
        
        # 🔥 CRITICAL: Check for summary - only count messages AFTER it!
        latest_summary = state_manager.get_latest_summary(session_id)
        
        if latest_summary:
            from datetime import datetime
            from_timestamp = datetime.fromisoformat(latest_summary['to_timestamp'])
            logger.info(f"   📝 Summary found (to: {latest_summary['to_timestamp']})")
            logger.info(f"   ⏩ Counting only messages AFTER summary")
            
            # Get ALL messages, then filter
            all_messages = state_manager.get_conversation(session_id, limit=100000)
            
            # Filter: Only messages AFTER summary (INCLUDING system messages!)
            # 🔥 FIX: Don't include ALL system messages - they add 100k+ tokens!
            conversation_messages = [
                msg for msg in all_messages
                if msg.timestamp > from_timestamp
            ]
            
            logger.info(f"   ✓ Filtered to {len(conversation_messages)} messages (after summary)")
        else:
            # No summary - count all messages
            conversation_messages = state_manager.get_conversation(session_id, limit=100)
            logger.info(f"   ✓ No summary - counting all {len(conversation_messages)} messages")
        
        tool_schemas = memory_tools.get_tool_schemas()
        
        # Get REAL context window from agent settings (NOT hardcoded!)
        model = state_manager.get_state("agent.model", os.getenv("DEFAULT_LLM_MODEL", "qwen/qwen-2.5-72b-instruct"))
        max_tokens_str = state_manager.get_state("agent.context_window", "128000")
        
        try:
            max_tokens = int(max_tokens_str)
        except (ValueError, TypeError):
            max_tokens = 128000  # Fallback
        
        logger.info(f"📊 Context Usage: session={session_id}, model={model}, max_tokens={max_tokens}")
        
        # Calculate usage
        usage = context_calculator.calculate_usage(
            system_prompt=system_prompt,
            memory_blocks=[b.to_dict() for b in memory_blocks],
            tool_schemas=tool_schemas,
            conversation_messages=[m.to_dict() for m in conversation_messages],
            max_tokens=max_tokens
        )
        
        return jsonify(usage.to_dict())
    
    except Exception as e:
        logger.error(f"❌ Context usage error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/debug/logs', methods=['GET'])
def get_debug_logs():
    """
    Debug endpoint: Get backend logs
    
    Query params:
    - lines: Number of lines to return (default: 100, max: 1000)
    - file: Log file to read (default: 'stable', options: 'stable', 'backend', 'startup')
    - filter: Filter logs by string (optional)
    """
    try:
        lines = min(int(request.args.get('lines', 100)), 1000)
        log_file = request.args.get('file', 'stable')
        filter_str = request.args.get('filter', '')
        
        # Map to actual file paths
        log_files = {
            'stable': 'logs/stable.log',
            'backend': 'logs/backend.log',
            'startup': 'logs/startup.log'
        }
        
        log_path = log_files.get(log_file, 'logs/stable.log')
        
        # Check if file exists
        if not os.path.exists(log_path):
            return jsonify({
                "error": f"Log file not found: {log_path}",
                "available_files": list(log_files.keys())
            }), 404
        
        # Read last N lines
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()
            
            # Filter if requested
            if filter_str:
                all_lines = [line for line in all_lines if filter_str.lower() in line.lower()]
            
            # Get last N lines
            recent_lines = all_lines[-lines:]
        
        return jsonify({
            "file": log_file,
            "path": log_path,
            "total_lines": len(all_lines),
            "returned_lines": len(recent_lines),
            "filter": filter_str if filter_str else None,
            "logs": recent_lines
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/debug/logs/stream', methods=['GET'])
def stream_debug_logs():
    """
    Debug endpoint: Stream logs in real-time using Server-Sent Events (SSE)
    
    Query params:
    - file: Log file to watch (default: 'stable')
    """
    log_file = request.args.get('file', 'stable')
    
    log_files = {
        'stable': 'logs/stable.log',
        'backend': 'logs/backend.log',
        'startup': 'logs/startup.log'
    }
    
    log_path = log_files.get(log_file, 'logs/stable.log')
    
    def generate():
        """Generate log stream"""
        import time
        
        # Send initial connection message
        yield f"data: {json.dumps({'type': 'connected', 'file': log_file})}\n\n"
        
        try:
            # Open file and seek to end
            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                # Go to end of file
                f.seek(0, 2)
                
                while True:
                    line = f.readline()
                    if line:
                        # Send new line
                        yield f"data: {json.dumps({'type': 'log', 'line': line.rstrip()})}\n\n"
                    else:
                        # No new data, sleep briefly
                        time.sleep(0.5)
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route('/api/debug/context', methods=['GET'])
def get_debug_context():
    """
    Debug endpoint: Shows exactly what would be sent to OpenRouter
    
    Query params:
    - session_id: Session ID (default: 'default')
    - history_limit: Number of history messages (default: 3)
    - include_tools: Include tool schemas (default: true)
    """
    try:
        session_id = request.args.get('session_id', 'default')
        history_limit = int(request.args.get('history_limit', 3))
        include_tools = request.args.get('include_tools', 'true').lower() == 'true'
        
        # Get system prompt
        base_prompt = state_manager.get_state("agent:system_prompt", "")
        
        # Get memory blocks
        blocks = state_manager.list_blocks(include_hidden=False)
        
        # Build system prompt with blocks
        system_parts = [base_prompt]
        if blocks:
            system_parts.append("\n\n### MEMORY BLOCKS\n")
            system_parts.append("You have access to the following memory blocks:\n")
            
            for block in blocks:
                ro_marker = "🔒 READ-ONLY" if block.read_only else "✏️ EDITABLE"
                system_parts.append(f"\n**{block.label}** ({ro_marker}):")
                if block.description:
                    system_parts.append(f"\n*Purpose: {block.description}*")
                system_parts.append(f"\n```\n{block.content}\n```\n")
        
        system_prompt = "".join(system_parts)
        
        # Get conversation history
        history = state_manager.get_conversation(session_id, limit=history_limit)
        
        # Build messages array (as would be sent to OpenRouter)
        messages = [
            {
                "role": "system",
                "content": system_prompt
            }
        ]
        
        for msg in history:
            if msg.role != "system":
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        # Get tool schemas
        tool_schemas = memory_tools.get_tool_schemas() if include_tools else []
        
        # Estimate token counts (rough)
        import tiktoken
        try:
            enc = tiktoken.get_encoding("cl100k_base")  # GPT-4 tokenizer
            system_tokens = len(enc.encode(system_prompt))
            history_tokens = sum(len(enc.encode(msg.content)) for msg in history if msg.role != "system")
            tool_tokens = len(enc.encode(str(tool_schemas))) if tool_schemas else 0
        except:
            system_tokens = len(system_prompt) // 4  # Rough estimate
            history_tokens = sum(len(msg.content) for msg in history) // 4
            tool_tokens = len(str(tool_schemas)) // 4
        
        return jsonify({
            "session_id": session_id,
            "model": os.getenv("DEFAULT_LLM_MODEL", "qwen/qwen-2.5-72b-instruct"),
            "messages": messages,
            "tools": tool_schemas if include_tools else None,
            "stats": {
                "total_messages": len(messages),
                "system_prompt_length": len(system_prompt),
                "history_messages": len(history),
                "memory_blocks": len(blocks),
                "tools_count": len(tool_schemas),
                "estimated_tokens": {
                    "system": system_tokens,
                    "history": history_tokens,
                    "tools": tool_tokens,
                    "total": system_tokens + history_tokens + tool_tokens
                }
            }
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================
# STATISTICS
# ============================================

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get database statistics"""
    try:
        db_stats = state_manager.get_stats()
        
        stats = {
            "database": db_stats,
        }
        
        # OpenRouter stats (if available)
        if openrouter_client:
            stats["openrouter"] = openrouter_client.get_stats()
        else:
            stats["openrouter"] = {"status": "not_configured", "message": "Add API key via welcome modal"}
        
        if memory_system:
            stats["memory_system"] = memory_system.get_stats()
        
        return jsonify(stats)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================
# MAIN
# ============================================

if __name__ == '__main__':
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", 8284))
    # IMPORTANT: Debug mode creates 2 processes (auto-reload) causing instability!
    # Keep debug=True for error messages, but disable reloader
    debug = True
    
    print(f"\n{'='*60}")
    print(f"🖤 SUBSTRATE AI SERVER")
    print(f"{'='*60}\n")
    
    print(f"✅ Agent: {state_manager.get_state('agent:name', 'Not loaded')}")
    print(f"✅ Model: {os.getenv('DEFAULT_LLM_MODEL', 'qwen/qwen-2.5-72b-instruct')}")
    print(f"✅ Memory Blocks: {len(state_manager.list_blocks())}")
    print(f"✅ Archival Memory: {'Enabled' if memory_system else 'Disabled'}")
    
    print(f"\n🚀 Server starting on http://{host}:{port}")
    print(f"🎯 UI endpoint: /ollama/api/chat (Ollama-compatible!)")
    print(f"📊 Health check: /api/health")
    print(f"💾 Memory blocks: /api/memory/blocks")
    print(f"📈 Statistics: /api/stats")
    
    print(f"\n💡 Connect your React UI to: http://localhost:{port}")
    print(f"   (Already compatible with /ollama/api/chat!)")
    
    print(f"\n{'='*60}\n")
    
    # STABILITY FIX: Disable auto-reloader to prevent:
    # - Multiple processes on same port
    # - SQLite DB locks from concurrent access
    # - Port conflicts on file changes
    
    # Use socketio.run() instead of app.run() for WebSocket support!
    socketio.run(
        app,
        host=host, 
        port=port, 
        debug=debug,
        use_reloader=False,  # ← THIS FIXES EVERYTHING!
        allow_unsafe_werkzeug=True  # For development
    )

