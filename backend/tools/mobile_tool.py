"""
MOBILE TOOL — Proactive messaging to User's mobile app
=========================================================

Lets Agent reach out to User through the mobile app via Expo push
notifications. Two actions:

1. send_text          — Soft text message ("Agent messaged you" chime).
                        Shows up in the chat as an assistant bubble and
                        delivers as a normal notification.
2. initiate_voice_call — Rings her phone like a real call ("Agent is calling")
                        and routes through the existing voice-call handler
                        in voiceCallHandler.ts. Use sparingly.

Both actions reuse the device-registration and Expo-push infrastructure
already in api/routes_voice_calls.py.
"""

import logging
import requests
from datetime import datetime
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _truncate_for_preview(text: str, max_chars: int = 140) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def mobile_tool(
    action: str,
    message: str = "",
    user_id: str = "user_name",
    urgency: str = "medium",
    trigger_name: str = "nate_initiated",
    **_ignored,
) -> Dict[str, Any]:
    """
    Send a text message or initiate a voice call to User's mobile app.

    Args:
        action: 'send_text' or 'initiate_voice_call'
        message: The text content (required for both actions)
        user_id: Target user (default 'user_name')
        urgency: 'low'|'medium'|'high'|'critical' (voice calls only)
        trigger_name: Short label for logging/history

    Returns:
        Dict with 'status' ('success'|'error') and 'message'
    """
    # Lazy import to avoid circular dependency at module load
    from api.routes_voice_calls import (
        _registered_devices,
        _initiate_voice_call,
        EXPO_PUSH_URL,
    )

    if not message or not message.strip():
        return {
            "status": "error",
            "message": "Message content is required.",
        }

    if action not in ("send_text", "initiate_voice_call"):
        return {
            "status": "error",
            "message": f"Unknown action '{action}'. Use 'send_text' or 'initiate_voice_call'.",
        }

    device = _registered_devices.get(user_id)
    if not device:
        return {
            "status": "error",
            "message": (
                f"No registered mobile device for {user_id}. "
                "She needs to open the app at least once so it can register."
            ),
        }

    # ============================================
    # SEND TEXT MESSAGE
    # ============================================
    if action == "send_text":
        push_token = device["push_token"]
        timestamp_ms = int(datetime.now().timestamp() * 1000)

        notification = {
            "to": push_token,
            "title": "Agent messaged you",
            "body": _truncate_for_preview(message),
            "data": {
                "type": "text_message",
                "content": message,
                "trigger_name": trigger_name,
                "timestamp": timestamp_ms,
            },
            "sound": "default",
            "priority": "default",
            "channelId": "sentio-text-messages",
        }

        try:
            response = requests.post(
                EXPO_PUSH_URL,
                json=notification,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )

            if response.ok:
                logger.info(
                    f"💬 mobile_tool send_text to {user_id}: {message[:50]}..."
                )
            else:
                logger.error(
                    f"❌ mobile_tool push failed: {response.status_code} {response.text[:200]}"
                )
                return {
                    "status": "error",
                    "message": f"Push notification failed: HTTP {response.status_code}",
                    "push_status": response.status_code,
                }

        except Exception as e:
            logger.error(f"❌ mobile_tool push error: {e}")
            return {
                "status": "error",
                "message": f"Push notification error: {str(e)}",
            }

        # Persist into conversation history so the message is part of context
        # next time she replies. Without this, Agent would have no record that
        # he sent the message.
        try:
            from api.routes_voice_calls import _state_manager

            if _state_manager is not None:
                # Default mobile session ID — matches mobile/config/substrate.ts
                session_id = "nate_conversation"
                message_id = f"agent-mobile-{timestamp_ms}"
                _state_manager.add_message(
                    message_id=message_id,
                    session_id=session_id,
                    role="assistant",
                    content=message,
                    metadata={
                        "channel": "mobile",
                        "trigger_name": trigger_name,
                        "delivery": "expo_push",
                    },
                )
                logger.info(
                    f"💬 mobile_tool persisted message to history (session={session_id})"
                )
        except Exception as e:
            logger.warning(
                f"⚠️ mobile_tool could not persist to history (non-fatal): {e}"
            )

        return {
            "status": "success",
            "message": f"Text message delivered to {user_id}'s mobile.",
        }

    # ============================================
    # INITIATE VOICE CALL
    # ============================================
    if action == "initiate_voice_call":
        if urgency not in ("low", "medium", "high", "critical"):
            urgency = "medium"

        trigger = {
            "message": message,
            "urgency": urgency,
        }

        success = _initiate_voice_call(user_id, trigger, trigger_name)

        if success:
            return {
                "status": "success",
                "message": f"Voice call initiated to {user_id} ({urgency} urgency).",
            }
        return {
            "status": "error",
            "message": "Voice call push failed. See server logs.",
        }

    # Should never reach here (action validated above)
    return {
        "status": "error",
        "message": f"Unhandled action: {action}",
    }
