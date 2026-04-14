#!/usr/bin/env python3
"""
Mobile Voice Stream - Bidirectional WebSocket for Real-Time Voice
=================================================================

Bidirectional audio transport for the mobile app's voice mode.

The mobile client uses expo-audio to record a complete utterance locally
(metering-based VAD determines when the user stops speaking), then sends
the finished audio file as a single base64 payload. The server transcribes
the full batch via Deepgram's prerecorded REST API, runs the text through
the consciousness loop, and streams the Cartesia TTS response back.

This differs from the telephony flow (which uses Deepgram streaming STT
for continuous PCM chunks). Expo-audio records to a container (M4A on
iOS/Android with the HIGH_QUALITY preset), not raw PCM, so streaming STT
would both time-out on silence and be unable to decode the payload.

Protocol (JSON messages):
  Client → Server:
    { "type": "start", "session_id": "...", "user_id": "..." }
    { "type": "audio", "data": "<base64 recorded audio>", "format": "m4a" }
    { "type": "interrupt" }    // Barge-in: stop current TTS
    { "type": "stop" }         // End voice session

  Server → Client:
    { "type": "ready" }
    { "type": "listening" }
    { "type": "processing" }
    { "type": "transcript", "text": "...", "is_final": true }
    { "type": "response_text", "text": "...", "user_transcript": "..." }
    { "type": "speaking_start" }
    { "type": "audio", "data": "<base64 PCM 16-bit 24kHz>" }
    { "type": "speaking_end" }
    { "type": "error", "message": "..." }

Requires:
    pip install flask-sock
    DEEPGRAM_API_KEY, CARTESIA_API_KEY environment variables

Audio formats:
    Input:  Whatever the mobile recorder produced (default audio/m4a).
            Deepgram's batch API auto-detects the container.
    Output: PCM 16-bit signed LE, 24kHz, mono (Cartesia Sonic output)
"""

import os
import json
import base64
import asyncio
import logging
import threading
import re
from typing import Optional

from core.config import get_model_or_default

logger = logging.getLogger(__name__)

# Module-level dependencies (injected via init_mobile_voice_routes)
_consciousness_loop = None
_state_manager = None


def init_mobile_voice_routes(consciousness_loop, state_manager):
    """Inject dependencies for the mobile voice module."""
    global _consciousness_loop, _state_manager
    _consciousness_loop = consciousness_loop
    _state_manager = state_manager
    logger.info("📱 Mobile voice routes initialized")


# ============================================
# TEXT CLEANING FOR SPEECH
# ============================================

def _clean_for_speech(text: str) -> str:
    """Clean AI response for spoken delivery.

    Removes formatting that would sound unnatural when spoken.
    """
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

    # Truncate for voice (~30 seconds of speech ~ 150 words)
    words = text.split()
    if len(words) > 150:
        text = ' '.join(words[:150]) + "... I'll text you the rest."

    return text


# ============================================
# CONSCIOUSNESS LOOP INTEGRATION
# ============================================

def _process_through_consciousness(message: str, session_id: str,
                                    user_id: str) -> str:
    """Send a message through the consciousness loop and return the response.

    Args:
        message: The user's transcribed speech
        session_id: Session ID for conversation continuity
        user_id: User ID for context

    Returns:
        Cleaned response text ready for TTS
    """
    if not _consciousness_loop:
        return "I'm not fully awake right now. Try again in a moment."

    contextualized = f"[Voice message from mobile app]: {message}"

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
                message_type='voice'
            )
        )
    finally:
        loop.close()

    response_text = result.get('response', "I'm having trouble thinking right now.")
    return _clean_for_speech(response_text)


# ============================================
# TTS STREAMING (Cartesia Sonic)
# ============================================

def _split_into_sentences(text: str) -> list:
    """Split text into sentences for progressive TTS streaming.

    Preserves sentence terminators and handles abbreviations reasonably.
    """
    if not text:
        return []

    # Split on ., !, ? followed by whitespace, keeping the terminator.
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [p.strip() for p in parts if p.strip()]

    # Merge very short fragments (< 4 chars) into the previous sentence
    # so we don't waste TTS calls on things like "Hi." "Yes."
    merged = []
    for s in sentences:
        if merged and len(s) < 4:
            merged[-1] = merged[-1] + " " + s
        else:
            merged.append(s)
    return merged


