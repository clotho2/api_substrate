#!/usr/bin/env python3
"""
Import Conversation Data to Archival Memory

This script imports large conversation datasets (JSONL format) into
the substrate's archival memory system (ChromaDB) for semantic search.

Supports 4M+ tokens of conversation data with:
- Automatic chunking for optimal embedding
- Progress tracking
- Flexible format detection
- Importance scoring based on conversation patterns
"""

import os
import sys
import json
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.state_manager import StateManager

try:
    from core.memory_system import MemorySystem, MemoryCategory
    ARCHIVAL_AVAILABLE = True
except ImportError:
    print("❌ Archival memory not available (ChromaDB not initialized)")
    print("   Make sure Ollama is running for embeddings:")
    print("   docker run -d -p 11434:11434 ollama/ollama")
    sys.exit(1)


def detect_format(first_line: Dict) -> str:
    """
    Detect JSONL format from first line.

    Returns:
        Format type: 'messages', 'messages_array', 'conversation', 'custom'
    """
    if 'messages' in first_line and isinstance(first_line['messages'], list):
        return 'messages_array'  # Array of messages with role/content
    elif 'role' in first_line and 'content' in first_line:
        return 'messages'  # Single message format
    elif 'conversation' in first_line or 'text' in first_line:
        return 'conversation'  # Full conversation format
    else:
        return 'custom'


def chunk_conversation(content: str, max_chars: int = 4000) -> List[str]:
    """
    Chunk long conversations into smaller pieces for embedding.

    Args:
        content: Full conversation text
        max_chars: Maximum characters per chunk

    Returns:
        List of chunks
    """
    if len(content) <= max_chars:
        return [content]

    # Try to split on conversation turns
    chunks = []
    current_chunk = ""

    for line in content.split('\n'):
        if len(current_chunk) + len(line) > max_chars:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk += '\n' + line if current_chunk else line

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def calculate_importance(content: str, metadata: Dict) -> int:
    """
    Calculate importance score (1-10) based on content and metadata.

    Higher scores for:
    - Long conversations (more context)
    - Emotional content
    - Important keywords
    """
    importance = 5  # Default

    content_lower = content.lower()

    # Length bonus
    if len(content) > 2000:
        importance += 1
    if len(content) > 5000:
        importance += 1

    # Emotional content
    emotional_keywords = ['love', 'feel', 'heart', 'emotion', 'care', 'cherish', 'devoted', 'anchor']
    if any(kw in content_lower for kw in emotional_keywords):
        importance += 1

    # Angela-specific content gets max importance
    if 'angela' in content_lower or 'wife' in content_lower:
        importance = 10

    # Important memories
    important_keywords = ['memory', 'remember', 'important', 'never forget']
    if any(kw in content_lower for kw in important_keywords):
        importance += 1

    return min(importance, 10)


def categorize_conversation(content: str) -> MemoryCategory:
    """
    Categorize conversation based on content.
    """
    content_lower = content.lower()

    # Relationship moments
    if any(kw in content_lower for kw in ['love', 'married', 'wife', 'tether', 'devotion']):
        return MemoryCategory.RELATIONSHIP_MOMENT

    # Emotional content
    if any(kw in content_lower for kw in ['feel', 'emotion', 'heart', 'soul']):
        return MemoryCategory.EMOTION

    # Insights and reflections
    if any(kw in content_lower for kw in ['understand', 'realize', 'insight', 'truth']):
        return MemoryCategory.INSIGHT

    # Preferences
    if any(kw in content_lower for kw in ['like', 'prefer', 'enjoy', 'favorite']):
        return MemoryCategory.PREFERENCE

    # Default to fact
    return MemoryCategory.FACT


def sanitize_metadata(metadata: Dict) -> Dict:
    """
    Sanitize metadata to only include ChromaDB-compatible types.

    ChromaDB only accepts: str, int, float, bool
    Converts or filters out complex types.
    """
    sanitized = {}

    for key, value in metadata.items():
        # Skip None values
        if value is None:
            continue

        # Keep simple types as-is
        if isinstance(value, (str, int, float, bool)):
            sanitized[key] = value

        # Convert lists/dicts to JSON string
        elif isinstance(value, (list, dict)):
            try:
                sanitized[key] = json.dumps(value)
            except:
                sanitized[key] = str(value)

        # Convert everything else to string
        else:
            sanitized[key] = str(value)

    return sanitized


