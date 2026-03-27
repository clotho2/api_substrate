#!/usr/bin/env python3
"""
Hume EVI WebSocket Relay — Twilio ↔ EVI Bridge
=================================================

WebSocket relay that bridges Twilio Media Streams with Hume's Empathic Voice
Interface (EVI). Replaces the STT → Consciousness Loop → TTS pipeline with
EVI's integrated speech-to-speech system for dramatically lower latency.

Pipeline:
  Caller speaks → Twilio streams mulaw audio → This relay →
  → Hume EVI (STT + LLM + TTS) → Audio back → This relay →
  → mulaw audio → Twilio plays to caller

The relay handles:
- Audio format bridging (Twilio mulaw ↔ EVI PCM/WAV)
- Tool call execution (EVI invokes substrate tools via MemoryTools)
- Context injection (system prompt, memory blocks, Graph RAG)
- Conversation history sync (saves messages to state_manager)
- Post-call processing (summary, archival, call logging)

Twilio TwiML setup:
  <Connect>
      <Stream url="wss://your_url_here/phone/evi-stream">
          <Parameter name="callerNumber" value="+1234567890" />
          <Parameter name="callerName" value="User" />
      </Stream>
  </Connect>

Requires:
    pip install flask-sock websocket-client
    HUME_EVI_ENABLED=true in .env
"""

import os
import io
import json
import base64
import struct
import asyncio
import logging
import threading
import time
import wave
import uuid
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Module-level dependencies (injected via init_evi_routes)
_consciousness_loop = None
_state_manager = None
_evi_manager = None  # HumeEVIManager instance

# Mulaw chunk size for streaming to Twilio (same as routes_telephony.py)
STREAM_CHUNK_SIZE = 640


def init_evi_routes(consciousness_loop, state_manager, evi_manager):
    """Inject dependencies for the EVI relay module.

    Args:
        consciousness_loop: ConsciousnessLoop instance (for tool execution)
        state_manager: StateManager instance (for context + history)
        evi_manager: HumeEVIManager instance (for config + WebSocket URL)
    """
    global _consciousness_loop, _state_manager, _evi_manager
    _consciousness_loop = consciousness_loop
    _state_manager = state_manager
    _evi_manager = evi_manager
    logger.info("EVI relay routes initialized")


# ============================================
# AUDIO CONVERSION HELPERS
# ============================================

# Mulaw decoding table (ITU-T G.711)
_MULAW_DECODE_TABLE = None


def _init_mulaw_table():
    """Initialize the mulaw-to-linear decode lookup table."""
    global _MULAW_DECODE_TABLE
    if _MULAW_DECODE_TABLE is not None:
        return

    table = []
    for i in range(256):
        val = ~i
        sign = val & 0x80
        exponent = (val >> 4) & 0x07
        mantissa = val & 0x0F
        sample = ((mantissa << 3) + 0x84) << exponent
        sample -= 0x84
        if sign:
            sample = -sample
        table.append(sample)
    _MULAW_DECODE_TABLE = table


def _mulaw_bytes_to_pcm16(mulaw_data: bytes) -> bytes:
    """Convert raw mulaw bytes to 16-bit signed PCM.

    Args:
        mulaw_data: Raw mulaw encoded audio bytes (8kHz mono).

    Returns:
        Raw 16-bit signed little-endian PCM bytes.
    """
    _init_mulaw_table()
    pcm_samples = [_MULAW_DECODE_TABLE[b] for b in mulaw_data]
    return struct.pack(f"<{len(pcm_samples)}h", *pcm_samples)


def _pcm16_to_mulaw(pcm_data: bytes) -> bytes:
    """Convert 16-bit signed PCM to mulaw encoding.

    Args:
        pcm_data: Raw 16-bit signed little-endian PCM bytes.

    Returns:
        Mulaw encoded bytes.
    """
    n_samples = len(pcm_data) // 2
    samples = struct.unpack(f"<{n_samples}h", pcm_data[:n_samples * 2])

    mulaw_bytes = bytearray(n_samples)
    for i, sample in enumerate(samples):
        # Bias
        sign = 0
        if sample < 0:
            sign = 0x80
            sample = -sample
        sample = min(sample + 0x84, 0x7FFF)

        # Find exponent and mantissa
        exponent = 7
        exp_mask = 0x4000
        for e in range(7, 0, -1):
            if sample & exp_mask:
                exponent = e
                break
            exp_mask >>= 1
        else:
            exponent = 0

        mantissa = (sample >> (exponent + 3)) & 0x0F
        mulaw_bytes[i] = ~(sign | (exponent << 4) | mantissa) & 0xFF

    return bytes(mulaw_bytes)


