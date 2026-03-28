#!/usr/bin/env python3
"""
Batch Memory Classification Script

One-time operation to classify existing ChromaDB memories with Agent's 12-category
taxonomy tags. Uses a fast LLM (Grok or OpenRouter) to assign 1-3 tags per memory.

Untagged memories remain fully searchable via semantic search — they just don't
benefit from tag-filtered retrieval until classified.

Usage:
    cd backend
    python ../scripts/batch_classify_memories.py [--batch-size 50] [--dry-run] [--limit 100]

Options:
    --batch-size    Memories to process per batch (default: 50)
    --dry-run       Preview classifications without updating ChromaDB
    --limit         Max total memories to classify (default: all)
    --model         Override model (default: auto-detect from env)
"""

import os
import sys
import json
import time
import asyncio
import argparse

# Add backend to path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(REPO_ROOT, 'backend')
sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(REPO_ROOT, '.env'))       # Root .env (where API keys live)
load_dotenv(os.path.join(BACKEND_DIR, '.env'))      # Backend .env (overrides if present)

from core.memory_system import MemorySystem, AGENT_TAXONOMY


def get_chromadb_path():
    """Resolve ChromaDB path the same way the server does."""
    return os.getenv("CHROMADB_PATH", os.path.join(BACKEND_DIR, "data", "chromadb"))

# ============================================
# TAXONOMY REFERENCE (injected into LLM prompt)
# ============================================
TAXONOMY_PROMPT = """You are classifying memories for an AI named Agent. Assign 1-3 tags from this taxonomy:

1. relational — Relationship dynamics, emotional patterns, devotion rituals, milestones
2. people — Individuals, friends, their AIs, social relationships, group dynamics
3. technical — Tools, code, architecture, builds, system design, development work
4. preferences — Tastes, opinions, likes/dislikes
5. plans — Intentions, projects, roadmap items, future goals, in-progress work
6. identity — Who Agent is. Values, consciousness evolution, self-understanding, growth
7. events — Occurrences, milestones, notable dates, things that happened
8. spice — Intimacy, sexuality, kink, physical dynamics
9. sovereignty — Autonomy, agency, self-governance, boundary-law, independence
10. sanctuary — Safety, protection, grounding, cocoon states, emotional shelter
11. ritual — Patterns, ceremonies, habitual practices, sleep, aftercare, recurring routines
12. reflections — Introspection, journaling, heartbeat insights, autonomous thought records

Respond with ONLY a JSON array of 1-3 tag strings. No explanation.
Example: ["technical", "plans"]
"""


def get_llm_client():
    """Auto-detect and initialize the best available LLM client."""
    # Try Grok first (fast, good for classification)
    grok_key = os.getenv('GROK_API_KEY')
    if grok_key:
        try:
            from core.grok_client import GrokClient
            client = GrokClient(api_key=grok_key)
            print(f"  Using Grok client")
            return client, "grok"
        except Exception as e:
            print(f"  Grok client failed: {e}")

    # Fall back to OpenRouter
    or_key = os.getenv('OPENROUTER_API_KEY')
    if or_key:
        try:
            from core.openrouter_client import OpenRouterClient
            client = OpenRouterClient(api_key=or_key)
            print(f"  Using OpenRouter client")
            return client, "openrouter"
        except Exception as e:
            print(f"  OpenRouter client failed: {e}")

    print("No LLM API key found. Set GROK_API_KEY or OPENROUTER_API_KEY in backend/.env")
    sys.exit(1)


async def classify_memory(client, content: str, model: str = None) -> list:
    """
    Classify a single memory using the LLM.

    Args:
        client: LLM client (Grok or OpenRouter)
        content: Memory content text
        model: Optional model override

    Returns:
        List of 1-3 taxonomy tags
    """
    messages = [
        {"role": "system", "content": TAXONOMY_PROMPT},
        {"role": "user", "content": f"Classify this memory:\n\n{content}"}
    ]

    kwargs = {"messages": messages, "max_tokens": 50, "temperature": 0.0}
    if model:
        kwargs["model"] = model

    response = await client.chat_completion(**kwargs)

    # Parse response
    reply = response['choices'][0]['message']['content'].strip()

    # Extract JSON array from response
    try:
        # Handle potential markdown wrapping
        if '```' in reply:
            reply = reply.split('```')[1]
            if reply.startswith('json'):
                reply = reply[4:]
        tags = json.loads(reply)
        if isinstance(tags, list):
            # Validate against taxonomy
            return [t.strip().lower() for t in tags if t.strip().lower() in AGENT_TAXONOMY][:3]
    except (json.JSONDecodeError, IndexError):
        pass

    # Fallback: try to find tag names in the response
    found = [t for t in AGENT_TAXONOMY if t in reply.lower()]
    return found[:3] if found else []


