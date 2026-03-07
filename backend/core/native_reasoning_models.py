#!/usr/bin/env python3
"""
Native Reasoning Models Detection
Models that have built-in reasoning capabilities via OpenRouter

Set NATIVE_REASONING=true/false in .env to enable/disable.
"""
import os

# Models that support native reasoning (don't need <think> tags!)
NATIVE_REASONING_MODELS = {
    'openai/o1',
    'openai/o1-preview',
    'openai/o1-mini',
    'openai/gpt-5',
    'gpt-5',
    'deepseek/deepseek-r1',
    'deepseek/deepseek-v3.2',
    'deepseek/deepseek-v3.1-terminus',
    'deepseek/deepseek-reasoner',
    'moonshotai/kimi-k2-thinking',
    'moonshotai/moonshot-v1-thinking',
    'moonshotai/kimi-k2.5',
    'minimax/minimax-m2.5',
    # Mistral AI reasoning models
    'magistral-medium-2509',
    'magistral-medium',
    'mistralai/magistral-medium',
    # Qwen thinking/reasoning models
    'qwen3-235b-a22b-thinking-2507',
    'qwen3-235b-a22b-thinking',
    'qwen/qwen3.5-397b-a17b',
    'qwen3.5:cloud',
    'x-ai/grok-4.1-fast',
    'grok-4.20-experimental-beta-0304-reasoning',
    # GLM 4.7 (Z-AI) - has built-in reasoning and tool calling
    'z-ai/glm-4.6',
    'zai-org-glm-4.7',      # Venice
    'z-ai/glm-4.7',         # OpenRouter
    'z-ai/glm-5',
    'glm-4.6',              # Fallback variations
    'glm-4-7',
    'glm-5',
}

# NOTE: Models NOT in this list (like Mistral Large 3) are treated as standard models
# They work perfectly with function calling but don't have native reasoning capabilities

def has_native_reasoning(model: str) -> bool:
    """
    Check if a model has native reasoning capabilities.

    Controlled by NATIVE_REASONING env var (default: true).
    Set NATIVE_REASONING=false in .env to disable for all models.

    Args:
        model: Model identifier (e.g. "moonshotai/kimi-k2-thinking")

    Returns:
        True if model has native reasoning, False otherwise
    """
    # Check .env toggle
    env_val = os.getenv("NATIVE_REASONING", "true").lower()
    if env_val in ("false", "0", "no", "off"):
        return False

    # Normalize model name (remove version suffixes, etc)
    model_lower = model.lower()
    
    # Direct match
    if model_lower in NATIVE_REASONING_MODELS:
        return True
    
    # Partial match (e.g. "openai/o1-2024-12-17" matches "openai/o1")
    for native_model in NATIVE_REASONING_MODELS:
        if model_lower.startswith(native_model):
            return True
    
    # Check for "thinking" in name (heuristic)
    if 'thinking' in model_lower or 'reasoning' in model_lower or '/o1' in model_lower or '/r1' in model_lower:
        return True
    
    return False


if __name__ == "__main__":
    # Test
    test_models = [
        "moonshotai/kimi-k2-thinking",
        "openai/o1-preview",
        "openai/gpt-4",
        "deepseek/deepseek-r1",
        "openrouter/polaris-alpha",
    ]
    
    for model in test_models:
        result = has_native_reasoning(model)
        print(f"{model}: {'✅ NATIVE' if result else '❌ NEEDS PROMPT'}")

