#!/usr/bin/env python3
"""
Deepgram Streaming STT Client
==============================

Real-time speech-to-text via Deepgram's WebSocket API.
Used by the mobile voice WebSocket endpoint for low-latency transcription.

Deepgram streams interim transcripts as the user speaks and sends a final
transcript when it detects the end of an utterance (~500ms silence).

Requires:
    DEEPGRAM_API_KEY environment variable

Usage:
    client = DeepgramStreamingClient()
    client.on_transcript(callback)      # Register transcript handler
    client.on_utterance_end(callback)   # Register utterance-end handler
    await client.connect()
    client.send_audio(pcm_bytes)        # Send audio chunks
    await client.close()
"""

import os
import json
import base64
import logging
import asyncio
import threading
from typing import Optional, Callable

logger = logging.getLogger(__name__)

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"


class DeepgramStreamingClient:
    """Manages a streaming WebSocket connection to Deepgram for real-time STT.

    This client is designed for synchronous WebSocket handlers (flask-sock).
    It runs the Deepgram WebSocket in a background thread with its own
    asyncio event loop, and provides a synchronous send_audio() method.
    """

    def __init__(
        self,
        language: str = "en",
        model: str = "nova-3",
        endpointing_ms: int = 500,
        sample_rate: int = 16000,
    ):
        self.api_key = DEEPGRAM_API_KEY
        if not self.api_key:
            raise ValueError("DEEPGRAM_API_KEY not set in environment")

        self.language = language
        self.model = model
        self.endpointing_ms = endpointing_ms
        self.sample_rate = sample_rate

        # Callbacks
        self._on_transcript: Optional[Callable] = None
        self._on_utterance_end: Optional[Callable] = None
        self._on_error: Optional[Callable] = None

        # Connection state
        self._ws = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._connected = False
        self._closing = False

        # Accumulate partial transcripts between utterance boundaries
        self._current_transcript = ""

    def on_transcript(self, callback: Callable[[str, bool], None]):
        """Register callback for transcripts: callback(text, is_final)"""
        self._on_transcript = callback

    def on_utterance_end(self, callback: Callable[[str], None]):
        """Register callback for utterance end: callback(full_transcript)"""
        self._on_utterance_end = callback

    def on_error(self, callback: Callable[[str], None]):
        """Register callback for errors: callback(error_message)"""
        self._on_error = callback

    def connect(self):
        """Start the Deepgram WebSocket connection in a background thread."""
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="deepgram-stt"
        )
        self._thread.start()

        # Wait for connection to establish (up to 5s)
        for _ in range(50):
            if self._connected:
                return
            import time
            time.sleep(0.1)

        if not self._connected:
            logger.error("Deepgram WebSocket connection timed out")
            raise ConnectionError("Failed to connect to Deepgram")

    def _run_loop(self):
        """Run the asyncio event loop for the Deepgram WebSocket."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect_and_listen())

    async def _connect_and_listen(self):
        """Connect to Deepgram and listen for transcript events."""
        try:
            import websockets
        except ImportError:
            logger.error("websockets package not installed. Install with: pip install websockets")
            return

        params = (
            f"?model={self.model}"
            f"&language={self.language}"
            f"&encoding=linear16"
            f"&sample_rate={self.sample_rate}"
            f"&channels=1"
            f"&endpointing={self.endpointing_ms}"
            f"&interim_results=true"
            f"&utterance_end_ms=1000"
            f"&smart_format=true"
            f"&punctuate=true"
        )

        url = f"{DEEPGRAM_WS_URL}{params}"
        headers = {"Authorization": f"Token {self.api_key}"}

        try:
            async with websockets.connect(url, extra_headers=headers) as ws:
                self._ws = ws
                self._connected = True
                logger.info(f"🎙️ Deepgram streaming STT connected (model={self.model})")

                async for message in ws:
                    if self._closing:
                        break
                    self._handle_message(message)

        except Exception as e:
            logger.error(f"Deepgram WebSocket error: {e}")
            if self._on_error:
                self._on_error(str(e))
        finally:
            self._connected = False
            self._ws = None
            logger.info("🎙️ Deepgram streaming STT disconnected")

    def _handle_message(self, message: str):
        """Parse Deepgram WebSocket message and dispatch callbacks."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return

        msg_type = data.get("type", "")

        if msg_type == "Results":
            channel = data.get("channel", {})
            alternatives = channel.get("alternatives", [])
            if not alternatives:
                return

            transcript = alternatives[0].get("transcript", "").strip()
            is_final = data.get("is_final", False)
            speech_final = data.get("speech_final", False)

            if transcript:
                if is_final:
                    # Final transcript for this segment
                    self._current_transcript += (" " + transcript if self._current_transcript else transcript)

                if self._on_transcript:
                    self._on_transcript(transcript, is_final)

                # speech_final means Deepgram detected end of utterance
                if speech_final and self._current_transcript:
                    full = self._current_transcript.strip()
                    self._current_transcript = ""
                    if self._on_utterance_end:
                        self._on_utterance_end(full)

        elif msg_type == "UtteranceEnd":
            # Backup utterance end signal
            if self._current_transcript.strip():
                full = self._current_transcript.strip()
                self._current_transcript = ""
                if self._on_utterance_end:
                    self._on_utterance_end(full)

    def send_audio(self, audio_bytes: bytes):
        """Send raw PCM audio bytes to Deepgram (thread-safe).

        Args:
            audio_bytes: Raw 16-bit PCM audio at the configured sample rate
        """
        if not self._connected or not self._ws or not self._loop:
            return

        try:
            asyncio.run_coroutine_threadsafe(
                self._ws.send(audio_bytes), self._loop
            )
        except Exception as e:
            logger.debug(f"Failed to send audio to Deepgram: {e}")

    def close(self):
        """Close the Deepgram WebSocket connection."""
        self._closing = True
        self._current_transcript = ""

        if self._ws and self._loop and self._connected:
            try:
                # Send close signal to Deepgram
                asyncio.run_coroutine_threadsafe(
                    self._ws.send(json.dumps({"type": "CloseStream"})),
                    self._loop,
                )
            except Exception:
                pass

        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

        self._connected = False
        logger.info("🎙️ Deepgram streaming client closed")

    @property
    def is_connected(self) -> bool:
        return self._connected
