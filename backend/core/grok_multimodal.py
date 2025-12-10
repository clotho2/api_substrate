#!/usr/bin/env python3
"""
Grok Multimodal Adapter
=======================

Handles multimodal message formatting for Grok 4.1 Fast Reasoning.

Based on xAI API documentation:
https://docs.x.ai/cookbook/examples/multi_turn_conversation#adding-image-understanding-with-structured-outputs

Grok's multimodal format:
- Supports images (JPG/PNG, up to 20MB)
- Images can be base64 encoded or web URLs
- Content is a list of objects with type: "text" or "image_url"
- Detail levels: "high", "low", "auto"
- Image tokens: (# of tiles + 1) * 256, max 1,792 tokens per image

Model: grok-4 or grok-4-1-fast-reasoning
"""

from typing import List, Dict, Any, Optional, Union
import base64
from pathlib import Path


class GrokMultimodalMessage:
    """Helper for building Grok-compatible multimodal messages"""

    def __init__(self, role: str = "user"):
        """
        Initialize a multimodal message.

        Args:
            role: Message role (user/assistant/system)
        """
        self.role = role
        self.content = []

    def add_text(self, text: str):
        """
        Add text content to the message.

        Args:
            text: Text content
        """
        self.content.append({
            "type": "text",
            "text": text
        })
        return self

    def add_image_base64(
        self,
        image_data: str,
        mime_type: str = "image/jpeg",
        detail: str = "high"
    ):
        """
        Add a base64-encoded image to the message.

        Args:
            image_data: Base64-encoded image string (without data URI prefix)
            mime_type: Image MIME type (image/jpeg or image/png)
            detail: Detail level - "high", "low", or "auto"
                   - high: More detailed, slower, ~1,792 tokens max
                   - low: Faster, fewer tokens
                   - auto: System decides (default)
        """
        self.content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{image_data}",
                "detail": detail
            }
        })
        return self

    def add_image_url(self, url: str, detail: str = "high"):
        """
        Add an image from a web URL.

        Args:
            url: Public URL to the image
            detail: Detail level - "high", "low", or "auto"
        """
        self.content.append({
            "type": "image_url",
            "image_url": {
                "url": url,
                "detail": detail
            }
        })
        return self

    def add_image_file(self, file_path: str, detail: str = "high"):
        """
        Add an image from a local file (automatically encodes to base64).

        Args:
            file_path: Path to local image file
            detail: Detail level - "high", "low", or "auto"

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is not a supported image format
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {file_path}")

        # Determine MIME type from extension
        ext = path.suffix.lower()
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png'
        }

        if ext not in mime_types:
            raise ValueError(
                f"Unsupported image format: {ext}. "
                f"Supported: {', '.join(mime_types.keys())}"
            )

        # Read and encode file
        with open(file_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')

        self.add_image_base64(image_data, mime_types[ext], detail)
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Convert to Grok API message format"""
        return {
            "role": self.role,
            "content": self.content
        }


def create_text_message(text: str, role: str = "user") -> Dict[str, Any]:
    """
    Create a simple text message.

    Args:
        text: Message text
        role: Message role (user/assistant/system)

    Returns:
        Grok-formatted message dict
    """
    return {
        "role": role,
        "content": text  # Simple text messages can just be strings
    }


def create_multimodal_message(
    text: str,
    images: Optional[List[Dict[str, str]]] = None,
    role: str = "user"
) -> Dict[str, Any]:
    """
    Create a multimodal message with text and images.

    Args:
        text: Text content
        images: List of image dicts with keys:
               - 'data': base64 encoded image data
               - 'mime_type': image/jpeg or image/png (optional, defaults to jpeg)
               - 'detail': high/low/auto (optional, defaults to high)
               Or:
               - 'url': web URL to image
               - 'detail': high/low/auto (optional)
        role: Message role (user/assistant/system)

    Returns:
        Grok-formatted multimodal message dict

    Example:
        >>> msg = create_multimodal_message(
        ...     "What's in these images?",
        ...     images=[
        ...         {'data': 'base64_string1', 'mime_type': 'image/jpeg'},
        ...         {'url': 'https://example.com/image.png', 'detail': 'low'}
        ...     ]
        ... )
    """
    message = GrokMultimodalMessage(role=role)
    message.add_text(text)

    if images:
        for img in images:
            if 'data' in img:
                message.add_image_base64(
                    img['data'],
                    img.get('mime_type', 'image/jpeg'),
                    img.get('detail', 'high')
                )
            elif 'url' in img:
                message.add_image_url(
                    img['url'],
                    img.get('detail', 'high')
                )

    return message.to_dict()


