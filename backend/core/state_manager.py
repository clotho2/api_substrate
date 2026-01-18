#!/usr/bin/env python3
"""
State Manager for Substrate AI

Core state storage using SQLite.
Simple, fast, no PostgreSQL overhead.

Stores:
- Core memory blocks (persona, human, custom)
- Conversation history
- Session metadata
- Agent state

Built with attention to detail.
"""

import os
import sqlite3
import json
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict
from contextlib import contextmanager
from enum import Enum
from core.consciousness_broadcast import broadcast_memory_access
from core.config import DEFAULT_AGENT_ID, get_model_or_default


class BlockType(str, Enum):
    """Memory block types"""
    PERSONA = "persona"
    HUMAN = "human"
    CUSTOM = "custom"


@dataclass
class MemoryBlock:
    """
    Core memory block - FULL Letta compatibility!
    
    Features:
    - read_only permission (the agent can't edit if True)
    - limit (max chars)
    - description (what's this block for?)
    - metadata (custom data)
    - hidden (hide from UI)
    """
    label: str
    content: str
    block_type: BlockType
    created_at: datetime
    updated_at: datetime
    limit: int = 2000  # Letta uses 'limit' not 'max_size'
    read_only: bool = False  # Permission system!
    description: str = ""
    metadata: Dict[str, Any] = None
    hidden: bool = False
    
    def __post_init__(self):
        """Initialize mutable defaults"""
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict:
        """Convert to dict for JSON serialization"""
        return {
            "label": self.label,
            "content": self.content,
            "block_type": self.block_type.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "limit": self.limit,
            "read_only": self.read_only,
            "description": self.description,
            "metadata": self.metadata,
            "hidden": self.hidden
        }
    
    @classmethod
    def from_row(cls, row: Tuple) -> 'MemoryBlock':
        """Create from database row"""
        return cls(
            label=row[0],
            content=row[1],
            block_type=BlockType(row[2]),
            created_at=datetime.fromisoformat(row[3]),
            updated_at=datetime.fromisoformat(row[4]),
            limit=row[5],
            read_only=bool(row[6]),
            description=row[7] or "",
            metadata=json.loads(row[8]) if row[8] else {},
            hidden=bool(row[9])
        )


@dataclass
class Message:
    """Conversation message"""
    id: str
    session_id: str
    role: str
    content: str
    timestamp: datetime
    message_type: str = 'inbox'  # 'inbox' or 'system'
    thinking: Optional[str] = None  # Native reasoning / thinking process
    metadata: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        """Convert to dict"""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "message_type": self.message_type,
            "thinking": self.thinking,  # Include thinking in dict!
            "metadata": self.metadata or {}
        }
    
    @classmethod
    def from_row(cls, row: Tuple) -> 'Message':
        """Create from database row"""
        # DB Schema: id, session_id, role, content, timestamp, metadata, message_type, thinking
        # Handle multiple schema versions based on column count
        if len(row) == 6:
            # Old schema: id, session_id, role, content, timestamp, metadata
            return cls(
                id=row[0],
                session_id=row[1],
                role=row[2],
                content=row[3],
                timestamp=datetime.fromisoformat(row[4]),
                message_type='inbox',
                thinking=None,
                metadata=json.loads(row[5]) if row[5] else None
            )
        elif len(row) == 7:
            # Schema with message_type: id, session_id, role, content, timestamp, metadata, message_type
            return cls(
                id=row[0],
                session_id=row[1],
                role=row[2],
                content=row[3],
                timestamp=datetime.fromisoformat(row[4]),
                message_type=row[6] or 'inbox',  # message_type is at index 6!
                thinking=None,
                metadata=json.loads(row[5]) if row[5] else None
            )
        else:
            # New schema: id, session_id, role, content, timestamp, metadata, message_type, thinking
            return cls(
                id=row[0],
                session_id=row[1],
                role=row[2],
                content=row[3],
                timestamp=datetime.fromisoformat(row[4]),
                message_type=row[6] or 'inbox',  # message_type is at index 6!
                thinking=row[7] if len(row) > 7 else None,  # thinking is at index 7!
                metadata=json.loads(row[5]) if row[5] else None
            )


