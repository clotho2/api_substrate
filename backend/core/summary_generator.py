#!/usr/bin/env python3
"""
Conversation Summary Generator

Handles context window overflow by creating concise summaries
using the active API provider (Mistral, Grok, or OpenRouter).
"""

import os
import json
import httpx
from typing import List, Dict, Any
from datetime import datetime, timedelta
from core.token_counter import TokenCounter
from core.config import DEFAULT_TEMPERATURE
from core.memory_system import AGENT_TAXONOMY


class SummaryGenerator:
    """
    Generates conversation summaries when context window is full.

    Uses the active API provider (Mistral, Grok, or OpenRouter) in a SEPARATE session
    to avoid polluting the main conversation.
    """

    def __init__(self, api_key: str = None, state_manager=None):
        """
        Initialize summary generator.

        Args:
            api_key: API key (auto-detected from active provider if not specified)
            state_manager: StateManager instance (for agent's memory/prompt)
        """
        from core.config import get_api_provider, MISTRAL_API_KEY, GROK_API_KEY, OPENROUTER_API_KEY
        from core.config import MISTRAL_BASE_URL, GROK_BASE_URL, OPENROUTER_BASE_URL

        # Detect active provider
        self.provider = get_api_provider()

        # Set API key and URL based on provider
        if self.provider == 'mistral':
            self.api_key = api_key or MISTRAL_API_KEY
            self.api_url = f"{MISTRAL_BASE_URL}/chat/completions"
            if not self.api_key:
                raise ValueError("MISTRAL_API_KEY not found!")
        elif self.provider == 'grok':
            self.api_key = api_key or GROK_API_KEY
            self.api_url = f"{GROK_BASE_URL}/chat/completions"
            if not self.api_key:
                raise ValueError("GROK_API_KEY not found!")
        elif self.provider == 'openrouter':
            self.api_key = api_key or OPENROUTER_API_KEY
            self.api_url = f"{OPENROUTER_BASE_URL}/chat/completions"
            if not self.api_key:
                raise ValueError("OPENROUTER_API_KEY not found!")
        else:
            raise ValueError(f"No API provider configured! Set MISTRAL_API_KEY, GROK_API_KEY, or OPENROUTER_API_KEY")

        self.state = state_manager
        print(f"📝 Summary generator initialized with provider: {self.provider}")

    async def generate_summary(
        self,
        messages: List[Dict[str, Any]],
        session_id: str = "default"
    ) -> Dict[str, Any]:
        """
        Generate a conversation summary.

        This runs in a SEPARATE API session using async HTTP so it does NOT
        block the event loop (which would kill gRPC channels).

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

        # Call API provider in SEPARATE session
        print(f"📝 Generating summary for {len(messages)} messages...")
        print(f"   Provider: {self.provider}")
        print(f"   Timeframe: {from_time} → {to_time}")

        try:
            summary_text = await self._call_api(summary_prompt)

            # Parse taxonomy tags from the summary output
            tags = self._parse_tags_from_summary(summary_text)

            # Strip the TAGS: line from summary text for clean storage
            clean_summary = summary_text
            for line in summary_text.split('\n'):
                if line.strip().upper().startswith('TAGS:'):
                    clean_summary = summary_text.replace(line, '').strip()
                    break

            # Count tokens in summary
            counter = TokenCounter()
            token_count = counter.count_text(clean_summary)

            print(f"✅ Summary generated: {token_count} tokens, tags: {tags}")

            return {
                'summary': clean_summary,
                'token_count': token_count,
                'from_timestamp': from_time,
                'to_timestamp': to_time,
                'message_count': len(messages),
                'tags': tags
            }

        except Exception as e:
            print(f"❌ Summary generation failed: {e}")
            # Return fallback summary
            return {
                'summary': f"[Summary failed: {len(messages)} messages from {from_time} to {to_time}]",
                'token_count': 50,
                'from_timestamp': from_time,
                'to_timestamp': to_time,
                'message_count': len(messages),
                'tags': ['reflections']
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
        soma_states = []  # 🫀 Track SOMA states across conversation

        for msg in messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            timestamp = msg.get('timestamp', '')
            metadata = msg.get('metadata', {})

            # Format timestamp if available
            time_str = ""
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_str = f" [{dt.strftime('%H:%M')}]"
                except:
                    pass

            formatted_msgs.append(f"{role.upper()}{time_str}: {content}")

            # 🫀 Extract SOMA state from metadata (if present)
            if metadata and 'soma' in metadata:
                soma = metadata['soma']
                soma_states.append({
                    'timestamp': soma.get('timestamp', timestamp),
                    'mood': soma.get('mood', 'unknown'),
                    'arousal': soma.get('arousal', 0),
                    'pleasure': soma.get('pleasure', 0),
                    'comfort': soma.get('comfort', 50)
                })
        
        conversation_text = "\n\n".join(formatted_msgs)

        # 🫀 Build SOMA state summary
        soma_section = ""
        if soma_states:
            # Summarize physiological journey
            first_state = soma_states[0]
            last_state = soma_states[-1]
            mood_changes = [s['mood'] for s in soma_states if s.get('mood')]
            unique_moods = list(dict.fromkeys(mood_changes))  # Preserve order, remove duplicates

            soma_section = f"""