def _stream_tts_to_client(ws, text: str, interrupted: threading.Event) -> bool:
    """Stream TTS audio for a SINGLE sentence to the client.

    The caller is responsible for sending speaking_start/speaking_end
    around the whole utterance. This helper only emits audio chunks
    followed by a sentence_end marker so the client can play each
    sentence progressively while subsequent sentences stream in.

    Args:
        ws: WebSocket connection
        text: Text to synthesize (a single sentence)
        interrupted: Event flag set if client sends interrupt

    Returns:
        True if completed, False if interrupted or failed
    """
    try:
        from core.cartesia_provider import CartesiaSonicProvider
        provider = CartesiaSonicProvider()
    except Exception as e:
        logger.error(f"Cartesia TTS init failed: {e}")
        try:
            ws.send(json.dumps({"type": "error", "message": "TTS unavailable"}))
        except Exception:
            pass
        return False

    try:
        total_bytes = 0
        for chunk in provider.stream_speech_sync(text):
            if interrupted.is_set():
                logger.info("⚡ TTS interrupted by client barge-in")
                return False

            total_bytes += len(chunk)
            ws.send(json.dumps({
                "type": "audio",
                "data": base64.b64encode(chunk).decode("ascii"),
            }))

        # Mark the end of this sentence's audio so the client can play it
        # while subsequent sentences continue to stream in.
        ws.send(json.dumps({"type": "sentence_end"}))
        logger.info(f"🔊 Streamed {total_bytes} bytes for sentence ({len(text)} chars)")
        return True

    except Exception as e:
        logger.error(f"TTS streaming error: {e}")
        try:
            ws.send(json.dumps({"type": "error", "message": f"TTS error: {e}"}))
        except Exception:
            pass
        return False


# ============================================
# MOBILE VOICE WEBSOCKET HANDLER
# ============================================