# ============================================
# EVI AUDIO DECODING (WAV → PCM → resample)
# ============================================

def _decode_evi_audio(audio_b64: str) -> Tuple[bytes, int]:
    """Decode audio from an EVI audio_output message.

    EVI sends each chunk as a base64-encoded WAV file (with headers).
    Parses the WAV header to extract the sample rate and raw PCM data.

    If the data has no WAV header, it's treated as raw PCM at 24 kHz
    (EVI's default web output rate).

    Returns:
        (pcm_data, sample_rate) — raw 16-bit signed LE PCM + Hz.
    """
    raw = base64.b64decode(audio_b64)

    # Check for RIFF/WAV magic bytes
    if len(raw) > 44 and raw[:4] == b"RIFF":
        try:
            with wave.open(io.BytesIO(raw), "rb") as wf:
                sample_rate = wf.getframerate()
                pcm_data = wf.readframes(wf.getnframes())
                return pcm_data, sample_rate
        except Exception:
            # Malformed WAV — strip first 44 bytes and hope for the best
            return raw[44:], 24000

    # No WAV header — raw PCM (assume 24 kHz)
    return raw, 24000


def _resample_pcm16(pcm_data: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Resample 16-bit signed LE PCM from src_rate to dst_rate.

    Uses linear interpolation.  Quality is fine for telephony voice.
    """
    if src_rate == dst_rate:
        return pcm_data

    n_samples = len(pcm_data) // 2
    if n_samples == 0:
        return pcm_data
    samples = struct.unpack(f"<{n_samples}h", pcm_data[: n_samples * 2])

    ratio = src_rate / dst_rate
    out_len = int(n_samples / ratio)
    out_samples = []

    for i in range(out_len):
        src_pos = i * ratio
        idx = int(src_pos)
        frac = src_pos - idx

        if idx + 1 < n_samples:
            sample = int(samples[idx] * (1.0 - frac) + samples[idx + 1] * frac)
        else:
            sample = samples[min(idx, n_samples - 1)]

        out_samples.append(max(-32768, min(32767, sample)))

    return struct.pack(f"<{len(out_samples)}h", *out_samples)


# ============================================
# CONTEXT BUILDING
# ============================================

def _build_evi_context(caller_name: str, caller_number: str) -> Dict[str, Any]:
    """Build a compact context payload for EVI session_settings.

    Only includes information useful for a real-time phone call:
    - persona, human, and relationship memory blocks
    - Caller info
    - Recent conversation turns (6-8 messages for continuity)
    - Previous conversation summary (if any)

    Intentionally omits the full system prompt (already in the EVI config's
    prompt), Graph RAG (agent can search via tools), and non-essential
    memory blocks (too verbose for voice context window).

    Args:
        caller_name: Contact name of the caller.
        caller_number: Phone number of the caller.

    Returns:
        Dict with 'context' string.
    """
    context_parts = []

    if not _state_manager:
        return {"context": ""}

    try:
        # Only load essential memory blocks
        PHONE_BLOCKS = {"persona", "human", "relationship"}
        blocks = _state_manager.list_blocks(include_hidden=False)
        if blocks:
            block_text = []
            for block in blocks:
                label = getattr(block, "label", "unknown")
                if label not in PHONE_BLOCKS:
                    continue
                content = getattr(block, "content", "")
                if content.strip():
                    block_text.append(f"[{label}]\n{content}")
            if block_text:
                context_parts.append("\n\n".join(block_text))

        # Add caller context
        context_parts.append(
            f"Caller: {caller_name} ({caller_number})"
        )

        # Load recent conversation turns for continuity.
        # Pull from the main conversation (not the call session) so the
        # agent knows what was just being discussed across all interfaces.
        try:
            history = _state_manager.get_conversation("default", limit=8)
            if history:
                turns = []
                for msg in history:
                    role = getattr(msg, "role", "user")
                    content = getattr(msg, "content", "")
                    if content:
                        # Truncate individual messages if too long
                        if len(content) > 200:
                            content = content[:200] + "..."
                        turns.append(f"{role}: {content}")
                if turns:
                    context_parts.append(
                        "Recent conversation:\n" + "\n".join(turns)
                    )
        except Exception:
            pass

        # Load previous call summary for this caller
        call_session_id = f"call_{caller_number.replace('+', '')}"
        try:
            latest_summary = _state_manager.get_latest_summary(call_session_id)
            if latest_summary and latest_summary.get("content"):
                summary = latest_summary["content"]
                if len(summary) > 500:
                    summary = summary[:500] + "..."
                context_parts.append(
                    f"Previous call summary: {summary}"
                )
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Error building EVI context: {e}", exc_info=True)

    return {
        "context": "\n\n".join(context_parts) if context_parts else "",
    }


# ============================================
# TOOL EXECUTION
# ============================================

def _execute_evi_tool_call(
    tool_name: str,
    tool_arguments: Dict[str, Any],
    session_id: str,
) -> str:
    """Execute a tool call from EVI using the substrate's MemoryTools.

    Routes the tool call through the same execution path as the consciousness
    loop, but synchronously since we're in a WebSocket handler.

    Args:
        tool_name: Name of the tool to execute.
        tool_arguments: Tool arguments dict.
        session_id: Session ID for conversation-scoped tools.

    Returns:
        JSON string of the tool result (for EVI tool_response message).
    """
    if not _consciousness_loop:
        return json.dumps({"status": "error", "message": "Tool execution unavailable"})

    try:
        # Use a ToolCall-like object for the existing execution path
        from dataclasses import dataclass

        @dataclass
        class _ToolCall:
            id: str
            name: str
            arguments: dict

        tc = _ToolCall(id="evi_call", name=tool_name, arguments=tool_arguments)
        result = _consciousness_loop._execute_tool_call(tc, session_id)
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"EVI tool execution error ({tool_name}): {e}", exc_info=True)
        return json.dumps({"status": "error", "message": str(e)})


# ============================================
# EVI WEBSOCKET RELAY
# ============================================

def setup_evi_stream(sock, consciousness_loop=None, state_manager=None, evi_manager=None):
    """Register the EVI relay WebSocket route on the Flask-Sock instance.

    Called from server.py after creating the Sock object.

    Args:
        sock: flask_sock.Sock instance
        consciousness_loop: ConsciousnessLoop instance
        state_manager: StateManager instance
        evi_manager: HumeEVIManager instance
    """
    if consciousness_loop:
        init_evi_routes(consciousness_loop, state_manager, evi_manager)

    @sock.route("/phone/evi-stream")
    def evi_stream(ws):
        """Bidirectional relay between Twilio Media Stream and Hume EVI.

        Receives mulaw audio from Twilio, converts and forwards to EVI.
        Receives audio and events from EVI, converts and forwards to Twilio.
        Handles tool calls by executing through the substrate's MemoryTools.
        """
        import websocket as ws_client

        stream_sid = None
        call_sid = None
        caller_number = ""
        caller_name = "Unknown"
        evi_ws = None
        evi_chat_id = None
        evi_chat_group_id = None
        is_playing_response = False
        session_id = ""

        logger.info("EVI relay: Twilio WebSocket opened")

        def _on_evi_message(evi_ws_conn, raw_message):
            """Handle messages received from Hume EVI WebSocket."""
            nonlocal is_playing_response, evi_chat_id, evi_chat_group_id

            try:
                msg = json.loads(raw_message)
                msg_type = msg.get("type", "")

                # --- Chat metadata (first message from EVI) ---
                if msg_type == "chat_metadata":
                    evi_chat_id = msg.get("chat_id", "")
                    evi_chat_group_id = msg.get("chat_group_id", "")
                    logger.info(
                        f"EVI session started: chat={evi_chat_id}, "
                        f"group={evi_chat_group_id}"
                    )

                # --- Audio output from EVI → forward to Twilio ---
                elif msg_type == "audio_output":
                    audio_data = msg.get("data", "")
                    if audio_data and stream_sid:
                        is_playing_response = True
                        _forward_evi_audio_to_twilio(ws, stream_sid, audio_data)

                # --- EVI finished speaking ---
                elif msg_type == "assistant_end":
                    is_playing_response = False
                    # Send mark to Twilio for barge-in tracking
                    if stream_sid:
                        try:
                            ws.send(json.dumps({
                                "event": "mark",
                                "streamSid": stream_sid,
                                "mark": {"name": "response_end"},
                            }))
                        except Exception:
                            pass

                # --- User message transcript from EVI ---
                elif msg_type == "user_message":
                    content = msg.get("message", {}).get("content", "")
                    if content and _state_manager:
                        try:
                            _state_manager.add_message(
                                message_id=str(uuid.uuid4()),
                                session_id=session_id,
                                role="user",
                                content=content,
                                message_type="phone_call",
                            )
                            logger.info(f"EVI user transcript saved: '{content[:80]}...'")
                        except Exception as e:
                            logger.error(f"Failed to save EVI user message: {e}")

                # --- Assistant message transcript from EVI ---
                elif msg_type == "assistant_message":
                    content = msg.get("message", {}).get("content", "")
                    if content and _state_manager:
                        try:
                            _state_manager.add_message(
                                message_id=str(uuid.uuid4()),
                                session_id=session_id,
                                role="assistant",
                                content=content,
                                message_type="phone_call",
                            )
                            logger.info(f"EVI assistant transcript saved: '{content[:80]}...'")
                        except Exception as e:
                            logger.error(f"Failed to save EVI assistant message: {e}")

                # --- Tool call from EVI ---
                elif msg_type == "tool_call":
                    tool_call_id = msg.get("tool_call_id", "")
                    tool_name = msg.get("name", "")
                    tool_params = msg.get("parameters", "{}")

                    logger.info(f"EVI tool call: {tool_name} (id={tool_call_id})")

                    # Parse parameters
                    try:
                        if isinstance(tool_params, str):
                            arguments = json.loads(tool_params)
                        else:
                            arguments = tool_params
                    except json.JSONDecodeError:
                        arguments = {}

                    # Execute the tool
                    result = _execute_evi_tool_call(tool_name, arguments, session_id)

                    # Send tool response back to EVI
                    try:
                        evi_ws_conn.send(json.dumps({
                            "type": "tool_response",
                            "tool_call_id": tool_call_id,
                            "content": result,
                        }))
                        logger.info(f"EVI tool response sent for {tool_name}")
                    except Exception as e:
                        logger.error(f"Failed to send tool response: {e}")
                        # Send error response so EVI doesn't hang
                        try:
                            evi_ws_conn.send(json.dumps({
                                "type": "tool_error",
                                "tool_call_id": tool_call_id,
                                "error": str(e),
                                "content": "",
                            }))
                        except Exception:
                            pass

                # --- User interruption ---
                elif msg_type == "user_interruption":
                    is_playing_response = False
                    # Clear Twilio's audio queue
                    if stream_sid:
                        try:
                            ws.send(json.dumps({
                                "event": "clear",
                                "streamSid": stream_sid,
                            }))
                            logger.info("EVI: User interruption → cleared Twilio audio")
                        except Exception:
                            pass

                # --- Error from EVI ---
                elif msg_type == "error":
                    error_msg = msg.get("message", "Unknown error")
                    error_code = msg.get("code", "")
                    logger.error(f"EVI error ({error_code}): {error_msg}")

            except Exception as e:
                logger.error(f"Error handling EVI message: {e}", exc_info=True)

        def _on_evi_error(evi_ws_conn, error):
            logger.error(f"EVI WebSocket error: {error}")

        def _on_evi_close(evi_ws_conn, close_status_code, close_msg):
            logger.info(
                f"EVI WebSocket closed: {close_status_code} - {close_msg}"
            )

        def _on_evi_open(evi_ws_conn):
            """Send session settings to EVI once connected."""
            logger.info("EVI WebSocket connected, sending session settings...")

            # Build context from state manager
            ctx = _build_evi_context(caller_name, caller_number)

            # Send session settings with audio format and context.
            # Twilio sends mulaw 8kHz, but we convert to linear16 PCM
            # before forwarding to EVI, so declare linear16 here.
            #
            # NOTE: The system prompt is already baked into the EVI config's
            # prompt object — do NOT also send it here or we'll double the
            # context window usage and risk an I0100 service error.
            settings = {
                "type": "session_settings",
                "audio": {
                    "encoding": "linear16",
                    "channels": 1,
                    "sample_rate": 8000,
                },
            }

            # Inject context (capped to avoid blowing the EVI context window).
            # The config's prompt already has the full system instructions;
            # this context is only for per-call dynamic info.
            MAX_CONTEXT_CHARS = 2000
            if ctx["context"]:
                context_text = ctx["context"]
                if len(context_text) > MAX_CONTEXT_CHARS:
                    context_text = context_text[:MAX_CONTEXT_CHARS] + "\n...(truncated)"
                    logger.warning(
                        f"EVI context truncated from {len(ctx['context'])} "
                        f"to {MAX_CONTEXT_CHARS} chars"
                    )
                settings["context"] = {
                    "type": "persistent",
                    "text": context_text,
                }

            # Pass supplemental LLM API key if configured
            llm_api_key = os.getenv("HUME_EVI_LLM_API_KEY", "")
            if llm_api_key:
                settings["language_model_api_key"] = llm_api_key

            # Log payload size for debugging (redact API key)
            debug_settings = {k: v for k, v in settings.items()
                              if k != "language_model_api_key"}
            ctx_len = len(settings.get("context", {}).get("text", ""))
            logger.info(
                f"EVI session settings: audio=linear16/8kHz, "
                f"context={ctx_len} chars, "
                f"llm_key={'yes' if llm_api_key else 'no'}"
            )

            try:
                evi_ws_conn.send(json.dumps(settings))
                logger.info("EVI session settings sent")
            except Exception as e:
                logger.error(f"Failed to send EVI session settings: {e}")

        # ----- Main Twilio event loop -----
        try:
            while True:
                message = ws.receive()
                if message is None:
                    break

                data = json.loads(message)
                event = data.get("event")

                # ----- CONNECTED -----
                if event == "connected":
                    logger.info("EVI relay: Twilio protocol ready")

                # ----- START -----
                elif event == "start":
                    start_data = data["start"]
                    stream_sid = start_data["streamSid"]
                    call_sid = start_data.get("callSid", "")
                    params = start_data.get("customParameters", {})
                    caller_number = params.get("callerNumber", "")
                    caller_name = params.get("callerName", "Unknown")
                    session_id = f"call_{caller_number.replace('+', '')}"

                    logger.info(
                        f"EVI relay: Stream started for {caller_name} "
                        f"({caller_number}) [call={call_sid}]"
                    )

                    # Connect to Hume EVI WebSocket
                    if not _evi_manager:
                        logger.error("EVI manager not initialized")
                        break

                    evi_url = _evi_manager.get_websocket_url()
                    logger.info(f"Connecting to EVI: {evi_url[:80]}...")

                    evi_ws = ws_client.WebSocketApp(
                        evi_url,
                        on_open=_on_evi_open,
                        on_message=_on_evi_message,
                        on_error=_on_evi_error,
                        on_close=_on_evi_close,
                    )

                    # Run EVI WebSocket in a background thread
                    evi_thread = threading.Thread(
                        target=evi_ws.run_forever,
                        kwargs={"ping_interval": 20, "ping_timeout": 10},
                        daemon=True,
                    )
                    evi_thread.start()

                    # Brief wait for EVI connection to establish
                    time.sleep(0.5)

                # ----- MEDIA (incoming audio from caller) -----
                elif event == "media":
                    payload = data["media"]["payload"]
                    mulaw_chunk = base64.b64decode(payload)

                    # Forward audio to EVI as base64 PCM
                    if evi_ws and evi_ws.sock and evi_ws.sock.connected:
                        # Convert mulaw to 16-bit PCM for EVI
                        pcm_chunk = _mulaw_bytes_to_pcm16(mulaw_chunk)
                        pcm_b64 = base64.b64encode(pcm_chunk).decode("ascii")

                        try:
                            evi_ws.send(json.dumps({
                                "type": "audio_input",
                                "data": pcm_b64,
                            }))
                        except Exception as e:
                            logger.error(f"Failed to forward audio to EVI: {e}")

                # ----- MARK -----
                elif event == "mark":
                    mark_name = data.get("mark", {}).get("name", "")
                    if mark_name == "response_end":
                        is_playing_response = False

                # ----- STOP -----
                elif event == "stop":
                    logger.info(
                        f"EVI relay: Stream ended for {caller_name} ({caller_number})"
                    )
                    break

        except Exception as e:
            logger.error(f"EVI relay error: {e}", exc_info=True)
        finally:
            # Close EVI WebSocket
            if evi_ws:
                try:
                    evi_ws.close()
                except Exception:
                    pass

            # Post-call processing
            _post_call_processing(
                session_id, caller_name, caller_number, evi_chat_id
            )

            logger.info(f"EVI relay: WebSocket closed for {caller_name}")

    logger.info("EVI relay WebSocket route registered at /phone/evi-stream")


# ============================================
# AUDIO FORWARDING
# ============================================

def _forward_evi_audio_to_twilio(twilio_ws, stream_sid: str, audio_b64: str):
    """Convert EVI audio output to mulaw and stream to Twilio.

    EVI sends each audio chunk as a base64-encoded WAV file (with
    headers, typically at 24 kHz).  We:
      1. Parse the WAV header to get sample rate + raw PCM
      2. Downsample to 8 kHz (Twilio telephony rate)
      3. Convert 16-bit PCM → mulaw
      4. Stream in 640-byte chunks to Twilio

    Args:
        twilio_ws: Twilio WebSocket connection.
        stream_sid: Twilio stream SID.
        audio_b64: Base64-encoded WAV audio from EVI.
    """
    try:
        # Decode WAV → raw PCM + discover sample rate
        pcm_data, src_rate = _decode_evi_audio(audio_b64)

        # Downsample to 8 kHz for Twilio
        if src_rate != 8000:
            pcm_data = _resample_pcm16(pcm_data, src_rate, 8000)

        # Convert PCM → mulaw
        mulaw_data = _pcm16_to_mulaw(pcm_data)

        # Stream in chunks
        for i in range(0, len(mulaw_data), STREAM_CHUNK_SIZE):
            chunk = mulaw_data[i : i + STREAM_CHUNK_SIZE]
            twilio_ws.send(json.dumps({
                "event": "media",
                "streamSid": stream_sid,
                "media": {
                    "payload": base64.b64encode(chunk).decode("ascii"),
                },
            }))

    except Exception as e:
        logger.error(f"Error forwarding EVI audio to Twilio: {e}")


# ============================================
# POST-CALL PROCESSING
# ============================================

def _post_call_processing(
    session_id: str,
    caller_name: str,
    caller_number: str,
    evi_chat_id: Optional[str],
):
    """Run post-call tasks after the EVI session ends.

    - Logs the call via caller_id
    - Triggers conversation summary if needed

    Args:
        session_id: State manager session ID.
        caller_name: Contact name.
        caller_number: Phone number.
        evi_chat_id: Hume EVI chat ID (for fetching events if needed).
    """
    # Log the call
    try:
        from core.caller_id import get_caller_id
        caller_id = get_caller_id()
        caller_id.log_call(
            caller_number, "inbound", "voice", "completed",
            screening_decision="accept",
        )
    except Exception:
        pass

    # Check if conversation needs summarization
    if _state_manager and session_id:
        try:
            history = _state_manager.get_conversation(session_id, limit=100)
            if history and len(history) > 30:
                logger.info(
                    f"EVI post-call: {len(history)} messages in {session_id}, "
                    f"summary may be needed on next interaction"
                )
        except Exception:
            pass

    logger.info(
        f"EVI post-call processing complete for {caller_name} ({caller_number})"
    )
