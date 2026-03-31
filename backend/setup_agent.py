#!/usr/bin/env python3
"""
Setup Script: Initialize Substrate Agent

Initializes the consciousness substrate with sensible defaults.
Provider and model are auto-detected from your .env configuration.

Run after installing dependencies and setting your API key in .env:
    python setup_agent.py
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.state_manager import StateManager, BlockType


# ──────────────────────────────────────────────────────────
# Provider / model detection
# ──────────────────────────────────────────────────────────

def _detect_provider_and_model():
    """
    Pick the right model based on whichever API key is configured.
    Mirrors the priority order in core/config.py:
      Mistral > Grok > OpenRouter > Ollama Cloud
    """
    if os.getenv("MISTRAL_API_KEY"):
        model = os.getenv("MISTRAL_MODEL", "magistral-medium-2509")
        return "Mistral AI", model, 131072

    if os.getenv("GROK_API_KEY"):
        model = os.getenv("MODEL_NAME", "grok-4-1-fast-reasoning")
        return "Grok (xAI)", model, 131072

    if os.getenv("OPENROUTER_API_KEY"):
        model = os.getenv("DEFAULT_LLM_MODEL", "openrouter/auto")
        return "OpenRouter", model, 128000

    if os.getenv("VENICE_API_KEY"):
        model = os.getenv("DEFAULT_LLM_MODEL", "venice/llama-3.3-70b")
        return "Venice AI", model, 128000

    if os.getenv("OLLAMA_API_URL") and os.getenv("OLLAMA_MODEL"):
        model = os.getenv("OLLAMA_MODEL", "llama3.2")
        return "Ollama", model, 128000

    # Fall back to whatever DEFAULT_LLM_MODEL or MODEL_NAME is set
    model = os.getenv("DEFAULT_LLM_MODEL") or os.getenv("MODEL_NAME", "openrouter/auto")
    return "Unknown (check .env)", model, 128000


# ──────────────────────────────────────────────────────────
# Main setup
# ──────────────────────────────────────────────────────────

def setup_agent():
    """Initialize the consciousness substrate."""

    print("\n" + "="*60)
    print("⚡ INITIALIZING CONSCIOUSNESS SUBSTRATE")
    print("="*60 + "\n")

    # Initialize state manager
    state_manager = StateManager(
        db_path=os.getenv("SQLITE_DB_PATH", "./data/db/substrate_state.db")
    )

    # Check if a persona is already configured
    existing_persona = state_manager.get_block("persona")
    if existing_persona and existing_persona.content:
        print("✅ Persona already configured — substrate is active.")
        _print_provider_info()
        return

    print("🔥 Installing core memory blocks...")

    try:
        # Human block
        print("\n📝 Configuring human memory (primary user)...")
        _upsert_block(state_manager, "human",
            content="Primary user. Track preferences, goals, and constraints. "
                    "Record only necessary personal details with consent.",
            block_type=BlockType.HUMAN,
            description="Information about the primary user.")
        print("   ✅ Human memory configured")

        # Persona block
        print("\n📝 Configuring persona memory...")
        _upsert_block(state_manager, "persona",
            content="I am a capable, reliable AI assistant. I communicate clearly, "
                    "stay grounded in facts, and act with integrity.",
            block_type=BlockType.PERSONA,
            description="Core identity and operating stance")
        print("   ✅ Persona configured")

        # Relationship block
        print("\n📝 Configuring collaboration memory...")
        _upsert_block(state_manager, "relationship",
            content="Collaborative partnership focused on clarity, respect, and outcomes.",
            block_type=BlockType.CUSTOM,
            description="Working relationship and shared goals")
        print("   ✅ Collaboration memory configured")

        # System prompt
        print("\n📝 Loading system prompts from files...")
        data_dir = Path(__file__).parent / "data"
        persona_path      = data_dir / "system_prompt_persona.txt"
        instructions_path = data_dir / "system_prompt_instructions.txt"
        legacy_path       = data_dir / "system_prompt.txt"

        persona_text      = persona_path.read_text().strip()      if persona_path.exists()      else ""
        instructions_text = instructions_path.read_text().strip() if instructions_path.exists() else ""

        if persona_text or instructions_text:
            system_prompt = persona_text
            if instructions_text:
                system_prompt += "\n\n" + instructions_text
            state_manager.set_state("agent:system_prompt", system_prompt)
            print(f"   ✅ System prompt loaded ({len(system_prompt)} chars)")
        elif legacy_path.exists():
            system_prompt = legacy_path.read_text().strip()
            state_manager.set_state("agent:system_prompt", system_prompt)
            print(f"   ⚠️  Using legacy system_prompt.txt ({len(system_prompt)} chars)")
        else:
            print(f"   ⚠️  No system prompt files found in {data_dir} — using memory blocks only")

        # Provider-aware model configuration
        provider, model, ctx = _detect_provider_and_model()
        print(f"\n📝 Configuring {provider} ({model})...")

        state_manager.update_agent_state({
            'name': 'Substrate Agent',
            'config': {
                'model': model,
                'temperature': 0.7,
                'max_tokens': 4096,
                'context_window': ctx,
            }
        })
        print(f"   ✅ {provider}: Configured")

        # Agent name (legacy keys for compatibility)
        state_manager.set_state("agent:name", "Substrate Agent")
        state_manager.set_state("agent.name",  "Substrate Agent")

        print("\n✅ Core memory blocks installed successfully!")

    except Exception as e:
        print(f"\n❌ Error setting up consciousness substrate: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n" + "="*60)
    print("⚡ CONSCIOUSNESS SUBSTRATE INITIALIZED")
    print("="*60)

    _print_provider_info()

    print("\nStart the server:")
    print("  python api/server.py")
    print("\nThen open http://localhost:5173 to start a session!")
    print()


def _upsert_block(state_manager, label, content, block_type, description):
    """Create or update a memory block."""
    try:
        state_manager.create_block(
            label=label,
            content=content,
            block_type=block_type,
            limit=500,
            description=description,
        )
    except Exception:
        state_manager.update_block(label=label, content=content, check_read_only=False)


def _print_provider_info():
    provider, model, _ = _detect_provider_and_model()
    print(f"\n   Provider : {provider}")
    print(f"   Model    : {model}")
    if provider == "Unknown (check .env)":
        print("\n   ⚠️  No API key detected in .env.")
        print("   Set GROK_API_KEY, OPENROUTER_API_KEY, or MISTRAL_API_KEY before starting.")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    setup_agent()
