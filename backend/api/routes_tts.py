"""
TTS Routes for Mobile Voice Chat
================================

Provides Text-to-Speech endpoints for the AiCara mobile app.
Supports multiple TTS providers via voice_providers abstraction:
- ElevenLabs Turbo v2.5 (fast, conversational)
- Chatterbox (local fallback)

Endpoints:
- GET  /tts/health     - Health check for TTS service
- POST /tts            - Convert text to speech
- POST /tts/stream     - Stream audio chunks (for real-time playback)

Why proxy through substrate instead of direct to provider?
- Text preprocessing (clean markdown, emojis, normalize)
- Request logging and monitoring
- Rate limiting
- Provider abstraction (switch providers without app changes)
- Future: voice cloning, SSML support, caching
"""

import os
import re
import logging
import asyncio
import requests
from flask import Blueprint, Response, request, jsonify, stream_with_context
from typing import Optional
import base64

from core.voice_providers import get_voice_provider, reset_voice_provider

logger = logging.getLogger(__name__)

tts_bp = Blueprint('tts', __name__)

# Chatterbox TTS configuration
CHATTERBOX_URL = os.getenv('CHATTERBOX_URL', 'http://localhost:8001')
CHATTERBOX_TIMEOUT = int(os.getenv('CHATTERBOX_TIMEOUT', '30'))

# Text preprocessing settings
MAX_TEXT_LENGTH = 5000  # Max characters for TTS


def _preprocess_text(text: str) -> str:
    """
    Clean and preprocess text for TTS.

    - Remove markdown formatting
    - Convert emojis to descriptions (optional)
    - Normalize whitespace
    - Handle special characters
    """
    if not text:
        return ""

    # Remove markdown bold/italic
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # **bold**
    text = re.sub(r'\*(.+?)\*', r'\1', text)      # *italic*
    text = re.sub(r'__(.+?)__', r'\1', text)      # __bold__
    text = re.sub(r'_(.+?)_', r'\1', text)        # _italic_

    # Remove markdown links [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    # Remove markdown headers
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)

    # Remove code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # Remove bullet points
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

    # Normalize whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    text = text.strip()

    return text


