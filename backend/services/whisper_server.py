#!/usr/bin/env python3
"""
Lightweight Whisper STT Server
==============================

A simple FastAPI server that wraps faster-whisper for speech-to-text.
OpenAI-compatible API at /v1/audio/transcriptions.

Usage:
    python whisper_server.py --port 9000 --model base

Requirements:
    pip install faster-whisper fastapi uvicorn python-multipart

Models: tiny, base, small, medium, large-v2, large-v3
- tiny: ~1GB VRAM, fastest, least accurate
- base: ~1GB VRAM, good balance for real-time
- small: ~2GB VRAM, better accuracy
- medium: ~5GB VRAM, high accuracy
- large-v3: ~10GB VRAM, best accuracy
"""

import os
import sys
import argparse
import tempfile
import logging
from typing import Optional

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Check for required packages
try:
    from faster_whisper import WhisperModel
except ImportError:
    print("❌ faster-whisper not installed. Run: pip install faster-whisper")
    sys.exit(1)

try:
    from fastapi import FastAPI, File, UploadFile, Form, HTTPException
    from fastapi.responses import JSONResponse
    import uvicorn
except ImportError:
    print("❌ FastAPI/uvicorn not installed. Run: pip install fastapi uvicorn python-multipart")
    sys.exit(1)


# ============================================
# WHISPER MODEL
# ============================================

_model: Optional[WhisperModel] = None
_model_name: str = "base"


def load_model(model_name: str = "base", device: str = "auto", compute_type: str = "auto"):
    """Load the Whisper model."""
    global _model, _model_name

    logger.info(f"🔄 Loading Whisper model: {model_name}")
    logger.info(f"   Device: {device}, Compute type: {compute_type}")

    # Auto-detect device
    if device == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"

    # Auto-detect compute type
    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"

    _model = WhisperModel(model_name, device=device, compute_type=compute_type)
    _model_name = model_name

    logger.info(f"✅ Whisper model loaded: {model_name} on {device} ({compute_type})")


def transcribe_audio(audio_path: str, language: Optional[str] = None) -> dict:
    """Transcribe audio file using Whisper."""
    if _model is None:
        raise RuntimeError("Whisper model not loaded")

    # Transcribe
    segments, info = _model.transcribe(
        audio_path,
        language=language,
        beam_size=5,
        vad_filter=True,  # Filter out silence
        vad_parameters=dict(min_silence_duration_ms=500)
    )

    # Combine segments
    text_parts = []
    for segment in segments:
        text_parts.append(segment.text.strip())

    full_text = " ".join(text_parts)

    return {
        "text": full_text,
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration
    }


# ============================================
# FASTAPI APP
# ============================================

app = FastAPI(
    title="Whisper STT Server",
    description="OpenAI-compatible Speech-to-Text API using faster-whisper",
    version="1.0.0"
)


@app.get("/health")
@app.get("/")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "model": _model_name,
        "model_loaded": _model is not None
    }


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    model: str = Form(default="whisper-1"),  # Ignored, use loaded model
    language: Optional[str] = Form(default=None),
    response_format: str = Form(default="json"),
    prompt: Optional[str] = Form(default=None)  # Ignored for now
):
    """
    OpenAI-compatible transcription endpoint.

    Accepts audio file and returns transcription.
    """
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    # Save uploaded file to temp location
    suffix = os.path.splitext(file.filename)[1] if file.filename else ".wav"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        logger.info(f"🎤 Transcribing: {file.filename} ({len(content)} bytes)")

        result = transcribe_audio(tmp_path, language=language)

        logger.info(f"✅ Transcription: '{result['text'][:100]}...' ({result['duration']:.1f}s)")

        # Return in requested format
        if response_format == "text":
            return result["text"]
        elif response_format == "verbose_json":
            return JSONResponse(content={
                "task": "transcribe",
                "language": result["language"],
                "duration": result["duration"],
                "text": result["text"]
            })
        else:  # json (default)
            return JSONResponse(content={"text": result["text"]})

    except Exception as e:
        logger.error(f"❌ Transcription error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except:
            pass


@app.post("/transcribe")
async def transcribe_alt(
    file: UploadFile = File(...),
    language: Optional[str] = Form(default=None)
):
    """Alternative transcription endpoint (simpler API)."""
    return await transcribe(file=file, language=language)


# ============================================
# MAIN
# ============================================

def main():
    parser = argparse.ArgumentParser(description="Whisper STT Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=9000, help="Port to listen on")
    parser.add_argument("--model", default="base",
                       choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"],
                       help="Whisper model to use")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"],
                       help="Device to run on")
    parser.add_argument("--compute-type", default="auto",
                       choices=["auto", "int8", "float16", "float32"],
                       help="Compute type for inference")

    args = parser.parse_args()

    # Load model
    load_model(args.model, args.device, args.compute_type)

    # Start server
    print(f"\n🚀 Whisper STT Server starting on http://{args.host}:{args.port}")
    print(f"   Model: {args.model}")
    print(f"   Endpoints:")
    print(f"   - GET  /health")
    print(f"   - POST /v1/audio/transcriptions (OpenAI-compatible)")
    print(f"   - POST /transcribe (simple API)")
    print()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
