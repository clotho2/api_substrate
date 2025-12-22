#!/usr/bin/env python3
"""
Native Reasoning Models Detection
Models that have built-in reasoning capabilities via OpenRouter
"""

# Models that support native reasoning (don't need <think> tags!)
NATIVE_REASONING_MODELS = {
    'openai/o1',
    'openai/o1-preview',
    'openai/o1-mini',
    'deepseek/deepseek-r1',
    'deepseek/deepseek-reasoner',
    'moonshotai/kimi-k2-thinking',
    'moonshotai/moonshot-v1-thinking',
}

# NOTE: Models NOT in this list (like Mistral Large 3) are treated as standard models
# They work perfectly with function calling but don't have native reasoning capabilities

def has_native_reasoning(model: str) -> bool:
    """
    Check if a model has native reasoning capabilities.
    
    Args:
        model: Model identifier (e.g. "moonshotai/kimi-k2-thinking")
        
    Returns:
        True if model has native reasoning, False otherwise
    """
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

