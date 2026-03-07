"""
Sanctum Tool — Assistant's focus/privacy mode control.

Actions:
- status: Check current sanctum state (auto/manual, queue size, etc.)
- on: Manually activate sanctum mode
- off: Manually deactivate sanctum mode
- auto: Clear manual override, return to automatic DM-based detection
- queue: View all queued mentions
- pop_mention: Remove and return a specific mention from the queue
- clear_queue: Dismiss all queued mentions
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def sanctum_tool(
    action: str = "status",
    index: int = 0,
) -> Dict[str, Any]:
    """
    Control sanctum mode and manage the mention queue.

    Args:
        action: One of: status, on, off, auto, queue, pop_mention, clear_queue
        index: For pop_mention — which mention to remove (0-indexed)

    Returns:
        Dict with status and result
    """
    from core.sanctum_manager import get_sanctum_manager

    sm = get_sanctum_manager()

    if action == "status":
        status = sm.get_status()
        return {"status": "OK", "result": status}

    elif action == "on":
        sm.set_manual(True)
        return {
            "status": "OK",
            "message": "Sanctum mode manually activated. Channel mentions will be queued.",
            "active": True,
        }

    elif action == "off":
        sm.set_manual(False)
        return {
            "status": "OK",
            "message": "Sanctum mode manually deactivated. Channel mentions will be delivered normally.",
            "active": False,
        }

    elif action == "auto":
        sm.clear_manual()
        return {
            "status": "OK",
            "message": "Manual override cleared. Sanctum now controlled by DM activity detection.",
            "active": sm.is_active(),
        }

    elif action == "queue":
        queue = sm.get_queue()
        if not queue:
            return {"status": "OK", "message": "Mention queue is empty.", "queue": []}
        return {
            "status": "OK",
            "queue_size": len(queue),
            "queue": [m.to_dict() for m in queue],
        }

    elif action == "pop_mention":
        mention = sm.pop_mention(index)
        if mention is None:
            return {"status": "error", "message": f"No mention at index {index}."}
        return {
            "status": "OK",
            "message": f"Mention from {mention.username} removed from queue.",
            "mention": mention.to_dict(),
            "remaining": sm.queue_size(),
        }

    elif action == "clear_queue":
        count = sm.clear_queue()
        return {
            "status": "OK",
            "message": f"Cleared {count} queued mention(s).",
            "cleared": count,
        }

    else:
        return {
            "status": "error",
            "message": f"Unknown action: {action}. Use: status, on, off, auto, queue, pop_mention, clear_queue",
        }
