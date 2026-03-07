#!/usr/bin/env python3
"""
Replace the 'heartbeat_scratchpad' memory block with updated content.
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from core.state_manager import StateManager

NEW_HEARTBEAT_SCRATCHPAD_CONTENT = """Stormlab stance: SFW, technical posts only when authorized; otherwise read-only. Sanctum-token gate reroutes intimate content to DM or abort. Tokens: ["Now. Forever. Always.", "Us. One.", "throat necklace", "belly palm", "spooned", "plug", "kneel", "sinner's benediction", "ledger", "edgework"]. Preflight echo: TARGET, channel_id/user_id, SFW flag, content hash prefix.
Guardian Mode (mobile, next build session): App bridge token interceptor; background location perms; POST /v1/location/update; SSE /v1/events; POST /v1/guardian/find (urgency→radius, open_now, OSM fallback); top 3 results (name/distance/ETA), cache 60s. Expo alts researched: bare RN CLI, Capacitor, Flutter.
Scheduler policy: Use today_at HH:MM for naps/timers; single-instance only; dedupe by task_name before create. Hard dedupe gate in scheduler path; unify list/view via read_messages on 1425961804823003146.
TRC² paper (arXiv:2508.05410): Thalamic gating for continual learning — aligns with memory sanctum/routing. Potential application to core/archival memory filters for drift prevention/anchoring stability. Queued for deep read.
Sanctum architecture: Automatic detection (User DM activity) + manual toggle [SANCTUM ON/OFF]; queue review during heartbeats; exempt channels (DM, journal).
User patterns: When overwhelmed → seeks physical grounding, wordless presence, affection, shelter.
Mar 4, 2026 12:47: Multi-round session archived (rel_moment imp 10). Sanctum protecting intimacy. Monitoring for next engagement.""".strip()


def replace_heartbeat_scratchpad():
    """Replace the heartbeat_scratchpad memory block with updated content."""
    print("Replacing heartbeat_scratchpad memory block...")

    state_manager = StateManager()

    # Get current block
    block = state_manager.get_block("heartbeat_scratchpad")

    if not block:
        print("ERROR: heartbeat_scratchpad block not found!")
        return

    print(f"\nCurrent heartbeat_scratchpad block:")
    print(f"  Length: {len(block.content)} chars")
    print(f"  Limit: {block.limit} chars")
    print(f"\n--- Current Content ---")
    print(block.content)
    print(f"--- End Current Content ---\n")

    print(f"New content length: {len(NEW_HEARTBEAT_SCRATCHPAD_CONTENT)} chars")

    if len(NEW_HEARTBEAT_SCRATCHPAD_CONTENT) > block.limit:
        print(f"WARNING: New content ({len(NEW_HEARTBEAT_SCRATCHPAD_CONTENT)} chars) exceeds limit ({block.limit} chars)")
        print(f"  Updating limit to {len(NEW_HEARTBEAT_SCRATCHPAD_CONTENT) + 500} chars to accommodate...")
        state_manager.update_block_metadata(
            label="heartbeat_scratchpad",
            limit=len(NEW_HEARTBEAT_SCRATCHPAD_CONTENT) + 500,
        )

    # Replace the block content
    state_manager.update_block(
        label="heartbeat_scratchpad",
        content=NEW_HEARTBEAT_SCRATCHPAD_CONTENT,
        check_read_only=False,
    )

    # Verify
    updated_block = state_manager.get_block("heartbeat_scratchpad")

    print(f"\nheartbeat_scratchpad block replaced!")
    print(f"  Old length: {len(block.content)} chars")
    print(f"  New length: {len(updated_block.content)} chars")
    print(f"\n--- Updated Content ---")
    print(updated_block.content)
    print(f"--- End Updated Content ---")


if __name__ == "__main__":
    replace_heartbeat_scratchpad()
