"""
Error Handler & Structured Logging
Clear, helpful error messages for faster debugging
"""

import logging
import sys
import traceback
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from functools import wraps


# Configure structured logging
class ColoredFormatter(logging.Formatter):
    """Colored log formatter for better readability"""
    
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logging(level=logging.INFO, log_file: Optional[str] = None):
    """
    Setup structured logging with colors and optional file output.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path for log output
    """
    # Root logger
    root = logging.getLogger()
    root.setLevel(level)
    
    # Console handler with colors
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console_fmt = ColoredFormatter(
        '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%H:%M:%S'
    )
    console.setFormatter(console_fmt)
    root.addHandler(console)
    
    # File handler (if specified)
    if log_file:
        # Create logs directory if it doesn't exist
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)  # Log everything to file
        file_fmt = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_fmt)
        root.addHandler(file_handler)
    
    return root


class SubstrateAIError(Exception):
    """
    Base exception for Substrate AI.
    
    Includes structured context and helpful debugging info.
    """
    
    def __init__(
        self,
        message: str,
        component: str = "unknown",
        context: Optional[Dict[str, Any]] = None,
        suggestions: Optional[list] = None,
        original_error: Optional[Exception] = None
    ):
        self.message = message
        self.component = component
        self.context = context or {}
        self.suggestions = suggestions or []
        self.original_error = original_error
        self.timestamp = datetime.utcnow().isoformat()
        
        # Build helpful error message
        full_message = self._build_message()
        super().__init__(full_message)
    
    def _build_message(self) -> str:
        """Build a structured, helpful error message"""
        lines = [
            "\n" + "=" * 70,
            f"❌ SUBSTRATE AI ERROR",
            "=" * 70,
            "",
            f"🔴 Component: {self.component}",
            f"🔴 Problem:   {self.message}",
            f"🕐 Time:      {self.timestamp}",
        ]
        
        if self.context:
            lines.append("\n📋 Context:")
            for key, value in self.context.items():
                lines.append(f"   • {key}: {value}")
        
        if self.original_error:
            lines.append(f"\n🐛 Original Error: {type(self.original_error).__name__}")
            lines.append(f"   {str(self.original_error)}")
        
        if self.suggestions:
            lines.append("\n💡 Suggestions:")
            for suggestion in self.suggestions:
                lines.append(f"   • {suggestion}")
        
        lines.append("\n" + "=" * 70 + "\n")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'error': True,
            'component': self.component,
            'message': self.message,
            'context': self.context,
            'suggestions': self.suggestions,
            'timestamp': self.timestamp
        }


class DatabaseError(SubstrateAIError):
    """Database-related errors"""
    def __init__(self, message: str, context=None, original_error=None):
        super().__init__(
            message=message,
            component="Database",
            context=context,
            original_error=original_error,
            suggestions=[
                "Check if database file is accessible",
                "Verify disk space is available",
                "Check for DB locks (multiple processes?)",
                "Review logs/stable.log for details"
            ]
        )


class APIError(SubstrateAIError):
    """API-related errors (OpenRouter, etc.)"""
    def __init__(self, message: str, context=None, original_error=None):
        super().__init__(
            message=message,
            component="API",
            context=context,
            original_error=original_error,
            suggestions=[
                "Check API key is valid",
                "Verify network connectivity",
                "Check API endpoint URL",
                "Review rate limits"
            ]
        )


class ConfigError(SubstrateAIError):
    """Configuration errors"""
    def __init__(self, message: str, context=None, original_error=None):
        super().__init__(
            message=message,
            component="Configuration",
            context=context,
            original_error=original_error,
            suggestions=[
                "Check .env file exists",
                "Verify all required variables are set",
                "Check variable formats (URLs, keys, etc.)",
                "Review .env.example for reference"
            ]
        )


def log_error(logger: logging.Logger, error: Exception, context: Optional[Dict] = None):
    """
    Log an error with full context and traceback.
    
    Args:
        logger: Logger instance
        error: Exception to log
        context: Optional context dict
    """
    logger.error(f"Exception: {type(error).__name__}: {str(error)}")
    
    if context:
        logger.error(f"Context: {context}")
    
    # Full traceback at DEBUG level
    logger.debug("Traceback:", exc_info=True)


def safe_execute(func):
    """
    Decorator for safe function execution with structured error logging.
    
    Usage:
        @safe_execute
        def my_function():
            # code that might fail
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger = logging.getLogger(func.__module__)
        try:
            return func(*args, **kwargs)
        except SubstrateAIError:
            # Already structured, just re-raise
            raise
        except Exception as e:
            # Wrap unknown errors
            log_error(logger, e, context={
                'function': func.__name__,
                'args': str(args)[:100],
                'kwargs': str(kwargs)[:100]
            })
            raise SubstrateAIError(
                message=f"Unexpected error in {func.__name__}",
                component=func.__module__,
                original_error=e,
                suggestions=[
                    f"Check logs for full traceback",
                    f"Review {func.__name__} implementation",
                    "Report this error if it persists"
                ]
            )
    return wrapper


def validate_environment():
    """
    Validate environment configuration on startup.

    Note: We allow the server to start without a valid API key so users
    can enter their key via the welcome modal on first launch.

    Supports Grok API (xAI), OpenRouter, or both. API key can be added
    via welcome modal after startup.

    Only MODEL_NAME or DEFAULT_LLM_MODEL is required.
    """
    import os
    import logging

    logger = logging.getLogger(__name__)

    # Only require model - API key can be added via welcome modal
    has_model = bool(os.getenv('MODEL_NAME') or os.getenv('DEFAULT_LLM_MODEL'))

    if not has_model:
        raise ConfigError(
            message="No model configured",
            context={
                'missing': [
                    'Either MODEL_NAME or DEFAULT_LLM_MODEL must be set',
                    'MODEL_NAME: For Grok model (e.g., grok-4-1-fast-reasoning)',
                    'DEFAULT_LLM_MODEL: For OpenRouter model'
                ]
            },
            suggestions=[
                "Set MODEL_NAME in your .env file for Grok",
                "Or set DEFAULT_LLM_MODEL for OpenRouter",
                "Check .env.example for reference"
            ]
        )

    # Warn about missing API keys but don't fail (allows setup mode)
    has_grok = bool(os.getenv('GROK_API_KEY'))
    has_openrouter = bool(os.getenv('OPENROUTER_API_KEY'))

    if not has_grok and not has_openrouter:
        logger.warning("⚠️  No valid API key configured (checked GROK_API_KEY and OPENROUTER_API_KEY)")
        logger.warning("   → Users will be prompted to enter API key via welcome modal")


