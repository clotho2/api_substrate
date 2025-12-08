#!/usr/bin/env python3
"""
Reload system prompt from file into state manager
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from core.state_manager import StateManager

def reload_system_prompt():
    """Reload system prompt from file"""
    print("🔄 Reloading system prompt from file...")

    # Initialize state manager
    state_manager = StateManager()

    # Load system prompt from file
    system_prompt_path = Path(__file__).parent / "data" / "system_prompt.txt"

    if not system_prompt_path.exists():
        print(f"❌ System prompt file not found at: {system_prompt_path}")
        return False

    with open(system_prompt_path, 'r') as f:
        system_prompt = f.read()

    # Save to state manager
    state_manager.set_state("agent:system_prompt", system_prompt)

    # Verify
    verified = state_manager.get_state("agent:system_prompt", "")

    if len(verified) == len(system_prompt):
        print(f"✅ System prompt reloaded successfully: {len(system_prompt)} chars")
        return True
    else:
        print(f"❌ Verification failed!")
        print(f"   Expected: {len(system_prompt)} chars")
        print(f"   Got: {len(verified)} chars")
        return False

if __name__ == "__main__":
    reload_system_prompt()
