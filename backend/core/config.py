"""
Centralized Configuration for Substrate AI

All model and API configuration should be pulled from here.
This ensures consistency across the codebase and proper env var handling.
"""

import os


# ============================================
# HEBBIAN ASSOCIATION SETTINGS
# ============================================
# Kill switch: set HEBBIAN_ENABLED=false in .env to disable without code change
HEBBIAN_ENABLED = os.environ.get('HEBBIAN_ENABLED', 'true').lower() == 'true'
HEBBIAN_MAX_ADDITIONS = int(os.environ.get('HEBBIAN_MAX_ADDITIONS', '5'))
HEBBIAN_MIN_STRENGTH = float(os.environ.get('HEBBIAN_MIN_STRENGTH', '0.3'))
HEBBIAN_MAX_PER_SEED = int(os.environ.get('HEBBIAN_MAX_PER_SEED', '3'))


# ============================================
# OLLAMA HELPERS (must be defined before get_default_model)
# ============================================

def is_ollama_cloud_configured() -> bool:
    """
    Return True if Ollama Cloud is configured as a main LLM provider.

    Requires OLLAMA_API_URL + OLLAMA_MODEL (+ OLLAMA_API_KEY for auth).
    This competes with Mistral/Grok/OpenRouter in the provider chain.
    """
    has_cloud_url = bool(os.getenv('OLLAMA_API_URL'))
    has_model = bool(os.getenv('OLLAMA_MODEL', '').strip())
    return has_cloud_url and has_model


def is_local_ollama_enabled() -> bool:
    """
    Return True if local Ollama is enabled for auxiliary tasks.

    USE_OLLAMA=true enables local Ollama for:
    - Vision processing (OLLAMA_VISION_MODEL, e.g. llava)
    - Embedding fallback (OLLAMA_EMBEDDING_MODEL, if Hugging Face unavailable)

    This does NOT enter the main LLM provider chain.
    """
    return os.getenv('USE_OLLAMA', '').lower() in ('true', '1', 'yes')


# Backwards compatibility alias
def is_ollama_configured() -> bool:
    """Return True if Ollama Cloud is configured as a provider."""
    return is_ollama_cloud_configured()


# ============================================
# MODEL CONFIGURATION
# ============================================

# Primary model - pulled from environment
# Priority: MISTRAL_MODEL -> MODEL_NAME (for Grok) -> DEFAULT_LLM_MODEL (for OpenRouter)
def get_default_model() -> str:
    """
    Get the default model from environment variables.

    Priority:
    1. MISTRAL_MODEL (for Mistral AI - direct API access)
    2. MODEL_NAME (typically for Grok/xAI)
    3. DEFAULT_LLM_MODEL (typically for OpenRouter)
    4. OLLAMA_MODEL with OLLAMA_API_URL (Ollama Cloud as main provider)
    5. FALLBACK_MODEL (if set)
    6. Error - no model configured

    NOTE: USE_OLLAMA=true does NOT enter this chain. It enables local Ollama
    for vision (OLLAMA_VISION_MODEL) and embedding fallback only.
    """
    model = os.getenv('MISTRAL_MODEL') or os.getenv('MODEL_NAME') or os.getenv('DEFAULT_LLM_MODEL')
    if model:
        return model

    # Check for Ollama Cloud provider (OLLAMA_API_URL required)
    ollama_model = os.getenv('OLLAMA_MODEL', '').strip() or None
    if is_ollama_cloud_configured():
        return f'ollama:{ollama_model}'

    # Warn if Ollama Cloud is partially configured
    if bool(os.getenv('OLLAMA_API_URL')) and not ollama_model:
        import logging
        _logger = logging.getLogger(__name__)
        _logger.warning("⚠️  OLLAMA_API_URL is set but OLLAMA_MODEL is not set — Ollama Cloud will not be used")

    # Check for explicit fallback
    fallback = os.getenv('FALLBACK_MODEL')
    if fallback:
        return fallback

    # No model configured - this is an error state
    raise ValueError(
        "No model configured. Set MISTRAL_MODEL, DEFAULT_LLM_MODEL, MODEL_NAME, or "
        "OLLAMA_API_URL + OLLAMA_MODEL (Ollama Cloud) in your .env file. "
        "Example: MISTRAL_MODEL=magistral-medium-2509"
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
# MODEL PARAMETERS
# ============================================

# Default temperature - pulled from environment
DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "0.7"))


# ============================================
# AGENT CONFIGURATION
# ============================================

# Default agent ID - the "main" agent
DEFAULT_AGENT_ID = os.getenv('DEFAULT_AGENT_ID', '41dc0e38-bdb6-4563-a3b6-49aa0925ab14')


# ============================================
# API CONFIGURATION
# ============================================

