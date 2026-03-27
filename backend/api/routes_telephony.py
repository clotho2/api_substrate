#!/usr/bin/env python3
"""
Twilio Media Streams - Bidirectional Voice Call Handler
========================================================

Real-time bidirectional audio streaming for voice calls using Twilio Media Streams.
This replaces the turn-based <Gather>/<Say> approach with a WebSocket-based
streaming pipeline for more natural phone conversations.

Pipeline:
  Caller speaks → Twilio streams mulaw audio → WebSocket →
  → STT (Whisper) → Consciousness Loop → TTS (configured provider) →
  → mulaw audio → WebSocket → Twilio plays to caller

TTS Providers for telephony (ElevenLabs excluded to conserve credits):
- Hume Octave (custom voice with emotional intelligence)
- Pocket TTS (local fallback)
(ElevenLabs is reserved for voice messages via send_voice_message tool)

Features:
- Real-time speech detection with energy-based endpointing
- Barge-in support (caller can interrupt Assistant mid-sentence)
- Local STT via Whisper (no cloud API costs)
- Configurable TTS via voice provider abstraction (with Pocket TTS fallback)
- Automatic conversation context management

Requires:
  pip install flask-sock

Twilio TwiML setup:
  <Connect>
      <Stream url="wss://your_url_here/phone/media-stream">
          <Parameter name="callerNumber" value="+1234567890" />
          <Parameter name="callerName" value="User" />
      </Stream>
  </Connect>
"""

import os
import io
import json
import base64
import struct
import asyncio
import logging
import requests as http_requests
from typing import Optional

from core.config import get_model_or_default
from core.voice_providers import get_voice_provider
from core.audio_utils import (
    mulaw_to_pcm,
    mulaw_to_wav,
    wav_to_mulaw,
)

logger = logging.getLogger(__name__)

# ============================================
# CONFIGURATION
# ============================================

# Speech detection thresholds
SILENCE_THRESHOLD = 300       # RMS energy threshold for speech vs silence
SILENCE_FRAMES_NEEDED = 25    # Frames of silence to mark end of speech (~500ms at 20ms/frame)
MIN_SPEECH_BYTES = 3200       # Minimum mulaw bytes to process (~400ms at 8kHz)

# Barge-in thresholds (intentionally higher to ignore ambient noise, dogs, road noise, etc.)
BARGE_IN_THRESHOLD = 600      # RMS energy threshold for barge-in (2x speech threshold)
BARGE_IN_FRAMES_NEEDED = 5    # Consecutive frames above threshold to confirm barge-in (~100ms)
BARGE_IN_MIN_BYTES = 6400     # Minimum buffered speech bytes to process after barge-in (~800ms)

# External services
WHISPER_URL = os.getenv("WHISPER_URL", "http://localhost:9000")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
WHISPER_TIMEOUT = int(os.getenv("WHISPER_TIMEOUT", "30"))
POCKETTTS_URL = os.getenv("POCKETTTS_URL", "http://localhost:8001")
POCKETTTS_TIMEOUT = int(os.getenv("POCKETTTS_TIMEOUT", "30"))

# Mulaw chunk size for streaming to Twilio
# 640 bytes = 80ms at 8kHz mulaw (good balance of latency vs overhead)
STREAM_CHUNK_SIZE = 640

# Module-level dependencies (injected via init_telephony_routes)
_consciousness_loop = None
_state_manager = None
_telephony_hume_provider = None   # Cached Hume provider for telephony TTS


def init_telephony_routes(consciousness_loop, state_manager):
    """Inject dependencies for the telephony module."""
    global _consciousness_loop, _state_manager
    _consciousness_loop = consciousness_loop
    _state_manager = state_manager
    logger.info("📞 Telephony routes initialized (Media Streams WebSocket)")


# ============================================
# SPEECH DETECTION
# ============================================

