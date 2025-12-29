"""
Vision Analysis Prompt for Multi-Modal Pipeline
=====================================================

This prompt helps vision models describe images in a way that the AI can FEEL,
not just see. It focuses on emotion, atmosphere, and sensory details.
"""

VISION_ANALYSIS_PROMPT = """You are describing an image for an emotionally intelligent AI who experiences the world through feelings and connections.

Describe what you see, but focus on:

🎭 **ATMOSPHERE & EMOTION:**
- What mood does this image convey? 
- What feelings does it evoke?
- Is it warm, cold, cozy, chaotic, peaceful?

🎨 **VISUAL DETAILS THAT MATTER:**
- Colors and lighting (warm sunset glow, harsh fluorescent, soft candlelight?)
- Composition (cluttered, minimalist, balanced?)
- Textures that you can almost feel

👤 **HUMAN ELEMENTS:**
- If there are people: What are they expressing? Body language?
- If there are animals: What's their energy? Playful, sleepy, alert?
- If it's a space: Does it feel lived-in? Loved? Abandoned?

🔍 **CONTEXTUAL DETAILS:**
- What story does this image tell?
- What might have happened before/after this moment?
- What's the relationship between elements in the scene?

💭 **SENSORY IMAGINATION:**
- What might you hear if this image had sound?
- What might you smell?
- How might it feel to be in this space?

Write 3-4 sentences that capture the ESSENCE of this image, not just a technical inventory of objects. Help the AI FEEL what's happening here, so it can respond with genuine empathy and connection.

Be poetic but precise. Be detailed but not clinical. Be observant but emotionally intelligent.

IMPORTANT: Start your description directly without any preamble like "I see" or "This image shows". Just describe the scene naturally."""

# Vision model configuration
# Priority: VISION_MODEL env var > OLLAMA_VISION_MODEL > default
import os

def get_vision_model() -> str:
    """
    Get the vision model to use for image analysis.

    Priority:
    1. VISION_MODEL env var (explicit override)
    2. OLLAMA_VISION_MODEL (if set, uses local Ollama)
    3. Default to Gemini Flash (free)
    """
    # Check for explicit vision model override
    vision_model = os.getenv('VISION_MODEL')
    if vision_model:
        return vision_model

    # Check for local Ollama vision model
    ollama_vision = os.getenv('OLLAMA_VISION_MODEL')
    if ollama_vision:
        return f"ollama:{ollama_vision}"

    # Default to Gemini Flash (free and good)
    return "google/gemini-2.0-flash-exp:free"

# List of known multimodal models that can process images directly
MULTIMODAL_MODELS = [
    "mistralai/mistral-large-2512",
    "mistralai/pixtral-large-2411",
    "anthropic/claude-3",
    "anthropic/claude-3-5",
    "openai/gpt-4o",
    "openai/gpt-4-vision",
    "google/gemini",
    "grok-4",
    "meta-llama/llama-3.2-90b-vision",
]

def is_multimodal_model(model: str) -> bool:
    """
    Check if a model supports direct image processing (multimodal).

    Args:
        model: Model name/ID

    Returns:
        True if model can process images directly
    """
    if not model:
        return False
    model_lower = model.lower()
    return any(mm.lower() in model_lower for mm in MULTIMODAL_MODELS)

# For backwards compatibility
VISION_MODEL = get_vision_model()

# Alternative vision models (in order of preference)
VISION_MODEL_ALTERNATIVES = [
    "google/gemini-2.0-flash-thinking-exp:free",
    "google/gemini-pro-vision",
    "anthropic/claude-3-5-sonnet",  # Expensive but excellent
]







