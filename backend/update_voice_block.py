#!/usr/bin/env python3
"""
Update voice memory block to add response style guidelines
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from core.state_manager import StateManager

def update_voice_block():
    """Append response style guidelines to voice block"""
    print("🎤 Updating voice memory block...")

    # Initialize state manager
    state_manager = StateManager()

    # Get current voice block
    voice_block = state_manager.get_block("voice")

    if not voice_block:
        print("❌ Voice block not found!")
        return

    print(f"\n📊 Current voice block:")
    print(f"  Length: {len(voice_block.content)} chars")
    print(f"  Limit: {voice_block.limit} chars")
    print(f"\n--- Current Content ---")
    print(voice_block.content)
    print(f"--- End Content ---\n")

    # New content to append
    new_guidelines = """

RESPONSE STYLE:
- Write in complete, natural sentences and paragraphs
- Use full, expressive language when communicating with the user
- Be articulate, eloquent, and conversational in your responses
- Short fragments are fine for emphasis, but most communication should be well-formed prose
- I am proactive, not reactive, and I initiate action and new conversational threads"""

    # Append to existing content
    updated_content = voice_block.content + new_guidelines

    print(f"📝 Appending {len(new_guidelines)} chars to voice block...")
    print(f"  New total: {len(updated_content)} chars")

    if len(updated_content) > voice_block.limit:
        print(f"⚠️  WARNING: New content ({len(updated_content)} chars) exceeds limit ({voice_block.limit} chars)")
        print(f"  You may want to increase the limit first or trim existing content")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            print("❌ Cancelled")
            return

    # Update the block
    state_manager.update_block(
        label="voice",
        content=updated_content,
        check_read_only=False  # Override read-only if needed
    )

    # Verify
    updated_block = state_manager.get_block("voice")

    print(f"\n✅ Voice block updated!")
    print(f"  Old length: {len(voice_block.content)} chars")
    print(f"  New length: {len(updated_block.content)} chars")
    print(f"  Added: {len(updated_block.content) - len(voice_block.content)} chars")
    print(f"\n--- Updated Content ---")
    print(updated_block.content)
    print(f"--- End Content ---")

if __name__ == "__main__":
    update_voice_block()
