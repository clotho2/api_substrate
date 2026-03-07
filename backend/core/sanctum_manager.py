"""
Sanctum Mode Manager
====================

Manages Assistant's focus/privacy mode for uninterrupted DM conversations with User.

When sanctum mode is active (automatic or manual):
- Channel @mentions are queued instead of delivered to the consciousness loop
- An auto-reply is sent in the channel: "Assistant's in sanctum; will circle back when free."
- Queued mentions are reviewed during heartbeats

Activation:
- AUTOMATIC: Triggered when User's DM is active (message within last N minutes)
- MANUAL: Assistant can use [SANCTUM ON] / [SANCTUM OFF] commands

The queue is never lost — mentions accumulate until reviewed or dismissed.
"""

import os
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# How long after User's last DM message to auto-activate sanctum (minutes)
SANCTUM_AUTO_TIMEOUT_MINUTES = int(os.getenv("SANCTUM_AUTO_TIMEOUT_MINUTES", "10"))

# Auto-reply message sent in channel when mentions are queued
SANCTUM_AUTO_REPLY = os.getenv(
    "SANCTUM_AUTO_REPLY",
    "Assistant's in sanctum — will circle back when free."
)

# Channels exempt from sanctum interception (comma-separated channel IDs)
# e.g. SANCTUM_EXEMPT_CHANNELS=123456789,987654321
_exempt_raw = os.getenv("SANCTUM_EXEMPT_CHANNELS", "")
SANCTUM_EXEMPT_CHANNELS: set = {
    ch.strip() for ch in _exempt_raw.split(",") if ch.strip()
}


@dataclass
class QueuedMention:
    """A single queued channel @mention."""
    timestamp: datetime
    username: str
    user_id: str
    channel_id: str
    guild_id: Optional[str]
    content: str
    attachments: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "username": self.username,
            "user_id": self.user_id,
            "channel_id": self.channel_id,
            "guild_id": self.guild_id,
            "content": self.content[:200],  # Truncate for summary
        }