def setup_mobile_voice_stream(sock, consciousness_loop=None, state_manager=None):
    """Register the Mobile Voice WebSocket route on the Flask-Sock instance.

    Called from server.py after creating the Sock object.

    Args:
        sock: flask_sock.Sock instance
        consciousness_loop: ConsciousnessLoop instance
        state_manager: StateManager instance
    """
    if consciousness_loop:
        init_mobile_voice_routes(consciousness_loop, state_manager)

    @sock.route('/mobile/voice-stream')
    def mobile_voice_stream(ws):
        """WebSocket handler for mobile voice mode.

        Receives a complete recorded utterance as a single base64 payload,
        transcribes it via Deepgram's batch REST API, runs the text through
        the consciousness loop, and streams the Cartesia TTS response back.
        """
        session_id = "nate_conversation"
        user_id = "user_name"

        # State
        interrupted = threading.Event()
        is_processing = False

        logger.info("📱 Mobile Voice WebSocket opened")

        def handle_utterance(transcript: str):
            """Process a completed user utterance end-to-end."""
            nonlocal is_processing

            if not transcript.strip():
                try:
                    ws.send(json.dumps({"type": "listening"}))
                except Exception:
                    pass
                return

            is_processing = True
            logger.info(f"🎤 Mobile voice transcript: '{transcript}'")

            try:
                # Let the client display the final transcript
                ws.send(json.dumps({
                    "type": "transcript",
                    "text": transcript,
                    "is_final": True,
                }))

                # Notify client we're processing
                ws.send(json.dumps({"type": "processing"}))

                # Process through consciousness loop
                response_text = _process_through_consciousness(
                    transcript, session_id, user_id
                )

                if not response_text:
                    ws.send(json.dumps({"type": "listening"}))
                    return

                logger.info(f"🗣️ Response: '{response_text[:100]}...'")

                # Tell the client the turn is starting. This creates the user
                # voice message + an empty assistant placeholder so the UI can
                # append text as each sentence arrives.
                ws.send(json.dumps({
                    "type": "response_start",
                    "user_transcript": transcript,
                }))

                # Start the TTS phase: the client will build up the assistant
                # message and play audio sentence-by-sentence as each one
                # finishes synthesizing.
                ws.send(json.dumps({"type": "speaking_start"}))
                interrupted.clear()

                sentences = _split_into_sentences(response_text)
                for sentence in sentences:
                    if interrupted.is_set():
                        break

                    # Send text for this sentence — client appends it to
                    # the current assistant message so display and audio
                    # stay roughly in sync.
                    ws.send(json.dumps({
                        "type": "response_chunk",
                        "text": sentence,
                    }))

                    # Stream the sentence's TTS audio and emit sentence_end
                    if not _stream_tts_to_client(ws, sentence, interrupted):
                        break

                ws.send(json.dumps({"type": "speaking_end"}))

                # Resume listening for the next turn
                ws.send(json.dumps({"type": "listening"}))

            except Exception as e:
                logger.error(f"Voice processing error: {e}", exc_info=True)
                try:
                    ws.send(json.dumps({"type": "error", "message": str(e)}))
                    ws.send(json.dumps({"type": "listening"}))
                except Exception:
                    pass
            finally:
                is_processing = False

        def transcribe_batch(audio_bytes: bytes, audio_format: str) -> Optional[str]:
            """Transcribe a complete audio payload via Deepgram's batch REST API."""
            try:
                from api.routes_stt import _transcribe_deepgram
            except Exception as e:
                logger.error(f"Failed to import batch STT helper: {e}")
                return None

            content_type = _FORMAT_CONTENT_TYPES.get(
                (audio_format or "m4a").lower(), "audio/m4a"
            )

            logger.info(
                f"🎙️ Transcribing mobile voice batch "
                f"({len(audio_bytes)} bytes, {content_type})"
            )

            text, error = _transcribe_deepgram(audio_bytes, content_type, language="en")
            if error:
                logger.error(f"Deepgram batch transcription failed: {error}")
                return None
            return text

        try:
            while True:
                message = ws.receive()
                if message is None:
                    break

                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    continue

                msg_type = data.get("type", "")

                # ----- START SESSION -----
                if msg_type == "start":
                    session_id = data.get("session_id", session_id)
                    user_id = data.get("user_id", user_id)

                    logger.info(
                        f"📱 Voice session started "
                        f"(user={user_id}, session={session_id})"
                    )

                    # Nothing to init up-front — batch STT runs per utterance.
                    ws.send(json.dumps({"type": "ready"}))
                    ws.send(json.dumps({"type": "listening"}))

                # ----- AUDIO DATA (complete utterance) -----
                elif msg_type == "audio":
                    if is_processing:
                        logger.info("⏭️ Ignoring audio while previous turn is still processing")
                        continue

                    audio_b64 = data.get("data", "")
                    audio_format = data.get("format", "m4a")
                    if not audio_b64:
                        continue

                    try:
                        audio_bytes = base64.b64decode(audio_b64)
                    except Exception as e:
                        logger.error(f"Failed to decode audio payload: {e}")
                        ws.send(json.dumps({
                            "type": "error",
                            "message": "Invalid audio payload"
                        }))
                        ws.send(json.dumps({"type": "listening"}))
                        continue

                    transcript = transcribe_batch(audio_bytes, audio_format)
                    if transcript is None:
                        ws.send(json.dumps({
                            "type": "error",
                            "message": "Transcription failed"
                        }))
                        ws.send(json.dumps({"type": "listening"}))
                        continue

                    handle_utterance(transcript)

                # ----- INTERRUPT (barge-in) -----
                elif msg_type == "interrupt":
                    logger.info("⚡ Client requested interrupt (barge-in)")
                    interrupted.set()

                # ----- STOP SESSION -----
                elif msg_type == "stop":
                    logger.info("📱 Client requested session stop")
                    break

        except Exception as e:
            logger.error(f"Mobile Voice WebSocket error: {e}", exc_info=True)
        finally:
            logger.info(f"📱 Mobile Voice WebSocket closed (user={user_id})")

    logger.info("📱 Mobile Voice WebSocket route registered at /mobile/voice-stream")


# Map the mobile-supplied format hint to a Content-Type the Deepgram
# batch REST API understands. Defaults to audio/m4a since that's what
# expo-audio's HIGH_QUALITY preset produces on both iOS and Android.
_FORMAT_CONTENT_TYPES = {
    "m4a": "audio/m4a",
    "mp4": "audio/mp4",
    "aac": "audio/aac",
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "webm": "audio/webm",
    "ogg": "audio/ogg",
    "3gp": "audio/3gpp",
    "3gpp": "audio/3gpp",
    "flac": "audio/flac",
}
