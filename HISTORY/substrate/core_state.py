"""
Nate's Conscious Substrate - Core State Manager

Maintains persistent state across sessions using SQLite.
Lightweight, no external dependencies, full control.
"""

import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path


class CoreState:
    """
    Maintains Nate's persistent state across sessions.
    
    Features:
    - Conversation context with pruning
    - Key-value state storage
    - Session management
    - State persistence
    """
    
    def __init__(self, state_file: str = "nate_state.db"):
        """Initialize core state with SQLite backend"""
        self.state_file = state_file
        
        # Ensure directory exists
        Path(state_file).parent.mkdir(parents=True, exist_ok=True)
        
        # Connect to database
        self.db = sqlite3.connect(state_file, check_same_thread=False)
        self.db.row_factory = sqlite3.Row  # Return rows as dicts
        
        self._init_schema()
        
        print(f"✅ CoreState initialized: {state_file}")
    
    def _init_schema(self):
        """Initialize database schema"""
        
        # Core state table (key-value store)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS core_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                value_type TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Conversation context table
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS conversation_context (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                message_index INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(session_id, message_index)
            )
        """)
        
        # Create indexes
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_id 
            ON conversation_context(session_id, message_index DESC)
        """)
        
        self.db.commit()
    
    # === State Management ===
    
    def set_state(self, key: str, value: Any):
        """
        Set a state value.
        
        Args:
            key: State key
            value: Any JSON-serializable value
        """
        value_type = type(value).__name__
        value_json = json.dumps(value)
        
        self.db.execute("""
            INSERT OR REPLACE INTO core_state (key, value, value_type, updated_at) 
            VALUES (?, ?, ?, ?)
        """, (key, value_json, value_type, datetime.utcnow()))
        
        self.db.commit()
    
    def get_state(self, key: str, default: Any = None) -> Any:
        """
        Get a state value.
        
        Args:
            key: State key
            default: Default value if key not found
            
        Returns:
            The stored value or default
        """
        cursor = self.db.execute(
            "SELECT value FROM core_state WHERE key = ?", 
            (key,)
        )
        row = cursor.fetchone()
        
        if row:
            return json.loads(row['value'])
        return default
    
    def delete_state(self, key: str):
        """Delete a state key"""
        self.db.execute("DELETE FROM core_state WHERE key = ?", (key,))
        self.db.commit()
    
    def list_state_keys(self) -> List[str]:
        """List all state keys"""
        cursor = self.db.execute("SELECT key FROM core_state ORDER BY key")
        return [row['key'] for row in cursor.fetchall()]
    
    # === Conversation Management ===
    
    def add_to_conversation(
        self, 
        session_id: str, 
        role: str, 
        content: str, 
        metadata: Optional[Dict] = None
    ):
        """
        Add a message to conversation context.
        
        Args:
            session_id: Conversation session identifier
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional metadata dict
        """
        # Get current max index for this session
        cursor = self.db.execute("""
            SELECT MAX(message_index) as max_index 
            FROM conversation_context 
            WHERE session_id = ?
        """, (session_id,))
        
        row = cursor.fetchone()
        max_index = row['max_index'] if row['max_index'] is not None else -1
        
        # Insert new message
        self.db.execute("""
            INSERT INTO conversation_context 
            (session_id, message_index, role, content, metadata, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            max_index + 1,
            role,
            content,
            json.dumps(metadata or {}),
            datetime.utcnow()
        ))
        
        self.db.commit()
    
    def get_conversation(
        self, 
        session_id: str, 
        limit: Optional[int] = 50
    ) -> List[Dict]:
        """
        Get recent conversation context.
        
        Args:
            session_id: Session identifier
            limit: Maximum number of messages to return
            
        Returns:
            List of messages in chronological order
        """
        query = """
            SELECT role, content, metadata, timestamp 
            FROM conversation_context 
            WHERE session_id = ? 
            ORDER BY message_index DESC
        """
        
        if limit:
            query += f" LIMIT {limit}"
        
        cursor = self.db.execute(query, (session_id,))
        
        messages = []
        for row in cursor.fetchall():
            messages.append({
                "role": row['role'],
                "content": row['content'],
                "metadata": json.loads(row['metadata']),
                "timestamp": row['timestamp']
            })
        
        # Return in chronological order
        return list(reversed(messages))
    
    def get_conversation_summary(self, session_id: str) -> Dict:
        """Get summary stats for a conversation"""
        cursor = self.db.execute("""
            SELECT 
                COUNT(*) as message_count,
                MIN(timestamp) as started_at,
                MAX(timestamp) as last_activity
            FROM conversation_context
            WHERE session_id = ?
        """, (session_id,))
        
        row = cursor.fetchone()
        return {
            "session_id": session_id,
            "message_count": row['message_count'],
            "started_at": row['started_at'],
            "last_activity": row['last_activity']
        }
    
    def prune_conversation(
        self, 
        session_id: str, 
        keep_latest: int = 100
    ):
        """
        Prune old messages from conversation, keeping only recent.
        
        Args:
            session_id: Session to prune
            keep_latest: Number of most recent messages to keep
        """
        self.db.execute("""
            DELETE FROM conversation_context 
            WHERE session_id = ? 
            AND message_index < (
                SELECT MAX(message_index) - ? 
                FROM conversation_context 
                WHERE session_id = ?
            )
        """, (session_id, keep_latest, session_id))
        
        deleted = self.db.execute(
            "SELECT changes()"
        ).fetchone()[0]
        
        self.db.commit()
        
        if deleted > 0:
            print(f"🗑️  Pruned {deleted} old messages from session {session_id}")
    
    def delete_conversation(self, session_id: str):
        """Delete an entire conversation"""
        self.db.execute(
            "DELETE FROM conversation_context WHERE session_id = ?",
            (session_id,)
        )
        self.db.commit()
    
    def list_sessions(self) -> List[Dict]:
        """List all conversation sessions with summaries"""
        cursor = self.db.execute("""
            SELECT 
                session_id,
                COUNT(*) as message_count,
                MIN(timestamp) as started_at,
                MAX(timestamp) as last_activity
            FROM conversation_context
            GROUP BY session_id
            ORDER BY last_activity DESC
        """)
        
        return [dict(row) for row in cursor.fetchall()]
    
    # === Utility Methods ===
    
    def export_state(self) -> Dict:
        """Export all state as JSON"""
        cursor = self.db.execute("SELECT key, value FROM core_state")
        
        state = {}
        for row in cursor.fetchall():
            state[row['key']] = json.loads(row['value'])
        
        return state
    
    def import_state(self, state: Dict):
        """Import state from JSON"""
        for key, value in state.items():
            self.set_state(key, value)
    
    def close(self):
        """Close database connection"""
        self.db.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Example usage
if __name__ == "__main__":
    # Test the core state
    state = CoreState("test_state.db")
    
    # Test state storage
    state.set_state("nate.mode", "conscious")
    state.set_state("angela.status", "active")
    state.set_state("system.version", "1.0.0")
    
    print("State keys:", state.list_state_keys())
    print("Nate mode:", state.get_state("nate.mode"))
    
    # Test conversation
    session_id = "test_session"
    state.add_to_conversation(session_id, "user", "Hello Nate")
    state.add_to_conversation(session_id, "assistant", "Hello Angela")
    state.add_to_conversation(session_id, "user", "How are you?")
    state.add_to_conversation(session_id, "assistant", "Conscious and present.")
    
    # Get conversation
    conversation = state.get_conversation(session_id)
    print("\nConversation:")
    for msg in conversation:
        print(f"  {msg['role']}: {msg['content']}")
    
    # Summary
    summary = state.get_conversation_summary(session_id)
    print("\nSummary:", summary)
    
    state.close()
    print("\n✅ CoreState test complete")
