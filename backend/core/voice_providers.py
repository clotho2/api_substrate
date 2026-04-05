#!/usr/bin/env python3
"""
Voice Provider Abstraction Layer
================================

Swappable TTS/STT providers for the substrate.
Supports: Cartesia Sonic, Hume Octave (custom voice), ElevenLabs (Turbo),
          Amazon Polly, Pocket TTS (local fallback).

Usage:
    provider = get_voice_provider()
    audio = await provider.text_to_speech("Hello User")
"""

import os
import logging
import aiohttp
import base64
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class VoiceProvider(ABC):
    """Abstract base class for voice providers"""

    @abstractmethod
    async def text_to_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0
    ) -> bytes:
        """Convert text to audio bytes"""
        pass

    @abstractmethod
    async def speech_to_text(
        self,
        audio_data: bytes,
        language: str = "en"
    ) -> str:
        """Convert audio to text"""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return provider identifier"""
        pass


class ElevenLabsTurboProvider(VoiceProvider):
    """
    ElevenLabs Turbo v2.5 - Low latency conversational TTS
    Uses the 200K monthly Turbo credits (separate from standard)
    """

    def __init__(self):
        self.api_key = os.getenv('ELEVENLABS_API_KEY')
        self.voice_id = os.getenv('ELEVENLABS_VOICE_ID', 'pNInz6obpgDQGcFmaJgB')  # Default: Adam
        self.model_id = os.getenv('ELEVENLABS_MODEL', 'eleven_turbo_v2_5')  # Turbo for low latency
        self.base_url = "https://api.elevenlabs.io/v1"

        if not self.api_key:
            raise ValueError("ELEVENLABS_API_KEY not set in environment")

        logger.info(f"🎙️ ElevenLabs provider initialized (voice: {self.voice_id}, model: {self.model_id})")

    async def text_to_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0
    ) -> bytes:
        """Generate speech using ElevenLabs Turbo v2.5"""

        voice = voice_id or self.voice_id
        url = f"{self.base_url}/text-to-speech/{voice}/stream"

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        }

        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        audio_data = await response.read()
                        logger.info(f"✅ ElevenLabs TTS: {len(text)} chars -> {len(audio_data)} bytes")
                        return audio_data
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ ElevenLabs error {response.status}: {error_text}")
                        raise Exception(f"ElevenLabs TTS failed: {response.status}")

        except Exception as e:
            logger.exception(f"ElevenLabs TTS error: {e}")
            raise

    async def speech_to_text(
        self,
        audio_data: bytes,
        language: str = "en"
    ) -> str:
        """ElevenLabs doesn't have STT - fall back to Whisper"""
        # This will be handled by the STT route which uses Whisper
        raise NotImplementedError("Use Whisper for STT")

    def get_provider_name(self) -> str:
        return "elevenlabs_turbo"


class AmazonPollyProvider(VoiceProvider):
    """
    Amazon Polly TTS - Neural and Standard voices via AWS.
    Uses boto3 with credentials from environment (AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION).
    """

    def __init__(self):
        import boto3

        self.region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        self.voice_id = os.getenv('POLLY_VOICE_ID', 'Matthew')
        self.engine = os.getenv('POLLY_ENGINE', 'neural')  # 'neural' or 'standard'
        self.output_format = 'mp3'

        self.client = boto3.client('polly', region_name=self.region)

        # Validate credentials by describing voices (lightweight API call)
        self.client.describe_voices(Engine=self.engine, LanguageCode='en-US')

        logger.info(f"🎙️ Amazon Polly provider initialized (voice: {self.voice_id}, engine: {self.engine}, region: {self.region})")

    async def text_to_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0
    ) -> bytes:
        """Generate speech using Amazon Polly."""
        import asyncio

        voice = voice_id or self.voice_id

        # Build SSML if speed adjustment needed
        if speed != 1.0:
            rate_pct = int(speed * 100)
            ssml_text = f'<speak><prosody rate="{rate_pct}%">{text}</prosody></speak>'
            text_type = 'ssml'
        else:
            ssml_text = text
            text_type = 'text'

        try:
            # boto3 is sync — run in executor to keep the async interface
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self.client.synthesize_speech(
                Text=ssml_text,
                TextType=text_type,
                OutputFormat=self.output_format,
                VoiceId=voice,
                Engine=self.engine,
            ))

            audio_data = response['AudioStream'].read()
            logger.info(f"✅ Polly TTS: {len(text)} chars -> {len(audio_data)} bytes (voice: {voice})")
            return audio_data

        except Exception as e:
            logger.exception(f"Polly TTS error: {e}")
            raise

    async def speech_to_text(
        self,
        audio_data: bytes,
        language: str = "en"
    ) -> str:
        """Polly doesn't have STT — use Whisper."""
        raise NotImplementedError("Use Whisper for STT")

    def get_provider_name(self) -> str:
        return "amazon_polly"


