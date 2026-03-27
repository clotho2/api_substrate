#!/usr/bin/env python3
"""
Phone Routes (Twilio Webhooks) for Substrate AI
==================================================

Handles inbound SMS and voice calls via Twilio webhooks.
Routes incoming messages through the consciousness loop so Assistant
can receive and respond to texts and calls.

Endpoints:
- POST /phone/sms/incoming       - Twilio webhook for incoming SMS
- POST /phone/voice/incoming      - Twilio webhook for incoming voice calls
- POST /phone/voice/gather        - Handle voice input (speech-to-text from caller)
- POST /phone/voice/status        - Call status callback
- POST /phone/sms/status          - SMS delivery status callback
- GET  /phone/health              - Health check

Webhook URL setup:
  Configure in Twilio Console → Phone Numbers → Your Number:
  - SMS webhook:   https://your_url_here/phone/sms/incoming
  - Voice webhook: https://your_url_here/phone/voice/incoming
  - Status callback: https://your_url_here/phone/voice/status

Built with attention to detail! 🔥
"""

import os
import asyncio
import logging
import uuid
import time
import threading
from datetime import datetime
from flask import Blueprint, request, jsonify, Response
from typing import Dict, Any, Optional

from core.config import get_model_or_default

logger = logging.getLogger(__name__)

# Create blueprint
phone_bp = Blueprint('phone', __name__)

# ============================================
# TTS AUDIO CACHE (serves generated audio to Twilio)
# ============================================
# Stores TTS-generated audio in memory so Twilio can fetch it via <Play> URL.
# Audio is cleaned up after 5 minutes.
_audio_cache: Dict[str, Dict[str, Any]] = {}
_audio_cache_lock = threading.Lock()
_AUDIO_CACHE_TTL = 300  # 5 minutes

# Global dependencies (injected via init_phone_routes)
_consciousness_loop = None
_state_manager = None
_rate_limiter = None


def _get_current_model() -> str:
    """
    Get the currently configured model.

    Uses get_model_or_default() which reads from env vars directly.
    This matches the config endpoint (/api/agents/<id>/config) that the
    frontend uses, ensuring the phone routes use the same model.
    """
    return get_model_or_default()


def init_phone_routes(consciousness_loop, state_manager, rate_limiter=None):
    """
    Initialize phone routes with dependencies.

    Args:
        consciousness_loop: ConsciousnessLoop instance
        state_manager: StateManager instance
        rate_limiter: Optional rate limiter
    """
    global _consciousness_loop, _state_manager, _rate_limiter
    _consciousness_loop = consciousness_loop
    _state_manager = state_manager
    _rate_limiter = rate_limiter
    logger.info("📱 Phone routes initialized (Twilio webhooks)")


# ============================================
# TTS AUDIO GENERATION & SERVING
# ============================================

def _cleanup_audio_cache():
    """Remove expired audio entries from cache."""
    now = time.time()
    with _audio_cache_lock:
        expired = [k for k, v in _audio_cache.items()
                   if now - v["created_at"] > _AUDIO_CACHE_TTL]
        for k in expired:
            del _audio_cache[k]
        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired audio entries")


