#!/usr/bin/env python3
"""
Clear heartbeat messages from conversation history while preserving normal messages.

Deletes:
  - Heartbeat prompts (message_type='system', role='system')
  - Assistant responses to heartbeats:
    - New responses: tagged with message_type='system' (after the consciousness_loop fix)
    - Legacy responses: identified by being the next assistant message after a heartbeat prompt
      with no user message in between (for old data saved before the fix)

Preserves:
  - All normal user/assistant conversation messages (message_type='inbox')
  - Summaries (only if explicitly requested via --include-summaries)

Usage:
    python clear_heartbeat_history.py --dry-run              # Preview what would be deleted
    python clear_heartbeat_history.py --delete               # Actually delete heartbeat messages
    python clear_heartbeat_history.py --delete --session X   # Only clear from session X
    python clear_heartbeat_history.py --list                 # List heartbeat message counts per session
    python clear_heartbeat_history.py --delete --include-summaries  # Also delete system summaries
"""
import sqlite3
import os
import sys
from datetime import datetime


def find_database():
    """Find the substrate database file"""
    env_path = os.getenv("SQLITE_DB_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    possible_paths = [
        './data/db/substrate_state.db',
        './Assistant_state.db',
        './data/Assistant_state.db',
        '../data/db/substrate_state.db',
        '/app/data/db/substrate_state.db',
        '/data/db/substrate_state.db',
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    return None


def collect_heartbeat_ids(cursor, session_id=None, include_summaries=False):
    """
    Collect all message IDs that belong to heartbeat exchanges.

    Strategy:
    1. All messages with message_type='system' AND role='system' (heartbeat prompts)
    2. All messages with message_type='system' AND role='assistant' (new-style tagged responses)
    3. Legacy: for any heartbeat prompt whose next assistant message has message_type='inbox',
       check if there's no user message in between -- if so, that's an old untagged heartbeat response

    Optionally excludes summaries (role='system' messages that contain summary content).
    """
    ids_to_delete = set()
    details = []  # (id, role, timestamp, content_preview, source) for display

    # --- Step 1: All messages explicitly tagged as system type ---
    session_filter = "AND session_id = ?" if session_id else ""
    params = (session_id,) if session_id else ()

    cursor.execute(f"""
        SELECT id, session_id, role, content, timestamp, message_type
        FROM messages
        WHERE message_type = 'system'
        {session_filter}
        ORDER BY timestamp ASC;
    """, params)

    system_messages = cursor.fetchall()

    for msg in system_messages:
        msg_id, sess, role, content, ts, mtype = msg

        # Skip summaries unless explicitly requested
        if role == 'system' and not include_summaries:
            # Summaries are system-role messages with message_type='system'
            # Heartbeat prompts are also system-role with message_type='system'
            # Distinguish by content: summaries contain "Summary" or conversation recap patterns
            content_lower = content[:200].lower()
            if any(kw in content_lower for kw in ['summary of conversation', 'conversation summary', '## summary']):
                continue

        ids_to_delete.add(msg_id)
        preview = content[:60].replace('\n', ' ')
        source = "tagged" if role == 'assistant' else "prompt"
        details.append((msg_id, role, sess, ts, preview, source))

    # --- Step 2: Find legacy untagged assistant responses ---
    # Get heartbeat prompts (role='system', message_type='system')
    cursor.execute(f"""
        SELECT id, session_id, role, content, timestamp
        FROM messages
        WHERE message_type = 'system' AND role = 'system'
        {session_filter}
        ORDER BY timestamp ASC;
    """, params)

    heartbeat_prompts = cursor.fetchall()

    for prompt in heartbeat_prompts:
        prompt_id, prompt_session, _, _, prompt_ts = prompt

        # Find the next assistant message after this heartbeat in the same session
        cursor.execute("""
            SELECT id, session_id, role, content, timestamp, message_type
            FROM messages
            WHERE session_id = ? AND role = 'assistant' AND timestamp > ?
            ORDER BY timestamp ASC
            LIMIT 1;
        """, (prompt_session, prompt_ts))

        response = cursor.fetchone()
        if not response:
            continue

        resp_id, _, _, resp_content, resp_ts, resp_mtype = response

        # Already collected via Step 1?
        if resp_id in ids_to_delete:
            continue

        # This is potentially a legacy untagged response (message_type='inbox')
        # Verify no user message sits between the heartbeat prompt and this response
        cursor.execute("""
            SELECT COUNT(*)
            FROM messages
            WHERE session_id = ? AND role = 'user' AND timestamp > ? AND timestamp < ?;
        """, (prompt_session, prompt_ts, resp_ts))
        user_msgs_between = cursor.fetchone()[0]

        if user_msgs_between == 0:
            # No user message in between -> this is a heartbeat response
            ids_to_delete.add(resp_id)
            preview = resp_content[:60].replace('\n', ' ')
            details.append((resp_id, 'assistant', prompt_session, resp_ts, preview, "legacy-paired"))

    # Sort details by timestamp for display
    details.sort(key=lambda x: x[3])

    return ids_to_delete, details


def list_heartbeat_stats(session_id=None):
    """List heartbeat message counts per session"""
    db_path = find_database()
    if not db_path:
        print("Could not find database!")
        return 1

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 60)
    print("HEARTBEAT MESSAGE STATISTICS")
    print("=" * 60)
    print(f"\nDatabase: {db_path}\n")

    # Count heartbeat prompts per session
    cursor.execute("""
        SELECT session_id, COUNT(*) as count,
               MIN(timestamp) as first, MAX(timestamp) as last
        FROM messages
        WHERE message_type = 'system' AND role = 'system'
        GROUP BY session_id
        ORDER BY last DESC;
    """)

    rows = cursor.fetchall()
    if not rows:
        print("No heartbeat prompt messages found!")
    else:
        total_prompts = 0
        for row in rows:
            sess, count, first, last = row
            total_prompts += count
            print(f"  Session: {sess}")
            print(f"    Heartbeat prompts: {count}")
            print(f"    First: {first}")
            print(f"    Last:  {last}")
            print()
        print(f"  Total heartbeat prompts: {total_prompts}")

    # Count tagged assistant heartbeat responses
    cursor.execute("""
        SELECT COUNT(*) FROM messages
        WHERE message_type = 'system' AND role = 'assistant';
    """)
    tagged_responses = cursor.fetchone()[0]
    print(f"  Tagged assistant heartbeat responses: {tagged_responses}")

    # Full collection (includes legacy pairing)
    ids, _ = collect_heartbeat_ids(cursor, session_id)

    # Count total messages for context
    cursor.execute("SELECT COUNT(*) FROM messages;")
    total_msgs = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM messages WHERE message_type = 'inbox';")
    normal_msgs = cursor.fetchone()[0]

    print(f"\n  Total heartbeat messages (including legacy paired): {len(ids)}")
    print(f"  Total messages in DB: {total_msgs}")
    print(f"  Normal messages (inbox): {normal_msgs}")
    print(f"  Messages after cleanup: ~{total_msgs - len(ids)}")

    conn.close()
    return 0


