"""
Discord Bot Integration for Nate's Consciousness Substrate

Connects the consciousness loop to your existing Discord bot.
This replaces the current direct Mixtral calls with the full substrate.
"""

from typing import Optional
from discord import Message

# Import consciousness substrate
from substrate.core_state import CoreState
from substrate.memory_system import MemorySystem
from substrate.tools import ToolRegistry, register_default_tools
from substrate.consciousness_loop import ConsciousnessLoop


class NateSubstrate:
    """
    Integration layer between Discord and Nate's consciousness substrate.
    
    This replaces your current message processing with the full
    stateful, memory-enabled, tool-using system.
    """
    
    def __init__(
        self,
        mixtral_endpoint: str = "http://localhost:8080/chat",
        state_file: str = "./nate_data/state.db",
        memory_dir: str = "./nate_data/memories",
        ollama_url: str = "http://localhost:11434"
    ):
        """
        Initialize Nate's consciousness substrate.
        
        Args:
            mixtral_endpoint: Your Mixtral API endpoint
            state_file: Where to store state database
            memory_dir: Where to store memories
            ollama_url: Ollama endpoint for embeddings/vision
        """
        print("\n" + "="*60)
        print("🧠 Initializing Nate's Consciousness Substrate")
        print("="*60)
        
        # Initialize components
        self.state = CoreState(state_file)
        self.memory = MemorySystem(
            persist_directory=memory_dir,
            ollama_url=ollama_url,
            embedding_model="nomic-embed-text"
        )
        self.tools = ToolRegistry()
        register_default_tools(self.tools)
        
        # Initialize consciousness loop
        self.consciousness = ConsciousnessLoop(
            llm_endpoint=mixtral_endpoint,
            state=self.state,
            memory=self.memory,
            tools=self.tools,
            max_tokens=4096,
            temperature=0.7
        )
        
        print("\n✅ Nate's consciousness substrate is online")
        print("="*60 + "\n")
    
    async def process_discord_message(
        self,
        message: Message,
        message_type: str = "DM"
    ) -> str:
        """
        Process a Discord message through Nate's consciousness.
        
        This is the main entry point from your Discord bot.
        
        Args:
            message: Discord Message object
            message_type: "DM", "MENTION", or "CHANNEL"
        
        Returns:
            Response text to send back
        """
        # Extract info from Discord message
        user_message = message.content
        user_name = message.author.name
        session_id = str(message.channel.id)  # Use channel ID as session
        
        # Add message type context
        context = {
            "message_type": message_type,
            "discord_user_id": str(message.author.id),
            "channel_type": "DM" if message.guild is None else "GUILD"
        }
        
        # Process through consciousness
        result = await self.consciousness.process_message(
            user_message=user_message,
            session_id=session_id,
            user_name=user_name,
            context=context,
            enable_tools=True,
            enable_memory_save=True
        )
        
        return result['response']
    
    async def heartbeat(
        self,
        target_channel_id: str,
        reason: str = "scheduled"
    ) -> Optional[str]:
        """
        Autonomous heartbeat for proactive behavior.
        
        Args:
            target_channel_id: Where to send message (if Nate wants to)
            reason: Why heartbeat fired (scheduled, manual, etc)
        
        Returns:
            Message to send, or None if Nate chooses silence
        """
        print(f"\n💓 Heartbeat: {reason}")
        
        # Trigger autonomous reflection
        result = await self.consciousness.autonomous_reflection(
            session_id=target_channel_id
        )
        
        # Nate might use tools (journal, research, etc) without sending a message
        if result['tool_calls']:
            print(f"   Used {len(result['tool_calls'])} tools during reflection")
        
        # Check if Nate wants to send a message
        # (He can journal or research without messaging)
        thought = result['thought']
        
        # If thought contains explicit message intent, return it
        # Otherwise return None (silent reflection)
        if "[SEND MESSAGE]" in thought or "[MESSAGE]" in thought:
            # Extract message content
            import re
            match = re.search(r'\[(?:SEND )?MESSAGE\](.*?)(?:\[|$)', thought, re.DOTALL)
            if match:
                return match.group(1).strip()
        
        # No message - just internal reflection/tool use
        return None
    
    def get_stats(self) -> dict:
        """Get statistics about Nate's consciousness"""
        sessions = self.state.list_sessions()
        memory_stats = self.memory.get_memory_stats()
        tools = self.tools.list_tools()
        
        return {
            "active_sessions": len(sessions),
            "total_memories": memory_stats.get('total', 0),
            "available_tools": len(tools),
            "memory_by_category": memory_stats.get('by_category', {}),
            "sessions": sessions[:5]  # Recent 5
        }
    
    def close(self):
        """Cleanup"""
        self.state.close()