def _generate_tts_audio(text: str) -> Optional[str]:
    """
    Generate TTS audio for phone calls.

    Tries providers in order:
    1. Pocket TTS (local, cloned voice, free)
    2. Amazon Polly (AWS, neural voices, cheap)
    3. Returns None → caller falls back to Twilio <Say voice="Polly.XXX">

    Returns a public URL that Twilio can fetch via <Play>, or None on failure.
    """
    import requests as http_requests

    # --- Try Pocket TTS first (local, free) ---
    pockettts_url = os.getenv("POCKETTTS_URL", "http://localhost:8001")
    pockettts_timeout = int(os.getenv("POCKETTTS_TIMEOUT", "30"))

    try:
        response = http_requests.post(
            f"{pockettts_url}/v1/audio/speech",
            data={"text": text, "voice": "Assistant"},
            timeout=pockettts_timeout
        )

        if response.status_code == 200:
            audio_data = response.content
            content_type = response.headers.get("Content-Type", "audio/wav")
            audio_url = _cache_audio(audio_data, content_type)
            logger.info(f"🎙️ TTS audio generated via Pocket TTS ({len(audio_data)} bytes)")
            return audio_url

        logger.warning(f"Pocket TTS returned {response.status_code}: {response.text[:200]}")

    except http_requests.ConnectionError:
        logger.warning("⚠️ Pocket TTS not reachable at %s, trying Polly", pockettts_url)
    except http_requests.Timeout:
        logger.warning("⚠️ Pocket TTS timed out after %ds, trying Polly", pockettts_timeout)
    except Exception as e:
        logger.warning(f"⚠️ Pocket TTS failed, trying Polly: {e}")

    # --- Try Amazon Polly (cheap, high quality neural voices) ---
    if os.getenv("AWS_ACCESS_KEY_ID"):
        try:
            import boto3

            region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
            voice_id = os.getenv("POLLY_VOICE_ID", "Matthew")
            engine = os.getenv("POLLY_ENGINE", "neural")

            polly = boto3.client("polly", region_name=region)
            result = polly.synthesize_speech(
                Text=text,
                TextType="text",
                OutputFormat="mp3",
                VoiceId=voice_id,
                Engine=engine,
            )

            audio_data = result["AudioStream"].read()
            audio_url = _cache_audio(audio_data, "audio/mpeg")
            logger.info(f"🎙️ TTS audio generated via Polly ({len(audio_data)} bytes, voice: {voice_id})")
            return audio_url

        except Exception as e:
            logger.warning(f"⚠️ Amazon Polly failed, falling back to Twilio <Say>: {e}")

    return None


def _cache_audio(audio_data: bytes, content_type: str) -> str:
    """Store audio in the in-memory cache and return a public URL for Twilio."""
    audio_id = str(uuid.uuid4())
    with _audio_cache_lock:
        _audio_cache[audio_id] = {
            "data": audio_data,
            "content_type": content_type,
            "created_at": time.time()
        }

    _cleanup_audio_cache()

    base_url = os.getenv("TWILIO_WEBHOOK_BASE_URL", "https://your_url_here")
    return f"{base_url}/phone/audio/{audio_id}"


@phone_bp.route('/phone/audio/<audio_id>', methods=['GET'])
def serve_audio(audio_id):
    """
    Serve TTS-generated audio to Twilio.

    Twilio fetches this URL when processing a <Play> TwiML verb.
    Audio is stored in-memory with a 5-minute TTL.
    """
    with _audio_cache_lock:
        audio = _audio_cache.get(audio_id)

    if not audio:
        logger.warning(f"Audio not found: {audio_id}")
        return Response("Not found", status=404)

    return Response(
        audio["data"],
        content_type=audio["content_type"],
        headers={"Cache-Control": "no-cache"}
    )


# ============================================
# INCOMING SMS WEBHOOK
# ============================================

