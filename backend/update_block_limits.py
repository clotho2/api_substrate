#!/usr/bin/env python3
"""
Update memory block size limits from 2000 to 5000 chars
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from core.state_manager import StateManager

def update_block_limits(new_limit: int = 5000):
    """Update all editable memory blocks to new limit"""
    print(f"🔄 Updating memory block limits to {new_limit} chars...")

    # Initialize state manager
    state_manager = StateManager()

    # Get all blocks
    blocks = state_manager.list_blocks(include_hidden=False)

    updated_count = 0
    skipped_count = 0

    for block in blocks:
        # Skip system blocks with small limits (those are intentionally small)
        if block.label in ["persona", "human", "relationship"] and block.limit <= 500:
            print(f"   ⏭️  Skipping '{block.label}' (system block, keeping limit={block.limit})")
            skipped_count += 1
            continue

        # Skip blocks that already have the new limit or higher
        if block.limit >= new_limit:
            print(f"   ✓ '{block.label}' already has limit={block.limit}")
            skipped_count += 1
            continue

        # Update the block limit
        old_limit = block.limit

        # Update directly in database using proper connection method
        with state_manager._get_connection() as conn:
            conn.execute(
                """
                UPDATE memory_blocks
                SET "limit" = ?
                WHERE label = ?
                """,
                (new_limit, block.label)
            )

        print(f"   ✅ Updated '{block.label}': {old_limit} → {new_limit} chars")
        updated_count += 1

    print(f"\n✅ Complete!")
    print(f"   Updated: {updated_count} blocks")
    print(f"   Skipped: {skipped_count} blocks")

    # Verify
    print(f"\n📊 Current block limits:")
    blocks = state_manager.list_blocks(include_hidden=False)
    for block in blocks:
        usage = len(block.content)
        pct = int((usage / block.limit) * 100) if block.limit > 0 else 0
        status = "⚠️" if pct > 80 else "✓"
        print(f"   {status} {block.label}: {usage}/{block.limit} chars ({pct}%)")

if __name__ == "__main__":
    update_block_limits()