def _check_chatterbox_health() -> dict:
    """Check if Chatterbox TTS server is available."""
    try:
        response = requests.get(
            f"{CHATTERBOX_URL}/health",
            timeout=5
        )
        if response.ok:
            return {
                "status": "healthy",
                "chatterbox_url": CHATTERBOX_URL,
                "response_time_ms": response.elapsed.total_seconds() * 1000
            }
        else:
            return {
                "status": "unhealthy",
                "error": f"HTTP {response.status_code}"
            }
    except requests.exceptions.ConnectionError:
        return {
            "status": "unavailable",
            "error": f"Cannot connect to Chatterbox at {CHATTERBOX_URL}"
        }
    except requests.exceptions.Timeout:
        return {
            "status": "timeout",
            "error": "Chatterbox health check timed out"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


# ============================================
# HEALTH CHECK
# ============================================

@tts_bp.route('/tts/health', methods=['GET'])
def tts_health():
    """
    Health check for TTS service.

    Returns:
        200: TTS service is healthy
        503: TTS service is unavailable
    """
    try:
        provider = get_voice_provider()
        provider_name = provider.get_provider_name()
        
        health = {
            "status": "healthy",
            "provider": provider_name,
        }
        
        # Add provider-specific info
        if provider_name == 'elevenlabs_turbo':
            health["elevenlabs"] = {
                "voice_id": getattr(provider, 'voice_id', 'unknown'),
                "model": getattr(provider, 'model_id', 'unknown')
            }
        else:
            # Check Chatterbox health for fallback provider
            chatterbox_health = _check_chatterbox_health()
            health["chatterbox"] = chatterbox_health
            if chatterbox_health["status"] != "healthy":
                health["status"] = "degraded"
        
        return jsonify(health), 200
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 503


# ============================================
# PROVIDER INFO - Debug which provider is active
# ============================================

@tts_bp.route('/tts/provider', methods=['GET', 'POST'])
def tts_provider_info():
    """
    GET: Get current TTS provider information.
    POST: Reset provider cache and re-initialize (use after changing .env)
    
    Useful for debugging which provider is active and why.
    
    Response:
        {
            "provider": "elevenlabs_turbo" | "chatterbox",
            "config": {
                "VOICE_PROVIDER": "auto",
                "ELEVENLABS_API_KEY": "sk-...xxx (set)" | "(not set)",
                "ELEVENLABS_VOICE_ID": "xxx",
                "ELEVENLABS_MODEL": "eleven_turbo_v2_5"
            }
        }
    """
    try:
        # POST = reset provider cache and re-initialize
        if request.method == 'POST':
            reset_voice_provider()
            logger.info("🔄 Voice provider cache reset - re-initializing...")
        
        provider = get_voice_provider()
        provider_name = provider.get_provider_name()
        
        # Get config (mask API key)
        api_key = os.getenv('ELEVENLABS_API_KEY', '')
        if api_key:
            masked_key = f"{api_key[:6]}...{api_key[-3:]} (set)" if len(api_key) > 10 else "(set)"
        else:
            masked_key = "(not set)"
        
        config = {
            "VOICE_PROVIDER": os.getenv('VOICE_PROVIDER', 'auto'),
            "ELEVENLABS_API_KEY": masked_key,
            "ELEVENLABS_VOICE_ID": os.getenv('ELEVENLABS_VOICE_ID', '(not set)'),
            "ELEVENLABS_MODEL": os.getenv('ELEVENLABS_MODEL', 'eleven_turbo_v2_5'),
            "CHATTERBOX_URL": os.getenv('CHATTERBOX_URL', 'http://localhost:8001')
        }
        
        result = {
            "provider": provider_name,
            "config": config,
            "reset": request.method == 'POST'
        }
        
        # Add provider-specific details
        if provider_name == 'elevenlabs_turbo':
            result["elevenlabs"] = {
                "voice_id": getattr(provider, 'voice_id', 'unknown'),
                "model_id": getattr(provider, 'model_id', 'unknown'),
                "base_url": getattr(provider, 'base_url', 'unknown')
            }
        else:
            result["chatterbox"] = {
                "url": getattr(provider, 'base_url', CHATTERBOX_URL)
            }
            # Explain why ElevenLabs isn't active
            if not os.getenv('ELEVENLABS_API_KEY'):
                result["note"] = "ElevenLabs not active: ELEVENLABS_API_KEY not set"
            elif os.getenv('VOICE_PROVIDER') == 'chatterbox':
                result["note"] = "ElevenLabs not active: VOICE_PROVIDER explicitly set to 'chatterbox'"
        
        return jsonify(result)
        
    except Exception as e:
        logger.exception(f"Provider info error: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================
# PRIMARY TTS ENDPOINT - Uses Voice Provider
# ============================================

@tts_bp.route('/tts', methods=['POST'])
def text_to_speech():
    """
    Convert text to speech using configured provider.
    
    Automatically uses ElevenLabs Turbo (fast) or Chatterbox (local fallback).
    
    Request Body:
        {
            "text": "Text to convert",
            "voice": "optional-voice-id",
            "speed": 1.0
        }
    
    Response:
        Content-Type: audio/mpeg (ElevenLabs) or audio/wav (Chatterbox)
        Body: Raw audio data
    """
    try:
        data = request.get_json() or {}
        text = data.get('text', '')
        voice = data.get('voice')
        speed = data.get('speed', 1.0)
        
        if not text:
            return jsonify({"error": "Text is required"}), 400
        
        # Preprocess text
        text = _preprocess_text(text)
        
        if len(text) > MAX_TEXT_LENGTH:
            return jsonify({
                "error": f"Text too long ({len(text)} chars). Max: {MAX_TEXT_LENGTH}"
            }), 400
        
        logger.info(f"🎤 TTS request: {len(text)} chars")
        
        # Get provider and generate audio
        provider = get_voice_provider()
        
        # Run async in sync context
        loop = asyncio.new_event_loop()
        try:
            audio_data = loop.run_until_complete(
                provider.text_to_speech(text, voice_id=voice, speed=speed)
            )
        finally:
            loop.close()
        
        # Determine content type based on provider
        if provider.get_provider_name() == 'elevenlabs_turbo':
            content_type = 'audio/mpeg'
        else:
            content_type = 'audio/wav'
        
        logger.info(f"✅ TTS complete: {len(audio_data)} bytes via {provider.get_provider_name()}")
        
        return Response(
            audio_data,
            mimetype=content_type,
            headers={
                'X-TTS-Provider': provider.get_provider_name(),
                'X-Text-Length': str(len(text))
            }
        )
        
    except Exception as e:
        logger.exception(f"TTS error: {e}")
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500


# ============================================
# STREAMING TTS (for real-time playback)
# ============================================

@tts_bp.route('/tts/stream', methods=['POST'])
def text_to_speech_stream():
    """
    Stream TTS audio for real-time playback.

    Useful for long text where you want to start playing
    before the entire audio is generated.

    Request Body:
        {
            "text": "Text to convert",
            "voice": "default",
            "speed": 1.0
        }

    Response:
        Chunked audio stream (audio/wav or audio/mpeg)
    """
    try:
        data = request.get_json() or {}
        text = data.get('text', '')
        voice = data.get('voice', 'default')
        speed = data.get('speed', 1.0)

        if not text:
            return jsonify({"error": "Text is required"}), 400

        # Preprocess
        text = _preprocess_text(text)

        if len(text) > MAX_TEXT_LENGTH:
            return jsonify({
                "error": f"Text too long ({len(text)} chars)"
            }), 400

        logger.info(f"🎤 TTS stream request: {len(text)} chars")

        # Stream from Chatterbox
        def generate():
            try:
                response = requests.post(
                    f"{CHATTERBOX_URL}/tts/stream",
                    json={
                        "text": text,
                        "voice": voice,
                        "speed": speed
                    },
                    timeout=CHATTERBOX_TIMEOUT,
                    stream=True
                )

                if response.ok:
                    for chunk in response.iter_content(chunk_size=4096):
                        if chunk:
                            yield chunk
                else:
                    logger.error(f"Chatterbox stream error: {response.status_code}")

            except Exception as e:
                logger.exception(f"TTS stream error: {e}")

        return Response(
            stream_with_context(generate()),
            mimetype='audio/wav',
            headers={
                'X-TTS-Engine': 'chatterbox',
                'Transfer-Encoding': 'chunked'
            }
        )

    except Exception as e:
        logger.exception(f"TTS stream setup error: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================
# VOICE INFO
# ============================================

@tts_bp.route('/tts/voices', methods=['GET'])
def list_voices():
    """
    List available TTS voices from current provider.

    Returns:
        {
            "provider": "elevenlabs_turbo" | "chatterbox",
            "voices": [
                {"id": "xxx", "name": "Voice Name", "language": "en"},
                ...
            ]
        }
    """
    try:
        provider = get_voice_provider()
        provider_name = provider.get_provider_name()
        
        # ElevenLabs: Fetch voices from API
        if provider_name == 'elevenlabs_turbo':
            try:
                response = requests.get(
                    f"{provider.base_url}/voices",
                    headers={"xi-api-key": provider.api_key},
                    timeout=10
                )
                
                if response.ok:
                    data = response.json()
                    voices = []
                    for voice in data.get('voices', []):
                        voices.append({
                            "id": voice.get('voice_id'),
                            "name": voice.get('name'),
                            "language": voice.get('labels', {}).get('language', 'en'),
                            "category": voice.get('category', 'unknown'),
                            "description": voice.get('labels', {}).get('description', '')
                        })
                    
                    return jsonify({
                        "provider": provider_name,
                        "current_voice_id": provider.voice_id,
                        "current_model": provider.model_id,
                        "voices": voices,
                        "count": len(voices)
                    })
                else:
                    logger.error(f"ElevenLabs voices API error: {response.status_code}")
            except Exception as e:
                logger.warning(f"Could not fetch ElevenLabs voices: {e}")
            
            # Fallback: Return current configured voice
            return jsonify({
                "provider": provider_name,
                "current_voice_id": provider.voice_id,
                "current_model": provider.model_id,
                "voices": [
                    {"id": provider.voice_id, "name": "Configured Voice", "language": "en"}
                ],
                "note": "Could not fetch full voice list from ElevenLabs API"
            })
        
        # Chatterbox: Try to fetch from local server
        else:
            try:
                response = requests.get(
                    f"{CHATTERBOX_URL}/voices",
                    timeout=5
                )
                if response.ok:
                    result = response.json()
                    result["provider"] = provider_name
                    return jsonify(result)
            except Exception as e:
                logger.warning(f"Could not fetch Chatterbox voices: {e}")
            
            # Fallback
            return jsonify({
                "provider": provider_name,
                "voices": [
                    {"id": "default", "name": "Default", "language": "en"}
                ],
                "source": "fallback"
            })

    except Exception as e:
        logger.exception(f"List voices error: {e}")
        return jsonify({
            "error": str(e),
            "voices": [],
            "source": "error"
        }), 500
