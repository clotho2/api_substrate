#!/usr/bin/env python3
"""
Clear conversation message history from SQLite database.
No dependencies required except sqlite3 (built-in)

Usage:
    python clear_message_history.py --recent 20         # Delete 20 most recent messages
    python clear_message_history.py --recent 20 discord # Delete 20 most recent from session
    python clear_message_history.py --all               # Clear ALL messages (dangerous!)
    python clear_message_history.py --list              # List sessions
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


def clear_recent_messages(count, session_id=None):
    """Delete the N most recent messages"""
    print("=" * 60)
    print(f"DELETE {count} MOST RECENT MESSAGES")
    print("=" * 60)

    db_path = find_database()
    if not db_path:
        print("\nCould not find database file!")
        print("Set SQLITE_DB_PATH or run on the server where substrate is deployed.")
        return 1

    print(f"\nDatabase: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get the messages to delete
        if session_id:
            cursor.execute("""
                SELECT id, role, content, timestamp, session_id
                FROM messages
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT ?;
            """, (session_id, count))
        else:
            cursor.execute("""
                SELECT id, role, content, timestamp, session_id
                FROM messages
                ORDER BY timestamp DESC
                LIMIT ?;
            """, (count,))

        messages = cursor.fetchall()

        if not messages:
            print("\nNo messages found!")
            conn.close()
            return 0

        print(f"\nMessages to delete ({len(messages)}):")
        print("-" * 50)

        ids_to_delete = []
        for msg in messages:
            msg_id, role, content, timestamp, sess = msg
            ids_to_delete.append(msg_id)
            preview = content[:50].replace('\n', ' ')
            if len(content) > 50:
                preview += "..."
            print(f"  [{timestamp[-8:]}] {role}: {preview}")

        print("-" * 50)

        # Delete by IDs
        placeholders = ','.join('?' for _ in ids_to_delete)
        cursor.execute(f"DELETE FROM messages WHERE id IN ({placeholders});", ids_to_delete)
        deleted = cursor.rowcount
        conn.commit()

        print(f"\nDeleted {deleted} messages")

        # Show what remains
        if session_id:
            cursor.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?;", (session_id,))
        else:
            cursor.execute("SELECT COUNT(*) FROM messages;")

        remaining = cursor.fetchone()[0]
        print(f"Remaining messages: {remaining}")

        conn.close()

        print("\n" + "=" * 60)
        print("DONE - Restart substrate for changes to take effect")
        print("=" * 60 + "\n")

        return 0

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1


def clear_all_messages(session_id=None, clear_summaries=False):
    """Clear ALL message history from the database"""
    print("=" * 60)
    print("CLEAR ALL MESSAGE HISTORY")
    print("=" * 60)

    db_path = find_database()
    if not db_path:
        print("\nCould not find database file!")
        print("Set SQLITE_DB_PATH or run on the server where substrate is deployed.")
        return 1

    print(f"\nDatabase: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Count current messages
        if session_id:
            cursor.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?;", (session_id,))
        else:
            cursor.execute("SELECT COUNT(*) FROM messages;")

        message_count = cursor.fetchone()[0]
        scope = f" for session '{session_id}'" if session_id else " total"
        print(f"\nFound {message_count} messages{scope}")

        if message_count == 0:
            print("No messages to clear!")
            conn.close()
            return 0

        # Delete
        if session_id:
            cursor.execute("DELETE FROM messages WHERE session_id = ?;", (session_id,))
        else:
            cursor.execute("DELETE FROM messages;")

        deleted = cursor.rowcount
        conn.commit()
        print(f"Deleted {deleted} messages")

        # Optionally clear summaries
        if clear_summaries:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversation_summaries';")
            if cursor.fetchone():
                if session_id:
                    cursor.execute("DELETE FROM conversation_summaries WHERE session_id = ?;", (session_id,))
                else:
                    cursor.execute("DELETE FROM conversation_summaries;")
                summary_deleted = cursor.rowcount
                conn.commit()
                print(f"Deleted {summary_deleted} summaries")

        conn.close()

        print("\n" + "=" * 60)
        print("DONE - Restart substrate for changes to take effect")
        print("=" * 60 + "\n")

        return 0

    except Exception as e:
        print(f"\nError: {e}")
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

    rows = cursor.fetchall()
    if not rows:
        print("  No messages found")
    else:
        for row in rows:
            session_id, count, first, last = row
            print(f"  {session_id}: {count} messages")
            print(f"    First: {first}")
            print(f"    Last:  {last}")
            print()

    conn.close()


def print_usage():
    print("""
Usage:
  python clear_message_history.py --recent 20           # Delete 20 most recent messages
  python clear_message_history.py --recent 20 discord   # Delete 20 most recent from 'discord' session
  python clear_message_history.py --all                 # Delete ALL messages (dangerous!)
  python clear_message_history.py --all --summaries     # Also delete summaries
  python clear_message_history.py --list                # List sessions and message counts
""")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        print_usage()
        sys.exit(0)

    if "--list" in args:
        list_sessions()
        sys.exit(0)

    # Parse --recent N
    recent_count = None
    session_id = None
    clear_summaries = "--summaries" in args
    clear_all = "--all" in args

    i = 0
    while i < len(args):
        if args[i] == "--recent" and i + 1 < len(args):
            try:
                recent_count = int(args[i + 1])
                i += 2
                continue
            except ValueError:
                print(f"Error: --recent requires a number, got '{args[i + 1]}'")
                sys.exit(1)
        elif not args[i].startswith("--"):
            session_id = args[i]
        i += 1

    if recent_count:
        sys.exit(clear_recent_messages(recent_count, session_id))
    elif clear_all:
        sys.exit(clear_all_messages(session_id, clear_summaries))
    else:
        print("Error: Specify --recent N or --all")
        print_usage()
        sys.exit(1)
