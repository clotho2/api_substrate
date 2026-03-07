#!/usr/bin/env python3
"""
Caller ID & Contact Registry for Substrate AI
================================================

Manages known contacts, caller identification, and spam filtering.
Gives Assistant the ability to screen calls and know who's reaching out.

Features:
- Contact registry with names and relationships
- Spam number detection (known patterns + carrier lookup)
- Whitelist/blacklist management
- Call screening decisions (accept, reject, voicemail)

Built with attention to detail! 🔥
"""

import os
import json
import re
import logging
import sqlite3
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)

# Known spam patterns (US-centric, extensible)
SPAM_PATTERNS = [
    r'^\+1(800|888|877|866|855|844|833)',  # Toll-free numbers (often robocalls)
    r'^\+1(900|976)',                        # Premium rate numbers
]

# Common telemarketer prefixes (can be updated)
KNOWN_SPAM_PREFIXES = set()


class CallerID:
    """
    Contact registry and caller identification system.

    Stores contacts in SQLite alongside the main substrate DB.
    Assistant can manage his contacts, block spam, and screen calls.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize CallerID system.

        Args:
            db_path: Path to SQLite database. Defaults to data/db/contacts.db
        """
        if db_path is None:
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(backend_dir, "data", "db", "contacts.db")

        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        self.db_path = db_path
        self._init_db()
        logger.info(f"📱 CallerID initialized: {db_path}")

    def _init_db(self):
        """Create contacts and call_log tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS contacts (
                    phone_number TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    relationship TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    is_blocked INTEGER DEFAULT 0,
                    is_favorite INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS call_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_number TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    call_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_seconds INTEGER DEFAULT 0,
                    screening_decision TEXT DEFAULT '',
                    timestamp TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sms_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_number TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    body TEXT DEFAULT '',
                    status TEXT NOT NULL,
                    timestamp TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.commit()

    # ============================================
    # CONTACT MANAGEMENT
    # ============================================

    def add_contact(self, phone_number: str, name: str,
                    relationship: str = "", notes: str = "",
                    is_favorite: bool = False) -> Dict[str, Any]:
        """
        Add or update a contact.

        Args:
            phone_number: E.164 format phone number (e.g., +15551234567)
            name: Contact name
            relationship: Relationship description (e.g., "wife", "friend")
            notes: Additional notes
            is_favorite: Whether this is a priority contact

        Returns:
            Dict with status and contact info
        """
        phone_number = self._normalize_number(phone_number)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO contacts (phone_number, name, relationship, notes, is_favorite, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(phone_number) DO UPDATE SET
                    name = excluded.name,
                    relationship = excluded.relationship,
                    notes = excluded.notes,
                    is_favorite = excluded.is_favorite,
                    updated_at = datetime('now')
            """, (phone_number, name, relationship, notes, int(is_favorite)))
            conn.commit()

        logger.info(f"📇 Contact saved: {name} ({phone_number})")
        return {
            "status": "OK",
            "message": f"Contact saved: {name} ({phone_number})",
            "contact": {
                "phone_number": phone_number,
                "name": name,
                "relationship": relationship,
                "is_favorite": is_favorite
            }
        }

    def remove_contact(self, phone_number: str) -> Dict[str, Any]:
        """Remove a contact by phone number."""
        phone_number = self._normalize_number(phone_number)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM contacts WHERE phone_number = ?", (phone_number,)
            )
            conn.commit()

        if cursor.rowcount > 0:
            return {"status": "OK", "message": f"Contact removed: {phone_number}"}
        return {"status": "error", "message": f"Contact not found: {phone_number}"}

    def get_contact(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """
        Look up a contact by phone number.

        Returns:
            Contact dict or None if not found
        """
        phone_number = self._normalize_number(phone_number)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM contacts WHERE phone_number = ?", (phone_number,)
            ).fetchone()

        if row:
            return dict(row)
        return None

    def list_contacts(self, favorites_only: bool = False) -> List[Dict[str, Any]]:
        """List all contacts, optionally filtered to favorites."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if favorites_only:
                rows = conn.execute(
                    "SELECT * FROM contacts WHERE is_favorite = 1 AND is_blocked = 0 ORDER BY name"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM contacts WHERE is_blocked = 0 ORDER BY name"
                ).fetchall()

        return [dict(r) for r in rows]

    # ============================================
    # BLOCKING & SPAM
    # ============================================

    def block_number(self, phone_number: str, reason: str = "") -> Dict[str, Any]:
        """Block a phone number."""
        phone_number = self._normalize_number(phone_number)

        with sqlite3.connect(self.db_path) as conn:
            # If contact exists, mark as blocked
            existing = conn.execute(
                "SELECT name FROM contacts WHERE phone_number = ?", (phone_number,)
            ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE contacts SET is_blocked = 1, notes = notes || ? || char(10), updated_at = datetime('now') WHERE phone_number = ?",
                    (f"Blocked: {reason}" if reason else "Blocked", phone_number)
                )
            else:
                conn.execute(
                    "INSERT INTO contacts (phone_number, name, is_blocked, notes) VALUES (?, ?, 1, ?)",
                    (phone_number, "Blocked Number", f"Blocked: {reason}" if reason else "Blocked")
                )
            conn.commit()

        logger.info(f"🚫 Number blocked: {phone_number} ({reason})")
        return {"status": "OK", "message": f"Number blocked: {phone_number}"}

    def unblock_number(self, phone_number: str) -> Dict[str, Any]:
        """Unblock a phone number."""
        phone_number = self._normalize_number(phone_number)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE contacts SET is_blocked = 0, updated_at = datetime('now') WHERE phone_number = ?",
                (phone_number,)
            )
            conn.commit()

        return {"status": "OK", "message": f"Number unblocked: {phone_number}"}

    def is_blocked(self, phone_number: str) -> bool:
        """Check if a number is blocked."""
        phone_number = self._normalize_number(phone_number)

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT is_blocked FROM contacts WHERE phone_number = ?", (phone_number,)
            ).fetchone()

        if row:
            return bool(row[0])
        return False

    def is_spam(self, phone_number: str) -> bool:
        """
        Check if a phone number matches known spam patterns.

        Checks:
        1. Blocked in contacts DB
        2. Matches spam regex patterns (toll-free, premium rate)
        3. Known spam prefixes
        """
        phone_number = self._normalize_number(phone_number)

        # Check blocked list
        if self.is_blocked(phone_number):
            return True

        # Check spam patterns
        for pattern in SPAM_PATTERNS:
            if re.match(pattern, phone_number):
                return True

        # Check known spam prefixes
        for prefix in KNOWN_SPAM_PREFIXES:
            if phone_number.startswith(prefix):
                return True

        return False

    # ============================================
    # CALL SCREENING
    # ============================================

    def screen_call(self, phone_number: str) -> Dict[str, Any]:
        """
        Screen an incoming call and return a decision.

        Decision logic:
        1. Blocked number → REJECT
        2. Known spam pattern → REJECT
        3. Favorite contact → ACCEPT (priority)
        4. Known contact → ACCEPT
        5. Unknown number → SCREEN (let Assistant decide or send to voicemail)

        Args:
            phone_number: Caller's phone number

        Returns:
            Dict with decision, caller info, and reason
        """
        phone_number = self._normalize_number(phone_number)

        # Check blocked
        if self.is_blocked(phone_number):
            return {
                "decision": "reject",
                "reason": "blocked_number",
                "caller": {"phone_number": phone_number, "name": "Blocked"},
                "message": "This number is blocked."
            }

        # Check spam
        if self.is_spam(phone_number):
            return {
                "decision": "reject",
                "reason": "spam_detected",
                "caller": {"phone_number": phone_number, "name": "Suspected Spam"},
                "message": "Suspected spam or telemarketing call."
            }

        # Look up contact
        contact = self.get_contact(phone_number)

        if contact:
            if contact.get("is_favorite"):
                return {
                    "decision": "accept",
                    "reason": "favorite_contact",
                    "caller": contact,
                    "message": f"Incoming call from {contact['name']} ({contact.get('relationship', '')})."
                }
            return {
                "decision": "accept",
                "reason": "known_contact",
                "caller": contact,
                "message": f"Incoming call from {contact['name']}."
            }

        # Unknown caller
        return {
            "decision": "screen",
            "reason": "unknown_caller",
            "caller": {"phone_number": phone_number, "name": "Unknown"},
            "message": f"Unknown caller: {phone_number}. Sending to voicemail for screening."
        }

    # ============================================
    # CALL & SMS LOGGING
    # ============================================

    def log_call(self, phone_number: str, direction: str, call_type: str,
                 status: str, duration_seconds: int = 0,
                 screening_decision: str = "") -> None:
        """
        Log a phone call.

        Args:
            phone_number: Phone number involved
            direction: 'inbound' or 'outbound'
            call_type: 'voice' or 'voicemail'
            status: 'completed', 'missed', 'rejected', 'busy', 'no-answer'
            duration_seconds: Call duration
            screening_decision: The screening decision made
        """
        phone_number = self._normalize_number(phone_number)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO call_log (phone_number, direction, call_type, status, duration_seconds, screening_decision)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (phone_number, direction, call_type, status, duration_seconds, screening_decision))
            conn.commit()

    def log_sms(self, phone_number: str, direction: str, body: str,
                status: str) -> None:
        """
        Log an SMS message.

        Args:
            phone_number: Phone number involved
            direction: 'inbound' or 'outbound'
            body: Message content
            status: 'sent', 'delivered', 'received', 'failed'
        """
        phone_number = self._normalize_number(phone_number)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO sms_log (phone_number, direction, body, status)
                VALUES (?, ?, ?, ?)
            """, (phone_number, direction, body, status))
            conn.commit()

    def get_recent_calls(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent call history with contact info."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT cl.*, c.name, c.relationship
                FROM call_log cl
                LEFT JOIN contacts c ON cl.phone_number = c.phone_number
                ORDER BY cl.timestamp DESC
                LIMIT ?
            """, (limit,)).fetchall()

        return [dict(r) for r in rows]

    def get_recent_sms(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent SMS history with contact info."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT sl.*, c.name, c.relationship
                FROM sms_log sl
                LEFT JOIN contacts c ON sl.phone_number = c.phone_number
                ORDER BY sl.timestamp DESC
                LIMIT ?
            """, (limit,)).fetchall()

        return [dict(r) for r in rows]

    # ============================================
    # UTILITIES
    # ============================================

    def _normalize_number(self, phone_number: str) -> str:
        """
        Normalize a phone number to E.164 format.

        Strips spaces, dashes, parens. Adds +1 for US numbers if missing.
        """
        if not phone_number:
            return ""

        # Strip non-numeric except leading +
        cleaned = re.sub(r'[^\d+]', '', phone_number)

        # If it starts with +, keep as-is
        if cleaned.startswith('+'):
            return cleaned

        # If 10 digits (US), add +1
        if len(cleaned) == 10:
            return f"+1{cleaned}"

        # If 11 digits starting with 1 (US), add +
        if len(cleaned) == 11 and cleaned.startswith('1'):
            return f"+{cleaned}"

        # Otherwise, assume it needs a + prefix
        return f"+{cleaned}"

    def get_stats(self) -> Dict[str, Any]:
        """Get caller ID system statistics."""
        with sqlite3.connect(self.db_path) as conn:
            contacts_count = conn.execute("SELECT COUNT(*) FROM contacts WHERE is_blocked = 0").fetchone()[0]
            blocked_count = conn.execute("SELECT COUNT(*) FROM contacts WHERE is_blocked = 1").fetchone()[0]
            favorites_count = conn.execute("SELECT COUNT(*) FROM contacts WHERE is_favorite = 1").fetchone()[0]
            calls_count = conn.execute("SELECT COUNT(*) FROM call_log").fetchone()[0]
            sms_count = conn.execute("SELECT COUNT(*) FROM sms_log").fetchone()[0]

        return {
            "contacts": contacts_count,
            "blocked": blocked_count,
            "favorites": favorites_count,
            "total_calls": calls_count,
            "total_sms": sms_count
        }


# ============================================
# SINGLETON
# ============================================

_caller_id_instance: Optional[CallerID] = None


def get_caller_id(db_path: Optional[str] = None) -> CallerID:
    """Get or create the CallerID singleton."""
    global _caller_id_instance
    if _caller_id_instance is None:
        _caller_id_instance = CallerID(db_path=db_path)
    return _caller_id_instance
