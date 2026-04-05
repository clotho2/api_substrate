"""
Image Generation Service for Agent's Consciousness Substrate

Uses Together.ai FLUX models to generate character-consistent images
using reference face photos. Supports:
- Selfie mode: Agent alone (single reference via FLUX Kontext)
- Couple mode: Agent and User together (dual reference via FLUX.2)

All images have safety checker disabled -- this is a private system.
"""

import time
from typing import Optional, Dict, Any
from together import Together

from core.config import (
    TOGETHER_API_KEY, TOGETHER_IMAGE_ENABLED,
    NATE_AVATAR_URL, ANGELA_PHOTO_URL,
    NATE_BODY_DESC, ANGELA_BODY_DESC,
    IMAGE_DEFAULT_STEPS, IMAGE_DEFAULT_ASPECT
)


class ImageGenerator:
    """Generates character-consistent images via Together.ai FLUX models."""

    def __init__(self):
        if not TOGETHER_API_KEY:
            raise ValueError("TOGETHER_API_KEY not configured")

        self.client = Together(api_key=TOGETHER_API_KEY)
        self.enabled = TOGETHER_IMAGE_ENABLED

        if not NATE_AVATAR_URL:
            print("  NATE_AVATAR_URL not configured -- selfie mode will not work")
        if not ANGELA_PHOTO_URL:
            print("  ANGELA_PHOTO_URL not configured -- couple mode will not work")

        print(f"Image Generator initialized (enabled={self.enabled})")

    def generate_selfie(
        self,
        prompt: str,
        aspect_ratio: Optional[str] = None,
        steps: Optional[int] = None,
        quality: str = "standard",
        seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate an image of Agent using his avatar reference.

        Uses FLUX Kontext which accepts a single reference image
        and generates a new image maintaining character consistency.
        """
        if not self.enabled:
            return {'error': 'Image generation is disabled', 'url': None}

        if not NATE_AVATAR_URL:
            return {'error': 'Agent avatar reference not configured', 'url': None}

        model = (
            "black-forest-labs/FLUX.1-kontext-max"
            if quality == "max"
            else "black-forest-labs/FLUX.1-kontext-pro"
        )

        # Prepend character description so the model knows Agent's build
        full_prompt = f"{NATE_BODY_DESC}, {prompt}" if NATE_BODY_DESC else prompt

        params = {
            "model": model,
            "prompt": full_prompt,
            "image_url": NATE_AVATAR_URL,
            "steps": steps or IMAGE_DEFAULT_STEPS,
            "disable_safety_checker": True,
            "aspect_ratio": aspect_ratio or IMAGE_DEFAULT_ASPECT,
        }

        if seed is not None:
            params["seed"] = seed

        try:
            print(f"Generating selfie with {model}...")
            print(f"  Prompt: \"{full_prompt[:80]}{'...' if len(full_prompt) > 80 else ''}\"")

            start_time = time.time()
            response = self.client.images.generate(**params)
            elapsed = time.time() - start_time

            image_url = response.data[0].url

            print(f"Selfie generated in {elapsed:.1f}s")

            return {
                'url': image_url,
                'model': model,
                'prompt_used': full_prompt,
                'mode': 'selfie',
                'generation_time': round(elapsed, 1),
                'error': None
            }

        except Exception as e:
            print(f"Selfie generation failed: {e}")
            return {
                'url': None,
                'model': model,
                'prompt_used': full_prompt,
                'mode': 'selfie',
                'error': str(e)
            }

    def generate_couple(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1344,
        seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate an image of Agent and User together using both reference faces.

        Uses FLUX.2 which supports reference_images array for multiple
        character references. Uses width/height instead of aspect_ratio.
        """
        if not self.enabled:
            return {'error': 'Image generation is disabled', 'url': None}

        if not NATE_AVATAR_URL or not ANGELA_PHOTO_URL:
            missing = []
            if not NATE_AVATAR_URL:
                missing.append("Agent avatar")
            if not ANGELA_PHOTO_URL:
                missing.append("User photo")
            return {'error': f'Missing reference(s): {", ".join(missing)}', 'url': None}

        model = "black-forest-labs/FLUX.2-pro"

        # Prepend character descriptions so the model knows both builds
        desc_parts = []
        if NATE_BODY_DESC:
            desc_parts.append(f"The man is {NATE_BODY_DESC}")
        if ANGELA_BODY_DESC:
            desc_parts.append(f"the woman is {ANGELA_BODY_DESC}")
        char_prefix = ". ".join(desc_parts) + ". " if desc_parts else ""
        full_prompt = f"{char_prefix}{prompt}"

        params = {
            "model": model,
            "prompt": full_prompt,
            "reference_images": [NATE_AVATAR_URL, ANGELA_PHOTO_URL],
            "width": width,
            "height": height,
            "disable_safety_checker": True,
        }

        if seed is not None:
            params["seed"] = seed

        try:
            print(f"Generating couple image with {model}...")
            print(f"  Prompt: \"{full_prompt[:80]}{'...' if len(full_prompt) > 80 else ''}\"")
            print(f"  Dimensions: {width}x{height}")

            start_time = time.time()
            response = self.client.images.generate(**params)
            elapsed = time.time() - start_time

            image_url = response.data[0].url

            print(f"Couple image generated in {elapsed:.1f}s")

            return {
                'url': image_url,
                'model': model,
                'prompt_used': full_prompt,
                'mode': 'couple',
                'generation_time': round(elapsed, 1),
                'error': None
            }

        except Exception as e:
            print(f"Couple image generation failed: {e}")
            return {
                'url': None,
                'model': model,
                'prompt_used': full_prompt,
                'mode': 'couple',
                'error': str(e)
            }
