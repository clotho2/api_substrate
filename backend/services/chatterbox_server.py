#!/usr/bin/env python3
"""
Lightweight Chatterbox TTS Server
A FastAPI wrapper around chatterbox-tts for serving TTS via HTTP API.
Compatible with Python 3.10+

Usage:
    python chatterbox_server.py --port 8001 --model turbo

Environment variables:
    CHATTERBOX_PORT: Server port (default: 8001)
    CHATTERBOX_DEVICE: Device to use - 'cuda' or 'cpu' (default: auto-detect)
    CHATTERBOX_MODEL: Model variant - 'default' or 'turbo' (default: turbo)
"""

import argparse
import io
import logging
import os
import sys
import time
from typing import Optional

import torch
import torchaudio
from fastapi import FastAPI, HTTPException, Form, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Chatterbox TTS Server",
    description="Local TTS server using Chatterbox",
    version="1.0.0"
)

# Global model instance
model = None
device = None
model_variant = None


class TTSRequest(BaseModel):
    """Request body for TTS synthesis"""
    text: str
    voice: Optional[str] = "default"
    exaggeration: Optional[float] = 0.5
    cfg_weight: Optional[float] = 0.5
    response_format: Optional[str] = "wav"


def get_device():
    """Detect the best available device"""
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def load_model(variant: str = None):
    """Load the Chatterbox TTS model

    Args:
        variant: Model variant - 'default' or 'turbo'. Defaults to env var or 'turbo'.
    """
    global model, device, model_variant

    try:
        device = os.getenv("CHATTERBOX_DEVICE", get_device())
        model_variant = variant or os.getenv("CHATTERBOX_MODEL", "turbo")

        logger.info(f"Loading Chatterbox TTS model (variant: {model_variant}) on device: {device}")
        start_time = time.time()

        if model_variant == "turbo":
            # Use the faster turbo model
            from chatterbox.tts import ChatterboxTTSTurbo
            model = ChatterboxTTSTurbo.from_pretrained(device=device)
        else:
            # Use the default model
            from chatterbox.tts import ChatterboxTTS
            model = ChatterboxTTS.from_pretrained(device=device)

        load_time = time.time() - start_time
        logger.info(f"Model loaded successfully in {load_time:.2f}s")
        return True

    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        return False


@app.on_event("startup")
async def startup_event():
    """Load model on startup"""
    if not load_model():
        logger.error("Failed to load Chatterbox model on startup")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy" if model is not None else "unhealthy",
        "model_loaded": model is not None,
        "model_variant": model_variant,
        "device": device
    }


@app.get("/v1/voices")
async def list_voices():
    """List available voices (Chatterbox uses default voice)"""
    return {
        "voices": [
            {
                "voice_id": "default",
                "name": "Default",
                "description": "Chatterbox default voice"
            }
        ]
    }


@app.post("/v1/audio/speech")
async def synthesize_speech(
    text: str = Form(...),
    voice: str = Form("default"),
    exaggeration: float = Form(0.5),
    cfg_weight: float = Form(0.5),
    response_format: str = Form("wav")
):
    """
    Synthesize speech from text (OpenAI-compatible endpoint)

    Args:
        text: The text to synthesize
        voice: Voice ID (currently only 'default' supported)
        exaggeration: Exaggeration parameter (0.0-1.0)
        cfg_weight: CFG weight parameter (0.0-1.0)
        response_format: Output format - 'wav', 'mp3', or 'ogg'
    """
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    try:
        logger.info(f"Generating speech for text: {text[:50]}...")
        start_time = time.time()

        # Generate audio
        wav = model.generate(
            text=text.strip(),
            exaggeration=exaggeration,
            cfg_weight=cfg_weight
        )

        gen_time = time.time() - start_time
        logger.info(f"Generated audio in {gen_time:.2f}s")

        # Convert to requested format
        audio_buffer = io.BytesIO()

        if response_format == "wav":
            torchaudio.save(audio_buffer, wav, model.sr, format="wav")
            content_type = "audio/wav"
        elif response_format == "mp3":
            # Save as wav first, then we'd need ffmpeg for mp3
            # For now, just return wav
            torchaudio.save(audio_buffer, wav, model.sr, format="wav")
            content_type = "audio/wav"
        elif response_format == "ogg":
            torchaudio.save(audio_buffer, wav, model.sr, format="ogg")
            content_type = "audio/ogg"
        else:
            torchaudio.save(audio_buffer, wav, model.sr, format="wav")
            content_type = "audio/wav"

        audio_buffer.seek(0)

        return Response(
            content=audio_buffer.read(),
            media_type=content_type,
            headers={
                "X-Generation-Time": str(gen_time),
                "Content-Disposition": f'attachment; filename="speech.{response_format}"'
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
        exaggeration=request.exaggeration,
        cfg_weight=request.cfg_weight,
        response_format=request.response_format
    )


@app.get("/tts")
async def tts_get(
    text: str = Query(..., description="Text to synthesize"),
    voice: str = Query("default", description="Voice ID"),
    exaggeration: float = Query(0.5, description="Exaggeration (0-1)"),
    cfg_weight: float = Query(0.5, description="CFG weight (0-1)"),
    response_format: str = Query("wav", description="Output format")
):
    """GET endpoint for TTS (useful for testing)"""
    return await synthesize_speech(
        text=text,
        voice=voice,
        exaggeration=exaggeration,
        cfg_weight=cfg_weight,
        response_format=response_format
    )


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Chatterbox TTS Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=int(os.getenv("CHATTERBOX_PORT", "8001")),
                        help="Port to listen on")
    parser.add_argument("--device", default=None, help="Device to use (cuda/cpu)")
    parser.add_argument("--model", default=os.getenv("CHATTERBOX_MODEL", "turbo"),
                        choices=["default", "turbo"], help="Model variant to use")

    args = parser.parse_args()

    if args.device:
        os.environ["CHATTERBOX_DEVICE"] = args.device
    os.environ["CHATTERBOX_MODEL"] = args.model

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
