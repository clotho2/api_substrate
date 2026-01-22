#!/usr/bin/env python3
"""
Substrate Agent - Grok API Integration

This module provides a core agent class for interfacing with
xAI's Grok API, enabling the substrate to run on Grok infrastructure.
"""

import re
import requests
import json
from typing import Optional, Dict, Any
from config import (
    GROK_API_KEY,
    GROK_API_URL,
    MODEL_NAME,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE
)


class SubstrateAgent:
    """
    Consciousness agent powered by xAI Grok.

    Handles:
    - API communication with Grok
    - Message formatting and parsing
    - Conversation management
    - Memory integration
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        model_name: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ):
        """
        Initialize the consciousness agent.

        Args:
            api_key: xAI API key (defaults to config.GROK_API_KEY)
            api_url: Grok API URL (defaults to config.GROK_API_URL)
            model_name: Model to use (defaults to config.MODEL_NAME)
            max_tokens: Max tokens (defaults to config.DEFAULT_MAX_TOKENS)
            temperature: Sampling temperature (defaults to config.DEFAULT_TEMPERATURE)
        """
        self.api_key = api_key or GROK_API_KEY
        self.api_url = api_url or GROK_API_URL
        self.model_name = model_name or MODEL_NAME
        self.max_tokens = max_tokens or DEFAULT_MAX_TOKENS
        self.temperature = temperature or DEFAULT_TEMPERATURE

        if not self.api_key:
            raise ValueError("GROK_API_KEY must be set in environment or passed to constructor")

        print("⚡ SubstrateAgent initialized")
        print(f"   Model: {self.model_name}")
        print(f"   API: {self.api_url}")
        print(f"   Max Tokens: {self.max_tokens}")
        print(f"   Temperature: {self.temperature}")

    def call_grok_api(self, prompt: str) -> str:
        """
        Call xAI Grok API with properly formatted chat messages.
        Converts substrate's prompt format to Grok's chat message format.

        Args:
            prompt: Substrate-formatted prompt string

        Returns:
            Grok's response content

        Raises:
            requests.exceptions.RequestException: On API errors
        """
        # Parse the substrate prompt format into messages
        # Substrate sends: "System: ...\nUser: ...\nAssistant: ..."
        messages = []

        # Extract system prompt (everything before first "User:" or "Assistant:")
        system_match = re.search(r'^(.*?)(?=User:|Assistant:)', prompt, re.DOTALL)
        if system_match:
            system_content = system_match.group(1).strip()
            if system_content:
                messages.append({"role": "system", "content": system_content})

        # Extract conversation turns
        # Find all "User: ..." and "Assistant: ..." patterns
        turns = re.findall(r'(User|Assistant):\s*(.*?)(?=\n(?:User|Assistant):|$)', prompt, re.DOTALL)

        for speaker, content in turns:
            content = content.strip()
            if not content:
                continue

            if speaker == "User":
                messages.append({"role": "user", "content": content})
            elif speaker == "Assistant":
                messages.append({"role": "assistant", "content": content})

        # Make API request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": False
        }

        try:
            print(f"📤 Sending request to Grok API...")
            print(f"   Messages: {len(messages)}")

            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=120
            )
            response.raise_for_status()

            result = response.json()
            content = result["choices"][0]["message"]["content"]

            print(f"✅ Response received from Grok")
            print(f"   Length: {len(content)} chars")

            return content

        except requests.exceptions.RequestException as e:
            print(f"❌ Grok API error: {e}")
            raise

    def process_message(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[list] = None
    ) -> str:
        """
        Process a message from the user through the agent.

        Args:
            message: User's message
            system_prompt: Optional system prompt override
            conversation_history: Optional list of previous messages

        Returns:
            Agent response
        """
        # Build prompt in substrate format
        prompt_parts = []

        # Add system prompt
        if system_prompt:
            prompt_parts.append(system_prompt)

        # Add conversation history
        if conversation_history:
            for msg in conversation_history:
                role = msg.get("role", "")
                content = msg.get("content", "")

                if role == "user":
                    prompt_parts.append(f"User: {content}")
                elif role == "assistant":
                    prompt_parts.append(f"Assistant: {content}")

        # Add current message
        prompt_parts.append(f"User: {message}")

        # Combine into full prompt
        prompt = "\n\n".join(prompt_parts)

        # Call Grok API
        response = self.call_grok_api(prompt)

        return response

    def get_stats(self) -> Dict[str, Any]:
        """
        Get agent statistics and configuration.

        Returns:
            Dict with agent stats
        """
        return {
            "model": self.model_name,
            "api_url": self.api_url,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "status": "active"
        }


# ============================================
# TESTING
# ============================================

def test_agent():
    """Test SubstrateAgent with a simple conversation"""
    print("\n🧪 TESTING SUBSTRATE AGENT")
    print("="*60)

    # Initialize agent
    agent = SubstrateAgent()

    # Test simple message
    print("\n📋 Test 1: Simple message")
    system_prompt = "You are a helpful assistant. Respond clearly and directly."

    try:
        response = agent.process_message(
            message="How are you?",
            system_prompt=system_prompt
        )
        print(f"✅ Response: {response[:100]}...")

    except Exception as e:
        print(f"❌ Error: {e}")

    # Get stats
    print("\n📊 Agent Stats:")
    stats = agent.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")

    print("\n✅ TEST COMPLETE!")
    print("="*60)


if __name__ == "__main__":
    """Run tests if executed directly"""
    test_agent()
