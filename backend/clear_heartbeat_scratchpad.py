#!/usr/bin/env python3
"""
Clear and update heartbeat_scratchpad memory block
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from core.state_manager import StateManager

def clear_heartbeat_scratchpad():
    """Clear heartbeat scratchpad and add simple instructions"""
    print("🧹 Clearing heartbeat_scratchpad...")

    # Initialize state manager
    state_manager = StateManager()

    # New simple content for the scratchpad
    new_content = """Use this space to:
- Note what you did during your heartbeat that you want to share
- Track things you want to do during future heartbeats
- Keep brief notes for yourself

Keep it simple and clear."""

    try:
        # Get current scratchpad content to show before/after
        current_block = state_manager.get_block('heartbeat_scratchpad')
        if current_block:
            print(f"\n📝 Current content ({len(current_block.content)} chars):")
            print(f"--- BEGIN ---")
            print(current_block.content[:200] + ("..." if len(current_block.content) > 200 else ""))
            print(f"--- END ---\n")

        # Update the block
        state_manager.update_block('heartbeat_scratchpad', new_content)

        # Verify the update
        updated_block = state_manager.get_block('heartbeat_scratchpad')
        print(f"✅ Updated heartbeat_scratchpad!")
        print(f"\n📝 New content ({len(updated_block.content)} chars):")
        print(f"--- BEGIN ---")
        print(updated_block.content)
        print(f"--- END ---\n")

    except Exception as e:
        print(f"❌ Error: {e}")
        print(f"\nℹ️  Note: The heartbeat_scratchpad block might not exist yet.")
        print(f"          Run setup_nate.py first to initialize the database.")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(clear_heartbeat_scratchpad())
