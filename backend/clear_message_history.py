#!/usr/bin/env python3
"""
Clear conversation message history from SQLite database.
No dependencies required except sqlite3 (built-in)

Usage:
    python clear_message_history.py                    # Clear all messages
    python clear_message_history.py <session_id>      # Clear specific session
    python clear_message_history.py --summaries       # Also clear summaries
"""
import sqlite3
import os
import sys
from datetime import datetime


def find_database():
    """Find the substrate database file"""
    # Check environment variable first (same as server.py uses)
    env_path = os.getenv("SQLITE_DB_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    possible_paths = [
        './data/db/substrate_state.db',
        './nate_state.db',
        './data/nate_state.db',
        '../data/db/substrate_state.db',
        # Common deployment paths
        '/app/data/db/substrate_state.db',
        '/data/db/substrate_state.db',
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    return None


def clear_message_history(session_id=None, clear_summaries=False):
    """Clear message history from the database"""
    print("=" * 60)
    print("CLEAR MESSAGE HISTORY")
    print("=" * 60)

    print("\n1. Looking for database...")
    db_path = find_database()

    if not db_path:
        print("   Could not find database file!")
        print("")
        print("   Set SQLITE_DB_PATH environment variable, or ensure one of these exists:")
        print("   - ./data/db/substrate_state.db")
        print("   - /app/data/db/substrate_state.db")
        print("")
        print("   If running remotely, you need to run this script on the server")
        print("   where the substrate is deployed, not locally.")
        return 1

    print(f"   Found database: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages';")
        if not cursor.fetchone():
            print("   Table 'messages' does not exist!")
            conn.close()
            return 1

        # Count current messages
        if session_id:
            cursor.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?;", (session_id,))
        else:
            cursor.execute("SELECT COUNT(*) FROM messages;")

        message_count = cursor.fetchone()[0]
        print(f"\n2. Found {message_count} messages" + (f" for session '{session_id}'" if session_id else " total"))

        if message_count == 0:
            print("   No messages to clear!")
            conn.close()
            return 0

        # Show sample of messages to be deleted
        print("\n3. Sample of messages to be deleted:")
        if session_id:
            cursor.execute("""
                SELECT role, content, timestamp, session_id
                FROM messages
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT 5;
            """, (session_id,))
        else:
            cursor.execute("""
                SELECT role, content, timestamp, session_id
                FROM messages
                ORDER BY timestamp DESC
                LIMIT 5;
            """)

        for row in cursor.fetchall():
            role, content, timestamp, sess = row
            preview = content[:60] + "..." if len(content) > 60 else content
            preview = preview.replace('\n', ' ')
            print(f"   [{sess}] {role}: {preview}")

        # Confirm deletion
        print(f"\n4. Deleting {message_count} messages...")

        if session_id:
            cursor.execute("DELETE FROM messages WHERE session_id = ?;", (session_id,))
        else:
            cursor.execute("DELETE FROM messages;")

        deleted = cursor.rowcount
        conn.commit()
        print(f"   Deleted {deleted} messages")

        # Optionally clear summaries
        if clear_summaries:
            print("\n5. Clearing conversation summaries...")
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversation_summaries';")
            if cursor.fetchone():
                if session_id:
                    cursor.execute("DELETE FROM conversation_summaries WHERE session_id = ?;", (session_id,))
                else:
                    cursor.execute("DELETE FROM conversation_summaries;")

                summary_deleted = cursor.rowcount
                conn.commit()
                print(f"   Deleted {summary_deleted} summaries")
            else:
                print("   No conversation_summaries table found")

        # Verify
        if session_id:
            cursor.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?;", (session_id,))
        else:
            cursor.execute("SELECT COUNT(*) FROM messages;")

        remaining = cursor.fetchone()[0]
        print(f"\n6. Remaining messages: {remaining}")

        conn.close()

        print("\n" + "=" * 60)
        print("MESSAGE HISTORY CLEARED!")
        print("=" * 60)
        print("\nNote: You may need to restart the substrate server")
        print("for changes to take effect.\n")

        return 0

    except Exception as e:
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def list_sessions():
    """List all sessions with message counts"""
    db_path = find_database()
    if not db_path:
        print("Could not find database!")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("\nSessions with messages:")
    print("-" * 50)

    cursor.execute("""
        SELECT session_id, COUNT(*) as msg_count,
               MIN(timestamp) as first_msg,
               MAX(timestamp) as last_msg
        FROM messages
        GROUP BY session_id
        ORDER BY last_msg DESC;
    """)

    for row in cursor.fetchall():
        session_id, count, first, last = row
        print(f"  {session_id}: {count} messages")
        print(f"    First: {first}")
        print(f"    Last:  {last}")
        print()

    conn.close()


if __name__ == "__main__":
    # Parse args
    session_id = None
    clear_summaries = False
    list_only = False

    for arg in sys.argv[1:]:
        if arg == "--summaries":
            clear_summaries = True
        elif arg == "--list":
            list_only = True
        elif not arg.startswith("--"):
            session_id = arg

    if list_only:
        list_sessions()
        sys.exit(0)

    sys.exit(clear_message_history(session_id=session_id, clear_summaries=clear_summaries))
