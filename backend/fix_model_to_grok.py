#!/usr/bin/env python3
"""
Fix agent model back to Grok
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from core.state_manager import StateManager

def fix_model_to_grok():
    """Set model back to Grok"""
    print("🔧 Fixing model configuration to use Grok...")

    # Initialize state manager
    state_manager = StateManager()

    # Get current agent state
    agent_state = state_manager.get_agent_state()
    config = agent_state.get('config', {})

    print(f"\n📊 Current Config:")
    print(f"  Model: {config.get('model', 'N/A')}")
    print(f"  Temperature: {config.get('temperature', 'N/A')}")
    print(f"  Max Tokens: {config.get('max_tokens', 'N/A')}")
    print(f"  Context Window: {config.get('context_window', 'N/A')}")

    # Update to Grok configuration
    config['model'] = 'grok-4-1-fast-reasoning'
    config['temperature'] = 0.7
    config['max_tokens'] = 8192  # Increased from 4096 for fuller responses
    config['context_window'] = 131072  # Grok's 131K context
    config['reasoning_enabled'] = True

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
    print(f"  Context Window: {updated_config.get('context_window', 'N/A')}")
    print(f"  Reasoning: {updated_config.get('reasoning_enabled', 'N/A')}")

    print("\n✅ Agent is now configured to use Grok with full responses!")

if __name__ == "__main__":
    fix_model_to_grok()
