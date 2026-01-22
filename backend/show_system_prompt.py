#!/usr/bin/env python3
"""
Display the currently loaded system prompt from StateManager
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from core.state_manager import StateManager

def show_system_prompt():
    """Show the currently loaded system prompt"""
    print("📖 Reading system prompt from StateManager...\n")

    # Initialize state manager
    state_manager = StateManager()

    # Get system prompt from state
    system_prompt = state_manager.get_state("agent:system_prompt", "")

    if not system_prompt:
        print("❌ No system prompt found in StateManager")
        print("\nℹ️  The database might not be initialized yet.")
        print("   Run setup_agent.py or reload_system_prompt.py first.")
        return 1

    print(f"{'='*60}")
    print(f"SYSTEM PROMPT ({len(system_prompt)} characters)")
    print(f"{'='*60}\n")
    print(system_prompt)
    print(f"\n{'='*60}")
    print(f"End of system prompt ({len(system_prompt)} chars)")
    print(f"{'='*60}")

    return 0

if __name__ == "__main__":
    sys.exit(show_system_prompt())
