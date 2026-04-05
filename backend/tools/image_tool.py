#!/usr/bin/env python3
"""
Image Generation Tool for Substrate AI

Action-based tool for generating character-consistent images via Together.ai FLUX models.
Follows the same dispatch pattern as discord_tool, phone_tool, lovense_tool, etc.

Actions:
- selfie: Generate an image of Agent using his avatar reference face
- couple: Generate an image of Agent and User together using both reference faces
"""

import sys
import os
from typing import Dict, Any

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Lazy singleton for the ImageGenerator
_generator = None


def _get_generator():
    """Get or create the ImageGenerator singleton."""
    global _generator
    if _generator is None:
        from services.image_generator import ImageGenerator
        _generator = ImageGenerator()
    return _generator


def image_tool(**kwargs) -> Dict[str, Any]:
    """
    Unified image generation tool — dispatcher function.

    Actions:
        selfie: Generate an image of Agent (single reference face)
        couple: Generate an image of Agent and User together (dual reference)

    Returns:
        Dict with status, image_url, mode, and message
    """
    action = kwargs.get("action", "")

    if not action:
        return {
            "status": "error",
            "message": "No action specified. Use 'selfie' or 'couple'."
        }

    try:
        generator = _get_generator()
    except Exception as e:
        return {
            "status": "error",
            "message": f"Image generator initialization failed: {str(e)}"
        }

    try:
        if action == "selfie":
            result = generator.generate_selfie(
                prompt=kwargs.get("prompt", ""),
                aspect_ratio=kwargs.get("aspect_ratio"),
                steps=kwargs.get("steps"),
                quality=kwargs.get("quality", "standard"),
                seed=kwargs.get("seed"),
            )

        elif action == "couple":
            result = generator.generate_couple(
                prompt=kwargs.get("prompt", ""),
                width=kwargs.get("width", 1024),
                height=kwargs.get("height", 1344),
                seed=kwargs.get("seed"),
            )

        else:
            return {
                "status": "error",
                "message": f"Unknown action: {action}. Use 'selfie' or 'couple'."
            }

        # Format response
        if result.get('error'):
            return {
                "status": "error",
                "message": result['error']
            }

        return {
            "status": "OK",
            "image_url": result['url'],
            "mode": result['mode'],
            "model": result.get('model', ''),
            "generation_time": result.get('generation_time', 0),
            "message": f"Image generated successfully. URL: {result['url']}"
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Image generation failed: {str(e)}"
        }
