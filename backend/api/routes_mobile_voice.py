#!/usr/bin/env python3
"""
Mobile Voice Stream - Bidirectional WebSocket for Real-Time Voice
=================================================================

Real-time bidirectional audio streaming for the mobile app's voice mode.
Modeled after routes_telephony.py (Twilio Media Streams) but adapted for
direct mobile WebSocket connections.

Pipeline:
  Mobile streams PCM audio → WebSocket →
  → Deepgram Streaming STT (real-time transcription) →
  → Consciousness Loop (AI response) →
  → Cartesia Sonic TTS (low-latency streaming) →
  → PCM audio → WebSocket → Mobile plays audio

Protocol (JSON messages):
  Client → Server:
    { "type": "start", "session_id": "...", "user_id": "..." }
    { "type": "audio", "data": "<base64 PCM 16-bit 16kHz>" }
    { "type": "interrupt" }    // Barge-in: stop current TTS
    { "type": "stop" }         // End voice session

  Server → Client:
    { "type": "ready" }
    { "type": "transcript", "text": "...", "is_final": false }
    { "type": "listening" }
    { "type": "processing" }
    { "type": "speaking_start" }
    { "type": "audio", "data": "<base64 PCM 16-bit 24kHz>" }
    { "type": "response_text", "text": "..." }
    { "type": "speaking_end" }
    { "type": "error", "message": "..." }

Requires:
    pip install flask-sock websockets
    DEEPGRAM_API_KEY, CARTESIA_API_KEY environment variables

Audio formats:
    Input:  PCM 16-bit signed LE, 16kHz, mono (from mobile mic)
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

def _stream_tts_to_client(ws, text: str, interrupted: threading.Event) -> bool:
    """Generate TTS via Cartesia Sonic and stream audio chunks to the client.

    Args:
        ws: WebSocket connection
        text: Text to synthesize
        interrupted: Event flag set if client sends interrupt

    Returns:
        True if completed, False if interrupted
    """
    try:
        from core.cartesia_provider import CartesiaSonicProvider
        provider = CartesiaSonicProvider()
    except Exception as e:
        logger.error(f"Cartesia TTS init failed: {e}")
        # Fallback: try to use any available provider for full synthesis
        try:
            from core.voice_providers import get_voice_provider
            provider = get_voice_provider()
            loop = asyncio.new_event_loop()
            try:
                wav_data = loop.run_until_complete(provider.text_to_speech(text))
            finally:
                loop.close()
            # Send full audio as single chunk
            ws.send(json.dumps({
                "type": "audio",
                "data": base64.b64encode(wav_data).decode("ascii"),
                "format": "wav"
            }))
            return True
        except Exception as fallback_err:
            logger.error(f"TTS fallback also failed: {fallback_err}")
            ws.send(json.dumps({"type": "error", "message": "TTS unavailable"}))
            return False

    try:
        ws.send(json.dumps({"type": "speaking_start"}))

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

        logger.info(f"🔊 Streamed {total_bytes} bytes of Cartesia audio to mobile")
        return True

    except Exception as e:
        logger.error(f"TTS streaming error: {e}")
        ws.send(json.dumps({"type": "error", "message": f"TTS error: {e}"}))
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
        """Bidirectional audio stream handler for mobile voice mode.

        Receives real-time PCM audio from the mobile app, transcribes via
        Deepgram streaming STT, processes through consciousness loop,
        generates TTS via Cartesia Sonic, and streams audio back.
        """
        session_id = "agent_conversation"
        user_id = "user_agent"

        # State
        deepgram_client = None
        interrupted = threading.Event()
        is_processing = False
        tts_thread: Optional[threading.Thread] = None

        logger.info("📱 Mobile Voice WebSocket opened")

        def handle_utterance_end(transcript: str):
            """Called when Deepgram detects end of utterance."""
            nonlocal is_processing

            if not transcript.strip():
                return

            is_processing = True
            logger.info(f"🎤 Mobile voice transcript: '{transcript}'")

            try:
                # Notify client we're processing
                ws.send(json.dumps({"type": "processing"}))

                # Process through consciousness loop
                response_text = _process_through_consciousness(
                    transcript, session_id, user_id
                )

                if not response_text:
                    is_processing = False
                    ws.send(json.dumps({"type": "listening"}))
                    return

                logger.info(f"🗣️ Response: '{response_text[:100]}...'")

                # Send response text for chat display
                ws.send(json.dumps({
                    "type": "response_text",
                    "text": response_text,
                    "user_transcript": transcript,
                }))

                # Stream TTS audio to client
                interrupted.clear()
                completed = _stream_tts_to_client(ws, response_text, interrupted)

                ws.send(json.dumps({"type": "speaking_end"}))

                # Resume listening
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

        def handle_transcript(text: str, is_final: bool):
            """Called for each Deepgram transcript (interim and final)."""
            try:
                ws.send(json.dumps({
                    "type": "transcript",
                    "text": text,
                    "is_final": is_final,
                }))
            except Exception:
                pass

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

                    # Initialize Deepgram streaming STT
                    try:
                        from core.deepgram_streaming import DeepgramStreamingClient

                        deepgram_client = DeepgramStreamingClient(
                            language="en",
                            model="nova-3",
                            endpointing_ms=500,
                            sample_rate=16000,
                        )
                        deepgram_client.on_transcript(handle_transcript)
                        deepgram_client.on_utterance_end(handle_utterance_end)
                        deepgram_client.connect()

                        ws.send(json.dumps({"type": "ready"}))
                        ws.send(json.dumps({"type": "listening"}))

                    except Exception as e:
                        logger.error(f"Deepgram init failed: {e}")
                        ws.send(json.dumps({
                            "type": "error",
                            "message": f"STT initialization failed: {e}"
                        }))

                # ----- AUDIO DATA -----
                elif msg_type == "audio":
                    if deepgram_client and deepgram_client.is_connected:
                        audio_b64 = data.get("data", "")
                        if audio_b64:
                            audio_bytes = base64.b64decode(audio_b64)
                            deepgram_client.send_audio(audio_bytes)

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
            # Clean up Deepgram
            if deepgram_client:
                try:
                    deepgram_client.close()
                except Exception:
                    pass

            logger.info(f"📱 Mobile Voice WebSocket closed (user={user_id})")

    logger.info("📱 Mobile Voice WebSocket route registered at /mobile/voice-stream")
