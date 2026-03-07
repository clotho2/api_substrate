#!/usr/bin/env python3
"""
Audio Format Conversion Utilities
===================================

Handles audio format conversions between Twilio Media Streams (8-bit 8kHz mulaw)
and local audio processing (16-bit PCM WAV).

Twilio Media Streams send/receive:
- 8-bit mulaw encoded audio
- 8000 Hz sample rate
- Mono channel
- Base64 encoded in JSON messages

Pocket TTS outputs:
- 32-bit float WAV (format 3) or 16-bit PCM WAV (format 1)
- Variable sample rate (typically 24000 Hz)
- Mono channel

Whisper STT expects:
- WAV or raw PCM
- 16000 Hz preferred
- Mono channel
"""

import audioop
import base64
import io
import logging
import struct
import wave

logger = logging.getLogger(__name__)

# Twilio Media Streams constants
TWILIO_SAMPLE_RATE = 8000
TWILIO_SAMPLE_WIDTH = 1  # 8-bit mulaw
PCM_SAMPLE_WIDTH = 2  # 16-bit PCM
WHISPER_SAMPLE_RATE = 16000


def mulaw_to_pcm(mulaw_data: bytes) -> bytes:
    """Convert 8-bit mulaw audio to 16-bit PCM.

    Args:
        mulaw_data: Raw mulaw encoded audio bytes

    Returns:
        16-bit PCM audio bytes at the same sample rate (8kHz)
    """
    return audioop.ulaw2lin(mulaw_data, PCM_SAMPLE_WIDTH)


def pcm_to_mulaw(pcm_data: bytes) -> bytes:
    """Convert 16-bit PCM audio to 8-bit mulaw.

    Args:
        pcm_data: Raw 16-bit PCM audio bytes

    Returns:
        8-bit mulaw encoded audio bytes
    """
    return audioop.lin2ulaw(pcm_data, PCM_SAMPLE_WIDTH)


def mulaw_to_wav(mulaw_data: bytes, sample_rate: int = TWILIO_SAMPLE_RATE) -> bytes:
    """Convert mulaw audio to WAV format.

    Args:
        mulaw_data: Raw mulaw encoded audio bytes
        sample_rate: Sample rate of the mulaw audio (default: 8000)

    Returns:
        WAV file bytes (16-bit PCM)
    """
    pcm_data = mulaw_to_pcm(mulaw_data)

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(PCM_SAMPLE_WIDTH)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)

    return wav_buffer.getvalue()


def _read_wav_bytes(wav_bytes: bytes):
    """Read WAV bytes, handling both integer PCM (format 1) and float32 (format 3).

    Python's wave module only supports format 1. Pocket-TTS outputs format 3
    (IEEE 754 float32). This helper detects float WAVs and converts them to
    16-bit PCM so the rest of the pipeline can process them normally.

    Returns:
        (frames, sample_rate, sample_width, n_channels) where frames are
        always integer PCM and sample_width reflects the PCM width.
    """
    try:
        with io.BytesIO(wav_bytes) as wav_io:
            with wave.open(wav_io, 'rb') as wav_file:
                frames = wav_file.readframes(wav_file.getnframes())
                return frames, wav_file.getframerate(), wav_file.getsampwidth(), wav_file.getnchannels()
    except wave.Error as e:
        if 'unknown format: 3' not in str(e):
            raise
    # Format 3 — IEEE float32 WAV. Parse the RIFF header manually.
    data = wav_bytes
    if data[:4] != b'RIFF' or data[8:12] != b'WAVE':
        raise wave.Error('Not a WAV file')
    pos = 12
    fmt_parsed = False
    n_channels = sample_rate = bits_per_sample = 0
    frames = b''
    while pos < len(data):
        chunk_id = data[pos:pos+4]
        chunk_size = struct.unpack_from('<I', data, pos+4)[0]
        pos += 8
        if chunk_id == b'fmt ':
            n_channels = struct.unpack_from('<H', data, pos+2)[0]
            sample_rate = struct.unpack_from('<I', data, pos+4)[0]
            bits_per_sample = struct.unpack_from('<H', data, pos+14)[0]
            fmt_parsed = True
        elif chunk_id == b'data':
            frames = data[pos:pos+chunk_size]
        pos += chunk_size
    if not fmt_parsed:
        raise wave.Error('No fmt chunk found in float WAV')
    # Convert float32 samples → 16-bit PCM
    n_samples = len(frames) // (bits_per_sample // 8)
    if bits_per_sample == 32:
        floats = struct.unpack(f'<{n_samples}f', frames)
        frames = struct.pack(f'<{n_samples}h',
                             *(max(-32768, min(32767, int(s * 32767))) for s in floats))
    elif bits_per_sample == 64:
        floats = struct.unpack(f'<{n_samples}d', frames)
        frames = struct.pack(f'<{n_samples}h',
                             *(max(-32768, min(32767, int(s * 32767))) for s in floats))
    logger.info("Converted float%d WAV → 16-bit PCM (%d samples, %d Hz)",
                bits_per_sample, n_samples, sample_rate)
    return frames, sample_rate, PCM_SAMPLE_WIDTH, n_channels