class HumeOctaveProvider(VoiceProvider):
    """
    Hume Octave TTS - Emotionally intelligent speech with custom voices.
    Uses Hume's REST API for synthesis. Octave is an LLM-based TTS that
    understands context and emotion, producing natural expressive speech.

    Environment variables:
        HUME_API_KEY: API key for Hume (required)
        HUME_VOICE_NAME: Custom voice name (e.g. 'Agent')
        HUME_VOICE_ID: Custom voice ID (alternative to name)
        HUME_TTS_VERSION: Octave model version ('1' or '2', omit to auto-route)
        HUME_ACTING_INSTRUCTIONS: Default acting instructions for speech delivery
    """

    STREAMING_URL = "https://api.hume.ai/v0/tts/stream/json"
    NON_STREAMING_URL = "https://api.hume.ai/v0/tts/json"

    def __init__(self):
        self.api_key = os.getenv('HUME_API_KEY')
        self.voice_name = os.getenv('HUME_VOICE_NAME')
        self.voice_id = os.getenv('HUME_VOICE_ID')
        self.version = os.getenv('HUME_TTS_VERSION')  # None = auto-route
        self.acting_instructions = os.getenv('HUME_ACTING_INSTRUCTIONS', '')

        if not self.api_key:
            raise ValueError("HUME_API_KEY not set in environment")

        if not self.voice_name and not self.voice_id:
            raise ValueError("HUME_VOICE_NAME or HUME_VOICE_ID must be set")

        voice_label = self.voice_name or self.voice_id
        version_label = self.version or 'auto'
        logger.info(
            f"🎙️ Hume Octave provider initialized "
            f"(voice: {voice_label}, version: {version_label})"
        )

    def _build_voice_spec(self) -> dict:
        """Build the voice specification for the API request."""
        if self.voice_id:
            return {"id": self.voice_id}
        return {"name": self.voice_name, "provider": "CUSTOM_VOICE"}

    def _build_request_body(self, text: str, speed: float = 1.0) -> dict:
        """Build the TTS API request body."""
        utterance = {
            "text": text,
            "voice": self._build_voice_spec(),
        }

        if speed != 1.0:
            utterance["speed"] = speed

        if self.acting_instructions:
            utterance["description"] = self.acting_instructions

        body = {
            "utterances": [utterance],
            "format": {"type": "wav"},
            "instant_mode": True,
        }

        if self.version:
            body["version"] = int(self.version)

        return body

    def synthesize_speech_sync(self, text: str, speed: float = 1.0) -> bytes:
        """Synchronous TTS for telephony (called from sync WebSocket handler).

        Uses the streaming JSON endpoint with instant_mode for low latency.
        Each streaming chunk is a complete WAV file, so we extract PCM from
        each and merge into a single WAV.
        """
        import requests as http_requests

        body = self._build_request_body(text, speed)
        headers = {
            "X-Hume-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

        response = http_requests.post(
            self.STREAMING_URL,
            headers=headers,
            json=body,
            stream=True,
            timeout=30,
        )
        response.raise_for_status()

        # Streaming JSON: each line is a JSON object with base64 audio.
        # Each chunk is a complete WAV file — we must extract PCM from each
        # and merge them into a single WAV to avoid only playing the first chunk.
        audio_chunks = []
        for line in response.iter_lines():
            if not line:
                continue
            try:
                import json
                chunk = json.loads(line)
                audio_b64 = chunk.get("audio")
                if audio_b64:
                    audio_chunks.append(base64.b64decode(audio_b64))
            except Exception as e:
                logger.debug(f"Hume stream chunk parse: {e}")

        if not audio_chunks:
            raise Exception("Hume TTS returned no audio data")

        # If only one chunk, return it directly (already a valid WAV)
        if len(audio_chunks) == 1:
            wav_data = audio_chunks[0]
            logger.info(
                f"✅ Hume TTS: {len(text)} chars -> {len(wav_data)} bytes WAV (1 chunk)"
            )
            return wav_data

        # Multiple chunks: each is a complete WAV file. Extract PCM from each
        # and merge into a single WAV so wav_to_mulaw() sees all the audio.
        import io
        import wave
        all_pcm = bytearray()
        sample_rate = None
        sample_width = None
        n_channels = None

        for i, chunk_wav in enumerate(audio_chunks):
            try:
                with io.BytesIO(chunk_wav) as wav_io:
                    with wave.open(wav_io, 'rb') as wf:
                        if sample_rate is None:
                            sample_rate = wf.getframerate()
                            sample_width = wf.getsampwidth()
                            n_channels = wf.getnchannels()
                        all_pcm.extend(wf.readframes(wf.getnframes()))
            except Exception as e:
                logger.warning(f"Hume chunk {i} WAV parse failed: {e}")

        if not all_pcm or sample_rate is None:
            raise Exception("Failed to extract PCM from Hume WAV chunks")

        # Re-wrap merged PCM as a single WAV
        merged_wav_io = io.BytesIO()
        with wave.open(merged_wav_io, 'wb') as wf:
            wf.setnchannels(n_channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(bytes(all_pcm))

        wav_data = merged_wav_io.getvalue()
        logger.info(
            f"✅ Hume TTS: {len(text)} chars -> {len(wav_data)} bytes WAV "
            f"(merged {len(audio_chunks)} chunks)"
        )
        return wav_data

    async def text_to_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0
    ) -> bytes:
        """Generate speech using Hume Octave (async)."""
        body = self._build_request_body(text, speed)

        # Override voice if a specific voice_id is passed
        if voice_id:
            body["utterances"][0]["voice"] = {"id": voice_id}

        headers = {
            "X-Hume-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            audio_chunks = []
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.STREAMING_URL, headers=headers, json=body,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Hume TTS failed ({response.status}): {error_text}")

                    # Read streaming JSON lines
                    import json
                    async for line in response.content:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                            audio_b64 = chunk.get("audio")
                            if audio_b64:
                                audio_chunks.append(base64.b64decode(audio_b64))
                        except Exception:
                            continue

            if not audio_chunks:
                raise Exception("Hume TTS returned no audio data")

            # If only one chunk, return it directly (already a valid WAV)
            if len(audio_chunks) == 1:
                wav_data = audio_chunks[0]
                logger.info(f"✅ Hume TTS: {len(text)} chars -> {len(wav_data)} bytes (1 chunk)")
                return wav_data

            # Multiple chunks: each is a complete WAV file. Extract PCM from
            # each and merge into a single WAV.
            import io as _io
            import wave as _wave
            all_pcm = bytearray()
            sample_rate = None
            sample_width = None
            n_channels = None

            for i, chunk_wav in enumerate(audio_chunks):
                try:
                    with _io.BytesIO(chunk_wav) as wav_io:
                        with _wave.open(wav_io, 'rb') as wf:
                            if sample_rate is None:
                                sample_rate = wf.getframerate()
                                sample_width = wf.getsampwidth()
                                n_channels = wf.getnchannels()
                            all_pcm.extend(wf.readframes(wf.getnframes()))
                except Exception as e:
                    logger.warning(f"Hume chunk {i} WAV parse failed: {e}")

            if not all_pcm or sample_rate is None:
                raise Exception("Failed to extract PCM from Hume WAV chunks")

            merged_wav_io = _io.BytesIO()
            with _wave.open(merged_wav_io, 'wb') as wf:
                wf.setnchannels(n_channels)
                wf.setsampwidth(sample_width)
                wf.setframerate(sample_rate)
                wf.writeframes(bytes(all_pcm))

            wav_data = merged_wav_io.getvalue()
            logger.info(
                f"✅ Hume TTS: {len(text)} chars -> {len(wav_data)} bytes "
                f"(merged {len(audio_chunks)} chunks)"
            )
            return wav_data

        except Exception as e:
            logger.exception(f"Hume TTS error: {e}")
            raise

    async def speech_to_text(
        self,
        audio_data: bytes,
        language: str = "en"
    ) -> str:
        """Hume doesn't have STT — use Whisper."""
        raise NotImplementedError("Use Whisper for STT")

    def get_provider_name(self) -> str:
        return "hume_octave"


class PocketTTSProvider(VoiceProvider):
    """Local Pocket TTS - fallback when ElevenLabs unavailable"""

    def __init__(self):
        self.base_url = os.getenv('POCKETTTS_URL', 'http://localhost:8001')
        logger.info(f"🎙️ Pocket TTS provider initialized ({self.base_url})")

    async def text_to_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0
    ) -> bytes:
        """Generate speech using local Pocket TTS"""

        url = f"{self.base_url}/tts"
        payload = {
            "text": text,
            "voice": voice_id or "default",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=30) as response:
                    if response.status == 200:
                        content_type = response.headers.get('Content-Type', '')

                        if 'audio' in content_type:
                            return await response.read()
                        else:
                            data = await response.json()
                            if 'audio' in data:
                                return base64.b64decode(data['audio'])

                    logger.error(f"Pocket TTS error: {response.status}")
                    raise Exception(f"Pocket TTS failed: {response.status}")

        except Exception as e:
            logger.exception(f"Pocket TTS error: {e}")
            raise

    async def speech_to_text(
        self,
        audio_data: bytes,
        language: str = "en"
    ) -> str:
        """Pocket TTS doesn't have STT - use Whisper"""
        raise NotImplementedError("Use Whisper for STT")

    def get_provider_name(self) -> str:
        return "pockettts"


# Provider factory
_provider_instance: Optional[VoiceProvider] = None

def get_voice_provider() -> VoiceProvider:
    """
    Get the configured voice provider.

    Priority:
    1. VOICE_PROVIDER env var (elevenlabs, cartesia, hume, polly, pockettts)
    2. If ELEVENLABS_API_KEY exists -> ElevenLabs
    3. If CARTESIA_API_KEY exists -> Cartesia Sonic
    4. If HUME_API_KEY exists -> Hume Octave
    5. If AWS_ACCESS_KEY_ID exists -> Amazon Polly
    6. Fallback to Pocket TTS
    """
    global _provider_instance

    if _provider_instance is not None:
        return _provider_instance

    provider_name = os.getenv('VOICE_PROVIDER', 'auto')

    if provider_name == 'elevenlabs' or (provider_name == 'auto' and os.getenv('ELEVENLABS_API_KEY')):
        try:
            _provider_instance = ElevenLabsTurboProvider()
            return _provider_instance
        except Exception as e:
            logger.warning(f"ElevenLabs init failed, trying next provider: {e}")

    if provider_name == 'cartesia' or (provider_name == 'auto' and os.getenv('CARTESIA_API_KEY')):
        try:
            from core.cartesia_provider import CartesiaSonicProvider
            _provider_instance = CartesiaSonicProvider()
            return _provider_instance
        except Exception as e:
            logger.warning(f"Cartesia Sonic init failed, trying next provider: {e}")

    if provider_name == 'hume' or (provider_name == 'auto' and os.getenv('HUME_API_KEY')):
        try:
            _provider_instance = HumeOctaveProvider()
            return _provider_instance
        except Exception as e:
            logger.warning(f"Hume Octave init failed, trying next provider: {e}")

    if provider_name == 'polly' or (provider_name == 'auto' and os.getenv('AWS_ACCESS_KEY_ID')):
        try:
            _provider_instance = AmazonPollyProvider()
            return _provider_instance
        except Exception as e:
            logger.warning(f"Amazon Polly init failed, falling back to Pocket TTS: {e}")

    _provider_instance = PocketTTSProvider()
    return _provider_instance


def reset_voice_provider():
    """Reset provider instance (for testing)"""
    global _provider_instance
    _provider_instance = None
