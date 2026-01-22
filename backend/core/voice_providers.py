#!/usr/bin/env python3
"""
Voice Provider Abstraction Layer
================================

Swappable TTS/STT providers for the substrate.
Supports: ElevenLabs (Turbo), Chatterbox (local), future providers.

Usage:
    provider = get_voice_provider()
    audio = await provider.text_to_speech("Hello there")
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


class ChatterboxProvider(VoiceProvider):
    """Local Chatterbox TTS - fallback when ElevenLabs unavailable"""
    
    def __init__(self):
        self.base_url = os.getenv('CHATTERBOX_URL', 'http://localhost:8001')
        logger.info(f"🎙️ Chatterbox provider initialized ({self.base_url})")
    
    async def text_to_speech(
        self, 
        text: str, 
        voice_id: Optional[str] = None,
        speed: float = 1.0
    ) -> bytes:
        """Generate speech using local Chatterbox"""
        
        url = f"{self.base_url}/tts"
        payload = {
            "text": text,
            "voice": voice_id or "default",
            "speed": speed
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
                    
                    logger.error(f"Chatterbox error: {response.status}")
                    raise Exception(f"Chatterbox TTS failed: {response.status}")
                    
        except Exception as e:
            logger.exception(f"Chatterbox TTS error: {e}")
            raise
    
    async def speech_to_text(
        self, 
        audio_data: bytes,
        language: str = "en"
    ) -> str:
        """Chatterbox doesn't have STT - use Whisper"""
        raise NotImplementedError("Use Whisper for STT")
    
    def get_provider_name(self) -> str:
        return "chatterbox"


# Provider factory
_provider_instance: Optional[VoiceProvider] = None

def get_voice_provider() -> VoiceProvider:
    """
    Get the configured voice provider.
    
    Priority:
    1. VOICE_PROVIDER env var (elevenlabs, chatterbox)
    2. If ELEVENLABS_API_KEY exists -> ElevenLabs
    3. Fallback to Chatterbox
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
            logger.warning(f"ElevenLabs init failed, falling back to Chatterbox: {e}")
    
    _provider_instance = ChatterboxProvider()
    return _provider_instance


def reset_voice_provider():
    """Reset provider instance (for testing)"""
    global _provider_instance
    _provider_instance = None