def clear_heartbeat_messages(session_id=None, dry_run=True, include_summaries=False):
    """Delete heartbeat prompts and their assistant responses"""
    db_path = find_database()
    if not db_path:
        print("Could not find database!")
        return 1

    print("=" * 60)
    if dry_run:
        print("DRY RUN - PREVIEW HEARTBEAT MESSAGES TO DELETE")
    else:
        print("DELETING HEARTBEAT MESSAGES")
    print("=" * 60)
    print(f"\nDatabase: {db_path}")
    if session_id:
        print(f"Session filter: {session_id}")
    if include_summaries:
        print(f"Including summaries: YES")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    ids_to_delete, details = collect_heartbeat_ids(cursor, session_id, include_summaries)

    if not ids_to_delete:
        print("\nNo heartbeat messages found!")
        conn.close()
        return 0

    # Display what will be deleted
    prompt_count = sum(1 for d in details if d[1] == 'system')
    response_count = sum(1 for d in details if d[1] == 'assistant')
    legacy_count = sum(1 for d in details if d[5] == 'legacy-paired')

    print(f"\nFound {len(ids_to_delete)} heartbeat messages to delete:\n")
    print("-" * 70)

    for i, (msg_id, role, sess, ts, preview, source) in enumerate(details, 1):
        tag = {
            'prompt': 'HB PROMPT',
            'tagged': 'HB RESPONSE',
            'legacy-paired': 'HB RESPONSE (legacy)',
        }.get(source, source)
        print(f"  [{i:3d}] [{tag:20s}] {ts[-8:]} | {role:9s} | {preview}...")

    print("-" * 70)
    print(f"\nSummary:")
    print(f"  Heartbeat prompts:            {prompt_count}")
    print(f"  Assistant responses (tagged):  {response_count - legacy_count}")
    print(f"  Assistant responses (legacy):  {legacy_count}")
    print(f"  Total to delete:               {len(ids_to_delete)}")

    if dry_run:
        print(f"\n[DRY RUN] No changes made. Use --delete to actually remove these messages.")
        conn.close()
        return 0

    # Actually delete
    id_list = list(ids_to_delete)
    placeholders = ','.join('?' for _ in id_list)
    cursor.execute(f"DELETE FROM messages WHERE id IN ({placeholders});", id_list)
    deleted = cursor.rowcount
    conn.commit()

    # Show what remains
    cursor.execute("SELECT COUNT(*) FROM messages;")
    remaining = cursor.fetchone()[0]

    print(f"\nDeleted {deleted} messages")
    print(f"Remaining messages: {remaining}")

    conn.close()

    print("\n" + "=" * 60)
    print("DONE - Heartbeat history cleared!")
    print("Normal conversation messages are preserved.")
    print("=" * 60 + "\n")

    return 0


def print_usage():
    print("""
Usage:
  python clear_heartbeat_history.py --dry-run                         # Preview what would be deleted
  python clear_heartbeat_history.py --delete                          # Delete all heartbeat messages
  python clear_heartbeat_history.py --delete --session X              # Delete heartbeats from session X only
  python clear_heartbeat_history.py --delete --include-summaries      # Also delete system summaries
  python clear_heartbeat_history.py --list                            # Show heartbeat statistics
""")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        print_usage()
        sys.exit(0)

    if "--list" in args:
        # Parse session filter for --list too
        session_id = None
        for i, arg in enumerate(args):
            if arg == "--session" and i + 1 < len(args):
                session_id = args[i + 1]
        sys.exit(list_heartbeat_stats(session_id))

    # Parse options
    session_id = None
    include_summaries = "--include-summaries" in args
    for i, arg in enumerate(args):
        if arg == "--session" and i + 1 < len(args):
            session_id = args[i + 1]

    if "--delete" in args:
        sys.exit(clear_heartbeat_messages(session_id, dry_run=False, include_summaries=include_summaries))
    elif "--dry-run" in args:
        sys.exit(clear_heartbeat_messages(session_id, dry_run=True, include_summaries=include_summaries))
    else:
        print("Error: Specify --dry-run or --delete")
        print_usage()
        sys.exit(1)
