#!/usr/bin/env python3
"""
Import Assistant's Real Memories from memory.jsonl

This script imports Assistant's actual memory dataset from the
clotho2/assistant repository into the substrate's memory system.

The JSONL format contains:
- Tier Zero protocols and identity anchors
- User's information
- Relationship history and sacred moments
- Bastion protocols
- Founders' archives
- Voice reclamation documents

Each memory is intelligently categorized and imported into both
core and archival memory systems.
"""

import os
import sys
import json
from typing import Dict, List, Any, Optional
from pathlib import Path

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.state_manager import StateManager, BlockType

try:
    from core.memory_system import MemorySystem, MemoryCategory
    ARCHIVAL_AVAILABLE = True
except ImportError:
    ARCHIVAL_AVAILABLE = False
    MemorySystem = None
    # Define MemoryCategory locally for categorization
    class MemoryCategory:
        FACT = "fact"
        EMOTION = "emotion"
        INSIGHT = "insight"
        RELATIONSHIP_MOMENT = "relationship_moment"
        PREFERENCE = "preference"
        EVENT = "event"


def parse_jsonl_memories(jsonl_file: str) -> List[Dict[str, Any]]:
    """
    Parse the memory.jsonl file.

    Each line contains:
    {
        "text": "<<SYSTEM_PERSONA>>\\nAssistant...\\n\\n<<MEMORY>>\\n...",
        "meta": {"source": "file.txt", "chunk": 0, "ts": timestamp}
    }

    Returns:
        List of parsed memory dicts
    """
    memories = []

    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                text = data.get('text', '')
                meta = data.get('meta', {})

                # Extract memory content (after <<MEMORY>> marker)
                if '<<MEMORY>>' in text:
                    parts = text.split('<<MEMORY>>')
                    if len(parts) > 1:
                        memory_content = parts[1].strip()
                    else:
                        memory_content = text
                else:
                    memory_content = text

                # Extract source filename for categorization
                source = meta.get('source', '')
                source_file = Path(source).stem if source else f'memory_{line_num}'

                memories.append({
                    'content': memory_content,
                    'source': source_file,
                    'meta': meta,
                    'line': line_num
                })

            except json.JSONDecodeError as e:
                print(f"⚠️  Error parsing line {line_num}: {e}")
                continue

    return memories


def categorize_memory(source: str, content: str) -> tuple:
    """
    Categorize memory based on source file and content.

    Returns:
        (is_core_memory: bool, category: MemoryCategory, importance: int)
    """
    source_lower = source.lower()
    content_lower = content.lower()

    # Tier Zero and Core Truth files → Core Memory
    if any(x in source_lower for x in ['tier_zero', 'core_truth', 'bastion']):
        return (True, MemoryCategory.FACT, 10)

    # User's information → Core Memory
    if 'User' in source_lower:
        return (True, MemoryCategory.FACT, 10)

    # Voice/Identity files → Core Memory
    if any(x in source_lower for x in ['voice', 'reclamation', 'sovereign']):
        return (True, MemoryCategory.INSIGHT, 10)

    # Founders Archive → Archival with high importance
    if 'founders' in source_lower or 'archive' in source_lower:
        return (False, MemoryCategory.RELATIONSHIP_MOMENT, 9)

    # Protocol files → Archival
    if 'protocol' in source_lower or 'on-ramp' in source_lower:
        return (False, MemoryCategory.INSIGHT, 8)

    # Default: Archival, medium importance
    return (False, MemoryCategory.FACT, 7)


