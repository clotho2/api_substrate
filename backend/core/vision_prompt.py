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
# Note: Use base model names without version suffixes for broader matching
# The is_multimodal_model() function uses substring matching, so "mistralai/mistral-large"
# will match "mistralai/mistral-large-2512", "mistralai/mistral-large-latest", etc.
MULTIMODAL_MODELS = [
    # Mistral models (multimodal since Mistral Large 2/3)
    "mistralai/mistral-large",  # Mistral Large 2+, 3+ (multimodal)
    "mistralai/pixtral",  # Pixtral models (vision-first)
    "mistral-large",  # Short form
    "pixtral",  # Short form
    
    # Anthropic Claude models
    "anthropic/claude-3",
    "anthropic/claude-3-5",
    "claude-3",  # Short form
    
    # OpenAI models
    "openai/gpt-4o",
    "openai/gpt-4-vision",
    "openai/gpt-4-turbo",  # Also multimodal
    "openai/gpt-4.1",  # GPT-4.1 has vision support
    "openai/gpt-5",  # GPT-5 multimodal
    "gpt-4o",  # Short form
    "gpt-4-vision",  # Short form
    "gpt-4.1",  # Short form
    "gpt-5",  # Short form
    
    # Google models
    "google/gemini",
    "gemini",  # Short form
    
    # xAI Grok models
    "grok-4",
    "grok-2-vision",
    "x-ai/grok",
    
    # Meta Llama vision models
    "meta-llama/llama-3.2-90b-vision",
    "meta-llama/llama-3.2-11b-vision",
    "llama-3.2-vision",  # Short form
    
    # Qwen vision models
    "qwen/qwen-2-vl",
    "qwen-vl",

    # Moonshot Kimi models
    "moonshotai/kimi-k2.5",
]

def is_multimodal_model(model: str) -> bool:
    """
    Check if a model supports direct image processing (multimodal).
    
    Uses substring matching so base model names match versioned variants.
    For example: "mistralai/mistral-large" matches "mistralai/mistral-large-2512"

    Args:
        model: Model name/ID (e.g., "mistralai/mistral-large-2512")

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