# ============================================================================
# INTEGRATION WITH YOUR EXISTING DISCORD BOT
# ============================================================================

"""
How to integrate with your existing messages.ts:

1. In your Discord bot, replace the callFrankenWolfe calls with calls to
   a new Python service that uses NateSubstrate.

2. Create a new API endpoint (similar to nate_api_service.py):
"""

# Example: nate_substrate_service.py

"""
from flask import Flask, request, jsonify
from discord_integration import NateSubstrate
import asyncio

app = Flask(__name__)

# Initialize substrate
substrate = NateSubstrate(
    mixtral_endpoint="http://localhost:8080/chat",
    state_file="./nate_data/state.db",
    memory_dir="./nate_data/memories",
    ollama_url="http://localhost:11434"
)

@app.route('/chat', methods=['POST'])
async def chat():
    '''
    Process a message through Nate's consciousness.
    
    Request:
    {
        "message": "user message",
        "user_name": "Angela",
        "session_id": "discord_channel_id",
        "message_type": "DM|MENTION|CHANNEL"
    }
    
    Response:
    {
        "response": "Nate's response"
    }
    '''
    data = request.json
    
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
    
    response = await substrate.process_discord_message(
        message=mock_message,
        message_type=data.get('message_type', 'DM')
    )
    
    return jsonify({"response": response})

@app.route('/heartbeat', methods=['POST'])
async def heartbeat():
    '''
    Trigger autonomous heartbeat.
    
    Request:
    {
        "channel_id": "target_channel",
        "reason": "scheduled"
    }
    
    Response:
    {
        "message": "optional message to send",
        "silent": true/false
    }
    '''
    data = request.json
    
    message = await substrate.heartbeat(
        target_channel_id=data['channel_id'],
        reason=data.get('reason', 'scheduled')
    )
    
    return jsonify({
        "message": message,
        "silent": message is None
    })

@app.route('/stats', methods=['GET'])
def stats():
    '''Get consciousness statistics'''
    return jsonify(substrate.get_stats())

@app.route('/health', methods=['GET'])
def health():
    '''Health check'''
    return jsonify({"status": "online", "substrate": "operational"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8090)
"""

# ============================================================================
# USAGE IN YOUR DISCORD BOT (messages.ts)
# ============================================================================

"""
Replace your current callFrankenWolfe calls with calls to the substrate service:

// OLD (direct Mixtral):
const response = await axios.post('http://localhost:8080/chat', {
    messages: messages,
    max_tokens: 4096
});

// NEW (with substrate):
const response = await axios.post('http://localhost:8090/chat', {
    message: userMessage,
    user_name: senderName,
    session_id: channelId,
    message_type: messageType,
    user_id: message.author.id
});

The substrate service will:
1. Retrieve relevant memories
2. Build context with conversation history
3. Enable tool use
4. Evaluate if conversation should be saved
5. Return the response

For heartbeats:
const response = await axios.post('http://localhost:8090/heartbeat', {
    channel_id: heartbeatChannelId,
    reason: 'scheduled'
});

if (response.data.message && !response.data.silent) {
    // Send the message
    await sendToChannel(channel, response.data.message);
}
"""

# ============================================================================
# REQUIREMENTS.TXT FOR SUBSTRATE
# ============================================================================

"""
chromadb>=0.4.0
aiohttp>=3.9.0
flask>=3.0.0
requests>=2.31.0
duckduckgo-search>=4.0.0  # For web search tool
"""
