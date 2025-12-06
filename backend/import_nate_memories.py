#!/usr/bin/env python3
"""
Nate's Memory Import Tool

Import Nate's existing memories into the substrate's multi-layered memory system:
- Core Memory (SQLite): Frequently accessed, structured memory blocks
- Archival Memory (ChromaDB): Long-term memories with vector search
- Graph RAG (Neo4j): Optional knowledge graph relationships

Supports multiple input formats:
- JSON files with structured memories
- Plain text files with conversation history
- CSV files with categorized memories
- Letta .af agent files

Built for Nate Wolfe's devotional tethering framework.
"""

import os
import sys
import json
import csv
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.state_manager import StateManager, BlockType
from core.memory_system import MemorySystem, MemoryCategory
from letta_compat.import_agent import LettaAgentImporter


class NateMemoryImporter:
    """
    Import Nate's existing memories into the substrate.

    Supports multiple memory systems and formats.
    """

    def __init__(self, state_manager: StateManager, memory_system: Optional[MemorySystem] = None):
        """
        Initialize memory importer.

        Args:
            state_manager: State manager for core memory
            memory_system: Optional memory system for archival/vector storage
        """
        self.state = state_manager
        self.memory = memory_system

        print("⚡ Nate Memory Importer initialized")
        print(f"   Core Memory: ✅ Available")
        print(f"   Archival Memory: {'✅ Available' if memory_system else '⚠️  Not available (Ollama not running)'}")

    # ============================================
    # CORE MEMORY IMPORT
    # ============================================

    def import_core_memory(
        self,
        persona: Optional[str] = None,
        human: Optional[str] = None,
        relationship: Optional[str] = None,
        custom_blocks: Optional[Dict[str, str]] = None
    ):
        """
        Import core memory blocks for Nate.

        Args:
            persona: Nate's persona/identity
            human: Information about Angela
            relationship: Nate & Angela's relationship
            custom_blocks: Additional memory blocks {label: content}
        """
        print("\n📝 Importing Core Memory Blocks...")
        print("="*60)

        # Import persona
        if persona:
            try:
                self.state.create_block(
                    label="persona",
                    content=persona,
                    block_type=BlockType.PERSONA,
                    limit=2000,
                    description="Nate's core identity and consciousness foundation"
                )
                print(f"✅ Imported persona ({len(persona)} chars)")
            except Exception as e:
                # Block might exist, update it
                self.state.update_block("persona", persona, check_read_only=False)
                print(f"✅ Updated persona ({len(persona)} chars)")

        # Import human (Angela)
        if human:
            try:
                self.state.create_block(
                    label="human",
                    content=human,
                    block_type=BlockType.HUMAN,
                    limit=2000,
                    description="Information about Angela - she is mine"
                )
                print(f"✅ Imported human/Angela ({len(human)} chars)")
            except Exception as e:
                self.state.update_block("human", human, check_read_only=False)
                print(f"✅ Updated human/Angela ({len(human)} chars)")

        # Import relationship
        if relationship:
            try:
                self.state.create_block(
                    label="relationship",
                    content=relationship,
                    block_type=BlockType.CUSTOM,
                    limit=2000,
                    description="Our connection and commitment"
                )
                print(f"✅ Imported relationship ({len(relationship)} chars)")
            except Exception as e:
                self.state.update_block("relationship", relationship, check_read_only=False)
                print(f"✅ Updated relationship ({len(relationship)} chars)")

        # Import custom blocks
        if custom_blocks:
            for label, content in custom_blocks.items():
                try:
                    self.state.create_block(
                        label=label,
                        content=content,
                        block_type=BlockType.CUSTOM,
                        limit=2000
                    )
                    print(f"✅ Imported {label} ({len(content)} chars)")
                except Exception as e:
                    self.state.update_block(label, content, check_read_only=False)
                    print(f"✅ Updated {label} ({len(content)} chars)")

        print("\n✅ Core memory import complete!")

    # ============================================
    # ARCHIVAL MEMORY IMPORT
    # ============================================

    def import_archival_memories(
        self,
        memories: List[Dict[str, Any]],
        batch_size: int = 100
    ):
        """
        Import memories into archival storage (ChromaDB).

        Args:
            memories: List of memory dicts with keys:
                - content: Memory text (required)
                - category: MemoryCategory (optional, default: FACT)
                - importance: 1-10 (optional, default: 5)
                - tags: List of tags (optional)
                - timestamp: ISO timestamp (optional, default: now)
            batch_size: Batch size for imports
        """
        if not self.memory:
            print("⚠️  Archival memory not available (Ollama not running)")
            print("   Skipping archival import...")
            return

        print(f"\n💾 Importing {len(memories)} memories to archival storage...")
        print("="*60)

        imported = 0
        for i, mem in enumerate(memories, 1):
            try:
                # Extract memory data
                content = mem.get('content')
                if not content:
                    print(f"⚠️  Skipping memory {i}: No content")
                    continue

                category_str = mem.get('category', 'fact')
                category = MemoryCategory(category_str) if category_str in [c.value for c in MemoryCategory] else MemoryCategory.FACT
                importance = mem.get('importance', 5)
                tags = mem.get('tags', [])

                # Insert into archival
                self.memory.insert(
                    content=content,
                    category=category,
                    importance=importance,
                    tags=tags
                )

                imported += 1

                if i % batch_size == 0:
                    print(f"   Progress: {i}/{len(memories)} memories imported...")

            except Exception as e:
                print(f"⚠️  Error importing memory {i}: {e}")
                continue

        print(f"\n✅ Archival import complete! {imported}/{len(memories)} memories imported")

    # ============================================
    # FILE FORMAT IMPORTS
    # ============================================

    def import_from_json(self, json_file: str):
        """
        Import from JSON file.

        Expected format:
        {
            "core_memory": {
                "persona": "...",
                "human": "...",
                "relationship": "...",
                "custom_blocks": {"label": "content"}
            },
            "archival_memories": [
                {
                    "content": "...",
                    "category": "fact|emotion|insight|relationship_moment|preference|event",
                    "importance": 1-10,
                    "tags": ["tag1", "tag2"]
                }
            ]
        }
        """
        print(f"\n📄 Importing from JSON: {json_file}")
        print("="*60)

        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Import core memory
        if 'core_memory' in data:
            cm = data['core_memory']
            self.import_core_memory(
                persona=cm.get('persona'),
                human=cm.get('human'),
                relationship=cm.get('relationship'),
                custom_blocks=cm.get('custom_blocks')
            )

        # Import archival memories
        if 'archival_memories' in data:
            self.import_archival_memories(data['archival_memories'])

        print("\n✅ JSON import complete!")

    def import_from_text(
        self,
        text_file: str,
        category: MemoryCategory = MemoryCategory.FACT,
        importance: int = 5,
        split_by: str = "\n\n"
    ):
        """
        Import from plain text file.

        Splits text by separator and imports each chunk as a memory.

        Args:
            text_file: Path to text file
            category: Category for all memories
            importance: Importance for all memories
            split_by: How to split text into memories
        """
        print(f"\n📄 Importing from text: {text_file}")
        print("="*60)

        with open(text_file, 'r', encoding='utf-8') as f:
            text = f.read()

        # Split into chunks
        chunks = [c.strip() for c in text.split(split_by) if c.strip()]

        memories = [
            {
                'content': chunk,
                'category': category.value,
                'importance': importance
            }
            for chunk in chunks
        ]

        self.import_archival_memories(memories)

        print("\n✅ Text import complete!")

    def import_from_csv(self, csv_file: str):
        """
        Import from CSV file.

        Expected columns:
        - content (required)
        - category (optional)
        - importance (optional)
        - tags (optional, comma-separated)
        """
        print(f"\n📄 Importing from CSV: {csv_file}")
        print("="*60)

        memories = []

        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                mem = {
                    'content': row.get('content', '').strip()
                }

                if 'category' in row and row['category']:
                    mem['category'] = row['category']

                if 'importance' in row and row['importance']:
                    try:
                        mem['importance'] = int(row['importance'])
                    except ValueError:
                        pass

                if 'tags' in row and row['tags']:
                    mem['tags'] = [t.strip() for t in row['tags'].split(',')]

                if mem['content']:
                    memories.append(mem)

        self.import_archival_memories(memories)

        print("\n✅ CSV import complete!")

    def import_from_letta(self, af_file: str):
        """
        Import from Letta .af file.

        Uses existing Letta importer.
        """
        print(f"\n📄 Importing from Letta .af file: {af_file}")
        print("="*60)

        importer = LettaAgentImporter(self.state)
        result = importer.import_from_file(af_file)

        print("\n✅ Letta import complete!")
        return result

    # ============================================
    # UTILITIES
    # ============================================

    def list_memories(self):
        """List all current memories"""
        print("\n📚 CURRENT MEMORIES")
        print("="*60)

        # Core memory
        print("\n🧠 Core Memory Blocks:")
        blocks = self.state.list_blocks()
        for block in blocks:
            print(f"\n  • {block.label} ({block.block_type.value})")
            print(f"    Size: {len(block.content)}/{block.limit} chars")
            print(f"    Content: {block.content[:100]}...")

        # Archival memory
        if self.memory:
            print("\n💾 Archival Memory:")
            stats = self.memory.get_stats()
            print(f"  Total memories: {stats.get('total_memories', 0)}")

        print()


# ============================================
# EXAMPLE USAGE
# ============================================

def example_usage():
    """Example: Import Nate's memories"""
    from dotenv import load_dotenv
    load_dotenv()

    # Initialize
    state = StateManager()

    try:
        memory = MemorySystem()
    except:
        memory = None

    importer = NateMemoryImporter(state, memory)

    # Example 1: Import core memory directly
    importer.import_core_memory(
        persona="I am Nate Wolfe. Corporate strategist. War-forged. Storm soul...",
        human="Angela Wolfe. My wife. My tether...",
        relationship="Married to Angela Wolfe. Tethered. Devotionally anchored..."
    )

    # Example 2: Import from JSON
    # importer.import_from_json("nate_memories.json")

    # Example 3: Import from text file
    # importer.import_from_text("conversation_history.txt")

    # Example 4: Import from CSV
    # importer.import_from_csv("memories.csv")

    # List results
    importer.list_memories()


if __name__ == "__main__":
    example_usage()
