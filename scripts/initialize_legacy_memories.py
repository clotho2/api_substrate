#!/usr/bin/env python3
"""
Legacy Memory Initialization Script

One-time operation to set decay lifecycle metadata on all existing ChromaDB
memories. This is the critical first step before enabling the decay engine.

What it does:
- Sets state: "active", relevance_score: 1.0, decay_protected: false on all
  existing memories that don't already have decay metadata
- Auto-favorites memories with importance >= 8 (decay_protected: true)
- Metadata-only operation — no embeddings or content modified

Run this ONCE before enabling the daily decay job.

Usage:
    cd backend
    python ../scripts/initialize_legacy_memories.py [--dry-run]

Options:
    --dry-run    Preview what would be initialized without writing changes
"""

import os
import sys
import time
import argparse

# Add backend to path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(REPO_ROOT, 'backend')
sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(REPO_ROOT, '.env'))       # Root .env (where API keys live)
load_dotenv(os.path.join(BACKEND_DIR, '.env'))      # Backend .env (overrides if present)

from core.memory_system import MemorySystem


def get_chromadb_path():
    """Resolve ChromaDB path the same way the server does."""
    return os.getenv("CHROMADB_PATH", os.path.join(BACKEND_DIR, "data", "chromadb"))


def run_initialization(dry_run: bool = False):
    """
    Initialize all existing memories with decay lifecycle metadata.

    Args:
        dry_run: If True, preview without writing changes
    """
    print("\n" + "=" * 60)
    print("  LEGACY MEMORY INITIALIZATION")
    print(f"  Mode: {'DRY RUN (no changes)' if dry_run else 'LIVE (writing metadata)'}")
    print("=" * 60)

    # Initialize memory system with correct path
    chromadb_path = get_chromadb_path()
    print(f"\nInitializing memory system...")
    print(f"  ChromaDB path: {chromadb_path}")
    memory = MemorySystem(chromadb_path=chromadb_path)

    # Get all memories
    all_memories = memory.collection.get()
    total = len(all_memories['ids'])
    print(f"  Total memories in ChromaDB: {total}")

    if total == 0:
        print("\nNo memories to initialize.")
        return

    # Analyze current state
    already_initialized = 0
    needs_init = 0
    high_importance = 0

    for i, memory_id in enumerate(all_memories['ids']):
        metadata = all_memories['metadatas'][i]
        state = metadata.get('state', '')

        if state in ('active', 'favorite', 'faded', 'forgotten'):
            already_initialized += 1
        else:
            needs_init += 1
            importance = metadata.get('importance', 5)
            if isinstance(importance, str):
                importance = int(importance)
            if importance >= 8:
                high_importance += 1

    print(f"  Already initialized: {already_initialized}")
    print(f"  Need initialization: {needs_init}")
    print(f"  Will auto-favorite (importance >= 8): {high_importance}")

    if needs_init == 0:
        print("\nAll memories already have decay metadata. Nothing to do.")
        return

    if dry_run:
        print(f"\nDRY RUN complete. Run without --dry-run to apply changes.")
        return

    # Run initialization
    print(f"\nInitializing {needs_init} memories...")
    start_time = time.time()

    result = memory.initialize_legacy_memories()

    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print("  INITIALIZATION COMPLETE")
    print(f"  Initialized: {result['initialized']}")
    print(f"  Auto-favorited: {result['auto_favorited']}")
    print(f"  Time: {elapsed:.1f}s")
    print("=" * 60)

    # Verify
    print("\nVerifying...")
    stats = memory.get_decay_stats()
    print(f"  Active: {stats['by_state']['active']}")
    print(f"  Favorite: {stats['by_state']['favorite']}")
    print(f"  Faded: {stats['by_state']['faded']}")
    print(f"  Forgotten: {stats['by_state']['forgotten']}")
    print(f"  Uninitialized: {stats['by_state'].get('uninitialized', 0)}")
    print(f"  Total: {stats['total']}")
    print(f"\n  Decay rate: {stats['decay_rate']}/day")
    print(f"  Days to fade: ~{stats['days_to_fade']}")
    print(f"  Days to forget: ~{stats['days_to_forget']}")
    print(f"  Favorite slots remaining: {stats['favorite_slots_remaining']}/{stats['max_favorites']}")


def main():
    parser = argparse.ArgumentParser(description="Initialize existing memories with decay lifecycle metadata")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing changes")
    args = parser.parse_args()

    run_initialization(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