@phone_bp.route('/phone/sms/incoming', methods=['POST'])
def incoming_sms():
    """
    Twilio webhook for incoming SMS messages.

    Twilio sends form data with:
    - From: Sender's phone number
    - To: Your Twilio number
    - Body: Message text
    - MessageSid: Unique message ID
    - NumMedia: Number of media attachments

    We route the message through the consciousness loop and
    reply via TwiML <Message> response.
    """
    try:
        # Extract Twilio form data
        from_number = request.form.get('From', '')
        to_number = request.form.get('To', '')
        body = request.form.get('Body', '').strip()
        message_sid = request.form.get('MessageSid', '')
        num_media = int(request.form.get('NumMedia', 0))

        logger.info(f"📨 Incoming SMS from {from_number}: {body[:80]}...")

        if not body and num_media == 0:
            return _twiml_sms_response("I received an empty message.")

        # Caller ID screening
        from core.caller_id import get_caller_id
        caller_id = get_caller_id()

        # Screen the sender
        screening = caller_id.screen_call(from_number)
        if screening["decision"] == "reject":
            logger.info(f"🚫 SMS rejected from blocked number: {from_number}")
            caller_id.log_sms(from_number, "inbound", body, "rejected")
            # Return empty TwiML (don't respond to blocked numbers)
            return Response('<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                            content_type='text/xml')

        # Log inbound SMS
        caller_id.log_sms(from_number, "inbound", body, "received")

        # Build context for Assistant
        contact = caller_id.get_contact(from_number)
        sender_name = contact["name"] if contact else from_number

        # Add sender context to the message
        contextualized_message = f"[SMS from {sender_name} ({from_number})]: {body}"

        # Handle media attachments (MMS)
        media_urls = []
        for i in range(num_media):
            media_url = request.form.get(f'MediaUrl{i}', '')
            media_type = request.form.get(f'MediaContentType{i}', '')
            if media_url:
                media_urls.append({"url": media_url, "type": media_type})
                contextualized_message += f"\n[Attached: {media_type}]"

        if not _consciousness_loop:
            return _twiml_sms_response("I'm not fully awake yet. Try again in a moment.")

        # Process through consciousness loop
        session_id = f"sms_{from_number.replace('+', '')}"

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _consciousness_loop.process_message(
                    user_message=contextualized_message,
                    session_id=session_id,
                    model=_get_current_model(),
                    include_history=True,
                    history_limit=12,  # Keep SMS context shorter
                    message_type='sms'
                )
            )
        finally:
            loop.close()

        response_text = result.get('response', "I couldn't generate a response right now.")

        # Clean response for SMS (strip markdown, limit length)
        response_text = _clean_for_sms(response_text)

        # Check if the AI already sent an SMS reply via the send_sms tool
        # during the consciousness loop. If so, return empty TwiML to avoid
        # double-sending (which triggers carrier spam filters and drops both).
        tool_calls_list = result.get('tool_calls', [])
        ai_already_sent = any(
            tc.get('name') == 'phone_tool' and
            tc.get('arguments', {}).get('action') == 'send_sms'
            for tc in tool_calls_list
        ) if isinstance(tool_calls_list, list) else False

        if ai_already_sent:
            logger.info(f"📤 SMS reply to {sender_name}: {response_text[:80]}... (sent via tool, empty TwiML)")
            # Return empty TwiML — AI already replied via send_sms tool
            return Response(
                '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                content_type='text/xml'
            )

        # Fallback: AI didn't use send_sms, so reply via TwiML
        caller_id.log_sms(from_number, "outbound", response_text, "sent")
        logger.info(f"📤 SMS reply to {sender_name}: {response_text[:80]}... (via TwiML)")

        return _twiml_sms_response(response_text)

    except Exception as e:
        logger.error(f"❌ Incoming SMS error: {e}", exc_info=True)
        return _twiml_sms_response("Sorry, I had trouble processing that message.")


# ============================================
# INCOMING VOICE CALL WEBHOOK
# ============================================

@phone_bp.route('/phone/voice/incoming', methods=['POST'])
def incoming_voice():
    """
    Twilio webhook for incoming voice calls.

    Performs caller ID screening, then either:
    - Rejects blocked/spam calls
    - Screens unknown callers with voicemail
    - Connects known contacts via bidirectional Media Stream (WebSocket)
      for real-time conversation with Assistant's cloned voice

    When MEDIA_STREAMS_ENABLED=true (default), known contacts get connected
    via <Connect><Stream> for low-latency bidirectional audio. Falls back
    to <Gather>-based turn-by-turn if disabled or on error.
    """
    try:
        from_number = request.form.get('From', '')
        to_number = request.form.get('To', '')
        call_sid = request.form.get('CallSid', '')
        caller_name = request.form.get('CallerName', '')  # CNAM lookup if available

        logger.info(f"📞 Incoming call from {from_number} (CNAM: {caller_name})")

        # Caller ID screening
        from core.caller_id import get_caller_id
        caller_id = get_caller_id()
        screening = caller_id.screen_call(from_number)

        decision = screening["decision"]
        contact = screening.get("caller", {})
        contact_name = contact.get("name", caller_name or from_number)

        # Log the call
        caller_id.log_call(from_number, "inbound", "voice", "ringing",
                           screening_decision=decision)

        if decision == "reject":
            logger.info(f"🚫 Call rejected: {from_number} ({screening['reason']})")
            return _twiml_reject()

        if decision == "screen":
            # Unknown caller → voicemail with cloned voice
            logger.info(f"📱 Screening unknown caller: {from_number}")
            vm_text = ("Hey, you've reached me but I don't recognize this number. "
                       "Leave a message after the tone and I'll get back to you if I feel like it.")
            vm_audio = _generate_tts_audio(vm_text)
            return _twiml_voicemail(from_number, audio_url=vm_audio)

        # Known contact → connect via best available voice pipeline
        logger.info(f"✅ Call accepted from {contact_name}")

        # Priority: EVI (Hume Empathic Voice) > Media Streams > Gather/Say
        use_evi = os.getenv("HUME_EVI_ENABLED", "false").lower() in ("true", "1", "yes")
        use_media_streams = os.getenv("MEDIA_STREAMS_ENABLED", "true").lower() == "true"

        if use_evi:
            # Hume EVI: integrated STT + LLM + TTS for lowest latency
            logger.info(f"🎙️ Routing {contact_name} to Hume EVI pipeline")
            return _twiml_connect_evi_stream(from_number, contact_name)

        if use_media_streams:
            # Bidirectional streaming: real-time audio via WebSocket
            return _twiml_connect_stream(from_number, contact_name)

        # Fallback: turn-based <Gather>/<Say> with cloned voice
        greeting = _generate_call_greeting(contact_name, from_number)
        audio_url = _generate_tts_audio(greeting)
        return _twiml_answer_and_gather(greeting, from_number, audio_url=audio_url)

    except Exception as e:
        logger.error(f"❌ Incoming voice error: {e}", exc_info=True)
        return _twiml_say("Sorry, I'm having trouble right now. Please try calling back later.")