def wav_to_mulaw(wav_bytes: bytes) -> bytes:
    """Convert WAV audio to 8kHz mulaw for Twilio Media Streams.

    Handles resampling from any sample rate to 8kHz and converting
    stereo to mono if needed. Supports both integer PCM and float32 WAV.

    Args:
        wav_bytes: WAV file bytes

    Returns:
        8-bit mulaw encoded audio at 8kHz mono
    """
    frames, sample_rate, sample_width, n_channels = _read_wav_bytes(wav_bytes)

    # Convert to mono if stereo
    if n_channels == 2:
        frames = audioop.tomono(frames, sample_width, 1, 1)

    # Normalize to 16-bit PCM
    if sample_width != PCM_SAMPLE_WIDTH:
        frames = audioop.lin2lin(frames, sample_width, PCM_SAMPLE_WIDTH)

    # Resample to 8kHz for Twilio
    if sample_rate != TWILIO_SAMPLE_RATE:
        frames, _ = audioop.ratecv(
            frames, PCM_SAMPLE_WIDTH, 1,
            sample_rate, TWILIO_SAMPLE_RATE, None
        )

    # Convert to mulaw
    return audioop.lin2ulaw(frames, PCM_SAMPLE_WIDTH)


def wav_to_pcm_16khz(wav_bytes: bytes) -> bytes:
    """Convert WAV audio to 16kHz 16-bit PCM for Whisper STT.

    Supports both integer PCM and float32 WAV.

    Args:
        wav_bytes: WAV file bytes

    Returns:
        Raw 16-bit PCM bytes at 16kHz mono
    """
    frames, sample_rate, sample_width, n_channels = _read_wav_bytes(wav_bytes)

    # Convert to mono
    if n_channels == 2:
        frames = audioop.tomono(frames, sample_width, 1, 1)

    # Normalize to 16-bit
    if sample_width != PCM_SAMPLE_WIDTH:
        frames = audioop.lin2lin(frames, sample_width, PCM_SAMPLE_WIDTH)

    # Resample to 16kHz for Whisper
    if sample_rate != WHISPER_SAMPLE_RATE:
        frames, _ = audioop.ratecv(
            frames, PCM_SAMPLE_WIDTH, 1,
            sample_rate, WHISPER_SAMPLE_RATE, None
        )

    return frames


def mulaw_base64_to_pcm(base64_payload: str) -> bytes:
    """Decode a base64 mulaw payload from Twilio and convert to PCM.

    This is the format Twilio Media Streams sends in WebSocket messages:
    {"event": "media", "media": {"payload": "<base64 mulaw>"}}

    Args:
        base64_payload: Base64-encoded mulaw audio from Twilio

    Returns:
        16-bit PCM audio bytes at 8kHz
    """
    mulaw_data = base64.b64decode(base64_payload)
    return mulaw_to_pcm(mulaw_data)


def pcm_to_mulaw_base64(pcm_data: bytes) -> str:
    """Convert PCM audio to base64 mulaw for sending to Twilio.

    Args:
        pcm_data: 16-bit PCM audio bytes (should be 8kHz)

    Returns:
        Base64-encoded mulaw string for Twilio Media Streams
    """
    mulaw_data = pcm_to_mulaw(pcm_data)
    return base64.b64encode(mulaw_data).decode('ascii')


def wav_to_mulaw_base64(wav_bytes: bytes) -> str:
    """Convert WAV audio to base64 mulaw for Twilio Media Streams.

    Full conversion pipeline: WAV → resample to 8kHz → mulaw → base64.
    Used to convert Pocket TTS output for streaming to Twilio.

    Args:
        wav_bytes: WAV file bytes from TTS

    Returns:
        Base64-encoded mulaw string ready for Twilio
    """
    mulaw_data = wav_to_mulaw(wav_bytes)
    return base64.b64encode(mulaw_data).decode('ascii')


def chunk_mulaw_base64(mulaw_base64: str, chunk_size: int = 640) -> list:
    """Split base64 mulaw audio into chunks for streaming to Twilio.

    Twilio expects audio in small chunks (~20ms each at 8kHz = 160 bytes mulaw).
    We use 640 bytes (~80ms) as a good balance of latency and overhead.

    Args:
        mulaw_base64: Full base64-encoded mulaw audio
        chunk_size: Size of each chunk in mulaw bytes (default: 640 = 80ms)

    Returns:
        List of base64-encoded chunk strings
    """
    mulaw_data = base64.b64decode(mulaw_base64)
    chunks = []

    for i in range(0, len(mulaw_data), chunk_size):
        chunk = mulaw_data[i:i + chunk_size]
        chunks.append(base64.b64encode(chunk).decode('ascii'))

    return chunks
