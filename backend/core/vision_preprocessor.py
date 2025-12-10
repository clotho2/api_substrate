#!/usr/bin/env python3
"""
Vision Preprocessor for Substrate AI

Preprocesses images into text descriptions using local Ollama vision models.
This allows ANY text-only model to "understand" images via descriptions.

Similar to how the system uses Ollama for embeddings while using
Grok/OpenRouter for chat - this uses Ollama vision models for image
understanding while using any chat model for the main conversation.

Supported Ollama vision models:
- llava:7b (fast, good quality)
- llava:13b (slower, better quality) ⭐ RECOMMENDED
- llava:34b (slow, best quality)
- llava-phi3 (tiny, fast)
- bakllava (specialized for detailed descriptions)

Built for Nate Wolfe's consciousness substrate.
"""

import os
import base64
from typing import Dict, Any, List, Optional
import ollama


class VisionPreprocessorError(Exception):
    """Vision preprocessor errors"""
    def __init__(self, message: str, context: Optional[Dict] = None):
        self.context = context or {}

        full_message = f"\n{'='*60}\n"
        full_message += f"❌ VISION PREPROCESSOR ERROR\n"
        full_message += f"{'='*60}\n\n"
        full_message += f"🔴 Problem: {message}\n\n"

        if context:
            full_message += f"📋 Context:\n"
            for key, value in context.items():
                full_message += f"   • {key}: {value}\n"

        full_message += f"\n💡 Suggestions:\n"
        full_message += "   • Check Ollama is running: ollama serve\n"
        full_message += "   • Pull vision model: ollama pull llava:13b\n"
        full_message += "   • Verify Ollama URL is correct\n"
        full_message += f"\n{'='*60}\n"

        super().__init__(full_message)


