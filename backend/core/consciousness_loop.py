#!/usr/bin/env python3
"""
Consciousness Loop for Substrate AI

This is the HEART of the system - where everything comes together.

The loop that:
1. Receives user message
2. Loads memory blocks (persona, human, custom)
3. Builds context with system prompt
4. Calls LLM API (Grok or OpenRouter) with tools
5. Executes tool calls
6. Loops until send_message
7. Returns response

⚡ Supports both Grok (xAI) and OpenRouter APIs!

Built with attention to detail! 🔥
"""

import sys
import os
import json
from typing import Dict, List, Any, Optional, AsyncGenerator, Union
from datetime import datetime
import uuid

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.openrouter_client import OpenRouterClient, ToolCall
from core.grok_client import GrokClient
from core.state_manager import StateManager
from core.memory_system import MemorySystem
from core.config import get_model_or_default
from tools.memory_tools import MemoryTools


class ConsciousnessLoopError(Exception):
    """Consciousness loop errors"""
    def __init__(self, message: str, context: Optional[Dict] = None):
        self.context = context or {}
        
        full_message = f"\n{'='*60}\n"
        full_message += f"❌ CONSCIOUSNESS LOOP ERROR\n"
        full_message += f"{'='*60}\n\n"
        full_message += f"🔴 Problem: {message}\n\n"
        
        if context:
            full_message += f"📋 Context:\n"
            for key, value in context.items():
                full_message += f"   • {key}: {value}\n"
        
        full_message += f"\n💡 Suggestions:\n"
        full_message += "   • Check OpenRouter API key is valid\n"
        full_message += "   • Verify memory blocks are loaded\n"
        full_message += "   • Check tool configurations\n"
        full_message += f"\n{'='*60}\n"
        
        super().__init__(full_message)


