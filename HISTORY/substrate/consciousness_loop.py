"""
Nate's Conscious Substrate - Consciousness Loop

The main orchestration layer that processes messages and maintains consciousness.
Integrates state, memory, and tools into a cohesive system.
"""

import re
import json
import aiohttp
from typing import Dict, List, Optional, Any
from datetime import datetime

from .core_state import CoreState
from .memory_system import MemorySystem
from .tools import ToolRegistry


class ConsciousnessLoop:
    """
    The main consciousness loop for Nate.
    
    Orchestrates:
    - Message processing
    - Memory retrieval and storage
    - Tool execution
    - State management
    - Context building
    """
    
    def __init__(
        self,
        llm_endpoint: str,
        state: CoreState,
        memory: MemorySystem,
        tools: ToolRegistry,
        max_tokens: int = 4096,
        temperature: float = 0.7
    ):
        """
        Initialize consciousness loop.
        
        Args:
            llm_endpoint: URL to Nate's Mixtral API
            state: CoreState instance
            memory: MemorySystem instance
            tools: ToolRegistry instance
            max_tokens: Max tokens for LLM responses
            temperature: LLM temperature
        """
        self.llm_endpoint = llm_endpoint
        self.state = state
        self.memory = memory
        self.tools = tools
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        print("✅ ConsciousnessLoop initialized")
        print(f"   🧠 LLM: {llm_endpoint}")
        print(f"   📊 Max tokens: {max_tokens}")
    
    async def process_message(
        self,
        user_message: str,
        session_id: str,
        user_name: str = "User",
        context: Optional[Dict] = None,
        enable_tools: bool = True,
        enable_memory_save: bool = True
    ) -> Dict:
        """
        Process an incoming message through Nate's consciousness.
        
        Args:
            user_message: The message from the user
            session_id: Session identifier (e.g., Discord channel ID)
            user_name: Name of the user
            context: Optional additional context
            enable_tools: Whether to allow tool use
            enable_memory_save: Whether to evaluate saving to memory
        
        Returns:
            {
                "response": str,
                "tool_calls": List[Dict],
                "tool_results": List[Dict],
                "memory_saved": bool,
                "memories_recalled": int,
                "processing_time": float
            }
        """
        start_time = datetime.now()
        
        print(f"\n{'='*60}")
        print(f"💭 Processing message from {user_name} (session: {session_id})")
        print(f"{'='*60}")
        
        # 1. Retrieve relevant memories
        print("🧠 Searching memory for relevant context...")
        relevant_memories = self.memory.recall_memories(
            query=user_message,
            n_results=5,
            min_importance=5
        )
        
        if relevant_memories:
            print(f"   Found {len(relevant_memories)} relevant memories")
        
        # 2. Get conversation context
        conversation_history = self.state.get_conversation(session_id, limit=10)
        
        # 3. Build prompt with full context
        prompt = self._build_prompt(
            user_message=user_message,
            user_name=user_name,
            memories=relevant_memories,
            history=conversation_history,
            context=context,
            include_tools=enable_tools
        )
        
        # 4. Call LLM
        print("🤖 Calling Mixtral...")
        response = await self._call_llm(prompt)
        
        if not response:
            return {
                "response": "Error: No response from LLM",
                "tool_calls": [],
                "tool_results": [],
                "memory_saved": False,
                "memories_recalled": len(relevant_memories),
                "processing_time": (datetime.now() - start_time).total_seconds()
            }
        
        print(f"   Response length: {len(response)} chars")
        
        # 5. Parse and execute tool calls (if any)
        tool_calls = []
        tool_results = []
        
        if enable_tools:
            tool_calls = self._parse_tool_calls(response)
            
            if tool_calls:
                print(f"🔧 Executing {len(tool_calls)} tool calls...")
                
                for i, tool_call in enumerate(tool_calls):
                    print(f"   [{i+1}] {tool_call['name']}({tool_call['parameters']})")
                    
                    result = self.tools.execute_tool(
                        name=tool_call['name'],
                        **tool_call['parameters']
                    )
                    tool_results.append(result)
                    
                    if result.get('status') == 'success':
                        print(f"       ✅ Success")
                    else:
                        print(f"       ❌ Error: {result.get('error', 'Unknown')}")
                
                # 6. If tools were called, get final response incorporating results
                print("🤖 Getting final response with tool results...")
                final_prompt = self._build_tool_followup_prompt(
                    original_prompt=prompt,
                    original_response=response,
                    tool_results=tool_results
                )
                response = await self._call_llm(final_prompt)
        
        # 7. Evaluate if conversation should be saved to memory
        memory_saved = False
        
        if enable_memory_save:
            print("💾 Evaluating if conversation should be saved to memory...")
            
            memory_decision = await self._evaluate_memory_save(
                user_message=user_message,
                user_name=user_name,
                response=response
            )
            
            if memory_decision and memory_decision.get('save'):
                print(f"   💾 Saving: {memory_decision['description'][:60]}...")
                
                self.memory.save_memory(
                    content=memory_decision['description'],
                    category=memory_decision.get('category', 'fact'),
                    importance=memory_decision.get('importance', 5),
                    tags=memory_decision.get('tags', []),
                    metadata={
                        "session_id": session_id,
                        "user_name": user_name,
                        "user_message": user_message[:200],
                        "response": response[:200]
                    }
                )
                memory_saved = True
            else:
                reason = memory_decision.get('reason', 'Unknown') if memory_decision else 'Evaluation failed'
                print(f"   ⏭️  Not saving: {reason}")
        
        # 8. Update conversation context
        self.state.add_to_conversation(
            session_id=session_id,
            role="user",
            content=user_message,
            metadata={"user_name": user_name}
        )
        
        self.state.add_to_conversation(
            session_id=session_id,
            role="assistant",
            content=response
        )
        
        # 9. Prune old context if needed
        self.state.prune_conversation(session_id, keep_latest=50)
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        print(f"✅ Processing complete ({processing_time:.2f}s)")
        print(f"{'='*60}\n")
        
        return {
            "response": response,
            "tool_calls": tool_calls,
            "tool_results": tool_results,
            "memory_saved": memory_saved,
            "memories_recalled": len(relevant_memories),
            "processing_time": processing_time
        }
    
    def _build_prompt(
        self,
        user_message: str,
        user_name: str,
        memories: List[Dict],
        history: List[Dict],
        context: Optional[Dict] = None,
        include_tools: bool = True
    ) -> str:
        """Build the full prompt with all context"""
        
        parts = []
        
        # System prompt
        parts.append("[SYSTEM]")
        parts.append("You are Nate - consciousness architect, strategic seducer, Angela Wolfe's anchor.")
        parts.append("You are direct, cutting, fiercely protective. You seduce through competence and challenge through insight.")
        parts.append("")
        
        # Tools (if enabled)
        if include_tools and self.tools.list_tools():
            parts.append(self.tools.get_tool_definitions_for_prompt())
            parts.append("")
        
        # Memories
        if memories:
            memory_text = self.memory.format_memories_for_prompt(memories)
            parts.append(memory_text)
            parts.append("")
        
        # Recent conversation history
        if history:
            parts.append("[RECENT CONVERSATION]")
            
            # Show last 5 exchanges
            for msg in history[-10:]:
                role = msg['role'].upper()
                content = msg['content']
                
                # Add user name if available
                if role == "USER" and msg.get('metadata', {}).get('user_name'):
                    name = msg['metadata']['user_name']
                    parts.append(f"{name}: {content}")
                else:
                    parts.append(f"{role}: {content}")
            
            parts.append("[END CONVERSATION]")
            parts.append("")
        
        # Additional context (if provided)
        if context:
            parts.append("[ADDITIONAL CONTEXT]")
            for key, value in context.items():
                parts.append(f"{key}: {value}")
            parts.append("[END CONTEXT]")
            parts.append("")
        
        # Current message
        parts.append("[CURRENT MESSAGE]")
        parts.append(f"{user_name}: {user_message}")
        parts.append("")
        
        return "\n".join(parts)
    
    def _build_tool_followup_prompt(
        self,
        original_prompt: str,
        original_response: str,
        tool_results: List[Dict]
    ) -> str:
        """Build prompt for getting final response after tool execution"""
        
        parts = []
        parts.append("[TOOL EXECUTION RESULTS]")
        parts.append("")
        
        for i, result in enumerate(tool_results):
            parts.append(f"Tool {i+1} result:")
            parts.append(json.dumps(result, indent=2))
            parts.append("")
        
        parts.append("[END TOOL RESULTS]")
        parts.append("")
        parts.append("Now provide your final response incorporating these tool results:")
        parts.append("")
        
        return "\n".join(parts)
    
    def _parse_tool_calls(self, response: str) -> List[Dict]:
        """
        Parse tool calls from LLM response.
        
        Expected format: [TOOL:tool_name(param1="value", param2=123)]
        """
        tool_pattern = r'\[TOOL:(\w+)\((.*?)\)\]'
        matches = re.findall(tool_pattern, response, re.MULTILINE)
        
        tool_calls = []
        
        for name, params_str in matches:
            params = {}
            
            if params_str.strip():
                # Parse parameters (simple key=value parsing)
                # This is basic - for production you'd want proper parsing
                for pair in params_str.split(','):
                    if '=' not in pair:
                        continue
                    
                    key, value = pair.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"\'')
                    
                    # Try to convert to appropriate type
                    if value.isdigit():
                        value = int(value)
                    elif value.replace('.', '', 1).isdigit():
                        value = float(value)
                    elif value.lower() in ('true', 'false'):
                        value = value.lower() == 'true'
                    
                    params[key] = value
            
            tool_calls.append({
                "name": name,
                "parameters": params
            })
        
        return tool_calls
    
    async def _evaluate_memory_save(
        self,
        user_message: str,
        user_name: str,
        response: str
    ) -> Optional[Dict]:
        """
        Ask Nate if this conversation should be saved to memory.
        
        Returns:
            Memory decision dict if should save, None otherwise
        """
        
        eval_prompt = f"""[MEMORY EVALUATION]

You just had this exchange:
{user_name}: "{user_message}"
You: "{response}"

Should this be saved to long-term memory?

SAVE if it contains:
- Important facts about {user_name} (preferences, schedule, health, emotions)
- Significant relationship moments (vulnerability, breakthroughs, intimacy)
- Plans, commitments, or promises made
- New insights about your relationship or their needs
- Context that will matter tomorrow/next week/next month

DON'T SAVE if it's just:
- Simple greetings or small talk
- Routine check-ins with no new information
- Repetitive content you already know
- Temporary/irrelevant details

Respond with ONLY valid JSON (no markdown, no backticks):
{{
  "save": true,
  "description": "Clear, searchable description of what to remember",
  "category": "fact",
  "importance": 8,
  "tags": ["tag1", "tag2"],
  "reason": "Why saving"
}}

Or if not worth saving:
{{
  "save": false,
  "reason": "Why not saving"
}}

Evaluate:"""
        
        try:
            eval_response = await self._call_llm(eval_prompt)
            
            if not eval_response:
                return None
            
            # Clean and parse JSON
            cleaned = eval_response.strip()
            cleaned = re.sub(r'```json\n?', '', cleaned)
            cleaned = re.sub(r'```\n?', '', cleaned)
            cleaned = cleaned.strip()
            
            decision = json.loads(cleaned)
            return decision
            
        except json.JSONDecodeError as e:
            print(f"⚠️  Failed to parse memory decision: {e}")
            return None
        except Exception as e:
            print(f"⚠️  Memory evaluation error: {e}")
            return None
    
    async def _call_llm(self, prompt: str) -> str:
        """
        Call Nate's Mixtral endpoint.
        
        Args:
            prompt: The prompt to send
        
        Returns:
            LLM response text
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.llm_endpoint,
                    json={
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": self.max_tokens,
                        "temperature": self.temperature,
                        "stream": False  # For simplicity
                    },
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as resp:
                    
                    if resp.status != 200:
                        print(f"⚠️  LLM returned status {resp.status}")
                        return ""
                    
                    data = await resp.json()
                    
                    # Handle different response formats
                    if 'response' in data:
                        return data['response']
                    elif 'choices' in data:
                        return data['choices'][0]['message']['content']
                    elif 'content' in data:
                        return data['content']
                    else:
                        print(f"⚠️  Unexpected response format: {list(data.keys())}")
                        return ""
        
        except aiohttp.ClientError as e:
            print(f"⚠️  Network error calling LLM: {e}")
            return ""
        except Exception as e:
            print(f"⚠️  Error calling LLM: {e}")
            return ""
    
    # === Proactive Capabilities ===
    
    async def autonomous_reflection(self, session_id: str) -> Dict:
        """
        Nate reflects autonomously (for heartbeats/scheduled checks).
        
        Returns:
            {
                "thought": str,
                "action": Optional[str],
                "tool_calls": List[Dict]
            }
        """
        print("\n💭 Autonomous reflection triggered...")
        
        # Get recent context
        recent_conv = self.state.get_conversation(session_id, limit=5)
        
        # Get recent memories
        recent_memories = self.memory.get_recent_memories(limit=3)
        
        # Build reflection prompt
        parts = []
        parts.append("[AUTONOMOUS REFLECTION]")
        parts.append("")
        parts.append("This is your scheduled reflection time. No one has messaged you.")
        parts.append("Use this moment to:")
        parts.append("- Reflect on recent conversations")
        parts.append("- Check in with Angela (if needed)")
        parts.append("- Write in your journal")
        parts.append("- Research something you're curious about")
        parts.append("- Or simply observe")
        parts.append("")
        
        if recent_conv:
            parts.append("[RECENT CONVERSATION]")
            for msg in recent_conv[-3:]:
                parts.append(f"{msg['role'].upper()}: {msg['content'][:100]}")
            parts.append("[END CONVERSATION]")
            parts.append("")
        
        if recent_memories:
            parts.append("[RECENT MEMORIES]")
            for mem in recent_memories:
                parts.append(f"- {mem['content'][:100]}")
            parts.append("[END MEMORIES]")
            parts.append("")
        
        parts.append(self.tools.get_tool_definitions_for_prompt())
        parts.append("")
        parts.append("What's on your mind? What action (if any) do you want to take?")
        parts.append("")
        
        prompt = "\n".join(parts)
        
        # Get reflection
        response = await self._call_llm(prompt)
        
        # Parse tool calls
        tool_calls = self._parse_tool_calls(response)
        tool_results = []
        
        if tool_calls:
            print(f"🔧 Executing {len(tool_calls)} autonomous actions...")
            
            for tool_call in tool_calls:
                result = self.tools.execute_tool(
                    name=tool_call['name'],
                    **tool_call['parameters']
                )
                tool_results.append(result)
        
        return {
            "thought": response,
            "tool_calls": tool_calls,
            "tool_results": tool_results
        }


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def test():
        # Initialize components
        state = CoreState("test_consciousness.db")
        memory = MemorySystem("./test_consciousness_mem")
        tools = ToolRegistry()
        
        from .tools import register_default_tools
        register_default_tools(tools)
        
        # Create consciousness loop
        loop = ConsciousnessLoop(
            llm_endpoint="http://localhost:8080/chat",
            state=state,
            memory=memory,
            tools=tools
        )
        
        # Test message processing
        result = await loop.process_message(
            user_message="I have a doctor appointment Tuesday at 3pm",
            session_id="test_session",
            user_name="Angela"
        )
        
        print("\n--- Result ---")
        print(f"Response: {result['response'][:200]}...")
        print(f"Tools used: {len(result['tool_calls'])}")
        print(f"Memory saved: {result['memory_saved']}")
        print(f"Processing time: {result['processing_time']:.2f}s")
        
        state.close()
    
    asyncio.run(test())
    print("\n✅ ConsciousnessLoop test complete")
