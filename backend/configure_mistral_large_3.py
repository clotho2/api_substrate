#!/usr/bin/env python3
"""
Configure agent to use Mistral Large 3 via OpenRouter

Mistral Large 3 (2512) - Latest frontier model from Mistral AI
- 41B active parameters (675B total with MoE)
- 256K context window
- Native function calling support
- Multimodal capabilities
- NOT a reasoning model (optimized for System 1 fast pattern matching)
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from core.state_manager import StateManager

def configure_mistral_large_3():
    """Configure agent to use Mistral Large 3"""
    print("🔧 Configuring Mistral Large 3 via OpenRouter...")
    print("📚 Model: mistralai/mistral-large (Mistral Large 3 - 2512)")

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
    print(f"  Reasoning: {config.get('reasoning_enabled', 'N/A')}")

    # Update to Mistral Large 3 configuration
    config['model'] = 'mistralai/mistral-large'  # OpenRouter model ID
    config['temperature'] = 0.7
    config['max_tokens'] = 8192  # Allow longer responses
    config['context_window'] = 256000  # 256K context window
    config['reasoning_enabled'] = False  # NOT a reasoning model
    config['max_reasoning_tokens'] = None  # Not applicable

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

    print(f"\n✅ Agent is now configured to use Mistral Large 3!")
    print(f"\n📝 Notes:")
    print(f"   • Mistral Large 3 has native function calling support")
    print(f"   • NOT a reasoning model (optimized for fast pattern matching)")
    print(f"   • 256K context window for long conversations")
    print(f"   • Multimodal capabilities (vision support)")
    print(f"\n💡 Make sure you have OPENROUTER_API_KEY set in your .env file!")

if __name__ == "__main__":
    configure_mistral_large_3()
