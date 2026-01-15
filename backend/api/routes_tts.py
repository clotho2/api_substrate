"""
TTS Routes for Mobile Voice Chat
================================

Provides Text-to-Speech endpoints for the AiCara mobile app using Chatterbox TTS.
This acts as a proxy/preprocessor between the mobile app and Chatterbox.

Endpoints:
- GET  /tts/health     - Health check for TTS service
- POST /tts            - Convert text to speech
- POST /tts/stream     - Stream audio chunks (for real-time playback)

Why proxy through substrate instead of direct to Chatterbox?
- Text preprocessing (clean markdown, emojis, normalize)
- Request logging and monitoring
- Rate limiting
- Future: voice cloning, SSML support, caching
"""

import os
import re
import logging
import requests
from flask import Blueprint, Response, request, jsonify, stream_with_context
from typing import Optional
import base64

logger = logging.getLogger(__name__)

tts_bp = Blueprint('tts', __name__)

# Chatterbox TTS configuration
CHATTERBOX_URL = os.getenv('CHATTERBOX_URL', 'http://localhost:8000')
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

    Response:
        {
            "status": "healthy" | "unhealthy" | "unavailable",
            "chatterbox_url": "http://...",
            "response_time_ms": 50.5
        }
    """
    health = _check_chatterbox_health()

    if health["status"] == "healthy":
        return jsonify(health), 200
    else:
        return jsonify(health), 503


# ============================================
# TEXT TO SPEECH
# ============================================

@tts_bp.route('/tts', methods=['POST'])
def text_to_speech():
    """
    Convert text to speech using Chatterbox TTS.

    Request Body:
        {
            "text": "Text to convert to speech",
            "voice": "default",           // Optional: voice ID
            "speed": 1.0,                 // Optional: speech speed
            "preprocess": true,           // Optional: clean markdown (default: true)
            "format": "wav"               // Optional: audio format (wav, mp3)
        }

    Response Formats (based on Accept header or Chatterbox config):
        1. Direct audio: Content-Type: audio/wav, body is raw audio
        2. JSON with base64: {"audio": "base64-encoded-audio"}
        3. JSON with URL: {"audio_url": "https://..."}
    """
    try:
        # Parse request
        data = request.get_json() or {}
        text = data.get('text', '')
        voice = data.get('voice', 'default')
        speed = data.get('speed', 1.0)
        preprocess = data.get('preprocess', True)
        audio_format = data.get('format', 'wav')

        # Validate text
        if not text:
            return jsonify({
                "error": "Text is required",
                "status": "error"
            }), 400

        # Preprocess text if enabled
        if preprocess:
            original_length = len(text)
            text = _preprocess_text(text)
            logger.debug(f"TTS preprocessing: {original_length} -> {len(text)} chars")

        # Check text length
        if len(text) > MAX_TEXT_LENGTH:
            return jsonify({
                "error": f"Text too long ({len(text)} chars). Maximum is {MAX_TEXT_LENGTH}.",
                "status": "error"
            }), 400

        # Log request
        logger.info(f"🎤 TTS request: {len(text)} chars, voice={voice}")

        # Build Chatterbox request
        chatterbox_payload = {
            "text": text,
            "voice": voice,
            "speed": speed,
            "format": audio_format
        }

        # Call Chatterbox
        response = requests.post(
            f"{CHATTERBOX_URL}/tts",
            json=chatterbox_payload,
            timeout=CHATTERBOX_TIMEOUT,
            stream=True  # Allow streaming for large audio
        )

        if not response.ok:
            logger.error(f"Chatterbox error: {response.status_code} - {response.text}")
            return jsonify({
                "error": f"TTS service error: {response.status_code}",
                "status": "error"
            }), response.status_code

        # Check response type
        content_type = response.headers.get('Content-Type', '')

        # If Chatterbox returns direct audio, pass it through
        if 'audio' in content_type:
            logger.info(f"🔊 TTS response: direct audio ({content_type})")
            return Response(
                response.content,
                mimetype=content_type,
                headers={
                    'Content-Length': response.headers.get('Content-Length', ''),
                    'X-TTS-Engine': 'chatterbox'
                }
            )

        # If Chatterbox returns JSON, parse and forward
        elif 'application/json' in content_type:
            result = response.json()
            logger.info(f"🔊 TTS response: JSON format")

            # Add metadata
            result['tts_engine'] = 'chatterbox'
            result['text_length'] = len(text)

            return jsonify(result)

        # Unknown format - return as-is
        else:
            logger.warning(f"Unknown Chatterbox response type: {content_type}")
            return Response(
                response.content,
                mimetype=content_type
            )

    except requests.exceptions.Timeout:
        logger.error("Chatterbox TTS timeout")
        return jsonify({
            "error": "TTS request timed out",
            "status": "error"
        }), 504

    except requests.exceptions.ConnectionError:
        logger.error(f"Cannot connect to Chatterbox at {CHATTERBOX_URL}")
        return jsonify({
            "error": "TTS service unavailable",
            "status": "error",
            "fallback_hint": "Use device TTS"
        }), 503

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
# VOICE INFO (optional - for future voice selection)
# ============================================

@tts_bp.route('/tts/voices', methods=['GET'])
def list_voices():
    """
    List available TTS voices.

    Returns:
        {
            "voices": [
                {"id": "default", "name": "Default Voice", "language": "en"},
                ...
            ]
        }
    """
    try:
        # Try to get voices from Chatterbox
        response = requests.get(
            f"{CHATTERBOX_URL}/voices",
            timeout=5
        )

        if response.ok:
            return jsonify(response.json())
        else:
            # Return default if Chatterbox doesn't have this endpoint
            return jsonify({
                "voices": [
                    {"id": "default", "name": "Default", "language": "en"}
                ],
                "source": "fallback"
            })

    except Exception as e:
        logger.warning(f"Could not fetch voices from Chatterbox: {e}")
        return jsonify({
            "voices": [
                {"id": "default", "name": "Default", "language": "en"}
            ],
            "source": "fallback"
        })
