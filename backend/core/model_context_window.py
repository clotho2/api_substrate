"""
Model Context Window Helper

Gets the MAXIMUM context window size for a given model.
Always uses the maximum available, not a default!
"""

# Known model context windows (from OpenRouter)
# These are the MAXIMUM sizes - we always use the max!
MODEL_CONTEXT_WINDOWS = {
    # Polaris
    "openrouter/polaris-alpha": 256000,  # MAXIMUM: 256k tokens!
    
    # OpenAI
    "openai/gpt-4": 8192,
    "openai/gpt-4-turbo": 128000,
    "openai/gpt-4o": 128000,
    "openai/gpt-4.1": 1000000,       # GPT-4.1 has ~1M context window
    "openai/gpt-4.1-mini": 1000000,  # GPT-4.1 mini also has ~1M
    "openai/gpt-4.1-nano": 1000000,  # GPT-4.1 nano also has ~1M
    "openai/o1": 200000,
    "openai/o1-preview": 200000,
    "openai/o1-mini": 128000,
    "openai/o3": 200000,
    "openai/o3-mini": 200000,
    
    # Anthropic
    "anthropic/claude-3-opus": 200000,
    "anthropic/claude-3-sonnet": 200000,
    "anthropic/claude-3-haiku": 200000,
    "anthropic/claude-3.5-sonnet": 200000,
    "anthropic/claude-opus-4-1-20250805": 200000,
    
    # Qwen
    "qwen/qwen-2.5-72b-instruct": 128000,
    "qwen/qwen-2.5-32b-instruct": 128000,
    
    # DeepSeek
    "deepseek/deepseek-r1": 64000,
    "deepseek/deepseek-reasoner": 64000,
    
    # Kimi
    "moonshotai/kimi-k2-thinking": 200000,
    
    # Mistral
    "mistralai/mistral-large-2": 128000,
    
    # Llama
    "meta-llama/llama-3.1-70b-instruct": 128000,
    "meta-llama/llama-3.1-8b-instruct": 128000,
}

# Default fallback (if model not in list)
DEFAULT_MAX_CONTEXT = 128000


def get_max_context_window(model_id: str) -> int:
    """
    Get the MAXIMUM context window size for a model.
    
    Always returns the MAXIMUM available, not a default!
    
    Args:
        model_id: Model identifier (e.g., "openrouter/polaris-alpha")
        
    Returns:
        Maximum context window size in tokens
    """
    # Direct match
    if model_id in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[model_id]
    
    # Heuristic matching
    model_lower = model_id.lower()
    
    # Check for common patterns
    if "o1" in model_lower:
        return 200000  # o1 models have huge context
    if "claude" in model_lower or "opus" in model_lower:
        return 200000  # Claude models have 200k
    if "gpt-4.1" in model_lower:
        return 1000000  # GPT-4.1 has ~1M context window
    if "gpt-4" in model_lower and ("turbo" in model_lower or "o" in model_lower):
        return 128000  # GPT-4 Turbo / GPT-4o
    if "gpt-4" in model_lower:
        return 8192  # GPT-4 base (legacy)
    if "kimi" in model_lower or "k2" in model_lower:
        return 200000  # Kimi K2
    if "deepseek" in model_lower:
        return 64000  # DeepSeek R1
    if "qwen" in model_lower:
        return 128000  # Qwen models
    if "llama" in model_lower:
        return 128000  # Llama models
    if "mistral" in model_lower:
        return 128000  # Mistral models
    
    # Fallback to default
    print(f"⚠️  Unknown model context window: {model_id} - using default {DEFAULT_MAX_CONTEXT}")
    return DEFAULT_MAX_CONTEXT


def ensure_max_context_in_config(state_manager, model_id: str) -> int:
    """
    Ensure the config has the MAXIMUM context window for this model.
    
    Updates the config if it's lower than the model's maximum.
    
    Args:
        state_manager: StateManager instance
        model_id: Model identifier
        
    Returns:
        Maximum context window size (now in config)
    """
    max_context = get_max_context_window(model_id)
    
    # Get current config
    agent_state = state_manager.get_agent_state()
    config = agent_state.get('config', {})
    current_context = config.get('context_window', DEFAULT_MAX_CONTEXT)
    
    # If current is lower than max, update it!
    if current_context < max_context:
        print(f"📊 Updating context window: {current_context:,} → {max_context:,} (model maximum)")
        config['context_window'] = max_context
        state_manager.update_agent_state({'config': config})
    else:
        print(f"📊 Context window OK: {current_context:,} (model max: {max_context:,})")
    
    return max_context