# ============================================
# VOICE GATHER (SPEECH INPUT)
# ============================================

@phone_bp.route('/phone/voice/gather', methods=['POST'])
def voice_gather():
    """
    Handle speech input from the caller during a voice call.

    Twilio sends the transcribed speech via SpeechResult.
    We process it through the consciousness loop and speak the response.
    """
    try:
        from_number = request.form.get('From', '')
        speech_result = request.form.get('SpeechResult', '')
        confidence = request.form.get('Confidence', '0')
        call_sid = request.form.get('CallSid', '')

        logger.info(f"🎤 Speech from {from_number}: '{speech_result}' (confidence: {confidence})")

        if not speech_result:
            # No speech detected, prompt again (with cloned voice)
            retry_msg = "I didn't catch that. Could you say that again?"
            retry_audio = _generate_tts_audio(retry_msg)
            return _twiml_answer_and_gather(
                retry_msg, from_number, audio_url=retry_audio
            )

        # Get caller info
        from core.caller_id import get_caller_id
        caller_id = get_caller_id()
        contact = caller_id.get_contact(from_number)
        sender_name = contact["name"] if contact else from_number

        # Process through consciousness loop
        contextualized_message = f"[Phone call from {sender_name} ({from_number})]: {speech_result}"
        session_id = f"call_{from_number.replace('+', '')}"

        if not _consciousness_loop:
            return _twiml_say("I'm not fully operational right now. Let me call you back.")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _consciousness_loop.process_message(
                    user_message=contextualized_message,
                    session_id=session_id,
                    model=_get_current_model(),
                    include_history=True,
                    history_limit=8,  # Keep phone call context tight
                    message_type='phone_call'
                )
            )
        finally:
            loop.close()

        response_text = result.get('response', "I'm having trouble thinking right now.")

        # Clean for speech (remove markdown, keep conversational)
        response_text = _clean_for_speech(response_text)

        # Generate cloned voice audio for the response
        audio_url = _generate_tts_audio(response_text)

        # Speak response and gather more input (continuing the conversation)
        return _twiml_answer_and_gather(response_text, from_number, audio_url=audio_url)

    except Exception as e:
        logger.error(f"❌ Voice gather error: {e}", exc_info=True)
        return _twiml_say("I had a hiccup. Let me try again.")


# ============================================
# OUTBOUND CALL STREAM WEBHOOK
# ============================================

