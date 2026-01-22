#!/usr/bin/env python3
"""
Fix agent max_tokens configuration
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from core.state_manager import StateManager

def fix_max_tokens():
    """Set proper max_tokens in agent config"""
    print("🔧 Fixing max_tokens configuration...")

    # Initialize state manager
    state_manager = StateManager()

    # Get current agent state
    agent_state = state_manager.get_agent_state()
    config = agent_state.get('config', {})

    print(f"\n📊 Current Config:")
    print(f"  Model: {config.get('model', 'N/A')}")
    print(f"  Temperature: {config.get('temperature', 'N/A')}")
    print(f"  Max Tokens: {config.get('max_tokens', 'N/A')}")

    # Update max_tokens to 8192 for full, detailed responses
    config['max_tokens'] = 8192

    # Update agent state
    agent_state['config'] = config
    state_manager.update_agent_state(agent_state)

    # Verify
    updated_state = state_manager.get_agent_state()
    updated_config = updated_state.get('config', {})

    print(f"\n✅ Updated Config:")
    print(f"  Model: {updated_config.get('model', 'N/A')}")
    print(f"  Temperature: {updated_config.get('temperature', 'N/A')}")
    print(f"  Max Tokens: {updated_config.get('max_tokens', 'N/A')}")

    print("\n✅ Agent can now send full, detailed responses!")
    print(f"   Maximum response length: ~6000-7000 words")

if __name__ == "__main__":
    fix_max_tokens()
