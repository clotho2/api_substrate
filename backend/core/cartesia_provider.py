#!/usr/bin/env python3
"""
Cartesia Sonic TTS Provider
============================

Low-latency streaming text-to-speech via Cartesia's HTTP streaming API.
Designed for real-time voice conversations — streams PCM audio chunks
as they're generated, enabling playback to start before synthesis completes.

Cartesia Sonic has ~100-200ms time-to-first-byte, making it ideal for
conversational voice applications.

Environment variables:
    CARTESIA_API_KEY: API key (required)
    CARTESIA_VOICE_ID: Voice ID (optional, uses default male voice)
    CARTESIA_MODEL: Model ID (optional, defaults to sonic-2)

Usage:
    provider = CartesiaSonicProvider()

    # Synchronous streaming (for WebSocket handlers):
    for chunk in provider.stream_speech_sync("Hello"):
        ws.send(chunk)  # raw PCM bytes

    # Full synthesis:
    audio_bytes = provider.synthesize_speech_sync("Hello")
"""

import os
import io
import json
import logging
import struct
import wave
import requests as http_requests
from typing import Optional, Iterator

import aiohttp

logger = logging.getLogger(__name__)

# Cartesia API endpoints
CARTESIA_TTS_URL = "https://api.cartesia.ai/tts/bytes"
CARTESIA_TTS_SSE_URL = "https://api.cartesia.ai/tts/sse"
CARTESIA_VOICES_URL = "https://api.cartesia.ai/voices"

# Default voice: a natural male English voice
DEFAULT_VOICE_ID = "a0e99841-438c-4a64-b679-ae501e7d6091"  # Barbershop Man
DEFAULT_MODEL = "sonic-2"


class CartesiaSonicProvider:
    """Cartesia Sonic TTS provider for low-latency voice synthesis.

    Supports both streaming (chunk-by-chunk) and full synthesis modes.
    Output format: raw PCM 16-bit signed little-endian at 24kHz mono,
    which can be streamed directly to the mobile app or converted to WAV.
    """

    def __init__(self):
        self.api_key = os.getenv("CARTESIA_API_KEY", "")
        if not self.api_key:
            raise ValueError("CARTESIA_API_KEY not set in environment")

        self.voice_id = os.getenv("CARTESIA_VOICE_ID", DEFAULT_VOICE_ID)
        self.model_id = os.getenv("CARTESIA_MODEL", DEFAULT_MODEL)
        self.sample_rate = 24000  # Cartesia outputs 24kHz
        self.encoding = "pcm_s16le"  # 16-bit signed little-endian PCM

        logger.info(
            f"🎙️ Cartesia Sonic provider initialized "
            f"(voice: {self.voice_id}, model: {self.model_id})"
        )

    def _build_headers(self) -> dict:
        return {
            "X-API-Key": self.api_key,
            "Cartesia-Version": "2024-06-10",
            "Content-Type": "application/json",
        }

    def _build_payload(self, text: str, speed: float = 1.0) -> dict:
        payload = {
            "model_id": self.model_id,
            "transcript": text,
            "voice": {
                "mode": "id",
                "id": self.voice_id,
            },
            "output_format": {
                "container": "raw",
                "encoding": self.encoding,
                "sample_rate": self.sample_rate,
            },
            "language": "en",
        }
        if speed != 1.0:
            payload["voice"]["__experimental_controls"] = {
                "speed": "slow" if speed < 0.8 else ("fast" if speed > 1.2 else "normal")
            }
        return payload

    def stream_speech_sync(
        self,
        text: str,
        speed: float = 1.0,
        chunk_size: int = 4800,
    ) -> Iterator[bytes]:
        """Stream TTS audio chunks synchronously (for WebSocket handlers).

        Yields raw PCM chunks as Cartesia generates them. Each chunk is
        `chunk_size` bytes of 16-bit PCM at 24kHz (default 4800 bytes = 100ms).

        Args:
            text: Text to synthesize
            speed: Speech speed multiplier
            chunk_size: Bytes per yielded chunk (default 4800 = 100ms at 24kHz)

        Yields:
            Raw PCM 16-bit 24kHz audio chunks
        """
        payload = self._build_payload(text, speed)

        try:
            response = http_requests.post(
                CARTESIA_TTS_URL,
                headers=self._build_headers(),
                json=payload,
                stream=True,
                timeout=30,
            )
            response.raise_for_status()

            total_bytes = 0
            buffer = bytearray()

            for data in response.iter_content(chunk_size=chunk_size):
                buffer.extend(data)
                while len(buffer) >= chunk_size:
                    chunk = bytes(buffer[:chunk_size])
                    buffer = buffer[chunk_size:]
                    total_bytes += len(chunk)
                    yield chunk

            # Yield remaining buffer
            if buffer:
                total_bytes += len(buffer)
                yield bytes(buffer)

            logger.info(
                f"✅ Cartesia TTS streamed: {len(text)} chars -> "
                f"{total_bytes} bytes PCM ({total_bytes / (2 * self.sample_rate):.1f}s)"
            )

        except http_requests.HTTPError as e:
            logger.error(f"Cartesia HTTP error: {e.response.status_code} - {e.response.text[:200]}")
            raise
        except Exception as e:
            logger.error(f"Cartesia streaming error: {e}")
            raise

    def synthesize_speech_sync(self, text: str, speed: float = 1.0) -> bytes:
        """Synthesize full audio synchronously. Returns WAV bytes.

        Args:
            text: Text to synthesize
            speed: Speech speed multiplier

        Returns:
            WAV file bytes (16-bit PCM, 24kHz, mono)
        """
        pcm_chunks = list(self.stream_speech_sync(text, speed))
        pcm_data = b"".join(pcm_chunks)

        # Wrap in WAV container
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_data)

        return wav_io.getvalue()

    async def text_to_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
    ) -> bytes:
        """Async TTS - returns full WAV audio bytes.

        Compatible with the VoiceProvider interface pattern.
        """
        payload = self._build_payload(text, speed)
        if voice_id:
            payload["voice"]["id"] = voice_id

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    CARTESIA_TTS_URL,
                    headers=self._build_headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(
                            f"Cartesia TTS failed ({response.status}): {error_text[:200]}"
                        )

                    pcm_data = await response.read()

            # Wrap in WAV
            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(pcm_data)

            wav_bytes = wav_io.getvalue()
            logger.info(
                f"✅ Cartesia TTS: {len(text)} chars -> {len(wav_bytes)} bytes WAV"
            )
            return wav_bytes

        except Exception as e:
            logger.exception(f"Cartesia TTS error: {e}")
            raise

    def get_provider_name(self) -> str:
        return "cartesia_sonic"