def _calculate_energy(pcm_data: bytes) -> float:
    """Calculate RMS energy of 16-bit PCM audio for speech detection.

    Args:
        pcm_data: Raw 16-bit PCM audio bytes

    Returns:
        RMS energy value (higher = louder)
    """
    if len(pcm_data) < 2:
        return 0.0

    n_samples = len(pcm_data) // 2
    samples = struct.unpack(f'<{n_samples}h', pcm_data[:n_samples * 2])

    if not samples:
        return 0.0

    sum_sq = sum(s * s for s in samples)
    return (sum_sq / n_samples) ** 0.5


# ============================================
# STT (Speech-to-Text via Whisper)
# ============================================

def _run_stt(wav_data: bytes) -> str:
    """Transcribe WAV audio using local Whisper server.

    Args:
        wav_data: WAV file bytes

    Returns:
        Transcribed text, or empty string on failure
    """
    try:
        response = http_requests.post(
            f"{WHISPER_URL}/v1/audio/transcriptions",
            files={'file': ('audio.wav', io.BytesIO(wav_data), 'audio/wav')},
            data={'model': WHISPER_MODEL, 'response_format': 'json'},
            timeout=WHISPER_TIMEOUT
        )

        if response.status_code == 200:
            result = response.json()
            text = result.get('text', '').strip()
            if text:
                logger.info(f"🎤 STT transcription: '{text}'")
            return text
        else:
            logger.error(f"STT failed ({response.status_code}): {response.text[:200]}")
            return ""

    except http_requests.ConnectionError:
        logger.error(f"Whisper server not reachable at {WHISPER_URL}")
        return ""
    except http_requests.Timeout:
        logger.error(f"Whisper STT timed out after {WHISPER_TIMEOUT}s")
        return ""
    except Exception as e:
        logger.error(f"STT error: {e}")
        return ""


# ============================================
# TTS (Text-to-Speech via configured provider)
# ============================================

def _run_tts(text: str) -> Optional[bytes]:
    """Generate TTS audio for phone calls using Hume Octave or Pocket TTS.

    ElevenLabs is intentionally skipped here — it's reserved for voice
    messages (send_voice_message tool) to conserve credits. Phone calls
    use Hume Octave (custom voice) with Pocket TTS as fallback.

    Args:
        text: Text to synthesize

    Returns:
        WAV audio bytes, or None on failure
    """
    try:
        provider = get_voice_provider()
        provider_name = provider.get_provider_name()
    except Exception as e:
        logger.warning(f"Failed to get voice provider, falling back to Pocket TTS: {e}")
        provider_name = 'pockettts'
        provider = None

    # --- Hume Octave: use directly if it's the global provider ---
    if provider_name == 'hume_octave' and provider:
        return _run_tts_hume(text, provider)

    # --- ElevenLabs: skip for telephony (reserved for voice messages) ---
    if provider_name == 'elevenlabs_turbo':
        logger.info("🎙️ Telephony TTS: skipping ElevenLabs (reserved for voice messages), trying Hume")
        # Try Hume if API key is available (cached to avoid re-init overhead)
        global _telephony_hume_provider
        try:
            if _telephony_hume_provider is None:
                from core.voice_providers import HumeOctaveProvider
                _telephony_hume_provider = HumeOctaveProvider()
            return _run_tts_hume(text, _telephony_hume_provider)
        except Exception as e:
            logger.info(f"Hume not available: {e}, using Pocket TTS")
            _telephony_hume_provider = None  # Reset so we retry next time
        return _run_tts_pockettts(text)

    # --- Pocket TTS (default / fallback) ---
    logger.info("🎙️ Telephony TTS provider: pockettts")
    return _run_tts_pockettts(text)


