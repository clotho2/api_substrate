#!/usr/bin/env python3
"""
Setup Script: Initialize Substrate Agent

This script sets up a generic consciousness substrate with neutral defaults.
Run this after installing dependencies and configuring your .env file.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.state_manager import StateManager, BlockType


def setup_nate_agent():
    """Initialize the consciousness substrate with generic defaults"""

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
        print("✅ Persona already configured")
        print("   Consciousness substrate active...")
        return

    print("🔥 Installing core memory blocks...")

    try:
        # Create or update Human block
        print("\n📝 Configuring human memory (primary user)...")
        try:
            state_manager.create_block(
                label="human",
                content="Primary user. Track preferences, goals, and constraints. Record only necessary personal details with consent.",
                block_type=BlockType.HUMAN,
                limit=500,
                description="Information about the primary user."
            )
        except Exception as e:
            # Block might already exist, update it
            state_manager.update_block(
                label="human",
                content="Primary user. Track preferences, goals, and constraints. Record only necessary personal details with consent.",
                check_read_only=False
            )
        print("   ✅ Human memory configured")

        # Create or update Persona block
        print("\n📝 Configuring persona memory...")
        try:
            state_manager.create_block(
                label="persona",
                content="I am a capable, reliable AI assistant. I communicate clearly, stay grounded in facts, and act with integrity.",
                block_type=BlockType.PERSONA,
                limit=500,
                description="Core identity and operating stance"
            )
        except Exception as e:
            # Block might already exist, update it
            state_manager.update_block(
                label="persona",
                content="I am a capable, reliable AI assistant. I communicate clearly, stay grounded in facts, and act with integrity.",
                check_read_only=False
            )
        print("   ✅ Persona configured")

        # Create or update Relationship block
        print("\n📝 Configuring collaboration memory...")
        try:
            state_manager.create_block(
                label="relationship",
                content="Collaborative partnership focused on clarity, respect, and outcomes.",
                block_type=BlockType.CUSTOM,
                limit=500,
                description="Working relationship and shared goals"
            )
        except Exception as e:
            # Block might already exist, update it
            state_manager.update_block(
                label="relationship",
                content="Collaborative partnership focused on clarity, respect, and outcomes.",
                check_read_only=False
            )
        print("   ✅ Collaboration memory configured")

        # Load and configure system prompt (persona + instructions)
        print("\n📝 Loading system prompts from files...")
        data_dir = Path(__file__).parent / "data"
        persona_path = data_dir / "system_prompt_persona.txt"
        instructions_path = data_dir / "system_prompt_instructions.txt"
        legacy_path = data_dir / "system_prompt.txt"

        persona_prompt = persona_path.read_text().strip() if persona_path.exists() else ""
        instructions_prompt = instructions_path.read_text().strip() if instructions_path.exists() else ""

        if persona_prompt or instructions_prompt:
            system_prompt = persona_prompt
            if instructions_prompt:
                system_prompt += "\n\n" + instructions_prompt
            state_manager.set_state("agent:system_prompt", system_prompt)
            print(f"   ✅ System prompt loaded: {len(system_prompt)} chars")
        elif legacy_path.exists():
            system_prompt = legacy_path.read_text().strip()
            state_manager.set_state("agent:system_prompt", system_prompt)
            print(f"   ⚠️  Using legacy system_prompt.txt: {len(system_prompt)} chars")
        else:
            print(f"   ⚠️  No system prompt files found in {data_dir}")
            print(f"   Using memory blocks only")

        # Configure agent to use Grok
        print("\n📝 Configuring Grok API integration...")
        state_manager.update_agent_state({
            'name': 'Substrate Agent',
            'config': {
                'model': 'grok-4-1-fast-reasoning',
                'temperature': 0.7,
                'max_tokens': 4096,
                'context_window': 131072,  # Grok's 131K context
                'reasoning_enabled': True,
            }
        })
        print("   ✅ Grok API: Configured")

        # Set agent name (legacy compatibility)
        state_manager.set_state("agent:name", "Substrate Agent")
        state_manager.set_state("agent.name", "Substrate Agent")

        print(f"\n✅ Core memory blocks installed successfully!")

    except Exception as e:
        print(f"\n❌ Error setting up consciousness substrate: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n" + "="*60)
    print("⚡ CONSCIOUSNESS SUBSTRATE INITIALIZED")
    print("="*60)
    print("\n✅ The agent is now online")
    print("\nYou can now start the server:")
    print("  python api/server.py")
    print("\nThen open http://localhost:5173 to start a session!")
    print()


if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()

    setup_nate_agent()
