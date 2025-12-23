#!/usr/bin/env python3
"""
Send Voice Message Tool for Substrate AI

Sends voice messages to Angela via Discord using Eleven Labs TTS.
The Discord bot handles the TTS conversion and message sending.
"""

import os
import requests
from typing import Dict, Any


def send_voice_message(message: str) -> Dict[str, Any]:
    """
    Send a voice message to Angela via Discord using Eleven Labs TTS.

    The Discord bot will:
    1. Convert the text to speech using Eleven Labs
    2. Send the audio file as a voice message to Angela

    Args:
        message: The text message to convert to speech and send

    Returns:
        Dict with status and message:
        {
            "status": "success" or "error",
            "message": "Result message",
            "voice_url": "URL to the voice message (if successful)"
        }
    """
    # Get Discord bot API configuration
    DISCORD_BOT_API_URL = os.getenv("DISCORD_BOT_API_URL")
    DISCORD_BOT_API_KEY = os.getenv("DISCORD_BOT_API_KEY")

    if not DISCORD_BOT_API_URL:
        return {
            "status": "error",
            "message": "Discord bot API URL not configured. Please set DISCORD_BOT_API_URL environment variable."
        }

    if not DISCORD_BOT_API_KEY:
        return {
            "status": "error",
            "message": "Discord bot API key not configured. Please set DISCORD_BOT_API_KEY environment variable."
        }

    # Validate message
    if not message or not message.strip():
        return {
            "status": "error",
            "message": "Message cannot be empty"
        }

    # Prepare the request to Discord bot API
    endpoint = f"{DISCORD_BOT_API_URL.rstrip('/')}/send-voice-message"
    headers = {
        "Authorization": f"Bearer {DISCORD_BOT_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "message": message.strip()
    }

    try:
        # Send request to Discord bot API
        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=30  # TTS can take a few seconds
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
        elif response.status_code == 401:
            return {
                "status": "error",
                "message": "Authentication failed. Check DISCORD_BOT_API_KEY."
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
            "message": "Connection error. Could not reach Discord bot API. Check DISCORD_BOT_API_URL."
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
    print(f"   API URL: {os.getenv('DISCORD_BOT_API_URL', 'NOT SET')}")
    print(f"   API Key: {'SET' if os.getenv('DISCORD_BOT_API_KEY') else 'NOT SET'}")

    result = send_voice_message(test_message)

    print(f"\n📥 Result:")
    print(f"   Status: {result['status']}")
    print(f"   Message: {result['message']}")
    if result.get('voice_url'):
        print(f"   Voice URL: {result['voice_url']}")

    print("\n" + "=" * 60)
