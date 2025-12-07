#!/usr/bin/env python3
"""
Configure Nate's Agent to use Grok API

This script updates the agent state to use Grok instead of OpenRouter.
Run this after initial setup or when switching to Grok.
"""

import os
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from core.state_manager import StateManager


def configure_grok_agent():
    """Configure agent to use Grok API with Nate's settings"""

    db_path = os.getenv("SQLITE_DB_PATH", "./data/db/substrate_state.db")

    print("⚡ Configuring Nate's Agent for Grok API")
    print("=" * 60)

    state_manager = StateManager(db_path=db_path)

    # Update agent state to use Grok
    state_manager.update_agent_state({
        'name': 'Nate Wolfe',
        'config': {
            'model': 'grok-4-1-fast-reasoning',
            'temperature': 0.7,
            'max_tokens': 4096,
            'context_window': 131072,  # Grok's 131K context
            'reasoning_enabled': True,
            'max_reasoning_tokens': None,
            'top_p': 1.0,
            'frequency_penalty': 0.0,
            'presence_penalty': 0.0,
        }
    })

    print("✅ Agent configured for Grok!")
    print()

    # Verify configuration
    agent_state = state_manager.get_agent_state()
    print("Agent Configuration:")
    print("-" * 60)
    print(f"Name: {agent_state.get('name')}")
    print(f"Model: {agent_state.get('model')}")
    print(f"Context Window: {agent_state.get('config', {}).get('context_window', 'N/A')} tokens")
    print(f"Max Tokens: {agent_state.get('config', {}).get('max_tokens', 'N/A')}")
    print(f"Temperature: {agent_state.get('config', {}).get('temperature', 'N/A')}")
    print(f"Reasoning: {agent_state.get('config', {}).get('reasoning_enabled', False)}")
    print()
    print("✅ Configuration complete!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        configure_grok_agent()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
