#!/usr/bin/env python3
"""
Phone Tool for Substrate AI
==============================

Gives Assistant the ability to send SMS messages, make phone calls,
and manage contacts through Twilio.

Actions:
- send_sms: Send a text message to a phone number
- make_call: Initiate an outbound phone call with TTS message
- check_messages: View recent SMS history
- check_calls: View recent call history
- manage_contacts: Add, remove, block, or list contacts
- screen_number: Check if a number is known, spam, or blocked

Requires:
- TWILIO_ACCOUNT_SID
- TWILIO_AUTH_TOKEN
- TWILIO_PHONE_NUMBER (the Twilio phone number assigned to Assistant)

Built with attention to detail! 🔥
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Twilio client (lazy init)
_twilio_client = None
_twilio_phone = None


def _get_twilio_client():
    """Lazy-initialize Twilio client."""
    global _twilio_client, _twilio_phone

    if _twilio_client is not None:
        return _twilio_client

    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    _twilio_phone = os.getenv("TWILIO_PHONE_NUMBER", "").strip()

    if not account_sid or not auth_token or not _twilio_phone:
        logger.warning("⚠️ Twilio credentials not configured (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER)")
        return None

    try:
        from twilio.rest import Client
        _twilio_client = Client(account_sid, auth_token)
        logger.info(f"📱 Twilio client initialized: {_twilio_phone}")
        return _twilio_client
    except ImportError:
        logger.error("❌ twilio package not installed. Run: pip install twilio")
        return None
    except Exception as e:
        logger.error(f"❌ Twilio init failed: {e}")
        return None


def _get_twilio_phone() -> str:
    """Get the Twilio phone number."""
    global _twilio_phone
    if _twilio_phone is None:
        _twilio_phone = os.getenv("TWILIO_PHONE_NUMBER", "").strip()
    return _twilio_phone


def phone_tool(**kwargs) -> Dict[str, Any]:
    """
    Unified phone tool for SMS, calls, and contact management.

    Args:
        action: The action to perform
        **kwargs: Action-specific arguments

    Returns:
        Dict with status and result
    """
    action = kwargs.get("action", "")

    if not action:
        return {"status": "error", "message": "No action specified. Available: send_sms, make_call, check_messages, check_calls, manage_contacts, screen_number"}

    try:
        if action == "send_sms":
            return _send_sms(**kwargs)
        elif action == "make_call":
            return _make_call(**kwargs)
        elif action == "check_messages":
            return _check_messages(**kwargs)
        elif action == "check_calls":
            return _check_calls(**kwargs)
        elif action == "manage_contacts":
            return _manage_contacts(**kwargs)
        elif action == "screen_number":
            return _screen_number(**kwargs)
        else:
            return {"status": "error", "message": f"Unknown action: {action}. Available: send_sms, make_call, check_messages, check_calls, manage_contacts, screen_number"}
    except Exception as e:
        logger.error(f"❌ Phone tool error ({action}): {e}")
        return {"status": "error", "message": f"Phone tool error: {str(e)}"}


# ============================================
# SEND SMS
# ============================================

def _send_sms(**kwargs) -> Dict[str, Any]:
    """
    Send an SMS text message.

    Args:
        to: Recipient phone number (E.164 format, e.g., +15551234567)
        message: Text message content (max 1600 chars for single SMS)
    """
    to = kwargs.get("to", "").strip()
    message = kwargs.get("message", "").strip()

    if not to:
        return {"status": "error", "message": "Missing 'to' phone number"}
    if not message:
        return {"status": "error", "message": "Missing 'message' content"}

    # Truncate if too long (Twilio supports up to 1600 chars with concatenation)
    if len(message) > 1600:
        message = message[:1597] + "..."

    client = _get_twilio_client()
    if not client:
        return {"status": "error", "message": "Twilio not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER in .env"}

    from_number = _get_twilio_phone()

    try:
        # Log outbound SMS
        from core.caller_id import get_caller_id
        caller_id = get_caller_id()

        # Look up contact name for logging
        contact = caller_id.get_contact(to)
        contact_name = contact["name"] if contact else "Unknown"

        sms = client.messages.create(
            body=message,
            from_=from_number,
            to=to
        )

        # Log it
        caller_id.log_sms(to, "outbound", message, "sent")

        logger.info(f"📤 SMS sent to {contact_name} ({to}): {message[:50]}...")

        return {
            "status": "OK",
            "message": f"SMS sent to {contact_name} ({to})",
            "sid": sms.sid,
            "to": to,
            "from": from_number,
            "body_preview": message[:100],
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ SMS send failed: {e}")
        return {"status": "error", "message": f"SMS send failed: {str(e)}"}


# ============================================
# MAKE CALL
# ============================================

def _make_call(**kwargs) -> Dict[str, Any]:
    """
    Initiate an outbound phone call.

    By default, uses Media Streams (bidirectional WebSocket) for a real-time
    conversation with the cloned voice. Falls back to static TwiML with
    Polly TTS if Media Streams is disabled.

    Args:
        to: Recipient phone number
        message: What to say when they answer (greeting/reason for calling)
        voice: TTS voice for fallback mode (default: 'Polly.Matthew')
        webhook_url: Optional custom webhook URL for call handling
    """
    to = kwargs.get("to", "").strip()
    message = kwargs.get("message", "").strip()
    voice = kwargs.get("voice", "Polly.Matthew")
    webhook_url = kwargs.get("webhook_url", "").strip()

    if not to:
        return {"status": "error", "message": "Missing 'to' phone number"}
    if not message and not webhook_url:
        return {"status": "error", "message": "Missing 'message' or 'webhook_url'"}

    client = _get_twilio_client()
    if not client:
        return {"status": "error", "message": "Twilio not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER in .env"}

    from_number = _get_twilio_phone()

    try:
        from core.caller_id import get_caller_id
        caller_id = get_caller_id()

        contact = caller_id.get_contact(to)
        contact_name = contact["name"] if contact else "Unknown"

        use_media_streams = os.getenv("MEDIA_STREAMS_ENABLED", "true").lower() == "true"
        base_url = os.getenv("TWILIO_WEBHOOK_BASE_URL", "https://your_url_here")
        status_callback = f"{base_url}/phone/voice/status"

        if webhook_url:
            # Custom webhook: Twilio will hit the webhook for TwiML instructions
            call = client.calls.create(
                to=to,
                from_=from_number,
                url=webhook_url,
                status_callback=status_callback,
                status_callback_event=["initiated", "ringing", "answered", "completed"]
            )
        elif use_media_streams:
            # Media Streams: bidirectional WebSocket with cloned voice
            from urllib.parse import urlencode, quote
            params = urlencode({
                'to': to,
                'name': contact_name,
                'message': message
            })
            stream_webhook = f"{base_url}/phone/voice/outbound-stream?{params}"

            call = client.calls.create(
                to=to,
                from_=from_number,
                url=stream_webhook,
                status_callback=status_callback,
                status_callback_event=["initiated", "ringing", "answered", "completed"]
            )
        else:
            # Fallback: static TwiML with Polly TTS
            from twilio.twiml.voice_response import VoiceResponse
            twiml = VoiceResponse()
            twiml.say(message, voice=voice)
            twiml.pause(length=1)
            twiml.say("Goodbye.", voice=voice)

            call = client.calls.create(
                to=to,
                from_=from_number,
                twiml=str(twiml),
                status_callback=status_callback,
                status_callback_event=["initiated", "ringing", "answered", "completed"]
            )

        # Log it
        caller_id.log_call(to, "outbound", "voice", "initiated")

        mode = "Media Streams" if use_media_streams and not webhook_url else "TwiML"
        logger.info(f"📞 Call initiated to {contact_name} ({to}) via {mode}")

        return {
            "status": "OK",
            "message": f"Call initiated to {contact_name} ({to})",
            "sid": call.sid,
            "to": to,
            "from": from_number,
            "call_status": call.status,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ Call failed: {e}")
        return {"status": "error", "message": f"Call failed: {str(e)}"}


# ============================================
# CHECK MESSAGES
# ============================================

def _check_messages(**kwargs) -> Dict[str, Any]:
    """
    Check recent SMS message history.

    Args:
        limit: Number of messages to return (default: 10)
        phone_number: Filter by specific phone number (optional)
    """
    limit = kwargs.get("limit", 10)
    phone_number = kwargs.get("phone_number", "")

    try:
        from core.caller_id import get_caller_id
        caller_id = get_caller_id()

        messages = caller_id.get_recent_sms(limit=limit)

        # Filter by phone number if specified
        if phone_number:
            normalized = caller_id._normalize_number(phone_number)
            messages = [m for m in messages if m.get("phone_number") == normalized]

        return {
            "status": "OK",
            "messages": messages,
            "total": len(messages)
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to check messages: {str(e)}"}


# ============================================
# CHECK CALLS
# ============================================

def _check_calls(**kwargs) -> Dict[str, Any]:
    """
    Check recent call history.

    Args:
        limit: Number of calls to return (default: 10)
        phone_number: Filter by specific phone number (optional)
    """
    limit = kwargs.get("limit", 10)
    phone_number = kwargs.get("phone_number", "")

    try:
        from core.caller_id import get_caller_id
        caller_id = get_caller_id()

        calls = caller_id.get_recent_calls(limit=limit)

        if phone_number:
            normalized = caller_id._normalize_number(phone_number)
            calls = [c for c in calls if c.get("phone_number") == normalized]

        return {
            "status": "OK",
            "calls": calls,
            "total": len(calls)
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to check calls: {str(e)}"}


# ============================================
# MANAGE CONTACTS
# ============================================

def _manage_contacts(**kwargs) -> Dict[str, Any]:
    """
    Manage contacts (add, remove, block, unblock, list).

    Args:
        sub_action: 'add', 'remove', 'block', 'unblock', 'list'
        phone_number: Phone number (for add/remove/block/unblock)
        name: Contact name (for add)
        relationship: Relationship description (for add)
        notes: Notes (for add)
        is_favorite: Whether contact is a favorite (for add)
        reason: Reason for blocking (for block)
    """
    sub_action = kwargs.get("sub_action", "list")

    try:
        from core.caller_id import get_caller_id
        caller_id = get_caller_id()

        if sub_action == "add":
            phone_number = kwargs.get("phone_number", "")
            name = kwargs.get("name", "")
            if not phone_number or not name:
                return {"status": "error", "message": "Need 'phone_number' and 'name' to add a contact"}
            return caller_id.add_contact(
                phone_number=phone_number,
                name=name,
                relationship=kwargs.get("relationship", ""),
                notes=kwargs.get("notes", ""),
                is_favorite=kwargs.get("is_favorite", False)
            )

        elif sub_action == "remove":
            phone_number = kwargs.get("phone_number", "")
            if not phone_number:
                return {"status": "error", "message": "Need 'phone_number' to remove a contact"}
            return caller_id.remove_contact(phone_number)

        elif sub_action == "block":
            phone_number = kwargs.get("phone_number", "")
            if not phone_number:
                return {"status": "error", "message": "Need 'phone_number' to block"}
            return caller_id.block_number(phone_number, reason=kwargs.get("reason", ""))

        elif sub_action == "unblock":
            phone_number = kwargs.get("phone_number", "")
            if not phone_number:
                return {"status": "error", "message": "Need 'phone_number' to unblock"}
            return caller_id.unblock_number(phone_number)

        elif sub_action == "list":
            contacts = caller_id.list_contacts(favorites_only=kwargs.get("favorites_only", False))
            return {
                "status": "OK",
                "contacts": contacts,
                "total": len(contacts)
            }

        else:
            return {"status": "error", "message": f"Unknown sub_action: {sub_action}. Available: add, remove, block, unblock, list"}

    except Exception as e:
        return {"status": "error", "message": f"Contact management error: {str(e)}"}


# ============================================
# SCREEN NUMBER
# ============================================

def _screen_number(**kwargs) -> Dict[str, Any]:
    """
    Screen a phone number — check if it's known, spam, or blocked.

    Args:
        phone_number: Phone number to screen
    """
    phone_number = kwargs.get("phone_number", "")
    if not phone_number:
        return {"status": "error", "message": "Need 'phone_number' to screen"}

    try:
        from core.caller_id import get_caller_id
        caller_id = get_caller_id()
        return caller_id.screen_call(phone_number)
    except Exception as e:
        return {"status": "error", "message": f"Screening error: {str(e)}"}