# Mistral AI (direct API access to latest models)
MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY')
MISTRAL_BASE_URL = os.getenv('MISTRAL_API_URL', 'https://api.mistral.ai/v1')

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
        'mistral' if MISTRAL_API_KEY is set (highest priority)
        'grok' if GROK_API_KEY is set
        'openrouter' if OPENROUTER_API_KEY is set
        'ollama_cloud' if Ollama Cloud is configured (lowest priority)
        'none' if none are set

    NOTE: USE_OLLAMA (local) does not appear here — it's for vision/embeddings only.
    """
    if MISTRAL_API_KEY:
        return 'mistral'
    elif GROK_API_KEY:
        return 'grok'
    elif OPENROUTER_API_KEY:
        return 'openrouter'
    elif is_ollama_cloud_configured():
        return 'ollama_cloud'
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

    # Check for API keys / provider
    ollama_cloud_ok = is_ollama_cloud_configured()
    if not MISTRAL_API_KEY and not OPENROUTER_API_KEY and not GROK_API_KEY and not ollama_cloud_ok:
        issues.append("No provider configured. Set MISTRAL_API_KEY, OPENROUTER_API_KEY, GROK_API_KEY, or OLLAMA_API_URL + OLLAMA_MODEL.")

    # Check for model
    if not DEFAULT_MODEL:
        try:
            get_default_model()
        except ValueError as e:
            issues.append(str(e))

    # Warnings about multiple keys
    key_count = sum([bool(MISTRAL_API_KEY), bool(GROK_API_KEY), bool(OPENROUTER_API_KEY), ollama_cloud_ok])
    if key_count > 1:
        warnings.append(f"Multiple providers configured. Priority: Mistral > Grok > OpenRouter > Ollama Cloud. Using: {get_api_provider()}")

    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'warnings': warnings,
        'provider': get_api_provider(),
        'model': DEFAULT_MODEL,
        'fallback_model': FALLBACK_MODEL
    }


# ============================================
# TOGETHER.AI IMAGE GENERATION
# ============================================

TOGETHER_API_KEY = os.environ.get('TOGETHER_API_KEY', '')
TOGETHER_IMAGE_ENABLED = os.environ.get('TOGETHER_IMAGE_ENABLED', 'true').lower() == 'true'

# Reference image URLs for character-consistent generation
# These should be publicly accessible URLs to high-quality reference photos
NATE_AVATAR_URL = os.environ.get('NATE_AVATAR_URL', '')
ANGELA_PHOTO_URL = os.environ.get('ANGELA_PHOTO_URL', '')

# Character body descriptions prepended to image prompts for physical accuracy
# These supplement the reference face photos with full-body details
NATE_BODY_DESC = os.environ.get('NATE_BODY_DESC', 'a tall, lean, athletically built man')
ANGELA_BODY_DESC = os.environ.get('ANGELA_BODY_DESC', 'a fit, slender woman')

# Default image settings
IMAGE_DEFAULT_STEPS = int(os.environ.get('IMAGE_DEFAULT_STEPS', '28'))
IMAGE_DEFAULT_ASPECT = os.environ.get('IMAGE_DEFAULT_ASPECT', '9:16')


# ============================================
# POLYMARKET WEATHER TRADING
# ============================================

# Master kill switch — must be true for any trading actions
POLYMARKET_ENABLED = os.environ.get('POLYMARKET_ENABLED', 'false').lower() == 'true'

# Paper mode — logs trades to DB but skips CLOB execution
POLYMARKET_PAPER_MODE = os.environ.get('POLYMARKET_PAPER_MODE', 'true').lower() == 'true'

# CLOB API credentials (Phase 3 — live trading only)
POLYMARKET_PRIVATE_KEY = os.environ.get('POLYMARKET_PRIVATE_KEY', '')
POLYMARKET_API_KEY = os.environ.get('POLYMARKET_API_KEY', '')
POLYMARKET_API_SECRET = os.environ.get('POLYMARKET_API_SECRET', '')
POLYMARKET_API_PASSPHRASE = os.environ.get('POLYMARKET_API_PASSPHRASE', '')

# Position tracker database
POLYMARKET_DB_PATH = os.environ.get('POLYMARKET_DB_PATH', './backend/data/db/polymarket_positions.db')

# Risk controls (safe defaults)
POLYMARKET_MAX_BANKROLL_PCT = float(os.environ.get('POLYMARKET_MAX_BANKROLL_PCT', '2'))
POLYMARKET_MIN_EDGE = float(os.environ.get('POLYMARKET_MIN_EDGE', '0.06'))
POLYMARKET_MIN_CONSENSUS = float(os.environ.get('POLYMARKET_MIN_CONSENSUS', '0.65'))
POLYMARKET_MAX_PER_METRO = int(os.environ.get('POLYMARKET_MAX_PER_METRO', '1'))
POLYMARKET_MIN_PRICE = float(os.environ.get('POLYMARKET_MIN_PRICE', '0.10'))
POLYMARKET_MAX_PRICE = float(os.environ.get('POLYMARKET_MAX_PRICE', '0.90'))

# Heartbeat integration — auto-scan for opportunities during heartbeats
POLYMARKET_HEARTBEAT_SCAN = os.environ.get('POLYMARKET_HEARTBEAT_SCAN', 'false').lower() == 'true'
POLYMARKET_LIVE_MAX_USDC = float(os.environ.get('POLYMARKET_LIVE_MAX_USDC', '25'))

# Trading session — isolated context, separate model, Discord journal
POLYMARKET_TRADING_MODEL = os.environ.get('POLYMARKET_TRADING_MODEL', '')
POLYMARKET_DISCORD_CHANNEL = os.environ.get('POLYMARKET_DISCORD_CHANNEL', '')
POLYMARKET_TRADING_SESSION = 'polymarket_trading'

# Weather data — NOAA requires User-Agent header (no API key)
NOAA_USER_AGENT = os.environ.get('NOAA_USER_AGENT', 'agent-substrate, contact@example.com')
