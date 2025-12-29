"""
Centralized Configuration for Substrate AI

All model and API configuration should be pulled from here.
This ensures consistency across the codebase and proper env var handling.
"""

import os


# ============================================
# MODEL CONFIGURATION
# ============================================

# Primary model - pulled from environment
# Priority: MODEL_NAME (for Grok) -> DEFAULT_LLM_MODEL (for OpenRouter)
def get_default_model() -> str:
    """
    Get the default model from environment variables.

    Priority:
    1. MODEL_NAME (typically for Grok/xAI)
    2. DEFAULT_LLM_MODEL (typically for OpenRouter)
    3. FALLBACK_MODEL (if set)
    4. Error - no model configured
    """
    model = os.getenv('MODEL_NAME') or os.getenv('DEFAULT_LLM_MODEL')
    if model:
        return model

    # Check for explicit fallback
    fallback = os.getenv('FALLBACK_MODEL')
    if fallback:
        return fallback

    # No model configured - this is an error state
    # Return a placeholder that will cause a clear error
    raise ValueError(
        "No model configured. Set DEFAULT_LLM_MODEL or MODEL_NAME in your .env file. "
        "Example: DEFAULT_LLM_MODEL=mistralai/mistral-large-2512"
    )


def get_fallback_model() -> str:
    """
    Get the fallback model for when primary fails.

    Returns:
        Fallback model from FALLBACK_MODEL env var, or None if not set.
    """
    return os.getenv('FALLBACK_MODEL', 'moonshotai/kimi-k2-0905')


# Cached values for performance (loaded once at import)
try:
    DEFAULT_MODEL = get_default_model()
except ValueError:
    # During import, if no model is configured, use a placeholder
    # This allows the module to load, but will error when actually used
    DEFAULT_MODEL = None

FALLBACK_MODEL = get_fallback_model()


# ============================================
# AGENT CONFIGURATION
# ============================================

# Default agent ID - the "main" agent
DEFAULT_AGENT_ID = os.getenv('DEFAULT_AGENT_ID', '41dc0e38-bdb6-4563-a3b6-49aa0925ab14')


# ============================================
# API CONFIGURATION
# ============================================

# OpenRouter
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
OPENROUTER_BASE_URL = os.getenv('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')

# Grok/xAI
GROK_API_KEY = os.getenv('GROK_API_KEY')
GROK_BASE_URL = os.getenv('GROK_BASE_URL', 'https://api.x.ai/v1')

# Determine which API to use
def get_api_provider() -> str:
    """
    Determine which API provider to use based on available keys.

    Returns:
        'grok' if GROK_API_KEY is set
        'openrouter' if OPENROUTER_API_KEY is set
        'none' if neither is set
    """
    if GROK_API_KEY:
        return 'grok'
    elif OPENROUTER_API_KEY:
        return 'openrouter'
    return 'none'


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_model_or_default(model: str = None) -> str:
    """
    Get the model to use, falling back to default if none specified.

    Args:
        model: Explicitly specified model, or None to use default

    Returns:
        Model string to use

    Raises:
        ValueError: If no model configured and none specified
    """
    if model:
        return model

    if DEFAULT_MODEL:
        return DEFAULT_MODEL

    # Try to get it fresh (in case env was set after import)
    return get_default_model()


def validate_config() -> dict:
    """
    Validate the configuration and return status.

    Returns:
        Dict with validation results
    """
    issues = []
    warnings = []

    # Check for API keys
    if not OPENROUTER_API_KEY and not GROK_API_KEY:
        issues.append("No API key configured. Set OPENROUTER_API_KEY or GROK_API_KEY.")

    # Check for model
    if not DEFAULT_MODEL:
        try:
            get_default_model()
        except ValueError as e:
            issues.append(str(e))

    # Warnings
    if GROK_API_KEY and OPENROUTER_API_KEY:
        warnings.append("Both GROK_API_KEY and OPENROUTER_API_KEY are set. Grok will be preferred.")

    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'warnings': warnings,
        'provider': get_api_provider(),
        'model': DEFAULT_MODEL,
        'fallback_model': FALLBACK_MODEL
    }
