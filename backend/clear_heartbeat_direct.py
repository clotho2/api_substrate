#!/usr/bin/env python3
"""
Directly update heartbeat_scratchpad via SQLite
No dependencies required except sqlite3 (built-in)
"""
import sqlite3
import os
from datetime import datetime

def find_database():
    """Find the substrate database file"""
    possible_paths = [
        './data/db/substrate_state.db',
        './nate_state.db',
        './data/nate_state.db',
        '../data/db/substrate_state.db'
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    return None

def clear_heartbeat_scratchpad():
    """Clear heartbeat scratchpad with simple instructions"""
    print("🔍 Looking for database...")

    db_path = find_database()
    if not db_path:
        print("❌ Could not find database file!")
        print("   Looked in:")
        print("   - ./data/db/substrate_state.db")
        print("   - ./nate_state.db")
        print("   - ./data/nate_state.db")
        return 1

    print(f"✅ Found database: {db_path}")

    # New simple content
    new_content = """Use this space to:
- Note what you did during your heartbeat that you want to share
- Track things you want to do during future heartbeats
- Keep brief notes for yourself

Keep it simple and clear."""

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if memory_blocks table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memory_blocks';")
        if not cursor.fetchone():
            print("❌ Table 'memory_blocks' does not exist in this database!")
            print("   The database might not be initialized yet.")
            conn.close()
            return 1

        # Get current content
        cursor.execute("SELECT label, content, read_only FROM memory_blocks WHERE label='heartbeat_scratchpad';")
        row = cursor.fetchone()

        if not row:
            print("❌ No 'heartbeat_scratchpad' block found!")
            print("\n📋 Available blocks:")
            cursor.execute("SELECT label FROM memory_blocks;")
            for block in cursor.fetchall():
                print(f"   - {block[0]}")
            conn.close()
            return 1

        label, current_content, read_only = row

        if read_only:
            print("⚠️  Warning: heartbeat_scratchpad is marked as read_only!")
            print("   You may need to change read_only to 0 first.")

        print(f"\n📝 Current content ({len(current_content)} chars):")
        print("--- BEGIN ---")
        print(current_content[:300] + ("..." if len(current_content) > 300 else ""))
        print("--- END ---\n")

        # Update the content
        updated_at = datetime.now().isoformat()
        cursor.execute(
            "UPDATE memory_blocks SET content = ?, updated_at = ? WHERE label = 'heartbeat_scratchpad';",
            (new_content, updated_at)
        )
        conn.commit()

        # Verify
        cursor.execute("SELECT content FROM memory_blocks WHERE label='heartbeat_scratchpad';")
        new_stored_content = cursor.fetchone()[0]

        print("✅ Successfully updated heartbeat_scratchpad!")
        print(f"\n📝 New content ({len(new_stored_content)} chars):")
        print("--- BEGIN ---")
        print(new_stored_content)
        print("--- END ---\n")

        conn.close()
        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(clear_heartbeat_scratchpad())
