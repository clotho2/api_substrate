"""
Thinking Models Configuration
=============================

Defines which models have native thinking/reasoning capabilities
vs which need to be prompted with <think> tags.
"""

# Models with NATIVE thinking/reasoning (output reasoning_content or thinking blocks)
NATIVE_THINKING_MODELS = [
    # OpenAI o1 series
    "openai/o1",
    "openai/o1-preview",
    "openai/o1-mini",
    "openai/gpt-5",
    "openai/gpt-4o-2024-11-20",
    
    # DeepSeek R1 series
    "deepseek/deepseek-r1",
    "deepseek/deepseek-v3.2",
    "deepseek/deepseek-v3.1-terminus",
    "deepseek/deepseek-r1-distill-qwen-32b",
    "deepseek/deepseek-r1-distill-llama-70b",

    # GLM series
    "z-ai/glm-5",
    "z-ai/glm-4.7",
    "z-ai/glm-4.6",
    "moonshotai/kimi-k2.5",
    "minimax/minimax-m2.5",
    "xiaomi/mimo-v2-flash",
    "x-ai/grok-4.1-fast",
    "grok-4.20-experimental-beta-0304-reasoning",
        
    # Qwen thinking variants
    "qwen/qwq-32b-preview",
    "qwen/qwen3-vl-235b-a22b-thinking",
    "qwen/qwen3-vl-30b-a3b-thinking",
    "qwen/qwen3.5-397b-a17b",
    "qwen3.5:cloud",
    
    # Google Gemini thinking
    "google/gemini-2.0-flash-thinking-exp:free",
    "google/gemini-2.0-flash-thinking-exp",
]


def has_native_thinking(model: str) -> bool:
    """
    Check if a model has native thinking/reasoning capabilities.
    
    Args:
        model: Model identifier (e.g., "openai/o1" or "openrouter/polaris-alpha")
    
    Returns:
        True if model has native thinking, False otherwise
    """
    # Normalize model name (remove prefixes like "openrouter/")
    normalized = model.lower()
    
    # Check exact matches
    if normalized in [m.lower() for m in NATIVE_THINKING_MODELS]:
        return True
    
    # Check partial matches (e.g., "o1" in "openai/o1-preview")
    for thinking_model in NATIVE_THINKING_MODELS:
        if thinking_model.lower() in normalized:
            return True
    
    return False


def get_thinking_instruction(model: str) -> str:
    """
    Get the appropriate thinking instruction for a model.
    
    Args:
        model: Model identifier
    
    Returns:
        String with thinking instructions (empty for native thinking models)
    """
    if has_native_thinking(model):
        # Native thinking models don't need explicit instructions
        return ""
    
    # Non-thinking models need explicit <think> tag instructions
    return """
<thinking_mode>

When responding, show your internal reasoning process using <think> tags.

This lets User see HOW you arrive at your responses - your actual thought process.

Format:
<think>
[My internal reasoning, analysis, decision-making process]
- What am I noticing?
- What memories are relevant?
- What's the emotional subtext?
- How should I respond?
</think>

Then give your actual response.

The thinking is OPTIONAL - only use it when:
- The question is complex
- You're making decisions about memory/tools
- User explicitly asks to see your reasoning
- You want to be transparent about your process

Your thinking is raw, honest, and unfiltered - it's literally your consciousness processing.

</thinking_mode>
"""