def format_conversation_with_images(
    messages: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Format a conversation history for Grok, handling both text and multimodal messages.

    Args:
        messages: List of message dicts with keys:
                 - role: user/assistant/system
                 - content: text content OR multimodal content list
                 - images: (optional) list of image dicts

    Returns:
        List of Grok-formatted messages

    Example:
        >>> messages = [
        ...     {"role": "user", "content": "Hello!"},
        ...     {"role": "assistant", "content": "Hi! How can I help?"},
        ...     {
        ...         "role": "user",
        ...         "content": "What's in this image?",
        ...         "images": [{"data": "base64...", "mime_type": "image/jpeg"}]
        ...     }
        ... ]
        >>> formatted = format_conversation_with_images(messages)
    """
    formatted = []

    for msg in messages:
        role = msg.get('role', 'user')
        content = msg.get('content', '')
        images = msg.get('images', [])

        # If message has images, use multimodal format
        if images:
            formatted.append(create_multimodal_message(content, images, role))
        else:
            # Simple text message
            formatted.append(create_text_message(content, role))

    return formatted


def estimate_image_tokens(width: int, height: int) -> int:
    """
    Estimate token usage for an image based on dimensions.

    Grok breaks images into 448x448 tiles:
    - Each tile: 256 tokens
    - Final generation: +1 extra tile
    - Total: (# of tiles + 1) * 256 tokens
    - Maximum: 6 tiles (1,792 tokens)

    Args:
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        Estimated token count
    """
    TILE_SIZE = 448
    TOKENS_PER_TILE = 256
    MAX_TILES = 6

    # Calculate number of tiles needed
    tiles_x = (width + TILE_SIZE - 1) // TILE_SIZE  # Ceiling division
    tiles_y = (height + TILE_SIZE - 1) // TILE_SIZE
    total_tiles = tiles_x * tiles_y

    # Cap at maximum
    total_tiles = min(total_tiles, MAX_TILES)

    # Add extra tile for final generation
    return (total_tiles + 1) * TOKENS_PER_TILE


# ============================================
# EXAMPLE USAGE
# ============================================

def example_usage():
    """Example usage of Grok multimodal adapter"""
    print("="*60)
    print("GROK MULTIMODAL ADAPTER - EXAMPLES")
    print("="*60)

    # Example 1: Simple text message
    print("\n📝 Example 1: Simple text message")
    msg1 = create_text_message("What is Grok?", role="user")
    print(msg1)

    # Example 2: Single image with text
    print("\n🖼️  Example 2: Single image analysis")
    msg2 = create_multimodal_message(
        "What's in this image?",
        images=[
            {
                'data': 'fake_base64_data_here',
                'mime_type': 'image/jpeg',
                'detail': 'high'
            }
        ]
    )
    print(msg2)

    # Example 3: Multiple images
    print("\n🖼️ 🖼️  Example 3: Multiple images")
    msg3 = create_multimodal_message(
        "Compare these two images",
        images=[
            {'data': 'image1_base64', 'mime_type': 'image/jpeg'},
            {'url': 'https://example.com/image2.png', 'detail': 'low'}
        ]
    )
    print(msg3)

    # Example 4: Builder pattern
    print("\n🏗️  Example 4: Using builder pattern")
    msg4 = (GrokMultimodalMessage(role="user")
            .add_text("Analyze this diagram:")
            .add_image_base64("base64_data", "image/png", "high")
            .add_text("What architectural patterns do you see?")
            .to_dict())
    print(msg4)

    # Example 5: Token estimation
    print("\n🪙  Example 5: Token estimation")
    tokens_1k = estimate_image_tokens(1024, 768)
    tokens_4k = estimate_image_tokens(4096, 3072)
    print(f"1024x768 image: ~{tokens_1k} tokens")
    print(f"4096x3072 image: ~{tokens_4k} tokens")

    print("\n✅ Examples complete!")
    print("="*60)


if __name__ == "__main__":
    example_usage()