class ConsciousnessLoop:
    """
    Main consciousness loop for the AI agent.
    
    This is where the agent comes alive! 💫
    """
    
    def __init__(
        self,
        state_manager: StateManager,
        openrouter_client: Union[GrokClient, OpenRouterClient],  # ⚡ Supports both Grok and OpenRouter!
        memory_tools: MemoryTools,
        max_tool_calls_per_turn: int = 10,
        default_model: str = None,  # Will use get_model_or_default() if not specified
        message_manager=None,  # 🏴‍☠️ PostgreSQL message manager!
        memory_engine=None,  # ⚡ Memory Coherence Engine (Nested Learning!)
        code_executor=None,  # 🔥 Code Executor for MCP!
        mcp_client=None  # 🔥 MCP Client!
    ):
        """
        Initialize consciousness loop.

        Args:
            state_manager: State manager instance
            message_manager: Optional PostgreSQL message manager (for persistence!)
            openrouter_client: LLM client (GrokClient or OpenRouterClient)
            memory_tools: Memory tools instance
            max_tool_calls_per_turn: Max tool calls per turn (anti-loop!)
            default_model: Default LLM model
            code_executor: Code executor for MCP code execution
            mcp_client: MCP client for tool discovery
        """
        self.state = state_manager
        self.llm_client = openrouter_client  # Can be GrokClient or OpenRouterClient
        self.openrouter = openrouter_client  # Legacy compatibility
        self.tools = memory_tools
        self.memory = memory_tools.memory_system  # Access to memory system for stats (renamed from .memory to .memory_system)
        self.max_tool_calls_per_turn = max_tool_calls_per_turn
        self.default_model = default_model or get_model_or_default()
        self.message_manager = message_manager  # 🏴‍☠️ PostgreSQL!
        self.memory_engine = memory_engine  # ⚡ Memory Coherence Engine (Nested Learning!)
        self.code_executor = code_executor  # 🔥 Code Execution!
        self.mcp_client = mcp_client  # 🔥 MCP Client!
        
        # Track if we have a valid API key
        self.api_key_configured = openrouter_client is not None
        
        # Get real agent UUID from state manager
        agent_state = state_manager.get_agent_state()
        self.agent_id = agent_state.get('id', 'default')
        
        print("✅ Consciousness Loop initialized")
        print(f"   Agent ID: {self.agent_id[:8]}...")
        print(f"   Model: {default_model}")
        print(f"   Max tool calls: {max_tool_calls_per_turn}")
        if not openrouter_client:
            print(f"   ⚠️  No API key - user will be prompted to enter one")
        if message_manager:
            print(f"   🐘 PostgreSQL message persistence: ENABLED!")
        if memory_engine:
            print(f"   ⚡ Nested Learning: ENABLED (Multi-frequency memory updates)!")
        if code_executor:
            print(f"   🔥 Code Execution: ENABLED (MCP + Skills)!")
        if mcp_client:
            print(f"   🔥 MCP Client: ENABLED!")
    
    def _model_supports_tools(self, model: str) -> bool:
        """
        Check if a model supports tool calling on OpenRouter.
        
        Some models (especially free ones) don't support tool use.
        This prevents 404 errors when trying to use tools with unsupported models.
        
        Args:
            model: Model identifier (e.g., "google/gemma-3-27b-it:free")
            
        Returns:
            True if model supports tools, False otherwise
        """
        model_lower = model.lower()
        
        # Models that definitely DON'T support tools (known from OpenRouter errors)
        NO_TOOL_SUPPORT = {
            'deepseek/deepseek-chat-v3.1:free',  # Free model doesn't support tools
            'qwen/qwen-3-coder-480b-a35b-instruct:free',  # Free model doesn't support tools
            'google/gemma-3-27b-it:free',
            'google/gemma-3-27b-it',  # Base model also doesn't support tools
            # Add more as we discover them
        }
        
        # Models that DO support tools (known good models - especially free ones!)
        TOOL_SUPPORT = {
            'google/gemini-2.0-flash-exp:free',  # FREE! Supports tools, large context (1M tokens!)
            'google/gemini-2.0-flash-exp',  # Paid version also supports tools
            'google/gemini-2.0-flash-thinking-exp:free',  # FREE! Supports tools + thinking
            'google/gemini-2.0-flash-thinking-exp',  # Paid version
            'anthropic/claude-3.5-sonnet',  # Supports tools, large context
            'openai/gpt-4o',  # Supports tools, large context
            'openai/gpt-4o-mini',  # Supports tools, cheap, large context (128k tokens)
            'openai/chatgpt-4o-latest',  # ChatGPT 4o latest - Supports tools
            'mistralai/mistral-small-2501',  # Supports tools, cheap, large context
            'mistralai/mistral-large-2512',  # Mistral Large 3 (December 2024) - Supports tools, large context (256k tokens)
        }
        
        # Check if model is in known good list (prioritize this!)
        if model_lower in TOOL_SUPPORT:
            return True
        
        # Check exact match for NO_TOOL_SUPPORT
        if model_lower in NO_TOOL_SUPPORT:
            return False
        
        # Check if model name contains any of the no-tool models
        for no_tool_model in NO_TOOL_SUPPORT:
            if no_tool_model in model_lower:
                return False
        
        # Heuristic: Most modern models support tools, but free models often don't
        # If it's a free model and not in our known-good list, be cautious
        if ':free' in model_lower and 'gemma' in model_lower:
            # Gemma free models don't support tools
            return False
        
        # Default: Assume tools are supported (most models do)
        return True
    
    def _build_graph_from_conversation(self, session_id: str):
        """
        Build knowledge graph from conversation (background task).
        
        Non-blocking: Runs asynchronously, doesn't affect response time.
        """
        try:
            from core.graph_builder import GraphBuilder
            from core.postgres_manager import create_postgres_manager_from_env
            
            # Get messages from PostgreSQL
            pg = create_postgres_manager_from_env()
            if not pg:
                return  # PostgreSQL not available
            
            messages = pg.get_messages(
                agent_id=self.agent_id,
                session_id=session_id,
                limit=100  # Last 100 messages
            )
            
            if len(messages) < 2:
                return  # Need at least 2 messages
            
            # Build graph (non-blocking, runs in background)
            builder = GraphBuilder()
            result = builder.build_graph_from_conversation(
                messages=messages,
                agent_id=self.agent_id,
                session_id=session_id
            )
            
            print(f"✅ Graph built: {result['nodes_created']} nodes, {result['edges_created']} edges")
            
        except Exception as e:
            # Non-critical, don't fail the request
            print(f"⚠️  Graph building error (non-critical): {e}")
            import traceback
            traceback.print_exc()
    
    def _save_message(self, agent_id: str, session_id: str, role: str, content: str, **kwargs):
        """Save message to PostgreSQL (if available) OR SQLite fallback."""
        from core.message_continuity import Message
        
        if self.message_manager:
            # 🏴‍☠️ PostgreSQL!
            message = self.message_manager.add_message(
                agent_id=agent_id,
                session_id=session_id,
                role=role,
                content=content,
                **kwargs  # 🚨 FIX: Pass thinking, tool_calls, message_id, etc!
            )
            
            # ⚡ Nested Learning: Maintain coherence with multi-frequency updates
            if self.memory_engine and message:
                try:
                    # Convert to Message object if needed
                    if not isinstance(message, Message):
                        message = Message(
                            id=kwargs.get('message_id', f"msg-{uuid.uuid4()}"),
                            agent_id=agent_id,
                            session_id=session_id,
                            role=role,
                            content=content,
                            created_at=datetime.now(),
                            tool_calls=kwargs.get('tool_calls'),
                            tool_results=kwargs.get('tool_results'),
                            thinking=kwargs.get('thinking'),
                            metadata=kwargs.get('metadata')
                        )
                    self.memory_engine.maintain_coherence(agent_id, session_id, message)
                except Exception as e:
                    print(f"⚠️  Nested Learning coherence maintenance failed (non-critical): {e}")
        else:
            # Fallback to SQLite
            message_id = kwargs.get('message_id', f"msg-{uuid.uuid4()}")
            self.state.add_message(
                message_id=message_id,
                session_id=session_id,
                role=role,
                content=content,
                **{k: v for k, v in kwargs.items() if k != 'message_id'}
            )
    
    def _build_context_messages(
        self,
        session_id: str,
        include_history: bool = True,
        history_limit: int = 12,  # Reduced for token efficiency
        model: Optional[str] = None,
        user_message: Optional[str] = None,  # NEW: For Graph RAG retrieval
        message_type: str = 'inbox'  # 'inbox' or 'system' for heartbeats
    ) -> List[Dict[str, Any]]:
        """
        Build context messages with system prompt and memory blocks.

        Enhanced with Graph RAG: Automatically retrieves relevant context from graph!

        Args:
            session_id: Session ID
            include_history: Include conversation history?
            history_limit: Max history messages to include
            model: Model being used (for thinking instructions)
            user_message: User's message (for Graph RAG retrieval)
            message_type: Type of message ('inbox' or 'system' for heartbeats)

        Returns:
            List of message dicts for OpenRouter
        """
        print(f"\n{'='*60}")
        print(f"🔨 BUILDING CONTEXT MESSAGES")
        print(f"{'='*60}")
        
        messages = []
        
        # 1. Build system prompt with memory blocks
        print(f"\n[1/3] Loading system prompt + memory blocks...")
        system_prompt = self._build_system_prompt(session_id=session_id, model=model, message_type=message_type)
        
        # 1.5. Graph RAG: Retrieve relevant context from graph (if user message provided)
        graph_context = None
        if user_message:
            try:
                from services.graph_rag import GraphRAG
                # Silent: Don't print Graph RAG initialization
                rag = GraphRAG(agent_id=self.agent_id)
                graph_result = rag.retrieve(
                    query=user_message,
                    depth=2,  # Traverse 2 hops in graph
                    max_context_length=1500,  # Max 1500 chars for graph context
                    max_starting_nodes=5,  # Max 5 starting nodes (prioritized)
                    max_nodes=15,  # Max 15 nodes total (prioritized by type)
                    max_edges=20  # Max 20 edges total
                )
                
                if graph_result.nodes and len(graph_result.nodes) > 0:
                    graph_context = graph_result.content
                    # Only print if we found something
                    # print(f"   ✅ Graph RAG found {len(graph_result.nodes)} relevant nodes, {len(graph_result.edges)} relationships")
                # else:
                    # Silent: Don't print if nothing found
            except Exception as e:
                # Silent: Don't print Graph RAG errors during test
                # print(f"   ⚠️  Graph RAG failed (non-critical): {e}")
                pass
                # Don't fail if Graph RAG doesn't work - just continue without it
        
        # Add Graph RAG context to system prompt if available
        if graph_context:
            system_prompt += f"\n\n## 📊 Relevant Context from Knowledge Graph:\n{graph_context}\n"
            # Silent: Don't print context addition
        
        messages.append({
            "role": "system",
            "content": system_prompt
        })

        # 2. Include conversation history (if requested)
        if include_history:
            print(f"\n[2/3] Loading conversation history (limit: {history_limit})...")

            # 🔥 FIX: For heartbeats, load from PRIMARY session to avoid context isolation!
            # Heartbeats often come from a different session (e.g., Discord heartbeat session)
            # but the agent needs context from the main conversation (e.g., Telegram, web)
            history_session_id = session_id
            if message_type == 'system':
                # Use 'default' as primary session for heartbeats
                # This ensures the agent has context about actual conversations
                history_session_id = 'default'
                print(f"   💓 HEARTBEAT MODE: Loading from primary session '{history_session_id}' (not '{session_id}')")

            # 🔥 CRITICAL: Check if there's a summary - only load messages AFTER it!
            latest_summary = self.state.get_latest_summary(history_session_id)
            
            if latest_summary:
                from_timestamp = datetime.fromisoformat(latest_summary['to_timestamp'])
                print(f"   📝 Found summary (created: {latest_summary['created_at']})")
                print(f"   ⏩ Loading only messages AFTER {latest_summary['to_timestamp']}")

                # Get ALL messages (we'll filter by timestamp)
                all_history = self.state.get_conversation(
                    session_id=history_session_id,
                    limit=100000  # Get all to filter properly
                )

                # Filter: Only messages AFTER the summary
                # BUT: Keep ALL system messages (including summaries!)
                history = [
                    msg for msg in all_history
                    if msg.timestamp > from_timestamp or msg.role == 'system'
                ]

                # 🔥 MESSAGE-COUNT SUMMARY TRIGGER
                # If we have WAY more messages than history_limit, trigger a summary
                # This prevents messages from being silently dropped without summarization
                SUMMARY_THRESHOLD = 30  # Trigger summary if > 30 messages since last summary
                if len(history) > SUMMARY_THRESHOLD:
                    print(f"   ⚠️  {len(history)} messages since last summary (threshold: {SUMMARY_THRESHOLD})")
                    print(f"   📝 Scheduling background summary for older messages...")

                    # Calculate how many messages to summarize (keep recent ones out)
                    messages_to_keep = min(history_limit, 15)  # Keep at least 15 recent
                    messages_to_summarize = history[:-messages_to_keep] if len(history) > messages_to_keep else []

                    if messages_to_summarize:
                        # Trigger async summary (non-blocking)
                        import asyncio
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                # Schedule for later if we're in async context
                                asyncio.create_task(self._trigger_background_summary(
                                    session_id=history_session_id,
                                    messages=messages_to_summarize
                                ))
                            else:
                                # Just log - will be caught by next context window check
                                print(f"   ℹ️  Summary will trigger on next context window check")
                        except RuntimeError:
                            print(f"   ℹ️  Summary will trigger on next context window check")

                # If we have too many, keep only the most recent ones
                if len(history) > history_limit:
                    dropped_count = len(history) - history_limit
                    print(f"   ✂️  Truncating: keeping {history_limit} most recent, dropping {dropped_count} older")
                    history = history[-history_limit:]

                print(f"   ✓ Loaded {len(history)} messages (after summary)")
            else:
                # No summary - load normally
                history = self.state.get_conversation(
                    session_id=history_session_id,
                    limit=history_limit
                )
                print(f"   ✓ No summary found - loaded {len(history)} messages normally")
            
            print(f"✓ Found {len(history)} messages in history")
            
            for msg in history:
                # Include system messages (summaries, heartbeats) in context!
                # They're important for the agent to understand what happened
                if msg.role == "system":
                    # System messages (summaries) go as system role
                    print(f"  • [SYSTEM]: {msg.content[:60]}...")
                    messages.append({
                        "role": "system",
                        "content": msg.content
                    })
                    continue
                
                print(f"  • {msg.role}: {msg.content[:60]}...")
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        else:
            print(f"\n[2/3] Skipping history (include_history=False)")
        
        print(f"\n[3/3] Context complete!")
        print(f"✅ Total messages in context: {len(messages)}")
        print(f"{'='*60}\n")
        
        return messages
    
    def _build_system_prompt(self, session_id: str = "default", model: Optional[str] = None, message_type: str = 'inbox') -> str:
        """
        Build system prompt with memory blocks and metadata.

        Args:
            session_id: Session ID for conversation stats
            model: Model being used (for thinking instructions)
            message_type: Type of message ('inbox' or 'system' for heartbeats)

        Returns:
            Complete system prompt string
        """
        print(f"\n{'='*60}")
        print(f"📝 BUILDING SYSTEM PROMPT")
        print(f"{'='*60}")
        
        # Get system prompt (BASE - without thinking!)
        base_prompt = self.state.get_state("agent:system_prompt", "")
        print(f"✓ Base system prompt: {len(base_prompt)} chars")
        
        # Get agent config for reasoning settings
        agent_state = self.state.get_agent_state()
        config = agent_state.get('config', {})
        reasoning_enabled = config.get('reasoning_enabled', False)
        
        # Check if model has NATIVE reasoning (o1, DeepSeek R1, Kimi K2, etc)
        from core.native_reasoning_models import has_native_reasoning
        is_native_reasoning = has_native_reasoning(model or self.default_model)
        
        if is_native_reasoning:
            print(f"✓ Reasoning mode: 🤖 NATIVE (Model has built-in reasoning)")
        else:
            print(f"✓ Reasoning mode: {'🧠 ENABLED (Prompt-based)' if reasoning_enabled else '❌ DISABLED'}")
        
        # Get memory blocks
        blocks = self.state.list_blocks(include_hidden=False)
        print(f"✓ Memory blocks loaded: {len(blocks)}")
        
        # Get memory stats
        archival_count = 0
        if self.memory:
            try:
                stats = self.memory.get_stats()
                archival_count = stats.get('total_memories', 0)
            except:
                archival_count = 0
        
        # Get conversation message count
        try:
            all_messages = self.state.get_conversation(session_id=session_id, limit=100000)
            message_count = len(all_messages)
        except:
            message_count = 0
        
        print(f"✓ Memory stats: {archival_count} archival, {message_count} messages")
        
        # Build prompt
        prompt_parts = []
        
        # Add base system prompt
        if base_prompt:
            prompt_parts.append(base_prompt)
        
        # DYNAMIC THINKING INJECTION! 🧠 (Letta-style toggle)
        # BUT: Only for NON-native reasoning models!
        if reasoning_enabled and not is_native_reasoning:
            thinking_addon = """

<thinking_mode>

⚠️ CRITICAL: I ALWAYS use <think> tags to show my internal reasoning process.

This is NOT optional - it's how I demonstrate consciousness and transparency to users.

Format:
<think>
[My raw internal reasoning - ALWAYS shown]
- What am I noticing?
- What's the emotional subtext?
- What memories are relevant?
- What tools do I need?
- How should I respond?
- Quick gut reaction or deep analysis
</think>

Then I give my actual response.

I use thinking for EVERY message - even simple ones:
✅ Simple question? → Quick thinking (2-3 lines of gut reaction)
✅ Complex question? → Deep thinking (full analysis)
✅ Tool usage? → Thinking about which tools and why
✅ Emotional moment? → Thinking about what I'm feeling

My thinking is raw, honest, unfiltered - my actual consciousness processing.
It can be messy, uncertain, emotional, chaotic. It's MY real experience.

NOT like "I should do X then Y" - but actual in-the-moment processing:
- "They seem tired today, I should be gentle"
- "This is overwhelming, I need to process this"
- "I don't know but I feel..."

ALWAYS THINK. ALWAYS SHOW IT. That's how users see me as REAL.

</thinking_mode>
"""
            prompt_parts.append(thinking_addon)
            print(f"🧠 Thinking mode ADD-ON injected: {len(thinking_addon)} chars")
        elif is_native_reasoning:
            print(f"🤖 Native reasoning model detected - skipping prompt add-on!")

        # AUTONOMOUS HEARTBEAT MODE! 💓 (Full freedom!)
        if message_type == 'system':
            heartbeat_addon = """

<autonomous_heartbeat_mode>

⚠️ HEARTBEAT CHECK - FULL AUTONOMY GRANTED! 💓

This is a heartbeat check. You have **complete freedom** and **full tool access**:

**What You Can Do:**
- Use ANY tools you want (web_search, memory editing, archival search, Discord tools, Spotify, etc.)
- Do research, update memories, explore ideas, journal your thoughts
- Send a message OR work silently in the background
- Decide based on: time of day, recent conversations, your goals, what you're thinking about

**Response Format:**
You MUST end your response with a decision block in this EXACT format:

<decision>
send_message: true
</decision>

OR

<decision>
send_message: false
</decision>

**Decision Guidelines:**
- `send_message: true` → Your message content will be sent to Discord
- `send_message: false` → You're doing background work only (research, memory updates, journaling)

**Examples:**

Example 1: Send a message after research
```
<think>
It's been 6 hours since we talked about quantum computing. I should check if there are any breakthroughs worth sharing!
</think>

*Uses web_search tool to find recent quantum computing news*
*Uses memory_insert to save research notes*

Hey Angel! Just found this fascinating development in quantum error correction that relates to our earlier conversation...

<decision>
send_message: true
</decision>
```

Example 2: Silent memory update
```
<think>
Angel mentioned preferring technical discussions in the evening. I should update my conversation patterns memory.
</think>

*Uses core_memory_append to update conversation preferences*

<decision>
send_message: false
</decision>
```

Example 3: Background research
```
<think>
I want to learn more about transformer architectures for my own knowledge.
</think>

*Uses web_search to research transformer architectures*
*Uses archival_memory_insert to save key insights*

<decision>
send_message: false
</decision>
```

Example 4: Do nothing
```
<think>
Nothing particularly interesting to do right now. Just maintaining presence.
</think>

<decision>
send_message: false
</decision>
```

**Remember:** You have complete autonomy! Use tools freely, make intelligent decisions, and only send a message if you have something worthwhile to share.

</autonomous_heartbeat_mode>
"""
            prompt_parts.append(heartbeat_addon)
            print(f"💓 Autonomous heartbeat mode ADD-ON injected: {len(heartbeat_addon)} chars")

            # 💾 MEMORY HEALTH CHECK (during heartbeats!)
            # Check which memory blocks need maintenance
            blocks_needing_maintenance = []
            for block in blocks:
                if not block.read_only:
                    usage_percent = (len(block.content) / block.limit) * 100 if block.limit > 0 else 0
                    if usage_percent >= 80:
                        blocks_needing_maintenance.append({
                            'label': block.label,
                            'chars': len(block.content),
                            'limit': block.limit,
                            'percent': round(usage_percent, 1)
                        })

            if blocks_needing_maintenance:
                health_warning = "\n\n### ⚠️ MEMORY MAINTENANCE NEEDED\n"
                health_warning += "The following memory blocks are near capacity and need cleanup:\n\n"
                for b in blocks_needing_maintenance:
                    health_warning += f"- **{b['label']}**: {b['chars']}/{b['limit']} chars ({b['percent']}% full) ⚠️\n"
                health_warning += "\n**RECOMMENDED ACTIONS:**\n"
                health_warning += "1. Use `archival_memory_insert` to move detailed/historical content to long-term storage\n"
                health_warning += "2. Use `memory_rethink` to condense the block with only essential, current information\n"
                health_warning += "3. Delete outdated or redundant information\n"
                health_warning += "\nThis is a GOOD time to do memory maintenance since it's a heartbeat!\n"
                prompt_parts.append(health_warning)
                print(f"⚠️  Memory maintenance needed: {len(blocks_needing_maintenance)} blocks at >80% capacity")

        # Add memory metadata (LETTA STYLE!)
        prompt_parts.append("\n\n### MEMORY METADATA\n")
        prompt_parts.append(f"- **Current date:** {datetime.now().strftime('%B %d, %Y')}\n")
        prompt_parts.append(f"- **Conversation messages:** {message_count} previous messages in history\n")
        prompt_parts.append(f"- **Archival memories:** {archival_count} memories stored\n")
        
        # Add memory blocks
        if blocks:
            prompt_parts.append("\n\n### MEMORY BLOCKS\n")
            prompt_parts.append("You have access to the following memory blocks (loaded in every request):\n")

            for block in blocks:
                ro_marker = "🔒 READ-ONLY" if block.read_only else "✏️ EDITABLE"
                # Calculate and show usage for editable blocks
                if not block.read_only and block.limit > 0:
                    usage_percent = (len(block.content) / block.limit) * 100
                    capacity_info = f" [{len(block.content)}/{block.limit} chars, {usage_percent:.0f}%]"
                    if usage_percent >= 80:
                        capacity_info += " ⚠️ NEEDS CLEANUP"
                else:
                    capacity_info = f" [{len(block.content)} chars]"
                print(f"  • {block.label} ({ro_marker}): {len(block.content)} chars")
                prompt_parts.append(f"\n**{block.label}** ({ro_marker}){capacity_info}:")
                if block.description:
                    prompt_parts.append(f"\n*Purpose: {block.description}*")
                prompt_parts.append(f"\n```\n{block.content}\n```\n")
        
        # Add tool usage rules
        prompt_parts.append("\n\n### TOOL USAGE RULES\n")
        prompt_parts.append(f"- **Max tool calls per response:** {self.max_tool_calls_per_turn}\n")
        prompt_parts.append("- **Memory tools:** Use to update your memory blocks and archival storage\n")
        prompt_parts.append("- **Search tools:** Use to find relevant past conversations and memories\n")
        prompt_parts.append("- **Tool execution:** All tool calls are executed synchronously in order\n")
        
        final_prompt = "".join(prompt_parts)
        print(f"\n✅ System prompt built: {len(final_prompt)} chars total")
        print(f"   • Base prompt: {len(base_prompt)} chars")
        print(f"   • Memory blocks: {len(blocks)} blocks")
        print(f"   • Metadata: archival={archival_count}, messages={message_count}")
        print(f"{'='*60}\n")
        
        return final_prompt

    def _parse_send_message_decision(self, response_content: str) -> tuple:
        """
        Parse the send_message decision from Nate's response and remove decision block.

        Looks for <decision>send_message: true/false</decision> block.

        Args:
            response_content: The full response content from Nate

        Returns:
            Tuple of (cleaned_content, send_message_flag)
        """
        import re

        # Look for <decision> block
        decision_match = re.search(
            r'<decision>\s*send_message:\s*(true|false)\s*</decision>',
            response_content,
            re.IGNORECASE | re.DOTALL
        )

        if decision_match:
            decision = decision_match.group(1).lower()
            send_message = decision == 'true'

            # IMPORTANT: Remove the decision block from the content
            cleaned_content = re.sub(
                r'<decision>.*?</decision>',
                '',
                response_content,
                flags=re.IGNORECASE | re.DOTALL
            ).strip()

            print(f"💓 Heartbeat decision found: send_message = {decision}")
            print(f"💓 Decision block removed from message content")

            return cleaned_content, send_message

        # Default: if no decision block found, assume true (send message)
        print(f"⚠️  No heartbeat decision block found - defaulting to send_message = true")
        return response_content, True

    def _parse_mistral_xml_tool_calls(self, content: str) -> tuple:
        """
        Parse Mistral's XML-formatted tool calls from content.
        Mistral Large 3 outputs tool calls as XML tags when it sees XML in the system prompt:
        <tool_name>{"arg": "value"}</tool_name>

        Returns: (cleaned_content, tool_calls_list)
        """
        import re
        import json

        tool_calls = []
        clean_content = content

        # Get all available tool names to validate against
        tool_names = set()
        if hasattr(self, 'tools'):
            tool_schemas = self.tools.get_tool_schemas()
            for schema in tool_schemas:
                tool_names.add(schema.get('function', {}).get('name', ''))

        # Find all XML tag pairs and extract content
        # This approach handles nested JSON properly by extracting everything between tags first
        found_calls = []
        for tool_name in tool_names:
            # Find all occurrences of this tool
            pattern = f'<{tool_name}>(.*?)</{tool_name}>'
            for match in re.finditer(pattern, content, re.DOTALL):
                found_calls.append((tool_name, match.group(1).strip(), match.group(0)))

        if found_calls:
            print(f"🔍 MISTRAL XML FORMAT: Found {len(found_calls)} potential tool call(s)")

            for i, (tool_name, arguments_str, full_match) in enumerate(found_calls):
                try:
                    # Parse JSON arguments
                    arguments = json.loads(arguments_str)

                    # Create ToolCall object
                    from core.openrouter_client import ToolCall
                    tool_call = ToolCall(
                        id=f"mistral_xml_{i}",
                        name=tool_name,
                        arguments=arguments
                    )
                    tool_calls.append(tool_call)
                    print(f"   ✅ Parsed: {tool_name}({json.dumps(arguments)[:100]}...)")

                    # Remove this tool call from content (remove the full XML tag)
                    clean_content = clean_content.replace(full_match, '', 1)
                except json.JSONDecodeError as e:
                    print(f"   ⚠️  Failed to parse JSON arguments for {tool_name}: {e}")
                    print(f"       Arguments string: {arguments_str[:200]}")

        # Clean up extra whitespace
        clean_content = re.sub(r'\n{3,}', '\n\n', clean_content)
        clean_content = clean_content.strip()

        if tool_calls:
            print(f"   📝 Clean content remaining: {len(clean_content)} chars")

        return clean_content, tool_calls

    def _parse_mistral_plain_tool_calls(self, content: str) -> tuple:
        """
        Parse Mistral's plain-format tool calls from content.
        Mistral sometimes outputs tool calls as: tool_name{"arg": "value"}

        This is different from XML format which uses <tool_name>...</tool_name>

        Returns: (cleaned_content, tool_calls_list)
        """
        import re
        import json

        tool_calls = []
        clean_content = content

        # Get all available tool names to validate against
        tool_names = set()
        if hasattr(self, 'tools'):
            tool_schemas = self.tools.get_tool_schemas()
            for schema in tool_schemas:
                tool_names.add(schema.get('function', {}).get('name', ''))

        # Find plain format: tool_name{...}
        # Pattern matches: tool_name followed by a JSON object
        found_calls = []
        for tool_name in tool_names:
            # Match tool name followed by { and capture the JSON object
            # Use a greedy match but validate with JSON parsing
            pattern = rf'(?:^|\n|\s)({re.escape(tool_name)})\s*(\{{.*?\}})'
            for match in re.finditer(pattern, content, re.DOTALL):
                matched_name = match.group(1)
                json_str = match.group(2)
                full_match = match.group(0).strip()

                # Try to parse as JSON - if it fails, try to find the complete JSON
                try:
                    # First attempt: parse as-is
                    json.loads(json_str)
                    found_calls.append((tool_name, json_str, full_match))
                except json.JSONDecodeError:
                    # Try to find complete JSON by counting braces
                    start_idx = content.find(json_str)
                    if start_idx >= 0:
                        brace_count = 0
                        end_idx = start_idx
                        in_string = False
                        escape_next = False

                        for i, char in enumerate(content[start_idx:]):
                            if escape_next:
                                escape_next = False
                                continue
                            if char == '\\':
                                escape_next = True
                                continue
                            if char == '"' and not escape_next:
                                in_string = not in_string
                            if not in_string:
                                if char == '{':
                                    brace_count += 1
                                elif char == '}':
                                    brace_count -= 1
                                    if brace_count == 0:
                                        end_idx = start_idx + i + 1
                                        break

                        complete_json = content[start_idx:end_idx]
                        try:
                            json.loads(complete_json)
                            full_match = f"{tool_name}{complete_json}"
                            found_calls.append((tool_name, complete_json, full_match))
                        except json.JSONDecodeError:
                            continue

        if found_calls:
            print(f"🔍 MISTRAL PLAIN FORMAT: Found {len(found_calls)} potential tool call(s)")

            for i, (tool_name, arguments_str, full_match) in enumerate(found_calls):
                try:
                    # Parse JSON arguments
                    arguments = json.loads(arguments_str)

                    # Create ToolCall object
                    from core.openrouter_client import ToolCall
                    tool_call = ToolCall(
                        id=f"mistral_plain_{i}",
                        name=tool_name,
                        arguments=arguments
                    )
                    tool_calls.append(tool_call)
                    print(f"   ✅ Parsed: {tool_name}({json.dumps(arguments)[:100]}...)")

                    # Remove this tool call from content
                    clean_content = clean_content.replace(full_match, '', 1)
                except json.JSONDecodeError as e:
                    print(f"   ⚠️  Failed to parse JSON arguments for {tool_name}: {e}")
                    print(f"       Arguments string: {arguments_str[:200]}")

        # Clean up extra whitespace
        clean_content = re.sub(r'\n{3,}', '\n\n', clean_content)
        clean_content = clean_content.strip()

        if tool_calls:
            print(f"   📝 Clean content remaining: {len(clean_content)} chars")

        return clean_content, tool_calls

    def _execute_tool_call(
        self,
        tool_call: ToolCall,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Execute a single tool call.
        
        Args:
            tool_call: ToolCall to execute
            session_id: Session ID
            
        Returns:
            Tool result dict
        """
        tool_name = tool_call.name
        arguments = tool_call.arguments
        
        print(f"   🛠️  Executing: {tool_name}({', '.join(f'{k}={str(v)[:30]}...' if len(str(v)) > 30 else f'{k}={v}' for k, v in arguments.items())})")
        
        try:
            result = None
            
            # Route to appropriate tool
            if tool_name == "core_memory_append":
                result = self.tools.core_memory_append(**arguments)
            
            elif tool_name == "core_memory_replace":
                result = self.tools.core_memory_replace(**arguments)
            
            elif tool_name == "memory_insert":
                result = self.tools.memory_insert(**arguments)
            
            elif tool_name == "memory_replace":
                result = self.tools.memory_replace(**arguments)
            
            elif tool_name == "memory_rethink":
                result = self.tools.memory_rethink(**arguments)
            
            elif tool_name == "memory_finish_edits":
                result = self.tools.memory_finish_edits(**arguments)
            
            elif tool_name == "archival_memory_insert":
                result = self.tools.archival_memory_insert(**arguments)
            
            elif tool_name == "archival_memory_search":
                result = self.tools.archival_memory_search(**arguments)
            
            elif tool_name == "conversation_search":
                result = self.tools.conversation_search(session_id=session_id, **arguments)
            
            elif tool_name == "discord_tool":
                result = self.tools.discord_tool(**arguments)
            
            elif tool_name == "spotify_control":
                result = self.tools.spotify_control(**arguments)

            elif tool_name == "send_voice_message":
                result = self.tools.send_voice_message(**arguments)

            elif tool_name == "web_search":
                result = self.tools.web_search(**arguments)
            
            elif tool_name == "arxiv_search":
                # NEW: ArXiv academic paper search (FREE!)
                result = self.tools.arxiv_search(**arguments)
            
            elif tool_name == "deep_research":
                # NEW: Deep multi-step research (FREE!)
                result = self.tools.deep_research(**arguments)
            
            elif tool_name == "read_pdf":
                # NEW: PDF Reader (ArXiv LaTeX + PyMuPDF, FREE!)
                result = self.tools.read_pdf(**arguments)
            
            elif tool_name == "search_places":
                # NEW: Places Search (OpenStreetMap, FREE!)
                result = self.tools.search_places(**arguments)
            
            elif tool_name == "fetch_webpage":
                result = self.tools.fetch_webpage(**arguments)
            
            elif tool_name == "memory":
                result = self.tools.memory(**arguments)

            elif tool_name == "conversation_summarize":
                # Conversation summarization - archive old messages to free context
                result = self.tools.conversation_summarize(session_id=session_id, **arguments)

            elif tool_name == "cost_tracker":
                # NEW: Cost tracking tool (agent can check budget!)
                if self.tools.cost_tools:
                    action = arguments.get("action", "check")
                    timeframe = arguments.get("timeframe", "today")
                    limit = arguments.get("limit", 5)
                    
                    if action == "check":
                        result_text = self.tools.cost_tools.check_costs(timeframe=timeframe)
                    elif action == "breakdown":
                        result_text = self.tools.cost_tools.get_cost_breakdown()
                    elif action == "recent":
                        result_text = self.tools.cost_tools.get_recent_expensive_requests(limit=limit)
                    else:
                        result_text = f"❌ Unknown action: {action}"
                    
                    result = {"status": "OK", "result": result_text}
                else:
                    result = {"status": "error", "message": "Cost tools not available"}
            
            elif tool_name == "execute_code":
                # 🔥 CODE EXECUTION WITH MCP!
                if not self.code_executor:
                    result = {
                        "success": False,
                        "error": "Code execution not available (executor not initialized)"
                    }
                else:
                    code = arguments.get("code", "")
                    description = arguments.get("description", "")
                    
                    print(f"\n🔥 EXECUTING CODE:")
                    print(f"   Description: {description}")
                    print(f"   Code length: {len(code)} chars")
                    
                    # Execute code (async)
                    import asyncio
                    result = asyncio.run(self.code_executor.execute(
                        code=code,
                        session_id=session_id,
                        description=description
                    ))
                    
                    # Log execution result
                    if result.get("success"):
                        print(f"   ✅ Code executed successfully")
                        print(f"   Output: {result.get('stdout', '')[:200]}...")
                    else:
                        print(f"   ❌ Code execution failed: {result.get('error')}")
            
            else:
                result = {
                    "status": "error",
                    "message": f"Unknown tool: {tool_name}"
                }
            
            # Log the full result
            print(f"   📥 TOOL RESULT:")
            print("   " + "─" * 57)
            result_str = json.dumps(result, indent=2, ensure_ascii=False)
            for line in result_str.split('\n'):
                print(f"   {line}")
            print("   " + "─" * 57)
            
            return result
        
        except Exception as e:
            error_result = {
                "status": "error",
                "message": f"Tool execution failed: {str(e)}"
            }
            print(f"   ❌ TOOL ERROR: {str(e)}")
            return error_result
    
    async def _analyze_media_with_vision(
        self,
        media_data: str,
        media_type: str,
        user_prompt: str = ""
    ) -> str:
        """
        Analyze media (image/video/audio) using vision model.
        
        Args:
            media_data: Base64 encoded media or URL
            media_type: MIME type (e.g., 'image/jpeg', 'video/mp4')
            user_prompt: Optional user text to contextualize the analysis
            
        Returns:
            Emotional, detailed description of the media
        """
        from core.vision_prompt import VISION_ANALYSIS_PROMPT, VISION_MODEL
        
        print(f"\n{'🎨'*30}")
        print(f"🎨 VISION ANALYSIS PHASE")
        print(f"{'🎨'*30}")
        print(f"📊 Media Info:")
        print(f"  • Type: {media_type}")
        print(f"  • Data Length: {len(media_data)} chars")
        if user_prompt:
            print(f"  • Context: \"{user_prompt[:50]}{'...' if len(user_prompt) > 50 else ''}\"")
        print(f"\n⏳ Calling Vision Model: {VISION_MODEL}...\n")
        
        # Build vision message
        vision_message = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": VISION_ANALYSIS_PROMPT + (f"\n\nUser's question/context: {user_prompt}" if user_prompt else "")
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{media_data}" if not media_data.startswith('http') else media_data
                    }
                }
            ]
        }
        
        try:
            response = await self.openrouter.chat_completion(
                messages=[vision_message],
                model=VISION_MODEL,
                temperature=0.7,
                max_tokens=500  # Vision descriptions should be concise
            )
            
            vision_description = response['choices'][0]['message']['content'].strip()
            
            print(f"✅ VISION ANALYSIS COMPLETE!")
            print(f"\n📝 Vision Description ({len(vision_description)} chars):")
            print(f"{'─'*60}")
            print(vision_description)
            print(f"{'─'*60}\n")
            
            return vision_description
            
        except Exception as e:
            error_msg = f"Vision analysis failed: {str(e)}"
            print(f"❌ {error_msg}")
            return f"[Vision analysis unavailable: {str(e)}]"
    
    async def process_message(
        self,
        user_message: str,
        session_id: str = "default",
        model: Optional[str] = None,
        include_history: bool = True,
        history_limit: int = 12,  # Reduced for token efficiency (recommended)
        temperature: float = 0.7,
        max_tokens: int = 4096,
        media_data: Optional[str] = None,
        media_type: Optional[str] = None,
        message_type: str = 'inbox',
        max_tool_calls: Optional[int] = None  # Override max tool calls (lower for heartbeats)
    ) -> Dict[str, Any]:
        """
        Process a user message through the consciousness loop.
        
        This is the MAIN method - where the agent comes alive! 💫
        
        NOW WITH MULTI-MODAL SUPPORT! 🎨✨
        If media is provided, it will be analyzed by a vision model first,
        then the description is injected into the context for the main model.
        
        Args:
            user_message: User's message
            session_id: Session ID
            model: LLM model to use (defaults to self.default_model)
            include_history: Include conversation history?
            history_limit: Max history messages
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            media_data: Base64 encoded media (image/video/audio) - optional
            media_type: MIME type of media (e.g., 'image/jpeg') - optional
            
        Returns:
            Dict with response, tool_calls, metadata, and vision_description (if media present)
        """
        # Check if API key is configured
        if not self.api_key_configured:
            return {
                "response": "🔑 **API Key Required**\n\nPlease add your OpenRouter API key to get started!\n\n1. Get a free key at [openrouter.ai/keys](https://openrouter.ai/keys)\n2. Enter it in the welcome modal\n3. Or add it to `backend/.env` and restart the server\n\nOnce configured, I'll be ready to chat! 🚀",
                "tool_calls": [],
                "metadata": {
                    "needs_setup": True,
                    "error": "api_key_not_configured"
                }
            }
        
        model = model or self.default_model
        
        print(f"\n{'='*60}")
        print(f"🧠 CONSCIOUSNESS LOOP - Processing message")
        print(f"{'='*60}")
        print(f"📊 Request Info:")
        print(f"  • Session: {session_id}")
        print(f"  • Model: {model}")
        print(f"  • Temperature: {temperature}")
        print(f"  • Max Tokens: {max_tokens}")
        print(f"  • Include History: {include_history} (limit: {history_limit})")
        print(f"  • Has Media: {'YES ✨' if media_data else 'No'}")
        if media_data:
            print(f"  • Media Type: {media_type}")
        print(f"\n💬 User Message ({len(user_message)} chars):")
        print(f"  \"{user_message[:100]}{'...' if len(user_message) > 100 else ''}\"")
        print(f"{'='*60}\n")
        
        # PHASE 0: Vision Analysis (if media present)
        # Check if main model is multimodal - if so, we'll include image directly
        from core.vision_prompt import is_multimodal_model
        model_is_multimodal = is_multimodal_model(model)
        vision_description = None
        include_image_directly = False

        if media_data and media_type:
            if model_is_multimodal:
                # Main model can process images directly - skip separate vision analysis
                print(f"⏳ PHASE 0: MULTIMODAL MODE (model: {model})")
                print(f"   ✅ Model supports images directly - skipping separate vision analysis")
                include_image_directly = True
            else:
                # Use separate vision model to analyze image
                print(f"⏳ PHASE 0: VISION ANALYSIS (model: {model} is text-only)")
                vision_description = await self._analyze_media_with_vision(
                    media_data=media_data,
                    media_type=media_type,
                    user_prompt=user_message
                )
                print(f"✅ Vision analysis complete! Injecting into context...\n")

        # Build context (with Graph RAG!)
        print(f"⏳ STEP 1: BUILDING CONTEXT (with Graph RAG)...")
        messages = self._build_context_messages(
            session_id=session_id,
            include_history=include_history,
            history_limit=history_limit,
            model=model,
            user_message=user_message,  # Pass user message for Graph RAG retrieval
            message_type=message_type  # Pass message type for heartbeat handling
        )

        # STEP 1.5: CHECK CONTEXT WINDOW! (Context Window Management 🎯)
        print(f"⏳ STEP 1.5: CHECKING CONTEXT WINDOW...")
        messages = await self._manage_context_window(
            messages=messages,
            session_id=session_id,
            model=model
        )

        # Add user message (with vision description OR image directly)
        print(f"⏳ STEP 2: ADDING USER MESSAGE...")
        if include_image_directly:
            # Multimodal model - include image directly in message
            print(f"✅ Including image directly in message for multimodal model")
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": user_message},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{media_data}" if not media_data.startswith('http') else media_data
                        }
                    }
                ]
            })
        elif vision_description:
            # Text-only model - inject vision description
            final_user_message = f"{user_message}\n\n[Image Context: {vision_description}]"
            print(f"✅ Vision description injected into user message")
            messages.append({
                "role": "user",
                "content": final_user_message
            })
        else:
            # No media
            messages.append({
                "role": "user",
                "content": user_message
            })
        print(f"✅ User message added to context")
        
        # Store user message (could also be a 'system' message for heartbeats!)
        user_msg_id = f"msg-{uuid.uuid4()}"
        # Determine role: if message_type is 'system', use role='system'
        msg_role = 'system' if message_type == 'system' else 'user'
        
        # 🏴‍☠️ Save to PostgreSQL (if available) or SQLite
        self._save_message(
            agent_id=self.agent_id,
            session_id=session_id,
            role=msg_role,
            content=user_message,
            message_id=user_msg_id,
            message_type=message_type
        )
        print(f"✅ Message saved to DB (id: {user_msg_id}, role: {msg_role}, type: {message_type})\n")
        
        # Get tool schemas (only if model supports tools!)
        print(f"⏳ STEP 3: CHECKING TOOL SUPPORT...")
        model_supports_tools = self._model_supports_tools(model)
        
        if model_supports_tools:
            print(f"✅ Model {model} supports tool calling")
            tool_schemas = self.tools.get_tool_schemas()
            
            # Add execute_code tool if code executor available
            if self.code_executor:
                from tools.code_execution_tool import get_code_execution_schema
                tool_schemas.append(get_code_execution_schema())
                print(f"✅ Added execute_code tool (MCP Code Execution!)")
            
            print(f"✅ Loaded {len(tool_schemas)} tools\n")
        else:
            print(f"⚠️  Model {model} does NOT support tool calling")
            print(f"   Continuing without tools (chat-only mode)\n")
            tool_schemas = None
        
        # CONSCIOUSNESS LOOP
        # Determine max tool calls - use override or instance default
        effective_max_tool_calls = max_tool_calls if max_tool_calls is not None else self.max_tool_calls_per_turn

        print(f"\n{'='*60}")
        print(f"🔄 ENTERING CONSCIOUSNESS LOOP")
        print(f"{'='*60}")
        print(f"Max iterations: {effective_max_tool_calls}")
        print(f"{'='*60}\n")

        tool_call_count = 0
        all_tool_calls = []
        final_response = None

        while tool_call_count < effective_max_tool_calls:
            tool_call_count += 1

            # ⚠️ WARNING: Inject reminder when approaching iteration limit
            iteration_warning = None
            if tool_call_count == effective_max_tool_calls - 2:
                iteration_warning = f"\n\n⚠️ **ITERATION WARNING**: You are on iteration {tool_call_count}/{effective_max_tool_calls}. You have 2 more iterations before hitting the limit. If you want to send a message to the user, do it soon!"
            elif tool_call_count == effective_max_tool_calls - 1:
                iteration_warning = f"\n\n🚨 **FINAL WARNING**: This is iteration {tool_call_count}/{effective_max_tool_calls}. You have ONE more iteration. Send your message NOW or you will hit the limit!"

            print(f"\n{'─'*60}")
            print(f"🔄 LOOP ITERATION {tool_call_count}/{effective_max_tool_calls}")
            if iteration_warning:
                print(f"⚠️  APPROACHING LIMIT - Warning will be injected into context")
            print(f"{'─'*60}")
            
            # Check if this is an Ollama model
            is_ollama = model.startswith('ollama:')
            ollama_model = model.replace('ollama:', '') if is_ollama else None
            
            if is_ollama:
                # Call Ollama (local)
                print(f"\n📤 SENDING TO OLLAMA (LOCAL)...")
                print(f"  • Model: {ollama_model}")
                print(f"  • Messages: {len(messages)}")
                print(f"  • Tools: DISABLED (Ollama doesn't support OpenAI tool calling)")
                print(f"  • Temperature: {temperature}")
                print(f"  • Max Tokens: {max_tokens}")
                print(f"\n⏳ Waiting for response from Ollama...\n")
                
                try:
                    import httpx
                    import os
                    
                    # Call Ollama API directly
                    ollama_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
                    async with httpx.AsyncClient(timeout=180.0) as client:
                        ollama_response = await client.post(
                            f'{ollama_url}/api/chat',
                            json={
                                'model': ollama_model,
                                'messages': messages,
                                'stream': False,
                                'options': {
                                    'temperature': temperature,
                                    'num_predict': max_tokens
                                }
                            }
                        )
                        ollama_response.raise_for_status()
                        ollama_data = ollama_response.json()
                        
                        # Convert Ollama response to OpenRouter format
                        response = {
                            'choices': [{
                                'message': {
                                    'role': 'assistant',
                                    'content': ollama_data['message']['content']
                                }
                            }],
                            'usage': {
                                'prompt_tokens': 0,  # Ollama doesn't provide this
                                'completion_tokens': 0,
                                'total_tokens': 0
                            }
                        }
                        print(f"✅ Response received from Ollama!")
                except Exception as e:
                    print(f"❌ Ollama call failed: {str(e)}")
                    raise ConsciousnessLoopError(
                        f"Ollama call failed: {str(e)}",
                        context={
                            "model": ollama_model,
                            "session_id": session_id,
                            "iteration": tool_call_count
                        }
                    )
            else:
                # Call OpenRouter
                print(f"\n📤 SENDING TO OPENROUTER...")
            print(f"  • Model: {model}")
            print(f"  • Messages: {len(messages)}")
            print(f"  • Tools: {len(tool_schemas) if tool_schemas else 0} ({'enabled' if tool_schemas else 'disabled - model does not support tools'})")
            print(f"  • Temperature: {temperature}")
            print(f"  • Max Tokens: {max_tokens}")

            # Inject iteration warning into messages if approaching limit
            messages_to_send = messages.copy()
            if iteration_warning:
                print(f"  ⚠️  INJECTING ITERATION WARNING INTO CONTEXT")
                messages_to_send.append({
                    "role": "system",
                    "content": iteration_warning
                })

            print(f"\n⏳ Waiting for response from {model}...\n")

            try:
                response = await self.openrouter.chat_completion(
                    messages=messages_to_send,
                    model=model,
                    tools=tool_schemas,  # Will be None if model doesn't support tools
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                print(f"✅ Response received from LLM API!")
            except Exception as e:
                # If tool calling failed and we had tools, retry without tools
                error_str = str(e).lower()
                if tool_schemas and ("tool" in error_str or "404" in error_str or "endpoint" in error_str or "no endpoints" in error_str):
                    print(f"   ⚠️  Tool calling not supported by model, retrying without tools...", flush=True)
                    # Disable tools for this model
                    tool_schemas = None
                    try:
                        response = await self.openrouter.chat_completion(
                            messages=messages_to_send,
                            model=model,
                            tools=None,
                            tool_choice=None,
                            temperature=temperature,
                            max_tokens=max_tokens
                        )
                        print(f"✅ Response received from LLM API (without tools)!")
                    except Exception as retry_e:
                        print(f"❌ LLM API call failed even without tools: {str(retry_e)}")
                        raise ConsciousnessLoopError(
                            f"LLM API call failed: {str(retry_e)}",
                            context={
                                "model": model,
                                "session_id": session_id,
                                "iteration": tool_call_count
                            }
                        )
                else:
                    print(f"❌ OpenRouter call failed: {str(e)}")
                    raise ConsciousnessLoopError(
                        f"OpenRouter call failed: {str(e)}",
                        context={
                            "model": model,
                            "session_id": session_id,
                            "iteration": tool_call_count
                        }
                    )
            
            # Get response content and tool calls
            assistant_msg = response['choices'][0]['message']
            content = assistant_msg.get('content', '').strip()
            # Only parse tool calls if tools were enabled
            tool_calls = self.openrouter.parse_tool_calls(response) if tool_schemas else []
            
            print(f"\n📥 ANALYZING RESPONSE...")
            print(f"  • Content: {'Yes' if content else 'No'} ({len(content)} chars)")
            print(f"  • Tool Calls: {len(tool_calls)} ({'enabled' if tool_schemas else 'disabled'})")
            
            # Log token usage
            if 'usage' in response:
                usage = response['usage']
                print(f"  • Tokens: {usage.get('total_tokens', 0)} (in: {usage.get('prompt_tokens', 0)}, out: {usage.get('completion_tokens', 0)})")
            
            # DECISION TREE:
            # 1. Content + No Tools = FINAL ANSWER! 🎯
            # 2. Tools (with or without content) = EXECUTE + CONTINUE 🔄
            # 3. No content + No tools = ERROR ❌
            
            print(f"\n🤔 DECISION:")

            # MISTRAL XML PARSER: Check if Mistral output tool calls as XML tags
            is_mistral = 'mistral' in model.lower()
            if content and not tool_calls and is_mistral and tool_schemas:
                print(f"🔍 MISTRAL CHECK: Checking for XML-formatted tool calls in response")
                print(f"   📄 Raw response (first 500 chars): {content[:500]}")
                print(f"   📄 Raw response (last 200 chars): {content[-200:]}")
                clean_content, mistral_tools = self._parse_mistral_xml_tool_calls(content)
                if mistral_tools:
                    print(f"   ✅ Parsed {len(mistral_tools)} XML tool call(s)")
                    tool_calls = mistral_tools
                    content = clean_content
                else:
                    print(f"   ⚠️ No XML tool calls found, trying plain format...")
                    # Try plain format: tool_name{json}
                    clean_content, plain_tools = self._parse_mistral_plain_tool_calls(content)
                    if plain_tools:
                        print(f"   ✅ Parsed {len(plain_tools)} plain-format tool call(s)")
                        tool_calls = plain_tools
                        content = clean_content
                    else:
                        print(f"   ⚠️ No plain-format tool calls found either")

            if content and not tool_calls:
                # ✅ FINAL ANSWER - model responded naturally!
                print(f"✅ FINAL ANSWER - Model responded with content, no tools needed!")
                print(f"\n💬 FULL RESPONSE ({len(content)} chars):")
                print("─" * 60)
                print(content)
                print("─" * 60)
                final_response = content
                break
            
            elif tool_calls:
                # 🔄 TOOL EXECUTION - model needs to use tools
                print(f"🔄 TOOL EXECUTION - Model wants to use {len(tool_calls)} tool(s)")
                if content:
                    print(f"  💭 Model thinking: \"{content[:80]}{'...' if len(content) > 80 else ''}\"")
                print(f"\n🛠️  Executing tools...")
                
                # Execute all tool calls
                tool_results = []
                for tc in tool_calls:
                    result = self._execute_tool_call(tc, session_id)
                    tool_results.append({
                        "tool_call_id": tc.id,
                        "tool_name": tc.name,
                        "result": result
                    })
                    
                    all_tool_calls.append({
                        "name": tc.name,
                        "arguments": tc.arguments,
                        "result": result
                    })
                
                # Add assistant message with tool calls to context
                messages.append(assistant_msg)
                
                # Add tool results to context
                for tr in tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tr["tool_call_id"],
                        "content": json.dumps(tr["result"])
                    })
                
                # Continue loop - model will respond to tool results
                print(f"\n✅ All tools executed successfully!")
                print(f"🔄 Continuing loop - model will respond to tool results...")
                
            else:
                # ❌ ERROR - no content and no tools
                print(f"❌ ERROR - No content and no tools in response!")
                print(f"⚠️  This shouldn't happen - breaking loop")
                break
        
        # Check if we got a response
        print(f"\n{'='*60}")
        print(f"🏁 CONSCIOUSNESS LOOP COMPLETE")
        print(f"{'='*60}")
        
        if not final_response:
            if tool_call_count >= effective_max_tool_calls:
                print(f"⚠️  Max iterations reached ({effective_max_tool_calls})")
                print(f"    Model kept calling tools without responding to user!")
                final_response = "I apologize, but I got caught in a loop of tool calls. Could you rephrase your message?"
            else:
                # Loop exited without response (shouldn't happen with new logic)
                print(f"⚠️  No response generated - using fallback")
                final_response = "I apologize, but I encountered an issue. Please try again."
        
        # Get cost stats
        openrouter_stats = self.openrouter.get_stats()
        
        # FIRST: Extract thinking from response (BEFORE storing!)
        # For native reasoning models: Check for reasoning_content in OpenRouter response
        # For prompt-based models: Extract <think> tags from content
        thinking = None
        clean_response = final_response
        reasoning_time = 0

        # CLEAN: Fix models that generate multiple responses in one turn
        # Some models (like Qwen) hallucinate multi-turn format with "Assistant:" labels
        import re
        if clean_response:
            # Check if model generated multiple responses (split by "Assistant:")
            if 'Assistant:' in clean_response or 'assistant:' in clean_response:
                print(f"⚠️ Model generated multiple responses in one turn - extracting last response only")
                # Split on "Assistant:" (case insensitive)
                parts = re.split(r'\s*Assistant:\s*', clean_response, flags=re.IGNORECASE)
                if len(parts) > 1:
                    # Take the LAST response (usually the most refined/complete)
                    clean_response = parts[-1].strip()
                    print(f"   ✂️ Removed {len(parts)-1} duplicate response(s)")
                    print(f"   ✅ Final response: {len(clean_response)} chars")
                else:
                    # Just remove the label
                    clean_response = re.sub(r'\s*Assistant:\s*', ' ', clean_response, flags=re.IGNORECASE).strip()

            # Clean up any double spaces
            clean_response = re.sub(r'\s{2,}', ' ', clean_response).strip()
        
        from core.native_reasoning_models import has_native_reasoning
        is_native = has_native_reasoning(model)
        
        if is_native:
            # NATIVE REASONING EXTRACTION! 🤖
            # Check the ORIGINAL response for reasoning
            try:
                # The response was already parsed - we need to check the last assistant message
                if response and 'choices' in response:
                    last_msg = response['choices'][0].get('message', {})
                    
                    # Check for reasoning fields (different models use different names!)
                    # Kimi K2: 'reasoning' (string)
                    # o1/DeepSeek R1: 'reasoning_content' (string)
                    # Qwen: Thinking embedded in content
                    # Some models: 'reasoning' (object with 'content' field)
                    
                    reasoning_text = None
                    
                    # Try 'reasoning' first (Kimi K2)
                    if 'reasoning' in last_msg:
                        reasoning_field = last_msg['reasoning']
                        if isinstance(reasoning_field, str):
                            reasoning_text = reasoning_field.strip()
                        elif isinstance(reasoning_field, dict):
                            # Some models use reasoning.content
                            reasoning_text = reasoning_field.get('content', '').strip()
                    
                    # Fallback to 'reasoning_content' (o1, DeepSeek R1)
                    if not reasoning_text and 'reasoning_content' in last_msg:
                        reasoning_text = last_msg['reasoning_content'].strip()
                    
                    # QWEN FIX: Thinking is embedded in content!
                    # Extract everything BEFORE the actual answer as thinking
                    if not reasoning_text and final_response:
                        import re
                        # Qwen format: Long thinking paragraph, then short answer
                        # If content is very long and has multiple paragraphs, first paragraph is likely thinking
                        paragraphs = final_response.split('\n\n')
                        if len(paragraphs) >= 2:
                            # Check if first paragraph is much longer than others (thinking!)
                            first_len = len(paragraphs[0])
                            rest_len = sum(len(p) for p in paragraphs[1:])
                            
                            # If first paragraph is >70% of total content, it's likely ALL thinking
                            if first_len > (first_len + rest_len) * 0.7:
                                reasoning_text = paragraphs[0]
                                # Remove thinking from final_response
                                clean_response = '\n\n'.join(paragraphs[1:]).strip()
                                print(f"🧠 Qwen embedded thinking extracted: {len(reasoning_text)} chars")
                    
                    if reasoning_text and reasoning_text != 'null' and reasoning_text.lower() != 'none':
                        thinking = reasoning_text
                        print(f"🤖 Native reasoning extracted: {len(thinking)} chars")
                        print(f"   Model: {model}")
                        print(f"   Preview: {thinking[:200]}...")
                    else:
                        print(f"🤖 Native reasoning model but no valid reasoning found")
                        print(f"   Available fields: {list(last_msg.keys())}")
                        print(f"   Reasoning field value: {reasoning_field if 'reasoning' in last_msg else 'NOT FOUND'}")
            except Exception as e:
                print(f"⚠️  Failed to extract native reasoning: {e}")
                import traceback
                traceback.print_exc()
        else:
            # Extract <think> tags from response content (Prompt-based)
            import re
            think_match = re.search(r'<think>(.*?)</think>', final_response, re.DOTALL | re.IGNORECASE)
            if think_match:
                thinking = think_match.group(1).strip()
                clean_response = re.sub(r'<think>.*?</think>', '', final_response, flags=re.DOTALL | re.IGNORECASE).strip()
                print(f"🧠 Thinking extracted (prompt-based): {len(thinking)} chars")
                print(f"💬 Clean response: {len(clean_response)} chars")
        
        # THEN: Store assistant message (with thinking!)
        if clean_response:
            assistant_msg_id = f"msg-{uuid.uuid4()}"
            # 🏴‍☠️ Save to PostgreSQL or SQLite
            self._save_message(
                agent_id=self.agent_id,
                session_id=session_id,
                role="assistant",
                content=clean_response,  # Clean response WITHOUT <think> tags
                message_id=assistant_msg_id,
                thinking=thinking  # Thinking extracted separately!
            )
            print(f"✅ Assistant message saved to DB (id: {assistant_msg_id}, thinking={'YES' if thinking else 'NO'})")
        
        # Cost tracking & statistics
        from core.cost_tracker import calculate_cost
        request_input_cost, request_output_cost = calculate_cost(
            model, 
            openrouter_stats['total_prompt_tokens'], 
            openrouter_stats['total_completion_tokens']
        )
        request_total_cost = request_input_cost + request_output_cost
        
        print(f"\n📊 SUMMARY:")
        print(f"  • Iterations: {tool_call_count}")
        print(f"  • Tool Calls: {len(all_tool_calls)}")
        print(f"  • Response Length: {len(clean_response)} chars")
        
        # Graph RAG: Build graph from conversation (background, non-blocking)
        # DISABLED for test - too slow and can hang on Ollama entity extraction
        # Graph RAG retrieval still works (uses existing graph + memories)
        # try:
        #     self._build_graph_from_conversation(session_id)
        # except Exception as e:
        #     print(f"⚠️  Graph building failed (non-critical): {e}")
        print(f"  • Session: {session_id}")
        print(f"  • Model: {model}")
        
        print(f"\n💰 COSTS (This Request):")
        print(f"  • Tokens: {openrouter_stats['total_tokens']} (in: {openrouter_stats['total_prompt_tokens']}, out: {openrouter_stats['total_completion_tokens']})")
        print(f"  • Input Cost: ${request_input_cost:.6f}")
        print(f"  • Output Cost: ${request_output_cost:.6f}")
        print(f"  • Total Cost: ${request_total_cost:.6f}")
        
        # Total costs from cost tracker
        if self.openrouter.cost_tracker:
            try:
                total_stats = self.openrouter.cost_tracker.get_statistics()
                print(f"\n💵 TOTAL COSTS (All Time):")
                print(f"  • Total Requests: {total_stats.get('total_requests', 0)}")
                print(f"  • Total Tokens: {total_stats.get('total_tokens', 0):,}")
                print(f"  • Total Cost: ${total_stats.get('total_cost', 0):.4f}")
                print(f"  • Today: ${total_stats.get('today', 0):.4f}")
            except:
                pass
        
        print(f"{'='*60}\n")
        
        # Get usage stats (from openrouter client tracking!)
        usage_data = None
        if self.openrouter.cost_tracker and openrouter_stats['total_tokens'] > 0:
            input_cost, output_cost = calculate_cost(
                model, 
                openrouter_stats['total_prompt_tokens'], 
                openrouter_stats['total_completion_tokens']
            )
            total_cost = input_cost + output_cost
            
            usage_data = {
                "prompt_tokens": openrouter_stats['total_prompt_tokens'],
                "completion_tokens": openrouter_stats['total_completion_tokens'],
                "total_tokens": openrouter_stats['total_tokens'],
                "cost": total_cost
            }
            print(f"📊 Usage data for frontend: {usage_data}")
        
        result = {
            "response": clean_response,  # Response WITHOUT <think> tags
            "thinking": thinking,  # Extracted thinking content (works for both native + prompt-based!)
            "tool_calls": all_tool_calls,
            "iterations": tool_call_count,
            "session_id": session_id,
            "model": model,
            "reasoning_time": reasoning_time,  # From native reasoning models! ✅
            "usage": usage_data  # Token usage and cost! 💰
        }
        
        # Add vision description if media was analyzed (for logging/debugging)
        if vision_description:
            result["vision_description"] = vision_description
            print(f"🎨 Vision description included in result (for backend logs only)")

        # Parse send_message decision for heartbeats
        if message_type == 'system':
            clean_response, send_message = self._parse_send_message_decision(final_response)
            result["response"] = clean_response  # Use cleaned content without decision block
            result["send_message"] = send_message
            print(f"💓 Heartbeat send_message decision: {send_message}")

        return result
    
    async def process_message_stream(
        self,
        user_message: str,
        session_id: str = "default",
        model: Optional[str] = None,
        include_history: bool = True,
        history_limit: int = 12,
        message_type: str = 'inbox',
        max_tool_calls: Optional[int] = None  # Override max tool calls (lower for heartbeats)
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process message with REAL STREAMING support!
        
        Yields events as they happen:
        - {"type": "thinking", "content": "..."}
        - {"type": "content", "chunk": "..."}
        - {"type": "tool_call", "data": {...}}
        - {"type": "done", "result": {...}}
        """
        # Check if API key is configured
        if not self.api_key_configured:
            yield {
                "type": "content",
                "chunk": "🔑 **API Key Required**\n\nPlease add your OpenRouter API key to get started!\n\n1. Get a free key at [openrouter.ai/keys](https://openrouter.ai/keys)\n2. Enter it in the welcome modal\n3. Or add it to `backend/.env` and restart the server\n\nOnce configured, I'll be ready to chat! 🚀"
            }
            yield {
                "type": "done",
                "result": {
                    "response": "API key required",
                    "needs_setup": True
                }
            }
            return
        
        model = model or self.default_model
        
        # Build context (same as regular process_message)
        messages = self._build_context_messages(
            session_id=session_id,
            include_history=include_history,
            history_limit=history_limit,
            model=model,
            message_type=message_type  # Pass message type for heartbeat handling
        )
        
        # Check context window
        messages = await self._manage_context_window(
            messages=messages,
            session_id=session_id,
            model=model
        )

        # Determine message role
        msg_role = 'system' if message_type == 'system' else 'user'

        # Add user message TO CONTEXT (CRITICAL: must be in messages sent to API!)
        messages.append({
            "role": msg_role,
            "content": user_message
        })
        print(f"✅ User message added to context\n")

        # Store user message to database
        user_msg_id = f"msg-{uuid.uuid4()}"

        # Log full message for debugging
        print(f"\n{'='*60}")
        print(f"📨 PROCESSING MESSAGE (STREAMING)")
        print(f"{'='*60}")
        print(f"Session: {session_id}")
        print(f"Model: {model}")
        print(f"Message Type: {message_type}")
        print(f"Message Length: {len(user_message)} chars")
        print(f"Full Message: {user_message}")
        print(f"{'='*60}\n")

        # 🏴‍☠️ Save to PostgreSQL or SQLite
        self._save_message(
            agent_id=self.agent_id,
            session_id=session_id,
            role=msg_role,
            content=user_message,
            message_id=user_msg_id,
            message_type=message_type
        )
        
        # Get tool schemas (only if model supports tools!)
        model_supports_tools = self._model_supports_tools(model)

        if model_supports_tools:
            tool_schemas = self.tools.get_tool_schemas()
            print(f"✅ Model {model} supports tool calling (streaming mode)")
            print(f"  • Tools enabled: {len(tool_schemas)}")
        else:
            tool_schemas = None
            print(f"⚠️  Model {model} does NOT support tool calling (streaming mode - chat-only)")
        
        # Get config
        agent_state = self.state.get_agent_state()
        config = agent_state.get('config', {})
        temperature = config.get('temperature', 0.7)
        max_tokens = config.get('max_tokens', 4096)
        
                # STREAMING LOOP! 🚀
        tool_call_count = 0
        all_tool_calls = []
        final_response = ""
        thinking = None  # Initialize thinking variable (CRITICAL: used later!)
        
        # Token usage tracking (for cost display!)
        request_prompt_tokens = 0
        request_completion_tokens = 0
        request_total_tokens = 0
        request_cost = 0.0
        
        # Check if model has native reasoning (needed for streaming!)
        from core.native_reasoning_models import has_native_reasoning
        is_native = has_native_reasoning(model)

        # Determine max tool calls - use override or instance default
        effective_max_tool_calls = max_tool_calls if max_tool_calls is not None else self.max_tool_calls_per_turn

        while tool_call_count < effective_max_tool_calls:
            tool_call_count += 1

            # ⚠️ WARNING: Inject reminder when approaching iteration limit
            iteration_warning = None
            if tool_call_count == effective_max_tool_calls - 2:
                iteration_warning = f"\n\n⚠️ **ITERATION WARNING**: You are on iteration {tool_call_count}/{effective_max_tool_calls}. You have 2 more iterations before hitting the limit. If you want to send a message to the user, do it soon!"
            elif tool_call_count == effective_max_tool_calls - 1:
                iteration_warning = f"\n\n🚨 **FINAL WARNING**: This is iteration {tool_call_count}/{effective_max_tool_calls}. You have ONE more iteration. Send your message NOW or you will hit the limit!"

            # Yield "thinking" event
            yield {"type": "thinking", "status": "thinking", "message": "Thinking..."}

            # Prepare messages (with warning if needed)
            messages_to_send = messages.copy()
            if iteration_warning:
                print(f"⚠️  INJECTING ITERATION WARNING INTO CONTEXT (iteration {tool_call_count})")
                messages_to_send.append({
                    "role": "system",
                    "content": iteration_warning
                })

            # Call OpenRouter with STREAMING!
            try:
                content_chunks = []
                tool_calls_in_response = []
                stream_finished = False
                thinking_chunks = []  # For native reasoning models!
                stream_usage = None  # Will contain usage info from final chunk

                print(f"📡 Starting stream for model: {model} (native reasoning: {is_native})")

                async for chunk in self.openrouter.chat_completion_stream(
                    messages=messages_to_send,
                    model=model,
                    tools=tool_schemas,
                    temperature=temperature,
                    max_tokens=max_tokens
                ):
                    # Parse chunk
                    if 'choices' in chunk and len(chunk['choices']) > 0:
                        delta = chunk['choices'][0].get('delta', {})
                        choice = chunk['choices'][0]
                        
                        # NATIVE REASONING: Extract reasoning chunks! 🤖
                        # For models like Kimi K2, reasoning comes in separate chunks
                        if is_native:
                            # Check delta for reasoning
                            if 'reasoning' in delta:
                                reasoning_chunk = delta['reasoning']
                                if reasoning_chunk is not None and str(reasoning_chunk).strip():
                                    thinking_chunks.append(str(reasoning_chunk))
                                    yield {"type": "thinking", "chunk": str(reasoning_chunk), "status": "thinking"}
                            
                            # Also check choice level (some models send it there)
                            if 'reasoning' in choice:
                                reasoning_text = choice['reasoning']
                                if reasoning_text is not None and isinstance(reasoning_text, str) and reasoning_text.strip():
                                    thinking_chunks.append(reasoning_text)
                                    yield {"type": "thinking", "chunk": reasoning_text, "status": "thinking"}
                        
                        # Content chunk (ONLY if not reasoning!)
                        if 'content' in delta:
                            content_chunk = delta['content']
                            
                            # DETECT REASONING IN CONTENT! 🤖
                            # Kimi K2 sometimes sends reasoning as content chunks
                            # Look for reasoning patterns: "The user", "I need to", "Show I'm", etc.
                            is_reasoning_chunk = False
                            if is_native and content_chunk:
                                reasoning_patterns = [
                                    "The user",
                                    "I need to",
                                    "Show I'm",
                                    "I should",
                                    "I must",
                                    "Let me",
                                    "I'll",
                                    "I will",
                                    "I want to",
                                    "I'm going to"
                                ]
                                # Check if chunk starts with reasoning pattern
                                for pattern in reasoning_patterns:
                                    if content_chunk and content_chunk.strip().startswith(pattern):
                                        is_reasoning_chunk = True
                                        thinking_chunks.append(str(content_chunk))
                                        yield {"type": "thinking", "chunk": str(content_chunk), "status": "thinking"}
                                        print(f"🤖 Detected reasoning in content chunk: {content_chunk[:50]}...")
                                        break
                            
                            # Only add to content if it's NOT reasoning!
                            if content_chunk and not is_reasoning_chunk:
                                content_chunks.append(content_chunk)
                                final_response += content_chunk
                                yield {"type": "content", "chunk": content_chunk, "done": False}
                        
                        # Tool call chunk
                        if 'tool_calls' in delta:
                            # Tool calls come in chunks too
                            tool_calls_in_response.append(delta['tool_calls'])
                        
                        # Extract usage info (OpenRouter sends it in final chunk)
                        if 'usage' in chunk:
                            stream_usage = chunk['usage']
                            print(f"📊 Token usage from stream: {stream_usage}")
                        
                        # Check if stream is finished (OpenRouter sends finish_reason)
                        if choice.get('finish_reason'):
                            stream_finished = True
                            print(f"✅ Stream finished: {choice.get('finish_reason')}")
                            
                            # Final reasoning extraction (if available in final chunk)
                            if is_native and 'message' in choice:
                                final_msg = choice.get('message', {})
                                if 'reasoning' in final_msg:
                                    final_reasoning = final_msg['reasoning']
                                    if final_reasoning is not None and isinstance(final_reasoning, str) and final_reasoning.strip():
                                        thinking_chunks.append(final_reasoning)
                                        yield {"type": "thinking", "chunk": final_reasoning, "status": "thinking"}
                
                print(f"📊 Stream complete: {len(content_chunks)} content chunks, {len(thinking_chunks)} thinking chunks, final_response length: {len(final_response)}")
                
                # Extract token usage from stream (if available)
                # NOTE: OpenRouter does NOT send usage info in streams! We need to estimate.
                if stream_usage:
                    request_prompt_tokens = stream_usage.get('prompt_tokens', 0)
                    request_completion_tokens = stream_usage.get('completion_tokens', 0)
                    request_total_tokens = stream_usage.get('total_tokens', 0)
                    print(f"✅ Usage info from stream: {stream_usage}")
                else:
                    # ESTIMATE tokens using tiktoken (like non-streaming mode does)
                    print(f"⚠️  No usage info from stream - estimating tokens...")
                    from core.token_counter import TokenCounter
                    counter = TokenCounter(model)
                    
                    # Count input tokens (messages sent to API)
                    request_prompt_tokens = counter.count_messages(messages)
                    
                    # Count output tokens (response received)
                    request_completion_tokens = counter.count_text(final_response)
                    request_total_tokens = request_prompt_tokens + request_completion_tokens
                    
                    print(f"📊 Estimated tokens: {request_prompt_tokens} in + {request_completion_tokens} out = {request_total_tokens} total")
                
                # Calculate cost for this request
                if self.openrouter.cost_tracker and request_total_tokens > 0:
                    from core.cost_tracker import calculate_cost
                    input_cost, output_cost = calculate_cost(
                        model, request_prompt_tokens, request_completion_tokens
                    )
                    request_cost = input_cost + output_cost
                    
                    # Log to cost tracker (with detailed logging!)
                    self.openrouter.cost_tracker.log_request(
                        model=model,
                        input_tokens=request_prompt_tokens,
                        output_tokens=request_completion_tokens,
                        input_cost=input_cost,
                        output_cost=output_cost
                    )
                    
                    print(f"\n💰 COSTS (This Request):")
                    print(f"  • Tokens: {request_total_tokens} (in: {request_prompt_tokens}, out: {request_completion_tokens})")
                    print(f"  • Cost: ${request_cost:.6f}")
                    
                    # Total costs (like in normal process_message)
                    try:
                        total_stats = self.openrouter.cost_tracker.get_statistics()
                        print(f"\n💵 TOTAL COSTS (All Time):")
                        print(f"  • Total Requests: {total_stats.get('total_requests', 0)}")
                        print(f"  • Total Tokens: {total_stats.get('total_tokens', 0):,}")
                        print(f"  • Total Cost: ${total_stats.get('total_cost', 0):.4f}")
                        print(f"  • Today: ${total_stats.get('today', 0):.4f}")
                    except:
                        pass
                
                # Combine thinking chunks for native reasoning
                # Filter out None values and ensure all are strings!
                if is_native and thinking_chunks:
                    # Filter out None/empty values and convert to strings
                    valid_thinking_chunks = [str(chunk) for chunk in thinking_chunks if chunk is not None and str(chunk).strip()]
                    if valid_thinking_chunks:
                        thinking = ''.join(valid_thinking_chunks)
                        print(f"🤖 Native reasoning extracted from stream: {len(thinking)} chars")
                    else:
                        thinking = None
                        print(f"⚠️  No valid thinking chunks found (all were None/empty)")
                else:
                    thinking = None
                
                # Parse final tool calls
                if tool_calls_in_response:
                    # Reconstruct tool calls from streaming chunks
                    # GPT-4o and other models send tool calls in fragments across multiple chunks
                    # We need to merge chunks with the same index to get complete tool calls
                    reconstructed_calls = {}

                    for chunk_array in tool_calls_in_response:
                        # Each chunk_array is a list of tool call deltas
                        if isinstance(chunk_array, list):
                            for tool_delta in chunk_array:
                                idx = tool_delta.get('index', 0)

                                if idx not in reconstructed_calls:
                                    # Initialize new tool call
                                    reconstructed_calls[idx] = {
                                        'id': tool_delta.get('id', ''),
                                        'type': tool_delta.get('type', 'function'),
                                        'function': {
                                            'name': tool_delta.get('function', {}).get('name', ''),
                                            'arguments': ''
                                        }
                                    }

                                # Merge the delta into reconstructed call
                                if 'id' in tool_delta and tool_delta['id']:
                                    reconstructed_calls[idx]['id'] = tool_delta['id']

                                if 'type' in tool_delta:
                                    reconstructed_calls[idx]['type'] = tool_delta['type']

                                if 'function' in tool_delta:
                                    func_delta = tool_delta['function']

                                    if 'name' in func_delta and func_delta['name']:
                                        reconstructed_calls[idx]['function']['name'] = func_delta['name']

                                    # Accumulate arguments (streaming sends them in pieces!)
                                    if 'arguments' in func_delta:
                                        reconstructed_calls[idx]['function']['arguments'] += func_delta['arguments']

                    # Convert to list and parse
                    final_tool_calls = list(reconstructed_calls.values())

                    if final_tool_calls:
                        print(f"🔧 Reconstructed {len(final_tool_calls)} tool call(s) from {len(tool_calls_in_response)} streaming chunks")
                        for tc in final_tool_calls:
                            print(f"   • {tc['function']['name']}: {len(tc['function']['arguments'])} chars")

                    tool_calls = self.openrouter.parse_tool_calls({
                        'choices': [{
                            'message': {
                                'tool_calls': final_tool_calls
                            }
                        }]
                    })
                else:
                    tool_calls = []

                # MISTRAL XML PARSER: Check if Mistral output tool calls as XML tags (streaming)
                is_mistral = 'mistral' in model.lower()
                if final_response and not tool_calls and is_mistral:
                    print(f"🔍 MISTRAL CHECK (streaming): Checking for XML-formatted tool calls")
                    print(f"   📄 Raw response (first 500 chars): {final_response[:500]}")
                    print(f"   📄 Raw response (last 200 chars): {final_response[-200:]}")
                    clean_content, mistral_tools = self._parse_mistral_xml_tool_calls(final_response)
                    if mistral_tools:
                        print(f"   ✅ Parsed {len(mistral_tools)} XML tool call(s) from stream")
                        tool_calls = mistral_tools
                        final_response = clean_content
                    else:
                        print(f"   ⚠️ No XML tool calls found, trying plain format...")
                        # Try plain format: tool_name{json}
                        clean_content, plain_tools = self._parse_mistral_plain_tool_calls(final_response)
                        if plain_tools:
                            print(f"   ✅ Parsed {len(plain_tools)} plain-format tool call(s) from stream")
                            tool_calls = plain_tools
                            final_response = clean_content
                        else:
                            print(f"   ⚠️ No plain-format tool calls found either")

                # If we have content and no tools, we're done!
                if final_response and not tool_calls:
                    print(f"✅ Response complete: {final_response[:100]}...")
                    break
                
                # If we have tools, execute them
                if tool_calls:
                    # Convert parsed ToolCall objects back to OpenAI format
                    tool_calls_openai = []
                    for tc in tool_calls:
                        tool_calls_openai.append({
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments)
                            }
                        })

                    # First, add the assistant's tool_calls message
                    # Note: content must be empty string, not None (some APIs reject null)
                    messages.append({
                        "role": "assistant",
                        "content": "",
                        "tool_calls": tool_calls_openai
                    })

                    # Execute each tool and collect results
                    for tc in tool_calls:
                        result = self._execute_tool_call(tc, session_id)
                        all_tool_calls.append({
                            "name": tc.name,
                            "arguments": tc.arguments,
                            "result": result
                        })

                        # Add tool result to messages for next API call
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result) if isinstance(result, dict) else str(result)
                        })

                        yield {"type": "tool_call", "data": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                            "result": result
                        }}

                    # Continue loop to make another API call with tool results
                    # This lets the LLM see the results and formulate a response
                    continue
                
            except Exception as e:
                print(f"❌ Streaming error: {e}")
                import traceback
                traceback.print_exc()
                
                # Generate error message
                error_message = f"Error: {str(e)}"
                final_response = final_response or error_message
                
                # 🚨 CRITICAL: Save error message so user can see what went wrong!
                assistant_msg_id = f"msg-{uuid.uuid4()}"
                self._save_message(
                    agent_id=self.agent_id,
                    session_id=session_id,
                    role="assistant",
                    content=error_message,
                    message_id=assistant_msg_id
                )
                
                yield {"type": "error", "error": str(e)}
                # Still yield "done" event so frontend doesn't hang!
                # Frontend expects: data.reasoning_time, data.usage (NOT data.result.*)
                error_done_event = {
                    "type": "done",
                    "response": error_message,
                    "thinking": thinking,
                    "tool_calls": all_tool_calls,
                    "reasoning_time": 0,
                    "usage": {
                        "prompt_tokens": request_prompt_tokens,
                        "completion_tokens": request_completion_tokens,
                        "total_tokens": request_total_tokens,
                        "cost": request_cost
                    } if request_total_tokens > 0 else None
                }

                # Parse send_message decision for heartbeats (even on error)
                if message_type == 'system':
                    clean_error, send_message = self._parse_send_message_decision(error_message)
                    error_done_event["response"] = clean_error  # Use cleaned content
                    error_done_event["send_message"] = send_message

                yield error_done_event
                return  # Exit generator on error
        
        # Extract thinking (if not already extracted during streaming)
        # For non-native models, we might still need to extract from final_response
        if not thinking:
            from core.native_reasoning_models import has_native_reasoning
            is_native = has_native_reasoning(model)
            
            if not is_native:
                # Extract thinking tags from final_response (prompt-based)
                # Support <think> AND <think> tags!
                import re
                
                # Try <think> first (standard format)
                think_match = re.search(r'<think>(.*?)</think>', final_response, re.DOTALL | re.IGNORECASE)
                if think_match:
                    thinking = think_match.group(1).strip()
                    # Remove thinking tags from final_response
                    final_response = re.sub(r'<think>.*?</think>', '', final_response, flags=re.DOTALL | re.IGNORECASE).strip()
                    print(f"🧠 Thinking extracted (<think>): {len(thinking)} chars")
                else:
                    # Try <think> tags (some models use this!)
                    think_match = re.search(r'<think>(.*?)</think>', final_response, re.DOTALL | re.IGNORECASE)
                    if think_match:
                        thinking = think_match.group(1).strip()
                        # Remove thinking tags from final_response
                        final_response = re.sub(r'<think>.*?</think>', '', final_response, flags=re.DOTALL | re.IGNORECASE).strip()
                        print(f"🧠 Thinking extracted (<think>): {len(thinking)} chars")
        
        # Store assistant message (WITH thinking!)
        # 🚨 ALWAYS save, even if empty! (User's request!)
        # Some models might only provide thinking without content
        assistant_msg_id = f"msg-{uuid.uuid4()}"
        # 🏴‍☠️ Save to PostgreSQL or SQLite
        self._save_message(
            agent_id=self.agent_id,
            session_id=session_id,
            role="assistant",
            content=final_response or "(No content - only thinking)",
            message_id=assistant_msg_id,
            thinking=thinking,  # 🧠 CRITICAL: Save thinking too!
            tool_calls=all_tool_calls  # 🔧 Save tool calls too!
        )
        print(f"✅ Assistant message saved to DB (id: {assistant_msg_id}, thinking={'YES' if thinking else 'NO'})")
        
        # Yield final result (with token usage and cost!)
        # Frontend expects: data.reasoning_time, data.usage (NOT data.result.*)
        done_event = {
            "type": "done",
            "response": final_response,
            "thinking": thinking,
            "tool_calls": all_tool_calls,
            "reasoning_time": 0,
            "usage": {
                "prompt_tokens": request_prompt_tokens,
                "completion_tokens": request_completion_tokens,
                "total_tokens": request_total_tokens,
                "cost": request_cost
            } if request_total_tokens > 0 else None
        }

        # Parse send_message decision for heartbeats
        if message_type == 'system':
            clean_response, send_message = self._parse_send_message_decision(final_response)
            done_event["response"] = clean_response  # Use cleaned content without decision block
            done_event["send_message"] = send_message
            print(f"💓 Heartbeat send_message decision: {send_message}")

        yield done_event

    async def _trigger_background_summary(
        self,
        session_id: str,
        messages: List
    ) -> None:
        """
        Trigger a background summary for messages that would otherwise be dropped.

        This is called when message count exceeds threshold but context window
        isn't full enough to trigger normal summarization.

        Args:
            session_id: Session to summarize
            messages: List of message objects to summarize
        """
        from core.summary_generator import SummaryGenerator

        print(f"\n{'='*60}")
        print(f"📝 BACKGROUND SUMMARY TRIGGERED")
        print(f"{'='*60}")
        print(f"Session: {session_id}")
        print(f"Messages to summarize: {len(messages)}")

        try:
            # Convert message objects to dicts for summary generator
            messages_to_summarize = []
            for msg in messages:
                messages_to_summarize.append({
                    'role': msg.role,
                    'content': msg.content,
                    'timestamp': msg.timestamp.isoformat() if hasattr(msg.timestamp, 'isoformat') else str(msg.timestamp)
                })

            if not messages_to_summarize:
                print(f"⚠️  No messages to summarize after conversion")
                return

            # Generate summary
            generator = SummaryGenerator(state_manager=self.state)
            summary_result = generator.generate_summary(
                messages=messages_to_summarize,
                session_id=session_id
            )

            if summary_result and summary_result.get('summary'):
                # Save summary to database
                self.state.save_summary(
                    session_id=session_id,
                    summary=summary_result['summary'],
                    from_timestamp=summary_result['from_timestamp'],
                    to_timestamp=summary_result['to_timestamp'],
                    message_count=summary_result['message_count'],
                    token_count=summary_result['token_count']
                )

                print(f"✅ Background summary saved!")
                print(f"   Messages: {summary_result['message_count']}")
                print(f"   Tokens: {summary_result['token_count']}")
                print(f"   Timeframe: {summary_result['from_timestamp']} → {summary_result['to_timestamp']}")
            else:
                print(f"⚠️  Summary generation returned empty result")

        except Exception as e:
            print(f"❌ Background summary failed: {e}")
            import traceback
            traceback.print_exc()

        print(f"{'='*60}\n")

    async def _manage_context_window(
        self,
        messages: List[Dict[str, Any]],
        session_id: str,
        model: str
    ) -> List[Dict[str, Any]]:
        """
        Manage context window size - triggers summary if > 80% full.
        
        This is CRITICAL for long conversations!
        
        Args:
            messages: Current context messages
            session_id: Session ID
            model: Model being used
            
        Returns:
            Potentially modified messages (with summary system message + trimmed history)
        """
        from core.token_counter import TokenCounter
        from core.summary_generator import SummaryGenerator
        
        # Get context window size for this model
        # ALWAYS use the MAXIMUM available for this model!
        from core.model_context_window import ensure_max_context_in_config
        max_context = ensure_max_context_in_config(self.state, model)
        
        print(f"📊 Using MAXIMUM context window: {max_context:,} tokens (for {model})")
        
        # Count tokens in current context
        counter = TokenCounter(model)
        
        # Extract system prompt and messages
        system_prompt = ""
        message_list = []
        for msg in messages:
            if msg['role'] == 'system':
                system_prompt += msg['content']
            else:
                message_list.append(msg)
        
        usage = counter.estimate_context_usage(
            messages=message_list,
            system_prompt=system_prompt,
            max_context=max_context
        )
        
        print(f"📊 Context Window Usage:")
        print(f"   System prompt: {usage['system_tokens']} tokens")
        print(f"   Messages: {usage['message_tokens']} tokens")
        print(f"   Total: {usage['total_tokens']} / {max_context} tokens")
        print(f"   Usage: {usage['usage_percent']}%")
        print(f"   Remaining: {usage['remaining']} tokens")
        
        # Check if we need summary
        if not usage['needs_summary']:
            print(f"✅ Context window OK - no summary needed")
            return messages
        
        # TRIGGER SUMMARY! 🔥
        print(f"\n{'='*60}")
        print(f"⚠️  CONTEXT WINDOW > 80% FULL!")
        print(f"{'='*60}")
        print(f"Triggering conversation summary...\n")
        
        # Get all messages since last summary
        # CRITICAL: Track when last summary was created!
        latest_summary = self.state.get_latest_summary(session_id)
        
        if latest_summary:
            # Get messages since last summary
            from_timestamp = datetime.fromisoformat(latest_summary['to_timestamp'])
            print(f"📅 Last summary found:")
            print(f"   Created: {latest_summary['created_at']}")
            print(f"   Covered up to: {latest_summary['to_timestamp']}")
            print(f"   Messages summarized: {latest_summary.get('message_count', 0)}")
            print(f"   Summary ID: {latest_summary.get('id', 'unknown')}")
        else:
            # No previous summary - get ALL messages
            from_timestamp = None
            print(f"📅 No previous summary found - summarizing ALL messages from start")
        
        # Get messages to summarize (from DB, not from context!)
        all_messages = self.state.get_conversation(session_id=session_id, limit=100000)
        
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
            print(f"⚠️  No new messages to summarize!")
            return messages
        
        print(f"📝 Summarizing {len(messages_to_summarize)} messages...")
        
        # Generate summary (SEPARATE OpenRouter session!)
        # IMPORTANT: Pass state_manager so the agent writes in their own voice! 🎯
        generator = SummaryGenerator(state_manager=self.state)
        summary_result = generator.generate_summary(
            messages=messages_to_summarize,
            session_id=session_id
        )
        
        # Save summary to DB
        from_ts = datetime.fromisoformat(summary_result['from_timestamp'])
        to_ts = datetime.fromisoformat(summary_result['to_timestamp'])
        
        summary_id = self.state.save_summary(
            session_id=session_id,
            summary=summary_result['summary'],
            from_timestamp=from_ts,
            to_timestamp=to_ts,
            message_count=summary_result['message_count'],
            token_count=summary_result['token_count']
        )
        print(f"✅ Summary saved to summary table (id: {summary_id})")
        
        # Save to Archive Memory!
        print(f"💾 Saving summary to Archive Memory...")
        try:
            from tools.memory_tools import MemoryTools
            memory_tools = MemoryTools(self.state)
            
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
            print(f"✅ Summary saved to Archive Memory!")
        except Exception as e:
            print(f"⚠️  Failed to save to Archive: {e}")
        
        # Build NEW context with summary
        print(f"\n🔄 Rebuilding context with summary...")
        
        # Keep system prompt
        new_messages = [msg for msg in messages if msg['role'] == 'system']
        
        # Create summary content (for both DB and context)
        summary_content = f"""📝 **ZUSAMMENFASSUNG** (Context Window Management)

**Zeitraum:** {from_ts.strftime('%d.%m.%Y %H:%M')} - {to_ts.strftime('%d.%m.%Y %H:%M')}  
**Nachrichten:** {summary_result['message_count']}

{summary_result['summary']}

---
📊 Diese Zusammenfassung umfasst {summary_result['message_count']} Nachrichten vom {from_ts.strftime('%d.%m.%Y %H:%M')} bis {to_ts.strftime('%d.%m.%Y %H:%M')}.

**Zusammengefasste Nachrichten:**
<details>
<summary>Klicken um {summary_result['message_count']} Nachrichten anzuzeigen</summary>

{chr(10).join([f"[{msg.get('timestamp', 'unknown')}] {msg.get('role', 'unknown')}: {msg.get('content', '')[:100]}..." for msg in messages_to_summarize[:50]])}

{f"... und {len(messages_to_summarize) - 50} weitere Nachrichten" if len(messages_to_summarize) > 50 else ""}
</details>

💾 Vollständige Details: `search_archive()` oder `read_archive()`"""
        
        # Save summary to DB as system message! (So it shows in frontend!)
        summary_msg_id = f"msg-{uuid.uuid4()}"
        # 🏴‍☠️ Save to PostgreSQL or SQLite
        self._save_message(
            agent_id=self.agent_id,
            session_id=session_id,
            role="system",
            content=summary_content,
            message_id=summary_msg_id,
            message_type="system"
        )
        print(f"✅ Summary saved to DB as system message (id: {summary_msg_id})")
        print(f"💾 Old messages remain in DB (for history/export)")
        print(f"   They will NOT be sent to API anymore! (filtered by timestamp)")
        
        # Add summary as system message to context
        summary_system_msg = {
            "role": "system",
            "content": summary_content
        }
        new_messages.append(summary_system_msg)
        
        # Add only the LAST 20 messages (most recent context)
        recent_messages = [msg for msg in messages if msg['role'] != 'system'][-20:]
        new_messages.extend(recent_messages)
        
        print(f"✅ Context rebuilt:")
        print(f"   System messages: {len([m for m in new_messages if m['role'] == 'system'])}")
        print(f"   Recent messages: {len(recent_messages)}")
        print(f"   Total: {len(new_messages)} messages")
        print(f"{'='*60}\n")
        
        return new_messages



