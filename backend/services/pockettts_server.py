#!/usr/bin/env python3
"""
Lightweight Pocket TTS Server
A FastAPI wrapper around pocket-tts for serving TTS via HTTP API.
Compatible with Python 3.10+

Usage:
    python pockettts_server.py --port 8001 --voice Assistant

Environment variables:
    POCKETTTS_PORT: Server port (default: 8001)
    POCKETTTS_VOICES_DIR: Directory containing voice reference WAV/safetensors files (default: ./voices)
    POCKETTTS_DEFAULT_VOICE: Default voice file to use for cloning (e.g., 'Assistant.wav' or 'Assistant.safetensors')
    POCKETTTS_TEMP: Sampling temperature (default: 0.7)

Install:
    pip install pocket-tts fastapi uvicorn
"""

import argparse
import io
import logging
import os
import sys
import time
from typing import Optional

import scipy.io.wavfile
from fastapi import FastAPI, HTTPException, Form, Query
from fastapi.responses import Response
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Pocket TTS Server",
    description="Local TTS server using Pocket TTS (Kyutai)",
    version="1.0.0"
)

# Global model instance
tts_model = None
voice_states = {}  # Cache of loaded voice states
voices_dir = None
default_voice_name = None


class TTSRequest(BaseModel):
    """Request body for TTS synthesis"""
    text: str
    voice: Optional[str] = None  # Voice ID for cloning, uses default if not specified
    response_format: Optional[str] = "wav"


def get_voice_path(voice_name: str) -> Optional[str]:
    """Get the full path to a voice file.

    Args:
        voice_name: Voice name (e.g., 'Assistant', 'Assistant.wav', or 'Assistant.safetensors')

    Returns:
        Full path to voice file, or None if not found
    """
    if not voices_dir:
        return None

    # Check for safetensors first (faster loading)
    if not voice_name.endswith(('.wav', '.safetensors')):
        safetensors_path = os.path.join(voices_dir, f"{voice_name}.safetensors")
        if os.path.exists(safetensors_path):
            return safetensors_path
        wav_path = os.path.join(voices_dir, f"{voice_name}.wav")
        if os.path.exists(wav_path):
            return wav_path
        return None

    voice_path = os.path.join(voices_dir, voice_name)
    if os.path.exists(voice_path):
        return voice_path
    return None


def list_available_voices() -> list:
    """List all available voice files in the voices directory."""
    if not voices_dir or not os.path.exists(voices_dir):
        return []

    voices = []
    seen = set()
    for f in os.listdir(voices_dir):
        if f.endswith('.safetensors'):
            voice_id = f[:-len('.safetensors')]
            if voice_id not in seen:
                seen.add(voice_id)
                voices.append({
                    "voice_id": voice_id,
                    "name": voice_id.title(),
                    "file": f,
                    "format": "safetensors"
                })
        elif f.endswith('.wav'):
            voice_id = f[:-4]
            if voice_id not in seen:
                seen.add(voice_id)
                voices.append({
                    "voice_id": voice_id,
                    "name": voice_id.title(),
                    "file": f,
                    "format": "wav"
                })
    return voices


def get_or_load_voice_state(voice_name: str):
    """Get a cached voice state or load it from file.

    Args:
        voice_name: Voice name or 'default' for the default voice

    Returns:
        Voice state object for Pocket TTS generation
    """
    global voice_states

    if voice_name in voice_states:
        return voice_states[voice_name]

    voice_path = get_voice_path(voice_name)
    if voice_path:
        logger.info(f"Loading voice state: {voice_name} ({voice_path})")
        start = time.time()
        state = tts_model.get_state_for_audio_prompt(voice_path)
        logger.info(f"Voice state loaded in {time.time() - start:.2f}s")
        voice_states[voice_name] = state
        return state

    return None


def load_model(temp: float = None):
    """Load the Pocket TTS model

    Args:
        temp: Sampling temperature (default: from env or 0.7)
    """
    global tts_model, voices_dir, default_voice_name

    try:
        from pocket_tts import TTSModel

        # Initialize voices directory
        voices_dir = os.getenv("POCKETTTS_VOICES_DIR", "./voices")
        if not os.path.isabs(voices_dir):
            script_dir = os.path.dirname(os.path.abspath(__file__))
            voices_dir = os.path.join(script_dir, voices_dir)

        # Create voices directory if it doesn't exist
        os.makedirs(voices_dir, exist_ok=True)
        logger.info(f"Voices directory: {voices_dir}")

        # Set default voice
        default_voice_name = os.getenv("POCKETTTS_DEFAULT_VOICE", None)

        temperature = temp or float(os.getenv("POCKETTTS_TEMP", "0.7"))

        logger.info(f"Loading Pocket TTS model (temp: {temperature})")
        start_time = time.time()

        tts_model = TTSModel.load_model(temp=temperature)

        load_time = time.time() - start_time
        logger.info(f"Model loaded successfully in {load_time:.2f}s")

        # Pre-load default voice state if configured
        if default_voice_name:
            state = get_or_load_voice_state(default_voice_name)
            if state:
                logger.info(f"Default voice pre-loaded: {default_voice_name}")
            else:
                logger.warning(f"Default voice '{default_voice_name}' not found in {voices_dir}")

        # List available voices
        available = list_available_voices()
        if available:
            logger.info(f"Available voices: {[v['voice_id'] for v in available]}")
        else:
            logger.info("No custom voice files found. Using Pocket TTS built-in voices.")

        return True

    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        return False