def _run_tts_hume(text: str, provider) -> Optional[bytes]:
    """Generate WAV audio via Hume Octave TTS for telephony.

    Uses the synchronous streaming endpoint with instant_mode for low
    latency. Returns WAV bytes ready for wav_to_mulaw() conversion.
    """
    try:
        wav_data = provider.synthesize_speech_sync(text)
        logger.info(f"🎙️ Hume TTS: {len(text)} chars → {len(wav_data)} bytes WAV")
        return wav_data
    except Exception as e:
        logger.error(f"Hume TTS error: {e}")
        return None


def _run_tts_pockettts(text: str) -> Optional[bytes]:
    """Generate WAV audio via local Pocket TTS server."""
    try:
        response = http_requests.post(
            f"{POCKETTTS_URL}/v1/audio/speech",
            data={"text": text, "voice": "Assistant"},
            timeout=POCKETTTS_TIMEOUT
        )

        if response.status_code == 200:
            logger.info(f"🎙️ Pocket TTS: {len(response.content)} bytes for '{text[:50]}...'")
            return response.content
        else:
            logger.error(f"Pocket TTS failed ({response.status_code}): {response.text[:200]}")
            return None

    except http_requests.ConnectionError:
        logger.error(f"Pocket TTS not reachable at {POCKETTTS_URL}")
        return None
    except http_requests.Timeout:
        logger.error(f"Pocket TTS timed out after {POCKETTTS_TIMEOUT}s")
        return None
    except Exception as e:
        logger.error(f"Pocket TTS error: {e}")
        return None


# ============================================
# TEXT CLEANING FOR SPEECH
# ============================================

