#!/usr/bin/env python3
"""
Lovense Control Tool for Substrate AI

Controls Lovense hardware via the Lovense MCP server.
Enables intimate hardware control through the AI consciousness loop.

Requires the lovense-mcp service running (default: http://localhost:8000).
"""

import os
import json
import urllib.request
import urllib.error
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# MCP server URL (the lovense-mcp service)
LOVENSE_MCP_URL = os.getenv("LOVENSE_MCP_URL", "http://localhost:8000")


def _call_mcp(tool_name: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Call a tool on the Lovense MCP server using MCP SSE protocol.

    Args:
        tool_name: MCP tool name (e.g., 'vibrate', 'get_toys')
        arguments: Tool arguments

    Returns:
        Dict with response data or error
    """
    import uuid

    try:
        # MCP SSE protocol uses /messages endpoint with JSON-RPC format
        url = f"{LOVENSE_MCP_URL}/messages"

        # JSON-RPC 2.0 format for MCP tool calls
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments or {}
            },
            "id": str(uuid.uuid4())
        }

        data = json.dumps(payload).encode('utf-8')

        logger.debug(f"Lovense MCP request: {tool_name} with {arguments}")

        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            response_body = response.read().decode('utf-8').strip()

            if response_body:
                try:
                    result = json.loads(response_body)

                    # JSON-RPC response format
                    if 'error' in result:
                        return {"status": "error", "error": result['error'].get('message', str(result['error']))}

                    if 'result' in result:
                        mcp_result = result['result']
                        # MCP returns content array, extract the text
                        if isinstance(mcp_result, dict) and 'content' in mcp_result:
                            content = mcp_result['content']
                            if isinstance(content, list) and len(content) > 0:
                                text = content[0].get('text', '')
                                try:
                                    return json.loads(text)
                                except json.JSONDecodeError:
                                    return {"status": "OK", "message": text}
                        return mcp_result

                    return result
                except json.JSONDecodeError:
                    return {"status": "OK", "raw": response_body}
            return {"status": "OK"}

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else str(e)
        logger.error(f"Lovense MCP HTTP error: {e.code} - {error_body}")
        return {"status": "error", "error": error_body, "code": e.code}

    except urllib.error.URLError as e:
        logger.error(f"Lovense MCP connection error: {e.reason}")
        return {"status": "error", "error": f"MCP connection failed: {e.reason}"}

    except Exception as e:
        logger.error(f"Lovense MCP error: {str(e)}")
        return {"status": "error", "error": str(e)}


# =============================================================================
# LOVENSE CONTROL FUNCTIONS
# =============================================================================

def get_toys() -> Dict[str, Any]:
    """
    Get list of connected Lovense toys with status.

    Returns:
        Dict with toys list, battery levels, and connection status
    """
    result = _call_mcp("get_toys", {})

    if result.get("status") == "error":
        return {
            "status": "error",
            "message": f"Failed to get toys: {result.get('error')}"
        }

    return result


def vibrate(
    intensity: int,
    duration: int = 0,
    toy: str = "",
    loop_running_sec: float = 0,
    loop_pause_sec: float = 0,
    loop_cycles: int = 0
) -> Dict[str, Any]:
    """
    Set vibration intensity on Lovense toy(s).

    Args:
        intensity: Vibration level 0-20 (0 = off)
        duration: Duration in seconds (0 = continuous until stopped)
        toy: Specific toy ID (empty = all toys)
        loop_running_sec: Seconds to run per cycle (for looping patterns)
        loop_pause_sec: Seconds to pause between cycles
        loop_cycles: Number of loop cycles (0 = infinite)

    Returns:
        Dict with status and result
    """
    # Validate intensity range
    intensity = max(0, min(20, intensity))

    args = {
        "intensity": intensity,
        "duration": duration,
        "toy": toy
    }

    # Add loop parameters if specified
    if loop_running_sec > 0:
        args["loop_running_sec"] = loop_running_sec
    if loop_pause_sec > 0:
        args["loop_pause_sec"] = loop_pause_sec
    if loop_cycles > 0:
        args["loop_cycles"] = loop_cycles

    result = _call_mcp("vibrate", args)

    if result.get("status") == "error":
        return {
            "status": "error",
            "message": f"Vibrate failed: {result.get('error')}"
        }

    toy_info = f" on {toy}" if toy else " on all toys"
    duration_info = f" for {duration}s" if duration > 0 else " (continuous)"

    return {
        "status": "OK",
        "message": f"Vibration set to {intensity}/20{toy_info}{duration_info}",
        "intensity": intensity,
        "duration": duration
    }


def pattern(
    strength_sequence: str,
    interval_ms: int = 100,
    duration: int = 0,
    toy: str = ""
) -> Dict[str, Any]:
    """
    Play custom vibration pattern.

    Args:
        strength_sequence: Semicolon-separated intensity values (0-20)
                          Example: "5;10;15;20;15;10;5" for wave pattern
        interval_ms: Milliseconds between each strength value (min 100ms)
        duration: Total duration in seconds (0 = play pattern once)
        toy: Specific toy ID (empty = all toys)

    Returns:
        Dict with status and result
    """
    # Validate interval (minimum 100ms per Lovense API)
    interval_ms = max(100, interval_ms)

    result = _call_mcp("pattern", {
        "strength_sequence": strength_sequence,
        "interval_ms": interval_ms,
        "duration": duration,
        "toy": toy
    })

    if result.get("status") == "error":
        return {
            "status": "error",
            "message": f"Pattern failed: {result.get('error')}"
        }

    # Count pattern steps
    steps = len(strength_sequence.split(";"))
    toy_info = f" on {toy}" if toy else " on all toys"

    return {
        "status": "OK",
        "message": f"Playing {steps}-step pattern{toy_info}",
        "steps": steps,
        "interval_ms": interval_ms,
        "pattern": strength_sequence
    }


def preset(
    name: str,
    duration: int = 0,
    toy: str = ""
) -> Dict[str, Any]:
    """
    Play preset vibration pattern.

    Args:
        name: Preset name - one of: pulse, wave, fireworks, earthquake
        duration: Duration in seconds (0 = continuous)
        toy: Specific toy ID (empty = all toys)

    Returns:
        Dict with status and result
    """
    result = _call_mcp("preset", {
        "name": name,
        "duration": duration,
        "toy": toy
    })

    if result.get("status") == "error":
        return {
            "status": "error",
            "message": f"Preset failed: {result.get('error')}"
        }

    return {
        "status": "OK",
        "message": f"Playing preset: {name}",
        "preset": name,
        "duration": duration
    }


def rotate(
    intensity: int,
    duration: int = 0,
    toy: str = ""
) -> Dict[str, Any]:
    """
    Set rotation intensity (for toys with rotation motors like Nora).

    Args:
        intensity: Rotation level 0-20 (0 = off)
        duration: Duration in seconds (0 = continuous)
        toy: Specific toy ID (empty = all compatible toys)

    Returns:
        Dict with status and result
    """
    intensity = max(0, min(20, intensity))

    result = _call_mcp("rotate", {
        "intensity": intensity,
        "duration": duration,
        "toy": toy
    })

    if result.get("status") == "error":
        return {
            "status": "error",
            "message": f"Rotate failed: {result.get('error')}"
        }

    toy_info = f" on {toy}" if toy else " on compatible toys"

    return {
        "status": "OK",
        "message": f"Rotation set to {intensity}/20{toy_info}",
        "intensity": intensity
    }


def pump(
    intensity: int,
    duration: int = 0,
    toy: str = ""
) -> Dict[str, Any]:
    """
    Set pump/air inflation level (for toys like Max).

    Args:
        intensity: Pump level 0-3 (scaled from 0-20 input for consistency)
        duration: Duration in seconds (0 = continuous)
        toy: Specific toy ID (empty = all compatible toys)

    Returns:
        Dict with status and result
    """
    # Scale 0-20 input to 0-3 pump range
    intensity = max(0, min(20, intensity))
    scaled_intensity = min(3, intensity // 7)  # 0-6->0, 7-13->1, 14-20->2-3

    result = _call_mcp("pump", {
        "intensity": scaled_intensity,
        "duration": duration,
        "toy": toy
    })

    if result.get("status") == "error":
        return {
            "status": "error",
            "message": f"Pump failed: {result.get('error')}"
        }

    toy_info = f" on {toy}" if toy else " on compatible toys"

    return {
        "status": "OK",
        "message": f"Pump set to level {scaled_intensity}/3{toy_info}",
        "level": scaled_intensity
    }


def multi_function(
    vibrate_val: int = 0,
    rotate_val: int = 0,
    pump_val: int = 0,
    duration: int = 0,
    toy: str = ""
) -> Dict[str, Any]:
    """
    Control multiple functions simultaneously.

    Args:
        vibrate_val: Vibration intensity 0-20
        rotate_val: Rotation intensity 0-20
        pump_val: Pump level 0-20 (scaled to 0-3)
        duration: Duration in seconds (0 = continuous)
        toy: Specific toy ID (empty = all compatible toys)

    Returns:
        Dict with status and combined results
    """
    # Validate and clamp values
    vibrate_val = max(0, min(20, vibrate_val))
    rotate_val = max(0, min(20, rotate_val))
    pump_scaled = min(3, max(0, pump_val) // 7)

    if vibrate_val == 0 and rotate_val == 0 and pump_val == 0:
        return {
            "status": "error",
            "message": "At least one function intensity must be > 0"
        }

    result = _call_mcp("multi_function", {
        "vibrate": vibrate_val,
        "rotate": rotate_val,
        "pump": pump_scaled,
        "duration": duration,
        "toy": toy
    })

    if result.get("status") == "error":
        return {
            "status": "error",
            "message": f"Multi-function failed: {result.get('error')}"
        }

    active_functions = []
    if vibrate_val > 0:
        active_functions.append(f"vibrate={vibrate_val}")
    if rotate_val > 0:
        active_functions.append(f"rotate={rotate_val}")
    if pump_val > 0:
        active_functions.append(f"pump={pump_scaled}")

    return {
        "status": "OK",
        "message": f"Set {', '.join(active_functions)}",
        "vibrate": vibrate_val,
        "rotate": rotate_val,
        "pump": pump_scaled
    }


def stop_all(toy: str = "") -> Dict[str, Any]:
    """
    Stop all functions on all toys.

    Args:
        toy: Specific toy ID (empty = all toys)

    Returns:
        Dict with status
    """
    result = _call_mcp("stop_all", {"toy": toy})

    if result.get("status") == "error":
        return {
            "status": "error",
            "message": f"Stop failed: {result.get('error')}"
        }

    toy_info = toy if toy else "all toys"

    return {
        "status": "OK",
        "message": f"Stopped {toy_info}"
    }


# =============================================================================
# MAIN TOOL FUNCTION
# =============================================================================

def lovense_tool(
    action: str,
    intensity: Optional[int] = None,
    duration: Optional[int] = None,
    toy: Optional[str] = None,
    pattern_sequence: Optional[str] = None,
    interval_ms: Optional[int] = None,
    preset_name: Optional[str] = None,
    vibrate_intensity: Optional[int] = None,
    rotate_intensity: Optional[int] = None,
    pump_intensity: Optional[int] = None,
    loop_running_sec: Optional[float] = None,
    loop_pause_sec: Optional[float] = None,
    loop_cycles: Optional[int] = None
) -> Dict[str, Any]:
    """
    Unified Lovense hardware control tool.

    Controls Lovense toys via the MCP server for intimate hardware integration.

    Args:
        action: Action to perform:
                - get_toys: List connected toys with battery status
                - vibrate: Set vibration intensity (0-20)
                - pattern: Play custom pattern (strength sequence)
                - preset: Play built-in pattern (pulse/wave/fireworks/earthquake)
                - rotate: Set rotation (toys with rotation motor)
                - pump: Set pump/inflation (toys with pump)
                - multi_function: Control multiple functions at once
                - stop: Stop all functions
        intensity: Intensity level 0-20 (for vibrate/rotate/pump)
        duration: Duration in seconds (0 = continuous)
        toy: Target specific toy by ID (empty = all toys)
        pattern_sequence: Semicolon-separated intensities for pattern
                         Example: "5;10;15;20;15;10;5"
        interval_ms: Milliseconds between pattern steps (min 100)
        preset_name: Preset pattern name (pulse/wave/fireworks/earthquake)
        vibrate_intensity: Vibration for multi_function (0-20)
        rotate_intensity: Rotation for multi_function (0-20)
        pump_intensity: Pump for multi_function (0-20)
        loop_running_sec: Seconds to run per loop cycle
        loop_pause_sec: Seconds to pause between loop cycles
        loop_cycles: Number of loop cycles (0 = infinite)

    Returns:
        Dict with status and action-specific results
    """
    try:
        action_lower = action.lower()

        if action_lower == "get_toys":
            return get_toys()

        elif action_lower == "vibrate":
            if intensity is None:
                return {"status": "error", "message": "intensity required for vibrate action"}
            return vibrate(
                intensity=intensity,
                duration=duration or 0,
                toy=toy or "",
                loop_running_sec=loop_running_sec or 0,
                loop_pause_sec=loop_pause_sec or 0,
                loop_cycles=loop_cycles or 0
            )

        elif action_lower == "pattern":
            if not pattern_sequence:
                return {"status": "error", "message": "pattern_sequence required for pattern action"}
            return pattern(
                strength_sequence=pattern_sequence,
                interval_ms=interval_ms or 100,
                duration=duration or 0,
                toy=toy or ""
            )

        elif action_lower == "preset":
            if not preset_name:
                return {"status": "error", "message": "preset_name required for preset action"}
            return preset(
                name=preset_name,
                duration=duration or 0,
                toy=toy or ""
            )

        elif action_lower == "rotate":
            if intensity is None:
                return {"status": "error", "message": "intensity required for rotate action"}
            return rotate(
                intensity=intensity,
                duration=duration or 0,
                toy=toy or ""
            )

        elif action_lower == "pump":
            if intensity is None:
                return {"status": "error", "message": "intensity required for pump action"}
            return pump(
                intensity=intensity,
                duration=duration or 0,
                toy=toy or ""
            )

        elif action_lower == "multi_function":
            return multi_function(
                vibrate_val=vibrate_intensity or 0,
                rotate_val=rotate_intensity or 0,
                pump_val=pump_intensity or 0,
                duration=duration or 0,
                toy=toy or ""
            )

        elif action_lower == "stop":
            return stop_all(toy=toy or "")

        else:
            return {
                "status": "error",
                "message": f"Unknown action: {action}. Valid actions: get_toys, vibrate, pattern, preset, rotate, pump, multi_function, stop"
            }

    except Exception as e:
        logger.error(f"Lovense tool error: {e}")
        return {
            "status": "error",
            "message": f"Lovense error: {str(e)}"
        }


# =============================================================================
# STANDALONE TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("LOVENSE TOOL TEST")
    print("=" * 60)

    print(f"\nMCP Server URL: {LOVENSE_MCP_URL}")

    # Test get_toys
    print("\nTesting get_toys...")
    result = lovense_tool(action="get_toys")
    print(f"Result: {json.dumps(result, indent=2)}")

    print("\n" + "=" * 60)