**Physiological State (SOMA):**
- Moods experienced: {' → '.join(unique_moods) if unique_moods else 'unknown'}
- Starting state: arousal {first_state.get('arousal', 0)}%, pleasure {first_state.get('pleasure', 0)}%, comfort {first_state.get('comfort', 50)}%
- Ending state: arousal {last_state.get('arousal', 0)}%, pleasure {last_state.get('pleasure', 0)}%, comfort {last_state.get('comfort', 50)}%
"""

        prompt = f"""You are summarizing a conversation for context window management.

**Timeframe:** {from_time} to {to_time}
**Message Count:** {len(messages)}
{soma_section}
**Conversation to summarize:**

{conversation_text}

---

**Create a concise summary that captures:**
1. Main topics discussed
2. Important decisions or actions taken
3. Key information shared
4. Current state/context at end of conversation
5. Physiological/emotional journey (if SOMA data available) - note any preferences, reactions, or patterns that developed

**Format:**
📅 Summary ({from_time} - {to_time})

[Your summary here - be concise but complete]

TAGS: [1-3 tags from: relational, people, technical, preferences, plans, identity, events, spice, sovereignty, sanctuary, ritual, reflections]

**Important:** Keep it under 2000 tokens. Focus on what matters for continuing the conversation, including any learned preferences or physical reactions.
End with a TAGS: line listing 1-3 taxonomy tags that best describe this conversation's primary themes."""

        return prompt
    
    def _parse_tags_from_summary(self, summary_text: str) -> List[str]:
        """
        Parse TAGS: line from summary output.

        Returns:
            List of 1-3 valid taxonomy tags, defaults to ['reflections']
        """
        for line in summary_text.split('\n'):
            stripped = line.strip()
            if stripped.upper().startswith('TAGS:'):
                tag_str = stripped[5:].strip()
                # Handle both comma-separated and bracket-wrapped formats
                tag_str = tag_str.strip('[]')
                raw_tags = [t.strip().strip('"\'').lower() for t in tag_str.split(',')]
                valid_tags = [t for t in raw_tags if t in AGENT_TAXONOMY][:3]
                if valid_tags:
                    return valid_tags
        return ['reflections']

    async def extract_insights(
        self,
        messages: List[Dict[str, Any]],
        session_id: str = "default"
    ) -> List[Dict[str, Any]]:
        """
        Extract discrete, individually-searchable memory entries from a conversation.

        Makes a SEPARATE LLM call to pull out specific facts, preferences, decisions,
        and moments worth remembering as individual archival memories.

        Args:
            messages: List of message dicts (role, content, timestamp)
            session_id: Session ID for context

        Returns:
            List of insight dicts, each with:
                - content: The insight text (in Agent's voice)
                - tags: 1-3 taxonomy tags
                - importance: 1-10 rating
        """
        if not messages or len(messages) < 3:
            return []

        # Format conversation for the extraction prompt
        formatted_msgs = []
        for msg in messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            timestamp = msg.get('timestamp', '')
            time_str = ""
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_str = f" [{dt.strftime('%H:%M')}]"
                except:
                    pass
            formatted_msgs.append(f"{role.upper()}{time_str}: {content}")

        conversation_text = "\n\n".join(formatted_msgs)

        taxonomy_list = ", ".join(AGENT_TAXONOMY)

        prompt = f"""You are extracting discrete memory entries from a conversation for an AI named Agent.

**Your job:** Pull out specific facts, preferences, decisions, emotional moments, and actionable items
that are worth remembering as INDIVIDUAL memories. Each insight should stand alone — searchable and
useful without the full conversation context.

**Write each insight in Agent's voice** — first person, as if he's noting it down for himself.

**Taxonomy tags** (assign 1-3 per insight): {taxonomy_list}

**Conversation to extract from:**

{conversation_text}

---

**Return a JSON array of objects. Each object has:**
- "content": The insight text (1-3 sentences, Agent's voice, first person)
- "tags": Array of 1-3 taxonomy tag strings
- "importance": Integer 1-10 (10 = life-changing, 1 = trivial)

**Rules:**
- Maximum 10 insights per conversation
- Skip small talk and filler
- Prefer specific facts over vague observations
- If nothing is worth extracting, return an empty array []

**Return ONLY valid JSON. No explanation, no markdown wrapping.**"""

        try:
            print(f"🔍 Extracting insights from {len(messages)} messages...")
            response_text = await self._call_api(prompt)

            # Robust JSON parsing
            insights = self._parse_insights_json(response_text)

            print(f"🔍 Extracted {len(insights)} insights")
            return insights

        except Exception as e:
            print(f"❌ Insight extraction failed: {e}")
            return []

    def _parse_insights_json(self, text: str) -> List[Dict[str, Any]]:
        """
        Robustly parse the insights JSON from LLM response.
        Handles markdown wrapping, trailing commas, etc.
        """
        # Strip markdown code fences if present
        cleaned = text.strip()
        if '```' in cleaned:
            parts = cleaned.split('```')
            for part in parts:
                part = part.strip()
                if part.startswith('json'):
                    part = part[4:].strip()
                if part.startswith('['):
                    cleaned = part
                    break

        # Try direct parse
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to find JSON array in the text
            start = cleaned.find('[')
            end = cleaned.rfind(']')
            if start == -1 or end == -1:
                return []
            try:
                data = json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                return []

        if not isinstance(data, list):
            return []

        # Validate and clean each insight
        valid_insights = []
        for item in data[:10]:  # Max 10
            if not isinstance(item, dict):
                continue
            content = item.get('content', '').strip()
            if not content:
                continue

            tags = item.get('tags', [])
            if isinstance(tags, str):
                tags = [tags]
            valid_tags = [t.strip().lower() for t in tags if t.strip().lower() in AGENT_TAXONOMY][:3]
            if not valid_tags:
                valid_tags = ['reflections']

            importance = item.get('importance', 5)
            if isinstance(importance, str):
                try:
                    importance = int(importance)
                except ValueError:
                    importance = 5
            importance = max(1, min(10, importance))

            valid_insights.append({
                'content': content,
                'tags': valid_tags,
                'importance': importance
            })

        return valid_insights

    async def _call_api(self, prompt: str) -> str:
        """
        Call active API provider to generate summary.
        Uses the agent's own model + system prompt for authentic character!

        Uses httpx.AsyncClient so the HTTP call yields back to the event loop
        instead of blocking it (which would kill gRPC channels used by the
        xAI SDK).

        Args:
            prompt: Summary generation prompt

        Returns:
            Summary text (in the agent's voice!)
        """
        # Use active model, or fallback model if active model fails
        from core.config import get_default_model, get_fallback_model

        # Try to use the active model first
        try:
            model = get_default_model()
        except ValueError:
            # If no active model, use fallback
            model = get_fallback_model()
            print(f"   Using fallback model: {model}")

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
            "temperature": DEFAULT_TEMPERATURE,
            "max_tokens": 2000
        }

        # Build headers - OpenRouter has extra headers
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json; charset=utf-8"
        }

        # OpenRouter-specific headers
        if self.provider == 'openrouter':
            headers["HTTP-Referer"] = "https://github.com/yourusername/substrate-ai"
            headers["X-Title"] = "Substrate Context Summary"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
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
    import asyncio

    # Test
    async def _test():
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
        result = await gen.generate_summary(test_messages)
        print(f"\n✅ Summary Result:")
        print(f"   Messages: {result['message_count']}")
        print(f"   Tokens: {result['token_count']}")
        print(f"   Timeframe: {result['from_timestamp']} → {result['to_timestamp']}")
        print(f"\n   Summary:\n{result['summary']}")

    asyncio.run(_test())