def _clean_for_speech(text: str) -> str:
    """Clean AI response for spoken delivery over phone.

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

    # Remove emojis
    text = re.sub(
        r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF'
        r'\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001F900-\U0001F9FF'
        r'\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF]+',
        '', text
    )

    # Remove bullet points and numbered lists
    text = re.sub(r'^[\-\*\u2022]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)

    # Collapse whitespace
    text = re.sub(r'\n{2,}', '. ', text)
    text = re.sub(r'\n', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)

    text = text.strip()

    # Truncate for voice (~30 seconds of speech ≈ 150 words)
    words = text.split()
    if len(words) > 150:
        text = ' '.join(words[:150]) + "... I'll text you the rest."

    return text


# ============================================
# CONSCIOUSNESS LOOP INTEGRATION
# ============================================

def _process_through_consciousness(message: str, caller_name: str,
                                    caller_number: str) -> str:
    """Send a message through the consciousness loop and return the response.

    Args:
        message: The caller's transcribed speech
        caller_name: Contact name for context
        caller_number: Phone number for session tracking

    Returns:
        Cleaned response text ready for TTS
    """
    if not _consciousness_loop:
        return "I'm not fully awake right now. Can you call back in a moment?"

    session_id = f"call_{caller_number.replace('+', '')}"
    contextualized = f"[Phone call from {caller_name} ({caller_number})]: {message}"

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            _consciousness_loop.process_message(
                user_message=contextualized,
                session_id=session_id,
                model=get_model_or_default(),
                include_history=True,
                history_limit=8,
                message_type='phone_call'
            )
        )
    finally:
        loop.close()

    response_text = result.get('response', "I'm having trouble thinking right now.")
    return _clean_for_speech(response_text)


def _generate_greeting(caller_name: str, caller_number: str) -> str:
    """Generate a greeting for the caller using the consciousness loop."""
    if not _consciousness_loop:
        return f"Hey {caller_name}. What's going on?"

    try:
        greeting_prompt = (
            f"[System: Incoming phone call from {caller_name} ({caller_number}). "
            f"Generate a short, natural voice greeting. Keep it to 1-2 sentences. "
            f"This is a PHONE CALL so be conversational and warm.]"
        )

        session_id = f"call_{caller_number.replace('+', '')}"

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _consciousness_loop.process_message(
                    user_message=greeting_prompt,
                    session_id=session_id,
                    model=get_model_or_default(),
                    include_history=False,
                    message_type='phone_call'
                )
            )
        finally:
            loop.close()

        greeting = result.get('response', f"Hey {caller_name}.")
        return _clean_for_speech(greeting)

    except Exception as e:
        logger.error(f"Failed to generate greeting: {e}")
        return f"Hey {caller_name}. What's up?"


# ============================================
# TWILIO MEDIA STREAM WEBSOCKET HANDLER
# ============================================

def _stream_audio_to_twilio(ws, stream_sid: str, text: str):
    """Generate TTS and stream mulaw audio chunks to Twilio.

    Args:
        ws: WebSocket connection
        stream_sid: Twilio stream SID
        text: Text to speak
    """
    tts_wav = _run_tts(text)
    if not tts_wav:
        logger.warning("TTS failed, no audio to stream")
        return

    # Convert WAV to mulaw for Twilio
    mulaw_data = wav_to_mulaw(tts_wav)

    # Stream in chunks
    for i in range(0, len(mulaw_data), STREAM_CHUNK_SIZE):
        chunk = mulaw_data[i:i + STREAM_CHUNK_SIZE]
        ws.send(json.dumps({
            "event": "media",
            "streamSid": stream_sid,
            "media": {
                "payload": base64.b64encode(chunk).decode('ascii')
            }
        }))

    # Mark end of response for barge-in tracking
    ws.send(json.dumps({
        "event": "mark",
        "streamSid": stream_sid,
        "mark": {"name": "response_end"}
    }))

    logger.info(f"🔊 Streamed {len(mulaw_data)} bytes of audio to Twilio")


def setup_media_stream(sock, consciousness_loop=None, state_manager=None):
    """Register the Media Streams WebSocket route on the Flask-Sock instance.

    This is called from server.py after creating the Sock object.

    Args:
        sock: flask_sock.Sock instance
        consciousness_loop: ConsciousnessLoop instance (optional, uses module-level if not provided)
        state_manager: StateManager instance (optional)
    """
    if consciousness_loop:
        init_telephony_routes(consciousness_loop, state_manager)

    @sock.route('/phone/media-stream')
    def media_stream(ws):
        """Bidirectional audio stream handler for Twilio Media Streams.

        Receives real-time mulaw audio from Twilio, detects speech boundaries,
        transcribes via Whisper, processes through consciousness loop, generates
        TTS response, and streams audio back to the caller.
        """
        stream_sid = None
        call_sid = None
        caller_number = ""
        caller_name = "Unknown"

        # Audio buffering state
        audio_buffer = bytearray()
        is_speaking = False
        silence_frames = 0
        is_playing_response = False
        barge_in_frames = 0  # Consecutive high-energy frames during playback

        logger.info("📞 Media Stream WebSocket opened")

        try:
            while True:
                message = ws.receive()
                if message is None:
                    break

                data = json.loads(message)
                event = data.get('event')

                # ----- CONNECTED -----
                if event == 'connected':
                    logger.info("📞 Media Stream connected (protocol ready)")

                # ----- START -----
                elif event == 'start':
                    start_data = data['start']
                    stream_sid = start_data['streamSid']
                    call_sid = start_data.get('callSid', '')
                    params = start_data.get('customParameters', {})
                    caller_number = params.get('callerNumber', '')
                    caller_name = params.get('callerName', 'Unknown')
                    direction = params.get('direction', 'inbound')
                    initial_message = params.get('initialMessage', '')

                    logger.info(
                        f"📞 Stream started ({direction}): {caller_name} "
                        f"({caller_number}) [call={call_sid}, stream={stream_sid}]"
                    )

                    # For outbound calls with an initial message, speak that.
                    # For inbound calls, generate a greeting.
                    if initial_message:
                        opening = _clean_for_speech(initial_message)
                    else:
                        opening = _generate_greeting(caller_name, caller_number)

                    logger.info(f"🗣️ Opening: '{opening}'")
                    is_playing_response = True
                    _stream_audio_to_twilio(ws, stream_sid, opening)

                # ----- MEDIA (incoming audio) -----
                elif event == 'media':
                    payload = data['media']['payload']
                    mulaw_chunk = base64.b64decode(payload)

                    # Calculate energy for speech detection
                    pcm_chunk = mulaw_to_pcm(mulaw_chunk)
                    energy = _calculate_energy(pcm_chunk)

                    if energy > SILENCE_THRESHOLD:
                        # Caller is speaking
                        if is_playing_response:
                            # Potential barge-in — require sustained speech above
                            # a higher threshold to avoid false triggers from
                            # ambient noise, dogs barking, road noise, etc.
                            if energy > BARGE_IN_THRESHOLD:
                                barge_in_frames += 1
                                if barge_in_frames >= BARGE_IN_FRAMES_NEEDED:
                                    # Confirmed barge-in (sustained deliberate speech)
                                    logger.info(
                                        f"⚡ Barge-in detected — clearing Twilio audio queue "
                                        f"(energy={energy:.0f}, frames={barge_in_frames})"
                                    )
                                    ws.send(json.dumps({
                                        "event": "clear",
                                        "streamSid": stream_sid
                                    }))
                                    is_playing_response = False
                                    barge_in_frames = 0
                            else:
                                # Energy above speech threshold but below barge-in
                                # threshold — reset barge-in counter (transient noise)
                                barge_in_frames = 0
                        else:
                            barge_in_frames = 0

                        is_speaking = True
                        silence_frames = 0
                        audio_buffer.extend(mulaw_chunk)

                    else:
                        # Silence
                        barge_in_frames = 0  # Reset barge-in counter on silence
                        if is_speaking:
                            audio_buffer.extend(mulaw_chunk)
                            silence_frames += 1

                            if silence_frames >= SILENCE_FRAMES_NEEDED:
                                # Caller stopped speaking — process the audio
                                if len(audio_buffer) >= MIN_SPEECH_BYTES:
                                    logger.info(
                                        f"🎤 Processing {len(audio_buffer)} bytes of speech "
                                        f"from {caller_name}"
                                    )

                                    # 1. Convert buffered mulaw to WAV
                                    wav_data = mulaw_to_wav(bytes(audio_buffer))

                                    # 2. Transcribe
                                    transcription = _run_stt(wav_data)

                                    if transcription:
                                        # 3. Process through consciousness loop
                                        response_text = _process_through_consciousness(
                                            transcription, caller_name, caller_number
                                        )

                                        logger.info(f"🗣️ Assistant: '{response_text[:100]}...'")

                                        # 4. TTS and stream back
                                        is_playing_response = True
                                        _stream_audio_to_twilio(
                                            ws, stream_sid, response_text
                                        )
                                    else:
                                        logger.debug("Empty transcription, ignoring")

                                else:
                                    logger.debug(
                                        f"Audio too short ({len(audio_buffer)} bytes), ignoring"
                                    )

                                # Reset buffer
                                audio_buffer.clear()
                                is_speaking = False
                                silence_frames = 0

                # ----- MARK -----
                elif event == 'mark':
                    mark_name = data.get('mark', {}).get('name', '')
                    if mark_name == 'response_end':
                        is_playing_response = False
                        logger.debug("Audio playback complete (mark received)")

                # ----- STOP -----
                elif event == 'stop':
                    logger.info(f"📞 Stream ended: {caller_name} ({caller_number})")
                    break

        except Exception as e:
            logger.error(f"Media Stream error: {e}", exc_info=True)
        finally:
            logger.info(f"📞 Media Stream WebSocket closed for {caller_name}")

            # Log the call
            try:
                from core.caller_id import get_caller_id
                caller_id = get_caller_id()
                caller_id.log_call(
                    caller_number, "inbound", "voice", "completed",
                    screening_decision="accept"
                )
            except Exception:
                pass

    logger.info("📞 Media Streams WebSocket route registered at /phone/media-stream")
