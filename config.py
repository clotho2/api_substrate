import os
from dotenv import load_dotenv

load_dotenv()

# API Configuration
GROK_API_KEY = os.getenv("GROK_API_KEY", "")
GROK_API_URL = os.getenv("GROK_API_URL", "https://api.x.ai/v1/chat/completions")
MODEL_NAME = os.getenv("MODEL_NAME", "grok-4-1-fast-reasoning")

# Database Configuration
DB_PATH = os.getenv("DB_PATH", "nate_substrate.db")

# Service Configuration
PORT = int(os.getenv("PORT", "8091"))

# Model Parameters
N_CTX = int(os.getenv("N_CTX", "131072"))  # Grok supports 131K context
DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "4096"))
DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "0.7"))