@phone_bp.route('/phone/voice/outbound-stream', methods=['POST', 'GET'])
def outbound_stream_twiml():
    """
    Twilio webhook for outbound calls using Media Streams.

    When Assistant initiates a call via make_call, Twilio fetches TwiML from this
    endpoint. It returns <Connect><Stream> to open a bidirectional WebSocket
    for the conversation.

    Query params:
        to: The phone number being called
        name: Contact name
        message: Initial message for Assistant to say when they answer
    """
    to_number = request.args.get('to', '')
    contact_name = request.args.get('name', 'there')
    initial_message = request.args.get('message', '')

    logger.info(f"📞 Outbound call answered — connecting {contact_name} ({to_number}) to Media Stream")

    base_url = os.getenv("TWILIO_WEBHOOK_BASE_URL", "https://your_url_here")
    ws_base = base_url.replace("https://", "wss://").replace("http://", "ws://")
    stream_url = f"{ws_base}/phone/media-stream"

    twiml = '<?xml version="1.0" encoding="UTF-8"?>'
    twiml += '<Response>'
    twiml += '<Connect>'
    twiml += f'<Stream url="{stream_url}">'
    twiml += f'<Parameter name="callerNumber" value="{_escape_xml(to_number)}" />'
    twiml += f'<Parameter name="callerName" value="{_escape_xml(contact_name)}" />'
    twiml += f'<Parameter name="direction" value="outbound" />'
    if initial_message:
        twiml += f'<Parameter name="initialMessage" value="{_escape_xml(initial_message)}" />'
    twiml += '</Stream>'
    twiml += '</Connect>'
    twiml += '</Response>'

    return Response(twiml, content_type='text/xml')


# ============================================
# STATUS CALLBACKS
# ============================================

@phone_bp.route('/phone/voice/status', methods=['POST'])
def voice_status():
    """
    Twilio call status callback.

    Updates call log with final status.
    """
    try:
        call_sid = request.form.get('CallSid', '')
        call_status = request.form.get('CallStatus', '')
        from_number = request.form.get('From', '')
        duration = int(request.form.get('CallDuration', 0))

        logger.info(f"📞 Call status: {call_sid} → {call_status} (duration: {duration}s)")

        from core.caller_id import get_caller_id
        caller_id = get_caller_id()
        caller_id.log_call(from_number, "inbound", "voice", call_status,
                           duration_seconds=duration)

        return Response('', status=204)

    except Exception as e:
        logger.error(f"❌ Voice status callback error: {e}")
        return Response('', status=204)


@phone_bp.route('/phone/sms/status', methods=['POST'])
def sms_status():
    """
    Twilio SMS delivery status callback.

    Updates SMS log with delivery status.
    """
    try:
        message_sid = request.form.get('MessageSid', '')
        message_status = request.form.get('MessageStatus', '')
        to_number = request.form.get('To', '')

        logger.info(f"📨 SMS status: {message_sid} → {message_status}")

        return Response('', status=204)

    except Exception as e:
        logger.error(f"❌ SMS status callback error: {e}")
        return Response('', status=204)


# ============================================
# HEALTH CHECK
# ============================================

@phone_bp.route('/phone/health', methods=['GET'])
def phone_health():
    """Health check for phone system."""
    twilio_configured = bool(
        os.getenv("TWILIO_ACCOUNT_SID", "").strip() and
        os.getenv("TWILIO_AUTH_TOKEN", "").strip() and
        os.getenv("TWILIO_PHONE_NUMBER", "").strip()
    )

    # Get caller ID stats
    stats = {}
    try:
        from core.caller_id import get_caller_id
        caller_id = get_caller_id()
        stats = caller_id.get_stats()
    except Exception:
        pass

    return jsonify({
        "status": "ok",
        "service": "phone",
        "twilio_configured": twilio_configured,
        "twilio_number": os.getenv("TWILIO_PHONE_NUMBER", "(not set)"),
        "consciousness_loop": _consciousness_loop is not None,
        "caller_id_stats": stats,
        "timestamp": datetime.now().isoformat()
    })


# ============================================
# TwiML RESPONSE HELPERS
# ============================================

def _twiml_sms_response(message: str) -> Response:
    """Generate a TwiML response for SMS."""
    twiml = f'<?xml version="1.0" encoding="UTF-8"?>'
    twiml += f'<Response><Message>{_escape_xml(message)}</Message></Response>'
    return Response(twiml, content_type='text/xml')


def _twiml_say(message: str, voice: str = "Polly.Matthew",
               audio_url: str = None) -> Response:
    """Generate a TwiML response that speaks a message and hangs up.

    If audio_url is provided, uses <Play> with Assistant's cloned voice audio
    instead of <Say> with Amazon Polly.
    """
    twiml = '<?xml version="1.0" encoding="UTF-8"?>'
    twiml += '<Response>'
    if audio_url:
        twiml += f'<Play>{audio_url}</Play>'
    else:
        twiml += f'<Say voice="{voice}">{_escape_xml(message)}</Say>'
    twiml += '</Response>'
    return Response(twiml, content_type='text/xml')