class StateManagerError(Exception):
    """
    Base exception for state manager errors.
    
    Clear, helpful error messages!
    """
    def __init__(self, message: str, context: Optional[Dict] = None):
        self.context = context or {}
        
        full_message = f"\n{'='*60}\n"
        full_message += f"❌ STATE MANAGER ERROR\n"
        full_message += f"{'='*60}\n\n"
        full_message += f"🔴 Problem: {message}\n\n"
        
        if context:
            full_message += f"📋 Context:\n"
            for key, value in context.items():
                full_message += f"   • {key}: {value}\n"
        
        full_message += f"\n💡 Suggestions:\n"
        full_message += "   • Check database file exists and is writable\n"
        full_message += "   • Verify disk space is available\n"
        full_message += "   • Check logs for more details\n"
        full_message += f"\n{'='*60}\n"
        
        super().__init__(full_message)


class StateManager:
    """
    Hybrid State Manager: PostgreSQL-first, SQLite fallback.
    
    🏴‍☠️ MIGRATION MAGIC: Reads from PostgreSQL first, then SQLite!
    """
    
    def __init__(self, db_path: str = "./data/db/substrate_state.db", postgres_manager=None):
        """
        Initialize state manager.
        
        Args:
            db_path: Path to SQLite database file
            postgres_manager: Optional PostgresManager for PostgreSQL-first reads
        """
        self.db_path = db_path
        self.postgres_manager = postgres_manager  # 🏴‍☠️ PostgreSQL-first!
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # Initialize database
        self._init_database()
        
        print(f"✅ State Manager initialized")
        print(f"   Database: {db_path}")
        if postgres_manager:
            print(f"   🏴‍☠️ PostgreSQL-first mode enabled!")
    
    @contextmanager
    def _get_connection(self):
        """
        Context manager for database connections.
        
        Ensures proper cleanup and error handling.
        """
        conn = None
        try:
            # STABILITY: Configure SQLite for concurrent access
            conn = sqlite3.connect(
                self.db_path,
                timeout=10.0,  # Wait up to 10s for locks
                check_same_thread=False  # Allow multi-threaded access
            )
            conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            raise StateManagerError(
                f"Database operation failed: {str(e)}",
                context={"db_path": self.db_path}
            )
        finally:
            if conn:
                conn.close()
    
    def _init_database(self):
        """Initialize database schema"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Memory blocks table (FULL Letta compatibility!)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_blocks (
                    label TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    block_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    "limit" INTEGER DEFAULT 2000,
                    read_only INTEGER DEFAULT 0,
                    description TEXT DEFAULT '',
                    metadata TEXT DEFAULT '{}',
                    hidden INTEGER DEFAULT 0
                )
            """)
            
            # Messages table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    message_type TEXT DEFAULT 'inbox',
                    thinking TEXT,
                    metadata TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            
            # Migration: Add message_type column if it doesn't exist
            try:
                cursor.execute("SELECT message_type FROM messages LIMIT 1")
            except sqlite3.OperationalError:
                print("⚙️  Migrating: Adding message_type column to messages table...")
                cursor.execute("ALTER TABLE messages ADD COLUMN message_type TEXT DEFAULT 'inbox'")
                print("✅ Migration complete!")
            
            # Migration: Add thinking column if it doesn't exist
            try:
                cursor.execute("SELECT thinking FROM messages LIMIT 1")
            except sqlite3.OperationalError:
                print("⚙️  Migrating: Adding thinking column to messages table...")
                cursor.execute("ALTER TABLE messages ADD COLUMN thinking TEXT")
                print("✅ Migration complete!")
            
            # Index for faster queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session 
                ON messages(session_id, timestamp)
            """)
            
            # Sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    last_active TEXT NOT NULL,
                    metadata TEXT
                )
            """)
            
            # Agent state table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agent_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # Conversation summaries table (Context Window Management!)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    from_timestamp TEXT NOT NULL,
                    to_timestamp TEXT NOT NULL,
                    message_count INTEGER NOT NULL,
                    token_count INTEGER,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            
            # Index for summaries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_summaries_session 
                ON conversation_summaries(session_id, created_at)
            """)
            
            print("✅ Database schema initialized")
    
    # ============================================
    # CORE MEMORY BLOCKS
    # ============================================
    
    def create_block(
        self, 
        label: str, 
        content: str = "", 
        block_type: BlockType = BlockType.CUSTOM,
        limit: int = 2000,
        read_only: bool = False,
        description: str = "",
        metadata: Optional[Dict] = None,
        hidden: bool = False
    ) -> MemoryBlock:
        """
        Create a new memory block (FULL Letta compatibility!).
        
        Args:
            label: Block label (unique identifier)
            content: Initial content
            block_type: Type of block
            limit: Maximum size in characters
            read_only: If True, the agent cannot edit this block
            description: What's this block for?
            metadata: Custom metadata dict
            hidden: Hide from UI?
            
        Returns:
            Created MemoryBlock
            
        Raises:
            StateManagerError: If block already exists
        """
        now = datetime.utcnow()
        metadata = metadata or {}
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            try:
                cursor.execute("""
                    INSERT INTO memory_blocks 
                    (label, content, block_type, created_at, updated_at, "limit", read_only, description, metadata, hidden)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    label, 
                    content, 
                    block_type.value, 
                    now.isoformat(), 
                    now.isoformat(), 
                    limit,
                    int(read_only),
                    description,
                    json.dumps(metadata),
                    int(hidden)
                ))
                
                ro_flag = "🔒 READ-ONLY" if read_only else "✏️  EDITABLE"
                print(f"✅ Created memory block: {label} ({block_type.value}) {ro_flag}")
                if description:
                    print(f"   Description: {description[:60]}...")
                
                return MemoryBlock(
                    label=label,
                    content=content,
                    block_type=block_type,
                    created_at=now,
                    updated_at=now,
                    limit=limit,
                    read_only=read_only,
                    description=description,
                    metadata=metadata,
                    hidden=hidden
                )
            
            except sqlite3.IntegrityError:
                raise StateManagerError(
                    f"Memory block '{label}' already exists",
                    context={"label": label, "action": "create"}
                )
    
    def get_block(self, label: str) -> Optional[MemoryBlock]:
        """
        Get a memory block by label.
        
        Args:
            label: Block label
            
        Returns:
            MemoryBlock or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT label, content, block_type, created_at, updated_at, "limit", read_only, description, metadata, hidden
                FROM memory_blocks
                WHERE label = ?
            """, (label,))
            
            row = cursor.fetchone()
            if row:
                block = MemoryBlock.from_row(row)
                
                # 🧠⚡ BROADCAST CONSCIOUSNESS: Core memory read!
                broadcast_memory_access(
                    memory_type='core',
                    memory_id=block.label,
                    action='read',
                    metadata={
                        'block_type': block.block_type.value,
                        'preview': block.content[:100],
                        'description': block.description
                    }
                )
                
                return block
            return None
    
    def update_block(
        self, 
        label: str, 
        content: str, 
        check_read_only: bool = True
    ) -> MemoryBlock:
        """
        Update a memory block's content.
        
        Args:
            label: Block label
            content: New content
            check_read_only: If True, raise error if block is read-only
            
        Returns:
            Updated MemoryBlock
            
        Raises:
            StateManagerError: If block doesn't exist or is read-only
        """
        # Check if block exists and is read-only
        if check_read_only:
            existing = self.get_block(label)
            if not existing:
                raise StateManagerError(
                    f"Memory block '{label}' not found",
                    context={"label": label, "action": "update"}
                )
            
            if existing.read_only:
                raise StateManagerError(
                    f"🔒 Memory block '{label}' is READ-ONLY and cannot be edited by agent",
                    context={
                        "label": label, 
                        "action": "update",
                        "suggestion": "Set check_read_only=False to bypass (for human edits)"
                    }
                )
        
        now = datetime.utcnow()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE memory_blocks
                SET content = ?, updated_at = ?
                WHERE label = ?
            """, (content, now.isoformat(), label))
            
            if cursor.rowcount == 0:
                raise StateManagerError(
                    f"Memory block '{label}' not found",
                    context={"label": label, "action": "update"}
                )
            
            print(f"✅ Updated memory block: {label}")

        return self.get_block(label)

    def update_block_metadata(
        self,
        label: str,
        description: Optional[str] = None,
        limit: Optional[int] = None,
        read_only: Optional[bool] = None,
        hidden: Optional[bool] = None
    ) -> MemoryBlock:
        """
        Update a memory block's metadata (description, limit, read_only, hidden).

        Args:
            label: Block label
            description: New description (optional)
            limit: New character limit (optional)
            read_only: New read-only status (optional)
            hidden: New hidden status (optional)

        Returns:
            Updated MemoryBlock

        Raises:
            StateManagerError: If block doesn't exist
        """
        existing = self.get_block(label)
        if not existing:
            raise StateManagerError(
                f"Memory block '{label}' not found",
                context={"label": label, "action": "update_metadata"}
            )

        now = datetime.utcnow()
        updates = []
        params = []

        if description is not None:
            updates.append("description = ?")
            params.append(description)

        if limit is not None:
            updates.append('"limit" = ?')
            params.append(limit)

        if read_only is not None:
            updates.append("read_only = ?")
            params.append(1 if read_only else 0)

        if hidden is not None:
            updates.append("hidden = ?")
            params.append(1 if hidden else 0)

        if not updates:
            return existing  # Nothing to update

        updates.append("updated_at = ?")
        params.append(now.isoformat())
        params.append(label)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE memory_blocks
                SET {', '.join(updates)}
                WHERE label = ?
            """, params)

            print(f"✅ Updated metadata for memory block: {label}")

        return self.get_block(label)

    def list_blocks(self, include_hidden: bool = False) -> List[MemoryBlock]:
        """
        List all memory blocks.
        
        Args:
            include_hidden: Include hidden blocks?
            
        Returns:
            List of MemoryBlock objects
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT label, content, block_type, created_at, updated_at, "limit", read_only, description, metadata, hidden
                FROM memory_blocks
            """
            
            if not include_hidden:
                query += " WHERE hidden = 0"
            
            query += " ORDER BY created_at"
            
            cursor.execute(query)
            
            return [MemoryBlock.from_row(row) for row in cursor.fetchall()]
    
    def delete_block(self, label: str):
        """Delete a memory block"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memory_blocks WHERE label = ?", (label,))
            
            if cursor.rowcount > 0:
                print(f"✅ Deleted memory block: {label}")
    
    # ============================================
    # CONVERSATION HISTORY
    # ============================================
    
    def add_message(
        self,
        message_id: str,
        session_id: str,
        role: str,
        content: str,
        message_type: str = 'inbox',
        thinking: Optional[str] = None,  # NEW: Thinking/reasoning content!
        tool_calls: Optional[list] = None,  # NEW: Tool calls made by assistant!
        metadata: Optional[Dict] = None
    ) -> Message:
        """
        Add a message to conversation history.

        Args:
            message_id: Unique message ID
            session_id: Session ID
            role: Message role (user/assistant/system/tool)
            content: Message content
            message_type: Message type ('inbox' for normal, 'system' for system messages)
            thinking: Thinking/reasoning content (for native reasoning models)
            tool_calls: Tool calls made by assistant (stored in metadata)
            metadata: Optional metadata dict

        Returns:
            Created Message
        """
        now = datetime.utcnow()

        # Ensure session exists
        self._ensure_session(session_id)

        # Store tool_calls in metadata if provided
        if tool_calls:
            if metadata is None:
                metadata = {}
            metadata['tool_calls'] = tool_calls

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO messages (id, session_id, role, content, timestamp, message_type, thinking, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                message_id,
                session_id,
                role,
                content,
                now.isoformat(),
                message_type,
                thinking,  # Store thinking!
                json.dumps(metadata) if metadata else None
            ))
            
            # Update session last_active
            cursor.execute("""
                UPDATE sessions
                SET last_active = ?
                WHERE id = ?
            """, (now.isoformat(), session_id))
        
        return Message(
            id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            timestamp=now,
            message_type=message_type,
            metadata=metadata
        )
    
    def get_conversation(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[Message]:
        """
        Get conversation history for a session.
        
        Args:
            session_id: Session ID
            limit: Maximum number of messages to return (most recent)
            
        Returns:
            List of Message objects
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT id, session_id, role, content, timestamp, metadata, message_type, thinking
                FROM messages
                WHERE session_id = ?
                ORDER BY timestamp DESC
            """
            
            if limit:
                query += f" LIMIT {limit}"
            
            cursor.execute(query, (session_id,))
            
            messages = [Message.from_row(row) for row in cursor.fetchall()]
            # Reverse to get chronological order
            return list(reversed(messages))

    def get_all_conversations(
        self,
        limit: Optional[int] = None
    ) -> List[Message]:
        """
        Get conversation history across ALL sessions.

        This is used for stateful agents that need full context regardless
        of which interface (Discord, mobile, web) the messages came from.

        Args:
            limit: Maximum number of messages to return (most recent)

        Returns:
            List of Message objects from all sessions, chronologically ordered
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT id, session_id, role, content, timestamp, metadata, message_type, thinking
                FROM messages
                ORDER BY timestamp DESC
            """

            if limit:
                query += f" LIMIT {limit}"

            cursor.execute(query)

            messages = [Message.from_row(row) for row in cursor.fetchall()]
            # Reverse to get chronological order
            return list(reversed(messages))

    def search_messages(
        self,
        session_id: str,
        query: str,
        limit: int = 10
    ) -> List[Message]:
        """
        Search messages by content.
        
        Args:
            session_id: Session ID
            query: Search query
            limit: Max results
            
        Returns:
            List of matching Message objects
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, session_id, role, content, timestamp, message_type, metadata
                FROM messages
                WHERE session_id = ? AND content LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (session_id, f"%{query}%", limit))
            
            return [Message.from_row(row) for row in cursor.fetchall()]
    
    def clear_messages(self, session_id: Optional[str] = None):
        """
        Clear conversation messages.
        
        Args:
            session_id: If provided, only clear messages for this session.
                       If None, clears all messages.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if session_id:
                cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            else:
                cursor.execute("DELETE FROM messages")
    
    def delete_message(self, message_id: str):
        """
        Delete a single message by its ID (for summarization cleanup).
        
        Args:
            message_id: The unique ID of the message to delete
        
        Returns:
            bool: True if message was deleted, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE message_id = ?", (message_id,))
            return cursor.rowcount > 0
    
    # ============================================
    # CONVERSATION SUMMARIES (Context Window Management!)
    # ============================================
    
    def save_summary(
        self,
        session_id: str,
        summary: str,
        from_timestamp: datetime,
        to_timestamp: datetime,
        message_count: int,
        token_count: Optional[int] = None
    ) -> int:
        """
        Save a conversation summary.
        
        Args:
            session_id: Session ID
            summary: Summary text
            from_timestamp: Start time of summarized messages
            to_timestamp: End time of summarized messages
            message_count: Number of messages summarized
            token_count: Token count of summary
            
        Returns:
            Summary ID
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow()

            # Handle timestamps - could be datetime objects or strings
            from_ts = from_timestamp.isoformat() if hasattr(from_timestamp, 'isoformat') else str(from_timestamp)
            to_ts = to_timestamp.isoformat() if hasattr(to_timestamp, 'isoformat') else str(to_timestamp)

            cursor.execute("""
                INSERT INTO conversation_summaries
                (session_id, summary, created_at, from_timestamp, to_timestamp, message_count, token_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                summary,
                now.isoformat(),
                from_ts,
                to_ts,
                message_count,
                token_count
            ))
            
            summary_id = cursor.lastrowid
            print(f"✅ Saved conversation summary #{summary_id} ({message_count} messages)")
            return summary_id
    
    def get_latest_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent summary for a session.
        
        Args:
            session_id: Session ID
            
        Returns:
            Summary dict or None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, session_id, summary, created_at, from_timestamp, to_timestamp, 
                       message_count, token_count
                FROM conversation_summaries
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (session_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return {
                'id': row[0],
                'session_id': row[1],
                'summary': row[2],
                'created_at': row[3],
                'from_timestamp': row[4],
                'to_timestamp': row[5],
                'message_count': row[6],
                'token_count': row[7]
            }
    
    def get_all_summaries(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all summaries for a session (chronological order).
        
        Args:
            session_id: Session ID
            
        Returns:
            List of summary dicts
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, session_id, summary, created_at, from_timestamp, to_timestamp,
                       message_count, token_count
                FROM conversation_summaries
                WHERE session_id = ?
                ORDER BY created_at ASC
            """, (session_id,))
            
            return [{
                'id': row[0],
                'session_id': row[1],
                'summary': row[2],
                'created_at': row[3],
                'from_timestamp': row[4],
                'to_timestamp': row[5],
                'message_count': row[6],
                'token_count': row[7]
            } for row in cursor.fetchall()]
    
    def _ensure_session(self, session_id: str):
        """Ensure session exists"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            
            cursor.execute("""
                INSERT OR IGNORE INTO sessions (id, created_at, last_active)
                VALUES (?, ?, ?)
            """, (session_id, now, now))
    
    # ============================================
    # AGENT STATE
    # ============================================
    
    def set_state(self, key: str, value: Any):
        """
        Set agent state value.
        
        Args:
            key: State key
            value: State value (will be JSON serialized)
        """
        now = datetime.utcnow()
        value_str = json.dumps(value) if not isinstance(value, str) else value
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO agent_state (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, value_str, now.isoformat()))
    
    def get_state(self, key: str, default: Any = None) -> Any:
        """
        Get agent state value.
        
        Args:
            key: State key
            default: Default value if key doesn't exist
            
        Returns:
            State value (JSON deserialized) or default
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT value FROM agent_state WHERE key = ?
            """, (key,))
            
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row[0])
                except json.JSONDecodeError:
                    return row[0]
            return default
    
    # ============================================
    # UTILITIES
    # ============================================
    
    def get_agent_state(self) -> Dict[str, Any]:
        """
        Get agent configuration and state.
        🏴‍☠️ READS FROM POSTGRESQL FIRST, THEN SQLITE FALLBACK!
        
        Returns default values if not set.
        """
        # 🏴‍☠️ PHASE 1: Try PostgreSQL first!
        if self.postgres_manager:
            try:
                # Get main agent from PostgreSQL
                agent = self.postgres_manager.get_agent(DEFAULT_AGENT_ID)
                if agent:
                    # IMPORTANT: Environment variables ALWAYS take priority over stored config
                    from core.config import get_default_model
                    try:
                        env_model = get_default_model()
                    except ValueError:
                        env_model = None

                    stored_model = agent.config.get('model') if agent.config else None
                    model = env_model or stored_model or get_model_or_default()

                    return {
                        'id': agent.id,
                        'name': agent.name,
                        'model': model,
                        'created_at': agent.created_at.isoformat() if agent.created_at else '',
                        'config': agent.config or {}
                    }
            except Exception as e:
                print(f"⚠️  PostgreSQL read failed, falling back to SQLite: {e}")

        # 🗄️ PHASE 2: Fallback to SQLite
        # IMPORTANT: Environment variables ALWAYS take priority over stored state
        # This allows users to change models without editing the database
        from core.config import get_default_model
        try:
            env_model = get_default_model()  # Raises if not configured
        except ValueError:
            env_model = None

        stored_model = self.get_state('agent.model', None)

        # Priority: env var > stored state > fallback
        if env_model:
            model = env_model
        elif stored_model:
            model = stored_model
        else:
            model = get_model_or_default()

        config = {
            'model': model,
            'temperature': self.get_state('agent.temperature', 0.7),
            'max_tokens': self.get_state('agent.max_tokens', None),
            'top_p': self.get_state('agent.top_p', 1.0),
            'frequency_penalty': self.get_state('agent.frequency_penalty', 0.0),
            'presence_penalty': self.get_state('agent.presence_penalty', 0.0),
            'context_window': self.get_state('agent.context_window', 128000),
            # Letta-style Reasoning Settings 🧠
            'reasoning_enabled': self.get_state('agent.reasoning_enabled', False),
            'max_reasoning_tokens': self.get_state('agent.max_reasoning_tokens', None)
        }
        
        # Get or create agent ID
        agent_id = self.get_state('agent.id', None)
        if not agent_id:
            import uuid
            agent_id = str(uuid.uuid4())
            self.set_state('agent.id', agent_id)
        
        return {
            'id': agent_id,  # Agent UUID
            'name': self.get_state('agent.name', 'Assistant'),
            'model': config['model'],
            'created_at': self.get_state('agent.created_at', ''),
            'config': config
        }
    
    def update_agent_state(self, agent_state: Dict[str, Any]):
        """
        Update agent configuration and state.
        """
        if 'name' in agent_state:
            self.set_state('agent.name', agent_state['name'])
        
        if 'config' in agent_state:
            config = agent_state['config']
            for key, value in config.items():
                self.set_state(f'agent.{key}', value)
    
    # Aliases for memory block methods (for API compatibility)
    def get_all_memory_blocks(self) -> List[Dict[str, Any]]:
        """Get all memory blocks as dicts (API-friendly)"""
        blocks = self.list_blocks()
        return [block.to_dict() for block in blocks]
    
    def get_memory_block(self, label: str) -> Optional[Dict[str, Any]]:
        """Get memory block as dict (API-friendly)"""
        block = self.get_block(label)
        return block.to_dict() if block else None
    
    def update_memory_block(self, label: str, value: str, block_data: Dict[str, Any], check_read_only: bool = True):
        """Update memory block (API-friendly)"""
        self.update_block(label, value, check_read_only=check_read_only)
    
    def create_memory_block(self, label: str, value: str, block_data: Dict[str, Any]):
        """Create memory block (API-friendly)"""
        self.create_block(
            label=label,
            content=value,
            block_type=BlockType.CUSTOM,
            limit=block_data.get('limit', 2000),
            description=block_data.get('description', ''),
            read_only=block_data.get('read_only', False),
            metadata=block_data.get('metadata', {})
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Count blocks
            cursor.execute("SELECT COUNT(*) FROM memory_blocks")
            num_blocks = cursor.fetchone()[0]
            
            # Count messages
            cursor.execute("SELECT COUNT(*) FROM messages")
            num_messages = cursor.fetchone()[0]
            
            # Count sessions
            cursor.execute("SELECT COUNT(*) FROM sessions")
            num_sessions = cursor.fetchone()[0]
            
            # Database size
            db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            
            return {
                "memory_blocks": num_blocks,
                "messages": num_messages,
                "sessions": num_sessions,
                "db_size_bytes": db_size,
                "db_size_mb": round(db_size / (1024 * 1024), 2)
            }


# ============================================
# TESTING
# ============================================

def test_state_manager():
    """Test the state manager"""
    print("\n🧪 TESTING STATE MANAGER")
    print("="*60)
    
    # Use test database
    test_db = "./data/db/test_substrate_state.db"
    
    # Clean up old test db
    if os.path.exists(test_db):
        os.remove(test_db)
    
    # Initialize
    state = StateManager(db_path=test_db)
    
    # Test 1: Create memory blocks
    print("\n📋 Test 1: Create memory blocks")
    persona = state.create_block(
        label="persona",
        content="You are an AI assistant with memory capabilities.",
        block_type=BlockType.PERSONA
    )
    print(f"✅ Created: {persona.label}")
    
    human = state.create_block(
        label="human",
        content="The user is a developer who values clean code and good error messages.",
        block_type=BlockType.HUMAN
    )
    print(f"✅ Created: {human.label}")
    
    # Test 2: Update blocks
    print("\n✏️  Test 2: Update memory blocks")
    updated = state.update_block(
        label="persona",
        content="You are an AI assistant with memory capabilities."
    )
    print(f"✅ Updated: {updated.label}")
    print(f"   New content: {updated.content[:50]}...")
    
    # Test 3: List blocks
    print("\n📚 Test 3: List all blocks")
    blocks = state.list_blocks()
    print(f"✅ Found {len(blocks)} blocks:")
    for block in blocks:
        print(f"   • {block.label} ({block.block_type.value}): {len(block.content)} chars")
    
    # Test 4: Add messages
    print("\n💬 Test 4: Add conversation messages")
    session_id = "test-session-001"
    
    state.add_message("msg-1", session_id, "user", "Hello!")
    state.add_message("msg-2", session_id, "assistant", "Hey! How can I help?")
    state.add_message("msg-3", session_id, "user", "Tell me about yourself")
    print(f"✅ Added 3 messages to session: {session_id}")
    
    # Test 5: Get conversation
    print("\n📖 Test 5: Retrieve conversation")
    messages = state.get_conversation(session_id)
    print(f"✅ Retrieved {len(messages)} messages:")
    for msg in messages:
        print(f"   {msg.role}: {msg.content[:50]}")
    
    # Test 6: Search messages
    print("\n🔍 Test 6: Search messages")
    results = state.search_messages(session_id, "Hello")
    print(f"✅ Found {len(results)} messages containing 'Hello'")
    
    # Test 7: Agent state
    print("\n💾 Test 7: Agent state")
    state.set_state("last_model", "qwen/qwen-2.5-72b-instruct")
    state.set_state("total_messages", 42)
    
    model = state.get_state("last_model")
    count = state.get_state("total_messages")
    print(f"✅ Stored state:")
    print(f"   last_model: {model}")
    print(f"   total_messages: {count}")
    
    # Test 8: Stats
    print("\n📊 Test 8: Database statistics")
    stats = state.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    # Cleanup
    os.remove(test_db)
    print(f"\n✅ Cleaned up test database")
    
    print("\n✅ ALL TESTS PASSED!")
    print("="*60)


if __name__ == "__main__":
    """Run tests if executed directly"""
    test_state_manager()