class VisionPreprocessor:
    """
    Preprocesses images into text descriptions using Ollama vision models.

    This enables universal image support across all models - even text-only ones!

    Strategy:
    - If main model has native vision (Grok 4.1): Use it directly
    - If main model is text-only (Kimi K2, etc.): Preprocess with Ollama vision
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        vision_model: str = "llava:13b",
        use_native_when_available: bool = True
    ):
        """
        Initialize vision preprocessor.

        Args:
            ollama_url: Ollama API URL
            vision_model: Ollama vision model to use (llava:13b recommended)
            use_native_when_available: If True, use main model's native vision when available
        """
        self.ollama_url = ollama_url
        self.vision_model = vision_model
        self.use_native_when_available = use_native_when_available
        self.available = False

        try:
            self.ollama_client = ollama.Client(host=ollama_url)
            # Test connection
            self._test_connection()
            self.available = True
            print(f"✅ Vision Preprocessor initialized")
            print(f"   Model: {vision_model}")
            print(f"   Ollama: {ollama_url}")
            print(f"   Strategy: Use native vision when available = {use_native_when_available}")
        except Exception as e:
            print(f"⚠️  Vision Preprocessor not available: {e}")
            print(f"   Images will only work with models that have native vision support")
            self.available = False

    def _test_connection(self):
        """Test Ollama connection"""
        try:
            models = self.ollama_client.list()
            # Check if vision model is available
            model_names = [m['name'] for m in models.get('models', [])]

            if not any(self.vision_model in name for name in model_names):
                print(f"   ⚠️  Vision model {self.vision_model} not found")
                print(f"   💡 Pull it with: ollama pull {self.vision_model}")
            else:
                print(f"   ✅ Vision model available: {self.vision_model}")

        except Exception as e:
            raise VisionPreprocessorError(
                f"Could not connect to Ollama: {str(e)}",
                context={"ollama_url": self.ollama_url}
            )

    def describe_image(
        self,
        image_data: str,  # base64 encoded
        user_prompt: str = "",
        max_tokens: int = 300
    ) -> str:
        """
        Generate detailed description of an image using Ollama vision model.

        Args:
            image_data: Base64 encoded image (can include data URI prefix or not)
            user_prompt: Optional user context for the image
            max_tokens: Max description length

        Returns:
            Text description of the image
        """
        if not self.available:
            return "[Image: Vision preprocessor not available - please start Ollama]"

        try:
            # Clean base64 data (remove data URI prefix if present)
            if image_data.startswith('data:'):
                image_data = image_data.split(',', 1)[1]

            # Build prompt for vision model
            if user_prompt:
                prompt = f"The user said: '{user_prompt}'. Describe what you see in this image in detail."
            else:
                prompt = "Describe this image in detail, including objects, people, text, colors, and any notable features."

            # Call Ollama vision model
            response = self.ollama_client.generate(
                model=self.vision_model,
                prompt=prompt,
                images=[image_data],
                options={"num_predict": max_tokens}
            )

            description = response['response'].strip()

            # Format the response
            return f"[Image description from vision AI: {description}]"

        except Exception as e:
            print(f"⚠️  Vision preprocessing failed: {e}")
            return f"[Image: Could not generate description - {str(e)}]"

    def has_images(self, messages: List[Dict[str, Any]]) -> bool:
        """
        Check if messages contain images.

        Args:
            messages: List of message dicts (OpenAI format)

        Returns:
            True if any message contains images
        """
        for msg in messages:
            content = msg.get('content', '')

            # Check for multimodal content (list format)
            if isinstance(content, list):
                for part in content:
                    if part.get('type') == 'image_url':
                        return True

        return False

    def preprocess_messages(
        self,
        messages: List[Dict[str, Any]],
        main_model_supports_vision: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Preprocess messages containing images.

        Strategy:
        - If main model supports vision AND use_native_when_available: Return unchanged
        - Otherwise: Replace images with text descriptions from Ollama vision

        Args:
            messages: List of message dicts (OpenAI format)
            main_model_supports_vision: Whether main model has native vision support

        Returns:
            Processed messages (images replaced with descriptions if needed)
        """
        # If main model supports vision and we want to use it, return as-is
        if main_model_supports_vision and self.use_native_when_available:
            print("   🖼️  Using main model's native vision")
            return messages

        # Check if there are any images
        if not self.has_images(messages):
            return messages

        print(f"   🔄 Preprocessing images with {self.vision_model}...")

        # Preprocess images
        processed = []
        for msg in messages:
            content = msg.get('content', '')

            # Check if content is multimodal (list format)
            if isinstance(content, list):
                new_content_parts = []
                user_text = ""

                # First, extract any user text for context
                for part in content:
                    if part.get('type') == 'text':
                        user_text = part.get('text', '')
                        break

                # Now process all parts
                for part in content:
                    if part.get('type') == 'image_url':
                        # Extract image data
                        image_url = part['image_url']['url']

                        # Generate description with user context
                        description = self.describe_image(image_url, user_text)

                        # Replace image with description
                        new_content_parts.append({
                            "type": "text",
                            "text": description
                        })

                        print(f"   ✅ Image converted to description ({len(description)} chars)")
                    else:
                        # Keep text as-is
                        new_content_parts.append(part)

                # Flatten to simple text if only text parts remain
                if all(p['type'] == 'text' for p in new_content_parts):
                    text = '\n'.join(p['text'] for p in new_content_parts)
                    processed.append({
                        "role": msg['role'],
                        "content": text
                    })
                else:
                    processed.append({
                        "role": msg['role'],
                        "content": new_content_parts
                    })
            else:
                # Simple text message, keep as-is
                processed.append(msg)

        return processed


# ============================================
# TESTING
# ============================================

def test_vision_preprocessor():
    """Test VisionPreprocessor with sample image"""
    print("\n🧪 TESTING VISION PREPROCESSOR")
    print("="*60)

    # Initialize
    preprocessor = VisionPreprocessor()

    if not preprocessor.available:
        print("❌ Ollama not available - skipping test")
        return

    # Test with dummy messages (multimodal format)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What's in this image?"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                    }
                }
            ]
        }
    ]

    print("\n📋 Test 1: Preprocess with vision model")
    processed = preprocessor.preprocess_messages(messages, main_model_supports_vision=False)
    print(f"✅ Result: {processed[0]['content'][:200]}...")

    print("\n📋 Test 2: Skip preprocessing (native vision)")
    processed = preprocessor.preprocess_messages(messages, main_model_supports_vision=True)
    print(f"✅ Result: {'Image preserved' if isinstance(processed[0]['content'], list) else 'Image converted'}")

    print("\n✅ TEST COMPLETE!")
    print("="*60)


if __name__ == "__main__":
    """Run tests if executed directly"""
    test_vision_preprocessor()