@app.on_event("startup")
async def startup_event():
    """Load model on startup"""
    if not load_model():
        logger.error("Failed to load Pocket TTS model on startup")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy" if tts_model is not None else "unhealthy",
        "model_loaded": tts_model is not None,
        "engine": "pocket-tts",
        "voices_dir": voices_dir,
        "default_voice": default_voice_name,
        "available_voices": [v["voice_id"] for v in list_available_voices()]
    }


@app.get("/v1/voices")
async def list_voices_endpoint():
    """List available voices for cloning"""
    voices = list_available_voices()

    # Include Pocket TTS built-in voices
    builtins = ["alba", "marius", "javert", "jean", "fantine", "cosette", "eponine", "azelma"]
    result = [{"voice_id": name, "name": name.title(), "description": f"Pocket TTS built-in voice"} for name in builtins]

    # Add custom voice files
    for v in voices:
        result.append({
            "voice_id": v["voice_id"],
            "name": v["name"],
            "description": f"Custom voice from {v['file']}"
        })

    return {"voices": result}


@app.post("/v1/audio/speech")
async def synthesize_speech(
    text: str = Form(...),
    voice: str = Form(None),
    response_format: str = Form("wav")
):
    """
    Synthesize speech from text (OpenAI-compatible endpoint)

    Args:
        text: The text to synthesize
        voice: Voice ID for cloning (e.g., 'Assistant'). Uses POCKETTTS_DEFAULT_VOICE if not specified.
        response_format: Output format - 'wav' (only wav supported currently)
    """
    if tts_model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    try:
        # Determine which voice to use
        voice_to_use = voice or default_voice_name
        voice_state = None

        if voice_to_use and voice_to_use != "default":
            voice_state = get_or_load_voice_state(voice_to_use)
            if voice_state:
                logger.info(f"Using voice: {voice_to_use}")
            else:
                # Try as a built-in Pocket TTS voice name
                try:
                    voice_state = tts_model.get_state_for_audio_prompt(voice_to_use)
                    voice_states[voice_to_use] = voice_state
                    logger.info(f"Using built-in voice: {voice_to_use}")
                except Exception:
                    logger.warning(f"Voice '{voice_to_use}' not found, using default")

        # Fall back to a built-in voice if no voice state loaded
        if voice_state is None:
            voice_state = get_or_load_voice_state("alba")
            if voice_state is None:
                voice_state = tts_model.get_state_for_audio_prompt("alba")
                voice_states["alba"] = voice_state

        logger.info(f"Generating speech for text: {text[:50]}...")
        start_time = time.time()

        audio = tts_model.generate_audio(voice_state, text.strip())

        gen_time = time.time() - start_time
        logger.info(f"Generated audio in {gen_time:.2f}s")

        # Convert to 16-bit PCM WAV (format 1) so Python's wave module can read it.
        # pocket-tts returns float32 tensors; scipy would write those as format 3
        # (IEEE float) which the wave module can't parse and requires slow conversion.
        audio_np = audio.numpy()
        if audio_np.dtype.kind == 'f':
            audio_np = (audio_np * 32767).clip(-32768, 32767).astype('int16')
        audio_buffer = io.BytesIO()
        scipy.io.wavfile.write(audio_buffer, tts_model.sample_rate, audio_np)
        audio_buffer.seek(0)

        return Response(
            content=audio_buffer.read(),
            media_type="audio/wav",
            headers={
                "X-Generation-Time": str(gen_time),
                "Content-Disposition": f'attachment; filename="speech.wav"'
            }
        )

    except Exception as e:
        logger.error(f"TTS generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tts")
async def tts_simple(request: TTSRequest):
    """Simple TTS endpoint"""
    return await synthesize_speech(
        text=request.text,
        voice=request.voice,
        response_format=request.response_format
    )


@app.get("/tts")
async def tts_get(
    text: str = Query(..., description="Text to synthesize"),
    voice: str = Query("default", description="Voice ID"),
    response_format: str = Query("wav", description="Output format")
):
    """GET endpoint for TTS (useful for testing)"""
    return await synthesize_speech(
        text=text,
        voice=voice,
        response_format=response_format
    )


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Pocket TTS Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=int(os.getenv("POCKETTTS_PORT", "8001")),
                        help="Port to listen on")
    parser.add_argument("--voice", default=None, help="Default voice to use (e.g., 'Assistant')")
    parser.add_argument("--temp", type=float, default=None, help="Sampling temperature")

    args = parser.parse_args()

    if args.voice:
        os.environ["POCKETTTS_DEFAULT_VOICE"] = args.voice
    if args.temp is not None:
        os.environ["POCKETTTS_TEMP"] = str(args.temp)

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
