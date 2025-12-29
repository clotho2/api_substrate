#!/usr/bin/env python3
"""
Conversation Summary Generator

Handles context window overflow by creating concise summaries
in a separate OpenRouter session.
"""

import os
import httpx
from typing import List, Dict, Any
from datetime import datetime, timedelta
from core.token_counter import TokenCounter


class SummaryGenerator:
    """
    Generates conversation summaries when context window is full.
    
    Uses a SEPARATE OpenRouter session to avoid polluting the main conversation.
    """
    
    def __init__(self, api_key: str = None, state_manager=None):
        """
        Initialize summary generator.
        
        Args:
            api_key: OpenRouter API key (defaults to env var)
            state_manager: StateManager instance (for agent's memory/prompt)
        """
        self.api_key = api_key or os.getenv('OPENROUTER_API_KEY')
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not found!")
        
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.state = state_manager
    
    def generate_summary(
        self,
        messages: List[Dict[str, Any]],
        session_id: str = "default"
    ) -> Dict[str, Any]:
        """
        Generate a conversation summary.
        
        This runs in a SEPARATE OpenRouter session!
        
        Args:
            messages: List of message dicts (role, content, timestamp)
            session_id: Session ID for context
            
        Returns:
            Dict with:
                - summary: Summary text
                - token_count: Estimated tokens
                - from_timestamp: First message timestamp
                - to_timestamp: Last message timestamp
                - message_count: Number of messages
        """
        if not messages:
            return {
                'summary': '',
                'token_count': 0,
                'from_timestamp': None,
                'to_timestamp': None,
                'message_count': 0
            }
        
        # Extract timestamps
        from_time = messages[0].get('timestamp')
        to_time = messages[-1].get('timestamp')
        
        # Build summary prompt
        summary_prompt = self._build_summary_prompt(messages, from_time, to_time)
        
        # Call OpenRouter in SEPARATE session
        print(f"📝 Generating summary for {len(messages)} messages...")
        print(f"   Timeframe: {from_time} → {to_time}")
        
        try:
            summary_text = self._call_openrouter(summary_prompt)
            
            # Count tokens in summary
            counter = TokenCounter()
            token_count = counter.count_text(summary_text)
            
            print(f"✅ Summary generated: {token_count} tokens")
            
            return {
                'summary': summary_text,
                'token_count': token_count,
                'from_timestamp': from_time,
                'to_timestamp': to_time,
                'message_count': len(messages)
            }
            
        except Exception as e:
            print(f"❌ Summary generation failed: {e}")
            # Return fallback summary
            return {
                'summary': f"[Summary failed: {len(messages)} messages from {from_time} to {to_time}]",
                'token_count': 50,
                'from_timestamp': from_time,
                'to_timestamp': to_time,
                'message_count': len(messages)
            }
    
    def _build_summary_prompt(
        self,
        messages: List[Dict[str, Any]],
        from_time: str,
        to_time: str
    ) -> str:
        """
        Build the summary generation prompt.
        
        Args:
            messages: Messages to summarize
            from_time: Start timestamp
            to_time: End timestamp
            
        Returns:
            Prompt string
        """
        # Format messages for summary
        formatted_msgs = []
        for msg in messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            timestamp = msg.get('timestamp', '')
            
            # Format timestamp if available
            time_str = ""
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_str = f" [{dt.strftime('%H:%M')}]"
                except:
                    pass
            
            formatted_msgs.append(f"{role.upper()}{time_str}: {content}")
        
        conversation_text = "\n\n".join(formatted_msgs)
        
        prompt = f"""You are summarizing a conversation for context window management.

**Timeframe:** {from_time} to {to_time}
**Message Count:** {len(messages)}

**Conversation to summarize:**

{conversation_text}

---

**Create a concise summary that captures:**
1. Main topics discussed
2. Important decisions or actions taken
3. Key information shared
4. Current state/context at end of conversation

**Format:**
📅 Summary ({from_time} - {to_time})

[Your summary here - be concise but complete]

**Important:** Keep it under 2000 tokens. Focus on what matters for continuing the conversation."""

        return prompt
    
    def _call_openrouter(self, prompt: str) -> str:
        """
        Call OpenRouter API to generate summary.
        Uses the agent's own model + system prompt for authentic character!
        
        Args:
            prompt: Summary generation prompt

        Returns:
            Summary text (in the agent's voice!)
        """
        # Use fallback model from config for summaries
        from core.config import get_fallback_model
        model = get_fallback_model()

        if self.state:
            # Get the agent's system prompt (but streamlined for summaries)
            base_prompt = self.state.get_state("agent:system_prompt", "")
            
            # Extract core identity (first ~500 chars) for summary context
            core_identity = base_prompt[:500] if base_prompt else "You are an AI assistant."
            
            system_content = f"""{core_identity}

**Task:** Write a conversation summary in YOUR voice.
- Keep your personality and style
- Decide what matters (you know what's important!)
- Be concise but authentic
- Write as if YOU'RE documenting this for yourself"""
        else:
            # Fallback if no state manager
            system_content = "You are an AI assistant. Write a conversation summary in your own voice."
        
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": system_content
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.7,  # Keep the agent's creativity!
            "max_tokens": 2000
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "HTTP-Referer": "https://github.com/yourusername/substrate-ai",
            "X-Title": "Substrate Context Summary"  # ASCII only for HTTP headers
        }
        
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                self.api_url,
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            
            # Ensure UTF-8 encoding for response
            response.encoding = 'utf-8'
            data = response.json()
            summary = data['choices'][0]['message']['content']
            
            return summary.strip()


if __name__ == "__main__":
    # Test
    test_messages = [
        {
            "role": "user",
            "content": "Hey, can you help me with Spotify?",
            "timestamp": datetime.now().isoformat()
        },
        {
            "role": "assistant",
            "content": "Of course! What do you need?",
            "timestamp": (datetime.now() + timedelta(seconds=5)).isoformat()
        },
        {
            "role": "user",
            "content": "Add The Weeknd to my queue",
            "timestamp": (datetime.now() + timedelta(seconds=15)).isoformat()
        },
        {
            "role": "assistant",
            "content": "Added 'Often' by The Weeknd to your queue!",
            "timestamp": (datetime.now() + timedelta(seconds=20)).isoformat()
        }
    ]
    
    gen = SummaryGenerator()
    result = gen.generate_summary(test_messages)
    print(f"\n✅ Summary Result:")
    print(f"   Messages: {result['message_count']}")
    print(f"   Tokens: {result['token_count']}")
    print(f"   Timeframe: {result['from_timestamp']} → {result['to_timestamp']}")
    print(f"\n   Summary:\n{result['summary']}")