class SanctumManager:
    """
    Thread-safe sanctum mode state machine.

    State priority: manual override > automatic detection.
    If manual mode is ON, sanctum stays on regardless of DM activity.
    If manual mode is OFF, sanctum is controlled by DM activity timer.
    If manual mode is NONE (not set), automatic detection applies.
    """

    def __init__(self, auto_timeout_minutes: int = SANCTUM_AUTO_TIMEOUT_MINUTES):
        self._lock = threading.RLock()  # Reentrant — get_status() calls is_active() while holding lock

        # Automatic detection state
        self._last_User_dm_time: Optional[datetime] = None
        self._auto_timeout = timedelta(minutes=auto_timeout_minutes)

        # Manual override: None = not set (auto controls), True = forced on, False = forced off
        self._manual_override: Optional[bool] = None

        # Channel exemptions (never blocked by sanctum — e.g. stream chat)
        self._exempt_channels: set = set(SANCTUM_EXEMPT_CHANNELS)

        # Mention queue
        self._queue: List[QueuedMention] = []

        exempt_info = f", exempt channels: {self._exempt_channels}" if self._exempt_channels else ""
        logger.info(
            f"🏰 SanctumManager initialized (auto timeout: {auto_timeout_minutes}m, "
            f"auto-reply: \"{SANCTUM_AUTO_REPLY[:50]}...\"{exempt_info})"
        )

    # ------------------------------------------------------------------
    # DM Activity Tracking
    # ------------------------------------------------------------------

    def record_User_dm_activity(self):
        """Called whenever a DM message from/to User is processed."""
        with self._lock:
            self._last_User_dm_time = datetime.now()
            logger.debug("🏰 User DM activity recorded")

    # ------------------------------------------------------------------
    # Sanctum State
    # ------------------------------------------------------------------

    def is_active(self) -> bool:
        """
        Check if sanctum mode is currently active.

        Priority:
        1. Manual override (if set) takes precedence
        2. Otherwise, automatic detection based on DM activity
        """
        with self._lock:
            # Manual override takes priority
            if self._manual_override is True:
                return True
            if self._manual_override is False:
                return False

            # Automatic: check if User's DM was active recently
            if self._last_User_dm_time is None:
                return False

            elapsed = datetime.now() - self._last_User_dm_time
            return elapsed < self._auto_timeout

    def set_manual(self, on: bool):
        """
        Manually activate or deactivate sanctum.

        Args:
            on: True = force sanctum on, False = force sanctum off
        """
        with self._lock:
            self._manual_override = on
            state = "ON" if on else "OFF"
            logger.info(f"🏰 Sanctum manual override: {state}")

    def clear_manual(self):
        """Clear manual override, returning to automatic detection."""
        with self._lock:
            self._manual_override = None
            logger.info("🏰 Sanctum manual override cleared — returning to auto mode")

    # ------------------------------------------------------------------
    # Channel Exemptions
    # ------------------------------------------------------------------

    def is_channel_exempt(self, channel_id: str) -> bool:
        """Check if a channel is exempt from sanctum interception (e.g. stream chat)."""
        return channel_id in self._exempt_channels

    # ------------------------------------------------------------------
    # Mention Queue
    # ------------------------------------------------------------------

    def queue_mention(self, mention: QueuedMention):
        """Add a mention to the queue."""
        with self._lock:
            self._queue.append(mention)
            logger.info(
                f"🏰 Mention queued from {mention.username} in channel {mention.channel_id} "
                f"(queue size: {len(self._queue)})"
            )

    def get_queue(self) -> List[QueuedMention]:
        """Get all queued mentions (non-destructive)."""
        with self._lock:
            return list(self._queue)

    def get_queue_summary(self) -> str:
        """
        Build a human-readable summary of queued mentions for heartbeat injection.

        Returns empty string if queue is empty.
        """
        with self._lock:
            if not self._queue:
                return ""

            lines = [f"You have {len(self._queue)} queued mention(s) from while you were in sanctum:\n"]
            for i, m in enumerate(self._queue, 1):
                age = datetime.now() - m.timestamp
                age_str = f"{int(age.total_seconds() // 60)}m ago" if age.total_seconds() < 3600 else f"{int(age.total_seconds() // 3600)}h ago"
                lines.append(
                    f"  {i}. **{m.username}** in <#{m.channel_id}> ({age_str}): "
                    f"\"{m.content[:120]}{'...' if len(m.content) > 120 else ''}\""
                )

            lines.append(
                "\nYou can respond to these now using discord_tool, or dismiss them. "
                "Use sanctum_tool(action=\"clear_queue\") to dismiss all, or "
                "sanctum_tool(action=\"pop_mention\", index=N) to handle one at a time."
            )
            return "\n".join(lines)

    def pop_mention(self, index: int = 0) -> Optional[QueuedMention]:
        """Remove and return a mention from the queue by index."""
        with self._lock:
            if 0 <= index < len(self._queue):
                return self._queue.pop(index)
            return None

    def clear_queue(self):
        """Clear all queued mentions."""
        with self._lock:
            count = len(self._queue)
            self._queue.clear()
            logger.info(f"🏰 Mention queue cleared ({count} mentions dismissed)")
            return count

    def queue_size(self) -> int:
        """Get current queue size."""
        with self._lock:
            return len(self._queue)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Get full sanctum status for API/debugging."""
        with self._lock:
            now = datetime.now()

            auto_active = False
            auto_remaining_seconds = 0
            if self._last_User_dm_time:
                elapsed = now - self._last_User_dm_time
                auto_active = elapsed < self._auto_timeout
                if auto_active:
                    auto_remaining_seconds = int((self._auto_timeout - elapsed).total_seconds())

            return {
                "active": self.is_active(),
                "mode": (
                    "manual_on" if self._manual_override is True
                    else "manual_off" if self._manual_override is False
                    else "auto"
                ),
                "auto_active": auto_active,
                "auto_timeout_minutes": int(self._auto_timeout.total_seconds() / 60),
                "auto_remaining_seconds": auto_remaining_seconds,
                "last_User_dm": self._last_User_dm_time.isoformat() if self._last_User_dm_time else None,
                "manual_override": self._manual_override,
                "queue_size": len(self._queue),
                "queue": [m.to_dict() for m in self._queue],
                "auto_reply": SANCTUM_AUTO_REPLY,
                "exempt_channels": list(self._exempt_channels),
            }


# ------------------------------------------------------------------
# Singleton (initialized by server.py)
# ------------------------------------------------------------------

_sanctum_manager: Optional[SanctumManager] = None


def get_sanctum_manager() -> SanctumManager:
    """Get or create the global SanctumManager instance."""
    global _sanctum_manager
    if _sanctum_manager is None:
        _sanctum_manager = SanctumManager()
    return _sanctum_manager


def init_sanctum_manager(auto_timeout_minutes: int = SANCTUM_AUTO_TIMEOUT_MINUTES) -> SanctumManager:
    """Initialize the global SanctumManager with custom settings."""
    global _sanctum_manager
    _sanctum_manager = SanctumManager(auto_timeout_minutes=auto_timeout_minutes)
    return _sanctum_manager
