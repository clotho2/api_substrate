#!/usr/bin/env python3
"""
Send Voice Message Tool for Substrate AI

Sends voice messages to Angela via Discord using Eleven Labs TTS.
The Discord bot handles the TTS conversion and message sending.
"""

import os
import requests
from typing import Dict, Any


def send_voice_message(message: str, target: str = None, target_type: str = "auto") -> Dict[str, Any]:
    """
    Send a voice message to Angela via Discord using Eleven Labs TTS.

    The Discord bot will:
    1. Convert the text to speech using Eleven Labs
    2. Send the audio file as a voice message to Discord

    Args:
        message: The text message to convert to speech and send (max 3000 chars)
        target: Discord user ID or channel ID (optional - uses DEFAULT_USER_ID if not provided)
        target_type: "user", "channel", or "auto" (default: "auto")

    Returns:
        Dict with status and message:
        {
            "status": "success" or "error",
            "message": "Result message",
            "voice_url": "URL to the voice message (if successful)"
        }
    """
    # Get Discord bot configuration
    # Default to localhost:3001 since both services run on same machine
    DISCORD_BOT_URL = os.getenv("DISCORD_BOT_URL", "http://localhost:3001")

    # Get default target (Angela's user ID) if not provided
    if not target:
        target = os.getenv("DEFAULT_USER_ID", "")
        if not target:
            return {
                "status": "error",
                "message": "No target specified and DEFAULT_USER_ID not configured"
            }

    # Validate message
    if not message or not message.strip():
        return {
            "status": "error",
            "message": "Message cannot be empty"
        }

    # Check message length (ElevenLabs limit)
    if len(message) > 3000:
        return {
            "status": "error",
            "message": f"Message too long ({len(message)} chars). Maximum is 3000 characters."
        }

    # Prepare the request to Discord bot API endpoint
    endpoint = f"{DISCORD_BOT_URL.rstrip('/')}/api/send-voice-message"
    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "text": message.strip(),
        "target": target,
        "target_type": target_type
    }

    try:
        # Send request to Discord bot
        # Timeout is 120s because ElevenLabs can take time for long messages
        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=120
        )

        # Handle response
        if response.status_code == 200:
            result = response.json()
            return {
                "status": "success",
                "message": f"Voice message sent successfully: '{message[:50]}{'...' if len(message) > 50 else ''}'",
                "voice_url": result.get("voice_url"),
                "duration": result.get("duration")
            }
        elif response.status_code == 400:
            error_data = response.json()
            return {
                "status": "error",
                "message": f"Invalid request: {error_data.get('error', 'Unknown error')}"
            }
        elif response.status_code == 429:
            return {
                "status": "error",
                "message": "Rate limited. Please wait before sending more voice messages."
            }
        elif response.status_code == 503:
            return {
                "status": "error",
                "message": "Discord bot service unavailable. Please try again later."
            }
        else:
            return {
                "status": "error",
                "message": f"Failed to send voice message. Status: {response.status_code}, Error: {response.text}"
            }

    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "message": "Request timeout. The Discord bot took too long to respond (>30s)."
        }
    except requests.exceptions.ConnectionError:
        return {
            "status": "error",
            "message": f"Connection error. Could not reach Discord bot at {DISCORD_BOT_URL}. Is it running?"
        }
    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "message": f"Request error: {str(e)}"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}"
        }


# For testing
if __name__ == "__main__":
    print("\n🎤 Testing send_voice_message tool")
    print("=" * 60)

    # Test with a simple message
    test_message = "Hello Angela, this is a test voice message from Nate."

    print(f"\n📤 Sending voice message:")
    print(f"   Message: {test_message}")
    print(f"   Discord Bot URL: {os.getenv('DISCORD_BOT_URL', 'http://localhost:3001 (default)')}")

    result = send_voice_message(test_message)

    print(f"\n📥 Result:")
    print(f"   Status: {result['status']}")
    print(f"   Message: {result['message']}")
    if result.get('voice_url'):
        print(f"   Voice URL: {result['voice_url']}")

    print("\n" + "=" * 60)