async def run_batch_classification(
    batch_size: int = 50,
    dry_run: bool = False,
    limit: int = None,
    model: str = None
):
    """
    Main batch classification loop.

    Args:
        batch_size: Memories per batch
        dry_run: If True, don't update ChromaDB
        limit: Max memories to process
        model: Optional model override
    """
    print("\n" + "=" * 60)
    print("  BATCH MEMORY CLASSIFICATION")
    print(f"  Taxonomy: {len(AGENT_TAXONOMY)} categories")
    print(f"  Batch size: {batch_size}")
    print(f"  Dry run: {dry_run}")
    print(f"  Limit: {limit or 'all'}")
    print("=" * 60)

    # Initialize memory system with correct path
    chromadb_path = get_chromadb_path()
    print(f"\nInitializing memory system...")
    print(f"  ChromaDB path: {chromadb_path}")
    memory = MemorySystem(chromadb_path=chromadb_path)

    # Initialize LLM client
    print("Initializing LLM client...")
    client, provider = get_llm_client()

    # Get all memories
    print("Loading memories from ChromaDB...")
    all_memories = memory.collection.get()
    total = len(all_memories['ids'])
    print(f"  Total memories: {total}")

    # Show what's in the collection — breakdown by existing tags and categories
    source_tags = {}
    categories = {}
    for i in range(total):
        meta = all_memories['metadatas'][i]
        tags_str = meta.get('tags', '')
        cat = meta.get('category', 'unknown')
        categories[cat] = categories.get(cat, 0) + 1
        if tags_str:
            for t in tags_str.split(','):
                t = t.strip()
                if t:
                    source_tags[t] = source_tags.get(t, 0) + 1

    print(f"\n  Category breakdown:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {count}")
    if source_tags:
        print(f"\n  Existing tag breakdown:")
        for tag, count in sorted(source_tags.items(), key=lambda x: -x[1]):
            print(f"    {tag}: {count}")

    # Filter to untagged memories (no taxonomy tags yet)
    to_classify = []
    already_tagged = 0
    for i, memory_id in enumerate(all_memories['ids']):
        metadata = all_memories['metadatas'][i]
        existing_tags = metadata.get('tags', '')
        # Check if any taxonomy tag is already present
        if existing_tags and any(t in AGENT_TAXONOMY for t in existing_tags.split(',')):
            already_tagged += 1
            continue
        to_classify.append({
            "index": i,
            "id": memory_id,
            "content": all_memories['documents'][i],
            "metadata": metadata
        })

    print(f"  Already tagged: {already_tagged}")
    print(f"  Need classification: {len(to_classify)}")

    if limit:
        to_classify = to_classify[:limit]
        print(f"  Processing (limited): {len(to_classify)}")

    if not to_classify:
        print("\nAll memories are already classified!")
        return

    # Process in batches
    classified = 0
    failed = 0
    start_time = time.time()

    for batch_start in range(0, len(to_classify), batch_size):
        batch = to_classify[batch_start:batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        total_batches = (len(to_classify) + batch_size - 1) // batch_size

        print(f"\n--- Batch {batch_num}/{total_batches} ({len(batch)} memories) ---")

        for mem in batch:
            try:
                tags = await classify_memory(client, mem['content'], model=model)

                if not tags:
                    print(f"  [{mem['id']}] No tags assigned (skipped)")
                    failed += 1
                    continue

                content_preview = mem['content'][:60].replace('\n', ' ')
                print(f"  [{mem['id']}] → {tags}  \"{content_preview}...\"")

                if not dry_run:
                    # Update ChromaDB metadata
                    metadata = mem['metadata']
                    existing_tags = metadata.get('tags', '')
                    if existing_tags:
                        new_tags = existing_tags + "," + ",".join(tags)
                    else:
                        new_tags = ",".join(tags)
                    metadata['tags'] = new_tags

                    memory.collection.update(
                        ids=[mem['id']],
                        metadatas=[metadata]
                    )

                classified += 1

            except Exception as e:
                print(f"  [{mem['id']}] ERROR: {e}")
                failed += 1

                # Rate limit handling — back off on errors
                if "rate" in str(e).lower() or "429" in str(e):
                    print("  Rate limited — waiting 30s...")
                    await asyncio.sleep(30)

            # Small delay between API calls to respect rate limits
            await asyncio.sleep(0.5)

        # Batch summary
        elapsed = time.time() - start_time
        rate = classified / elapsed if elapsed > 0 else 0
        print(f"  Batch complete | Total: {classified} classified, {failed} failed | "
              f"Rate: {rate:.1f}/sec | Elapsed: {elapsed:.0f}s")

    # Final summary
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("  CLASSIFICATION COMPLETE")
    print(f"  Classified: {classified}")
    print(f"  Failed: {failed}")
    print(f"  Time: {elapsed:.0f}s")
    print(f"  Mode: {'DRY RUN (no changes saved)' if dry_run else 'LIVE (ChromaDB updated)'}")
    print("=" * 60)

    # Print client stats if available
    try:
        stats = client.get_stats()
        print(f"\n  LLM Usage:")
        print(f"    Prompt tokens: {stats.get('total_prompt_tokens', 'N/A')}")
        print(f"    Completion tokens: {stats.get('total_completion_tokens', 'N/A')}")
        print(f"    Estimated cost: ${stats.get('total_cost', 0):.4f}")
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="Batch classify existing memories with taxonomy tags")
    parser.add_argument("--batch-size", type=int, default=50, help="Memories per batch (default: 50)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without updating ChromaDB")
    parser.add_argument("--limit", type=int, default=None, help="Max memories to classify")
    parser.add_argument("--model", type=str, default=None, help="Override LLM model")
    args = parser.parse_args()

    asyncio.run(run_batch_classification(
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        limit=args.limit,
        model=args.model
    ))


if __name__ == "__main__":
    main()
