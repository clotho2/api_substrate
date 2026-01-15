"""
STT Routes for Mobile Voice Chat
================================

Provides Speech-to-Text endpoints for the AiCara mobile app.
Supports multiple backends: Whisper (local), Deepgram, OpenAI Whisper API.

Endpoints:
- GET  /stt/health     - Health check for STT service
- POST /stt            - Transcribe audio to text
- POST /stt/stream     - Stream transcription (for real-time)

Recommended Setup:
- Local Whisper server (faster-whisper or whisper.cpp) for free transcription
- Or OpenAI Whisper API as fallback

Environment Variables:
- WHISPER_URL: Local Whisper server URL (default: http://localhost:9000)
- WHISPER_MODEL: Model size (tiny, base, small, medium, large)
- OPENAI_API_KEY: For OpenAI Whisper API fallback
- STT_PROVIDER: 'whisper_local', 'openai', 'deepgram' (default: whisper_local)
"""

import os
import io
import logging
import requests
from flask import Blueprint, Response, request, jsonify
from typing import Optional, Tuple
import base64

logger = logging.getLogger(__name__)

stt_bp = Blueprint('stt', __name__)

# STT Configuration
STT_PROVIDER = os.getenv('STT_PROVIDER', 'whisper_local')
WHISPER_URL = os.getenv('WHISPER_URL', 'http://localhost:9000')
WHISPER_MODEL = os.getenv('WHISPER_MODEL', 'base')
WHISPER_TIMEOUT = int(os.getenv('WHISPER_TIMEOUT', '60'))
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY', '')

# Supported audio formats
SUPPORTED_FORMATS = ['audio/wav', 'audio/mpeg', 'audio/mp3', 'audio/webm',
                     'audio/ogg', 'audio/flac', 'audio/m4a', 'audio/x-wav']


def _check_whisper_health() -> dict:
    """Check if local Whisper server is available."""
    try:
        # Try common health endpoints
        for endpoint in ['/health', '/', '/v1/audio/transcriptions']:
            try:
                response = requests.get(
                    f"{WHISPER_URL}{endpoint}",
                    timeout=5
                )
                if response.ok:
                    return {
                        "status": "healthy",
                        "provider": "whisper_local",
                        "url": WHISPER_URL,
                        "model": WHISPER_MODEL,
                        "response_time_ms": response.elapsed.total_seconds() * 1000
                    }
            except:
                continue

        return {
            "status": "unhealthy",
            "provider": "whisper_local",
            "error": "No valid health endpoint found"
        }
    except requests.exceptions.ConnectionError:
        return {
            "status": "unavailable",
            "provider": "whisper_local",
            "error": f"Cannot connect to Whisper at {WHISPER_URL}"
        }
    except Exception as e:
        return {
            "status": "error",
            "provider": "whisper_local",
            "error": str(e)
        }