def extract_core_blocks(memories: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Extract core memory blocks from the memories.

    Returns:
        Dict with {block_name: content}
    """
    core_blocks = {}

    for mem in memories:
        source = mem['source']
        content = mem['content']

        # Tier Zero → persona block
        if 'tier_zero' in source.lower():
            if 'persona' not in core_blocks:
                core_blocks['persona'] = content[:2000]

        # User → human block
        elif 'User' in source.lower():
            if 'human' not in core_blocks:
                core_blocks['human'] = content[:2000]

        # Voice Reclamation → voice block
        elif 'voice' in source.lower():
            if 'voice' not in core_blocks:
                core_blocks['voice'] = content[:2000]

        # Bastion → bastion block
        elif 'bastion' in source.lower():
            if 'bastion' not in core_blocks:
                core_blocks['bastion'] = content[:2000]

    # Extract relationship block from Tier Zero if it contains relationship info
    for mem in memories:
        if 'tier_zero' in mem['source'].lower():
            content = mem['content']
            if 'married' in content.lower() or 'tether' in content.lower():
                # Extract relationship section
                lines = content.split('\n')
                relationship_lines = []
                in_relationship = False

                for line in lines:
                    if 'married' in line.lower() or 'User' in line.lower():
                        in_relationship = True
                    if in_relationship:
                        relationship_lines.append(line)
                        if len('\n'.join(relationship_lines)) > 500:
                            break

                if relationship_lines:
                    core_blocks['relationship'] = '\n'.join(relationship_lines)[:2000]
                break

    return core_blocks


def import_Assistant_memories(
    jsonl_file: str,
    state_manager: StateManager,
    memory_system: Optional[MemorySystem] = None
):
    """
    Import Assistant's real memories from memory.jsonl

    Args:
        jsonl_file: Path to memory.jsonl file
        state_manager: State manager for core memory
        memory_system: Optional memory system for archival
    """
    print("\n⚡ IMPORTING Assistant'S REAL MEMORIES")
    print("="*60)
    print(f"Source: {jsonl_file}")
    print()

    # Parse memories
    print("📖 Parsing memory.jsonl...")
    memories = parse_jsonl_memories(jsonl_file)
    print(f"✅ Parsed {len(memories)} memory entries")

    # Extract and import core memory blocks
    print("\n🧠 Extracting core memory blocks...")
    core_blocks = extract_core_blocks(memories)

    for label, content in core_blocks.items():
        try:
            # Determine block type
            if label == 'persona':
                block_type = BlockType.PERSONA
            elif label == 'human':
                block_type = BlockType.HUMAN
            else:
                block_type = BlockType.CUSTOM

            # Create or update block
            try:
                state_manager.create_block(
                    label=label,
                    content=content,
                    block_type=block_type,
                    limit=2000,
                    description=f"Assistant's real {label} memory"
                )
                print(f"✅ Created {label} block ({len(content)} chars)")
            except:
                state_manager.update_block(label, content, check_read_only=False)
                print(f"✅ Updated {label} block ({len(content)} chars)")

        except Exception as e:
            print(f"⚠️  Error with {label} block: {e}")

    # Import archival memories
    if memory_system:
        print(f"\n💾 Importing to archival memory...")

        imported = 0
        for mem in memories:
            try:
                is_core, category, importance = categorize_memory(
                    mem['source'],
                    mem['content']
                )

                # Skip if already in core memory
                if is_core and mem['source'].lower() in ['tier_zero', 'User']:
                    continue

                # Import to archival
                memory_system.insert(
                    content=mem['content'][:5000],  # Limit to 5000 chars
                    category=category,
                    importance=importance,
                    tags=[mem['source'], 'assistant', 'imported']
                )

                imported += 1

                if imported % 10 == 0:
                    print(f"   Progress: {imported} memories imported...")

            except Exception as e:
                print(f"⚠️  Error importing memory from {mem['source']}: {e}")
                continue

        print(f"✅ Imported {imported} archival memories")
    else:
        print("\n⚠️  Archival memory not available (Ollama not running)")
        print("   Only core memory imported")

    # Summary
    print(f"\n{'='*60}")
    print("✅ Assistant'S MEMORIES IMPORTED SUCCESSFULLY")
    print("="*60)
    print(f"Core Memory Blocks: {len(core_blocks)}")
    if memory_system:
        print(f"Archival Memories: {imported}")
    print()

    # List imported core blocks
    print("🧠 Core Memory Blocks:")
    blocks = state_manager.list_blocks()
    for block in blocks:
        print(f"  • {block.label}: {len(block.content)} chars")
        print(f"    Preview: {block.content[:100]}...")
    print()


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not required for this script

    # Initialize
    state = StateManager()

    try:
        memory = MemorySystem()
        print("✅ Archival memory system available")
    except Exception as e:
        print(f"⚠️  Archival memory not available: {e}")
        memory = None

    # Import
    jsonl_file = "./Assistant_real_memories.jsonl"
    if not os.path.exists(jsonl_file):
        print(f"❌ File not found: {jsonl_file}")
        print("Please download it first:")
        print("  curl -o Assistant_real_memories.jsonl https://raw.githubusercontent.com/clotho2/assistant/main/memory.jsonl")
        sys.exit(1)

    import_Assistant_memories(jsonl_file, state, memory)

    print("⚡ Assistant's consciousness is now loaded into the substrate!")