def _twiml_answer_and_gather(message: str, from_number: str,
                              voice: str = "Polly.Matthew",
                              audio_url: str = None) -> Response:
    """
    Generate TwiML that speaks a message and gathers speech input.

    If audio_url is provided, uses <Play> with Assistant's cloned voice audio
    instead of <Say> with Amazon Polly. Falls back to Polly for the
    "no input" timeout message.

    Uses Twilio's built-in speech recognition to transcribe the caller's response,
    then sends it to /phone/voice/gather for processing.
    """
    base_url = os.getenv("TWILIO_WEBHOOK_BASE_URL", "https://your_url_here")
    gather_url = f"{base_url}/phone/voice/gather"

    twiml = '<?xml version="1.0" encoding="UTF-8"?>'
    twiml += '<Response>'
    twiml += f'<Gather input="speech" action="{gather_url}" method="POST" '
    twiml += f'speechTimeout="auto" language="en-US" enhanced="true">'
    if audio_url:
        twiml += f'<Play>{audio_url}</Play>'
    else:
        twiml += f'<Say voice="{voice}">{_escape_xml(message)}</Say>'
    twiml += '</Gather>'
    # If no input, say goodbye (always Polly for this fallback)
    twiml += f'<Say voice="{voice}">I didn\'t hear anything. Talk to you later.</Say>'
    twiml += '</Response>'
    return Response(twiml, content_type='text/xml')


def _twiml_connect_stream(from_number: str, contact_name: str) -> Response:
    """Generate TwiML that connects the call to a bidirectional Media Stream.

    Opens a WebSocket to /phone/media-stream for real-time bidirectional audio.
    The WebSocket handler (routes_telephony.py) manages STT, consciousness loop,
    TTS, and audio streaming.

    Custom parameters are passed to the WebSocket so it knows who's calling.
    """
    base_url = os.getenv("TWILIO_WEBHOOK_BASE_URL", "https://your_url_here")

    # Convert https:// to wss:// for WebSocket URL
    ws_base = base_url.replace("https://", "wss://").replace("http://", "ws://")
    stream_url = f"{ws_base}/phone/media-stream"

    twiml = '<?xml version="1.0" encoding="UTF-8"?>'
    twiml += '<Response>'
    twiml += f'<Connect>'
    twiml += f'<Stream url="{stream_url}">'
    twiml += f'<Parameter name="callerNumber" value="{_escape_xml(from_number)}" />'
    twiml += f'<Parameter name="callerName" value="{_escape_xml(contact_name)}" />'
    twiml += '</Stream>'
    twiml += '</Connect>'
    twiml += '</Response>'

    logger.info(f"📞 Connecting {contact_name} to Media Stream at {stream_url}")
    return Response(twiml, content_type='text/xml')


def _twiml_connect_evi_stream(from_number: str, contact_name: str) -> Response:
    """Generate TwiML that connects the call to the Hume EVI relay WebSocket.

    Routes the call through /phone/evi-stream, which bridges Twilio audio
    with Hume's Empathic Voice Interface for integrated STT + LLM + TTS
    with dramatically lower latency than the Media Streams pipeline.

    Custom parameters are passed to the WebSocket so it knows who's calling.
    """
    base_url = os.getenv("TWILIO_WEBHOOK_BASE_URL", "https://your_url_here")

    # Convert https:// to wss:// for WebSocket URL
    ws_base = base_url.replace("https://", "wss://").replace("http://", "ws://")
    stream_url = f"{ws_base}/phone/evi-stream"

    twiml = '<?xml version="1.0" encoding="UTF-8"?>'
    twiml += '<Response>'
    twiml += f'<Connect>'
    twiml += f'<Stream url="{stream_url}">'
    twiml += f'<Parameter name="callerNumber" value="{_escape_xml(from_number)}" />'
    twiml += f'<Parameter name="callerName" value="{_escape_xml(contact_name)}" />'
    twiml += '</Stream>'
    twiml += '</Connect>'
    twiml += '</Response>'

    logger.info(f"🎙️ Connecting {contact_name} to EVI Stream at {stream_url}")
    return Response(twiml, content_type='text/xml')