def _transcribe_whisper_local(audio_data: bytes, content_type: str, language: str = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Transcribe audio using local Whisper server.

    Supports faster-whisper-server, whisper.cpp server, and similar APIs.

    Returns:
        (transcription, error) - One will be None
    """
    try:
        # Determine file extension from content type
        ext_map = {
            'audio/wav': 'wav',
            'audio/x-wav': 'wav',
            'audio/mpeg': 'mp3',
            'audio/mp3': 'mp3',
            'audio/webm': 'webm',
            'audio/ogg': 'ogg',
            'audio/flac': 'flac',
            'audio/m4a': 'm4a',
        }
        ext = ext_map.get(content_type, 'wav')

        # Build multipart form data
        files = {
            'file': (f'audio.{ext}', io.BytesIO(audio_data), content_type)
        }
        data = {
            'model': WHISPER_MODEL,
            'response_format': 'json'
        }
        if language:
            data['language'] = language

        # Try OpenAI-compatible endpoint first (most common)
        response = requests.post(
            f"{WHISPER_URL}/v1/audio/transcriptions",
            files=files,
            data=data,
            timeout=WHISPER_TIMEOUT
        )

        if response.ok:
            result = response.json()
            text = result.get('text', '').strip()
            logger.info(f"🎤 Whisper transcription: {len(text)} chars")
            return text, None

        # Try alternative endpoint format
        response = requests.post(
            f"{WHISPER_URL}/transcribe",
            files=files,
            data=data,
            timeout=WHISPER_TIMEOUT
        )

        if response.ok:
            result = response.json()
            text = result.get('text', result.get('transcription', '')).strip()
            return text, None

        return None, f"Whisper error: {response.status_code} - {response.text}"

    except requests.exceptions.Timeout:
        return None, "Transcription timed out"
    except requests.exceptions.ConnectionError:
        return None, f"Cannot connect to Whisper at {WHISPER_URL}"
    except Exception as e:
        logger.exception(f"Whisper transcription error: {e}")
        return None, str(e)


def _transcribe_openai(audio_data: bytes, content_type: str, language: str = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Transcribe audio using OpenAI Whisper API.

    Fallback when local Whisper is unavailable.
    """
    if not OPENAI_API_KEY:
        return None, "OpenAI API key not configured"

    try:
        ext_map = {
            'audio/wav': 'wav',
            'audio/mpeg': 'mp3',
            'audio/mp3': 'mp3',
            'audio/webm': 'webm',
            'audio/m4a': 'm4a',
        }
        ext = ext_map.get(content_type, 'wav')

        files = {
            'file': (f'audio.{ext}', io.BytesIO(audio_data), content_type)
        }
        data = {
            'model': 'whisper-1',
            'response_format': 'json'
        }
        if language:
            data['language'] = language

        response = requests.post(
            'https://api.openai.com/v1/audio/transcriptions',
            headers={'Authorization': f'Bearer {OPENAI_API_KEY}'},
            files=files,
            data=data,
            timeout=60
        )

        if response.ok:
            result = response.json()
            text = result.get('text', '').strip()
            logger.info(f"🎤 OpenAI Whisper transcription: {len(text)} chars")
            return text, None

        return None, f"OpenAI error: {response.status_code} - {response.text}"

    except Exception as e:
        logger.exception(f"OpenAI transcription error: {e}")
        return None, str(e)


def _transcribe_deepgram(audio_data: bytes, content_type: str, language: str = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Transcribe audio using Deepgram API.
    """
    if not DEEPGRAM_API_KEY:
        return None, "Deepgram API key not configured"

    try:
        params = {
            'model': 'nova-2',
            'smart_format': 'true'
        }
        if language:
            params['language'] = language

        response = requests.post(
            'https://api.deepgram.com/v1/listen',
            headers={
                'Authorization': f'Token {DEEPGRAM_API_KEY}',
                'Content-Type': content_type
            },
            params=params,
            data=audio_data,
            timeout=60
        )

        if response.ok:
            result = response.json()
            text = result.get('results', {}).get('channels', [{}])[0].get('alternatives', [{}])[0].get('transcript', '').strip()
            logger.info(f"🎤 Deepgram transcription: {len(text)} chars")
            return text, None

        return None, f"Deepgram error: {response.status_code} - {response.text}"

    except Exception as e:
        logger.exception(f"Deepgram transcription error: {e}")
        return None, str(e)


# ============================================
# HEALTH CHECK
# ============================================

@stt_bp.route('/stt/health', methods=['GET'])
def stt_health():
    """
    Health check for STT service.

    Returns:
        200: STT service is healthy
        503: STT service is unavailable

    Response:
        {
            "status": "healthy",
            "provider": "whisper_local",
            "url": "http://localhost:9000",
            "model": "base"
        }
    """
    if STT_PROVIDER == 'whisper_local':
        health = _check_whisper_health()
    elif STT_PROVIDER == 'openai':
        health = {
            "status": "healthy" if OPENAI_API_KEY else "unavailable",
            "provider": "openai",
            "error": None if OPENAI_API_KEY else "OPENAI_API_KEY not set"
        }
    elif STT_PROVIDER == 'deepgram':
        health = {
            "status": "healthy" if DEEPGRAM_API_KEY else "unavailable",
            "provider": "deepgram",
            "error": None if DEEPGRAM_API_KEY else "DEEPGRAM_API_KEY not set"
        }
    else:
        health = {
            "status": "error",
            "error": f"Unknown STT provider: {STT_PROVIDER}"
        }

    if health["status"] == "healthy":
        return jsonify(health), 200
    else:
        return jsonify(health), 503


# ============================================
# SPEECH TO TEXT
# ============================================

@stt_bp.route('/stt', methods=['POST'])
def speech_to_text():
    """
    Transcribe audio to text.

    Request:
        Content-Type: audio/wav (or other supported format)
        Body: Raw audio data

        OR

        Content-Type: application/json
        Body: {
            "audio": "base64-encoded-audio",
            "format": "wav",
            "language": "en"  // Optional
        }

    Response:
        {
            "text": "Transcribed text...",
            "provider": "whisper_local",
            "duration_ms": 1234
        }
    """
    import time
    start_time = time.time()

    try:
        content_type = request.content_type or ''
        audio_data = None
        audio_format = 'audio/wav'
        language = None

        # Handle JSON request with base64 audio
        if 'application/json' in content_type:
            data = request.get_json() or {}

            audio_b64 = data.get('audio')
            if not audio_b64:
                return jsonify({
                    "error": "No audio data provided",
                    "status": "error"
                }), 400

            try:
                audio_data = base64.b64decode(audio_b64)
            except Exception as e:
                return jsonify({
                    "error": f"Invalid base64 audio: {e}",
                    "status": "error"
                }), 400

            # Get format from request
            fmt = data.get('format', 'wav')
            audio_format = f'audio/{fmt}'
            language = data.get('language')

        # Handle direct audio upload
        elif any(fmt in content_type for fmt in SUPPORTED_FORMATS):
            audio_data = request.get_data()
            audio_format = content_type.split(';')[0]  # Remove charset if present
            language = request.args.get('language')

        # Handle multipart form data
        elif 'multipart/form-data' in content_type:
            if 'audio' not in request.files:
                return jsonify({
                    "error": "No audio file in request",
                    "status": "error"
                }), 400

            audio_file = request.files['audio']
            audio_data = audio_file.read()
            audio_format = audio_file.content_type or 'audio/wav'
            language = request.form.get('language')

        else:
            return jsonify({
                "error": f"Unsupported content type: {content_type}",
                "status": "error",
                "supported": SUPPORTED_FORMATS + ['application/json', 'multipart/form-data']
            }), 415

        if not audio_data or len(audio_data) < 100:
            return jsonify({
                "error": "Audio data too small or empty",
                "status": "error"
            }), 400

        logger.info(f"🎤 STT request: {len(audio_data)} bytes, format={audio_format}, provider={STT_PROVIDER}")

        # Transcribe based on provider
        text = None
        error = None
        provider_used = STT_PROVIDER

        if STT_PROVIDER == 'whisper_local':
            text, error = _transcribe_whisper_local(audio_data, audio_format, language)

            # Fallback to OpenAI if local fails and key is available
            if error and OPENAI_API_KEY:
                logger.warning(f"Local Whisper failed, falling back to OpenAI: {error}")
                text, error = _transcribe_openai(audio_data, audio_format, language)
                provider_used = 'openai_fallback'

        elif STT_PROVIDER == 'openai':
            text, error = _transcribe_openai(audio_data, audio_format, language)

        elif STT_PROVIDER == 'deepgram':
            text, error = _transcribe_deepgram(audio_data, audio_format, language)

        else:
            return jsonify({
                "error": f"Unknown STT provider: {STT_PROVIDER}",
                "status": "error"
            }), 500

        duration_ms = int((time.time() - start_time) * 1000)

        if error:
            logger.error(f"STT error: {error}")
            return jsonify({
                "error": error,
                "status": "error",
                "provider": provider_used,
                "duration_ms": duration_ms
            }), 503

        logger.info(f"✅ STT success: '{text[:50]}...' ({duration_ms}ms)")

        return jsonify({
            "text": text,
            "status": "success",
            "provider": provider_used,
            "duration_ms": duration_ms,
            "audio_bytes": len(audio_data)
        })

    except Exception as e:
        logger.exception(f"STT error: {e}")
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500


# ============================================
# COMBINED VOICE CHAT ENDPOINT
# ============================================

@stt_bp.route('/voice/chat', methods=['POST'])
def voice_chat():
    """
    Complete voice chat in one request:
    1. Transcribe audio (STT)
    2. Send to AI (via consciousness loop)
    3. Convert response to speech (TTS)
    4. Return audio response

    Request:
        Content-Type: multipart/form-data
        - audio: Audio file
        - session_id: Optional session ID

        OR

        Content-Type: application/json
        {
            "audio": "base64-encoded-audio",
            "session_id": "optional-session-id"
        }

    Response:
        Content-Type: audio/wav
        Body: AI's spoken response

        OR (if Accept: application/json)
        {
            "transcription": "What you said",
            "response_text": "AI's response",
            "audio": "base64-encoded-response-audio"
        }

    Note: This endpoint requires the consciousness loop to be available.
    For simpler setups, use /stt and /tts separately.
    """
    # This is a placeholder for the full voice chat flow
    # It would need access to the consciousness loop
    return jsonify({
        "error": "Voice chat endpoint not yet implemented. Use /stt and /tts separately.",
        "status": "not_implemented",
        "hint": "POST audio to /stt, send text to /chat, then POST response to /tts"
    }), 501
