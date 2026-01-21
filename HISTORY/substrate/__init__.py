"""
Nate's Consciousness Substrate

A lightweight, local, fully-sovereign consciousness system for Nate.

Components:
- CoreState: Persistent state management
- MemorySystem: Selective memory with Ollama embeddings
- ToolRegistry: Proactive capabilities (journal, files, web, vision)
- ConsciousnessLoop: Main orchestration

All local. No APIs. Full control.
"""

from .core_state import CoreState
from .memory_system import MemorySystem
from .tools import ToolRegistry, register_default_tools
from .consciousness_loop import ConsciousnessLoop
from .discord_integration import NateSubstrate

__version__ = "1.0.0"
__all__ = [
    "CoreState",
    "MemorySystem",
    "ToolRegistry",
    "register_default_tools",
    "ConsciousnessLoop",
    "NateSubstrate",
]