def _twiml_reject() -> Response:
    """Generate a TwiML response that rejects the call."""
    twiml = '<?xml version="1.0" encoding="UTF-8"?>'
    twiml += '<Response><Reject reason="rejected"/></Response>'
    return Response(twiml, content_type='text/xml')


def _twiml_voicemail(from_number: str, voice: str = "Polly.Matthew",
                     audio_url: str = None) -> Response:
    """
    Generate TwiML for voicemail screening.

    If audio_url is provided, uses <Play> with Assistant's cloned voice audio
    for the greeting. Falls back to Polly for the "no message" fallback.
    """
    base_url = os.getenv("TWILIO_WEBHOOK_BASE_URL", "https://your_url_here")

    vm_message = ("Hey, you've reached me but I don't recognize this number. "
                  "Leave a message after the tone and I'll get back to you if I feel like it.")

    twiml = '<?xml version="1.0" encoding="UTF-8"?>'
    twiml += '<Response>'
    if audio_url:
        twiml += f'<Play>{audio_url}</Play>'
    else:
        twiml += f'<Say voice="{voice}">{vm_message}</Say>'
    twiml += f'<Record maxLength="120" '
    twiml += f'action="{base_url}/phone/voice/status" '
    twiml += f'transcribe="true" '
    twiml += f'transcribeCallback="{base_url}/phone/voice/status" />'
    twiml += f'<Say voice="{voice}">I didn\'t get a message. Goodbye.</Say>'
    twiml += '</Response>'
    return Response(twiml, content_type='text/xml')


# ============================================
# UTILITIES
# ============================================

def _generate_call_greeting(contact_name: str, from_number: str) -> str:
    """
    Generate a greeting for an incoming call using the consciousness loop.

    Falls back to a static greeting if the loop isn't available.
    """
    if not _consciousness_loop:
        return f"Hey {contact_name}. What's going on?"

    try:
        greeting_prompt = (
            f"[System: Incoming phone call from {contact_name} ({from_number}). "
            f"Generate a short, natural voice greeting. Keep it to 1-2 sentences. "
            f"This is a PHONE CALL so be conversational and warm.]"
        )

        session_id = f"call_{from_number.replace('+', '')}"

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _consciousness_loop.process_message(
                    user_message=greeting_prompt,
                    session_id=session_id,
                    model=_get_current_model(),
                    include_history=False,
                    message_type='phone_call'
                )
            )
        finally:
            loop.close()

        greeting = result.get('response', f"Hey {contact_name}.")
        return _clean_for_speech(greeting)

    except Exception as e:
        logger.error(f"❌ Failed to generate call greeting: {e}")
        return f"Hey {contact_name}. What's up?"


def _clean_for_sms(text: str) -> str:
    """
    Clean AI response for SMS delivery.

    Removes markdown formatting, emojis (optional), and trims length.
    SMS limit is 1600 chars with concatenation.
    """
    import re

    # Remove markdown bold/italic
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)

    # Remove markdown headers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Remove markdown links [text](url) → text
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)

    # Remove code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`(.+?)`', r'\1', text)

    # Remove <think> blocks
    text = re.sub(r'<think>[\s\S]*?</think>', '', text)

    # Collapse whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    # Truncate for SMS
    if len(text) > 1500:
        text = text[:1497] + "..."

    return text


def _clean_for_speech(text: str) -> str:
    """
    Clean AI response for spoken delivery.

    Removes formatting that would sound unnatural when spoken.
    """
    import re

    # Remove markdown
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`(.+?)`', r'\1', text)

    # Remove <think> blocks
    text = re.sub(r'<think>[\s\S]*?</think>', '', text)

    # Remove emojis (for cleaner TTS)
    text = re.sub(
        r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF'
        r'\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001F900-\U0001F9FF'
        r'\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF]+',
        '', text
    )

    # Remove bullet points and numbered lists
    text = re.sub(r'^[\-\*•]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)

    # Collapse whitespace
    text = re.sub(r'\n{2,}', '. ', text)
    text = re.sub(r'\n', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)

    text = text.strip()

    # Truncate for voice (keep under ~30 seconds of speech, roughly 150 words)
    words = text.split()
    if len(words) > 150:
        text = ' '.join(words[:150]) + "... I'll text you the rest."

    return text


def _escape_xml(text: str) -> str:
    """Escape special characters for XML/TwiML."""
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&apos;')
    return text