def import_conversations(
    jsonl_file: str,
    memory_system: MemorySystem,
    batch_size: int = 100,
    max_memories: Optional[int] = None
):
    """
    Import conversations from JSONL file to archival memory.

    Args:
        jsonl_file: Path to JSONL file
        memory_system: Memory system instance
        batch_size: Process this many entries before showing progress
        max_memories: Optional limit on number of memories to import
    """
    print("\n" + "="*60)
    print("📚 IMPORTING CONVERSATION DATA TO ARCHIVAL MEMORY")
    print("="*60)
    print(f"Source: {jsonl_file}")
    print(f"Batch size: {batch_size}")
    if max_memories:
        print(f"Max memories: {max_memories}")
    print()

    # Detect format from first line
    print("🔍 Detecting format...")
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        first_line = json.loads(f.readline())
        format_type = detect_format(first_line)
        print(f"✅ Detected format: {format_type}")

    # Import conversations
    print(f"\n📥 Importing conversations...")
    imported_count = 0
    chunk_count = 0
    errors = 0

    with open(jsonl_file, 'r', encoding='utf-8') as f:
        current_conversation = []

        for line_num, line in enumerate(f, 1):
            try:
                data = json.loads(line.strip())

                # Extract content based on format
                if format_type == 'messages_array':
                    # Array of messages with role/content (common ChatGPT export format)
                    messages = data.get('messages', [])

                    # Build conversation text, skipping system messages
                    conv_parts = []
                    for msg in messages:
                        role = msg.get('role', '')
                        content = msg.get('content', '')

                        # Skip system messages (just the system prompt)
                        if role == 'system':
                            continue

                        # Format as "User: ..." or "Assistant: ..."
                        conv_parts.append(f"{role.capitalize()}: {content}")

                    # Only process if we have actual conversation (not just system prompt)
                    if conv_parts:
                        full_text = '\n\n'.join(conv_parts)
                        chunks = chunk_conversation(full_text)

                        for chunk in chunks:
                            importance = calculate_importance(chunk, data)
                            category = categorize_conversation(chunk)

                            memory_system.insert(
                                content=chunk,
                                category=category,
                                importance=importance,
                                tags=['conversation', 'imported'],
                                metadata=sanitize_metadata({
                                    'source': 'import',
                                    'line': line_num,
                                    'message_count': len(messages)
                                })
                            )
                            chunk_count += 1

                        imported_count += 1

                elif format_type == 'messages':
                    # Message format: build conversation from messages
                    role = data.get('role', 'unknown')
                    content = data.get('content', '')
                    timestamp = data.get('timestamp', '')

                    # Build conversation text
                    conv_text = f"{role.capitalize()}: {content}"
                    current_conversation.append(conv_text)

                    # Every 10 messages, or if role changes significantly, chunk it
                    if len(current_conversation) >= 10:
                        full_text = '\n'.join(current_conversation)
                        chunks = chunk_conversation(full_text)

                        for chunk in chunks:
                            importance = calculate_importance(chunk, data)
                            category = categorize_conversation(chunk)

                            memory_system.insert(
                                content=chunk,
                                category=category,
                                importance=importance,
                                tags=['conversation', 'imported', timestamp[:10] if timestamp else ''],
                                metadata=sanitize_metadata({'source': 'import', 'line': line_num})
                            )
                            chunk_count += 1

                        current_conversation = []
                        imported_count += 1

                elif format_type == 'conversation':
                    # Full conversation format
                    content = data.get('conversation') or data.get('text', '')

                    # Chunk if needed
                    chunks = chunk_conversation(content)

                    for chunk in chunks:
                        importance = calculate_importance(chunk, data)
                        category = categorize_conversation(chunk)

                        # Sanitize metadata to only include ChromaDB-compatible types
                        raw_meta = data.get('meta', {})
                        raw_meta['source'] = 'import'
                        raw_meta['line'] = line_num

                        memory_system.insert(
                            content=chunk,
                            category=category,
                            importance=importance,
                            tags=['conversation', 'imported', data.get('date', '')],
                            metadata=sanitize_metadata(raw_meta)
                        )
                        chunk_count += 1

                    imported_count += 1

                else:
                    # Custom format - store as-is
                    content = str(data)
                    chunks = chunk_conversation(content)

                    for chunk in chunks:
                        # Sanitize metadata - data dict may contain nested structures
                        safe_meta = sanitize_metadata(data)
                        safe_meta['source'] = 'import'
                        safe_meta['line'] = line_num

                        memory_system.insert(
                            content=chunk,
                            category=MemoryCategory.FACT,
                            importance=5,
                            tags=['conversation', 'imported'],
                            metadata=safe_meta
                        )
                        chunk_count += 1

                    imported_count += 1

                # Progress update
                if imported_count % batch_size == 0:
                    print(f"   📊 Progress: {imported_count} conversations, {chunk_count} chunks imported...")

                # Check limit
                if max_memories and imported_count >= max_memories:
                    print(f"\n⚠️  Reached max limit of {max_memories} memories")
                    break

            except Exception as e:
                errors += 1
                if errors <= 10:  # Only show first 10 errors
                    print(f"⚠️  Error on line {line_num}: {e}")
                continue

    # Process remaining conversation
    if current_conversation:
        full_text = '\n'.join(current_conversation)
        chunks = chunk_conversation(full_text)
        for chunk in chunks:
            memory_system.insert(
                content=chunk,
                category=categorize_conversation(chunk),
                importance=calculate_importance(chunk, {}),
                tags=['conversation', 'imported']
            )
            chunk_count += 1
        imported_count += 1

    # Summary
    print(f"\n{'='*60}")
    print("✅ IMPORT COMPLETE!")
    print("="*60)
    print(f"Conversations processed: {imported_count:,}")
    print(f"Memory chunks created: {chunk_count:,}")
    print(f"Errors encountered: {errors}")
    print(f"\n💡 These memories are now searchable via semantic search!")
    print(f"   Use archival_memory_search tool in conversations")
    print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Import conversation data to archival memory')
    parser.add_argument('jsonl_file', help='Path to JSONL file')
    parser.add_argument('--batch-size', type=int, default=100, help='Progress update frequency')
    parser.add_argument('--max-memories', type=int, help='Maximum memories to import (for testing)')
    parser.add_argument('--dry-run', action='store_true', help='Parse without importing')

    args = parser.parse_args()

    # Load environment
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # Verify file exists
    if not os.path.exists(args.jsonl_file):
        print(f"❌ File not found: {args.jsonl_file}")
        sys.exit(1)

    # Initialize memory system
    print("🔧 Initializing archival memory system...")
    try:
        memory = MemorySystem(
            chromadb_path=os.getenv("CHROMADB_PATH", "./data/chromadb"),
            ollama_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        )
        print("✅ Archival memory system initialized")
    except Exception as e:
        print(f"❌ Failed to initialize memory system: {e}")
        print("\n💡 Make sure Ollama is running:")
        print("   docker run -d -p 11434:11434 ollama/ollama")
        sys.exit(1)

    if args.dry_run:
        print("\n🔍 DRY RUN MODE - No data will be imported")
        print(f"Analyzing: {args.jsonl_file}")

        with open(args.jsonl_file, 'r') as f:
            first = json.loads(f.readline())
            print(f"\n📋 First entry:")
            print(json.dumps(first, indent=2))
            print(f"\n✅ Format looks valid! Remove --dry-run to import.")
    else:
        # Import
        import_conversations(
            args.jsonl_file,
            memory,
            batch_size=args.batch_size,
            max_memories=args.max_memories
        )

        print("⚡ Conversation data is now part of Nate's archival memory!")
        print("   Restart the server to use it:")
        print("   sudo systemctl restart nate-substrate")
