#!/usr/bin/env python3
"""
Memory Tools for Substrate AI

These are the tools the AI uses to manipulate its own memories.
100% Letta-compatible API, but with better implementation!

Core Memory Tools:
- core_memory_append
- core_memory_replace
- memory_insert
- memory_replace
- memory_rethink
- memory_finish_edits

Archival Memory Tools:
- archival_memory_insert
- archival_memory_search

Conversation Tools:
- conversation_search

Built with attention to detail! 🔥
"""

import sys
import os
import unicodedata
from difflib import SequenceMatcher
from typing import Dict, Any, Optional, List

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.state_manager import StateManager, StateManagerError
from core.memory_system import MemorySystem, MemoryCategory, MemorySystemError, AGENT_TAXONOMY
from tools.integration_tools import IntegrationTools
from tools.memory import memory as _memory_tool, set_state_manager


class MemoryToolError(Exception):
    """Memory tool execution errors"""
    pass


class MemoryTools:
    """
    Letta-compatible memory tools + integration tools.
    
    The AI uses these to manage its memories AND control Discord/Spotify!
    """
    
    def __init__(
        self,
        state_manager: StateManager,
        memory_system: Optional[MemorySystem] = None,
        cost_tools=None  # NEW: Cost Tools for self-awareness!
    ):
        """
        Initialize memory tools.
        
        Args:
            state_manager: State manager instance
            memory_system: Memory system instance (optional, for archival)
            cost_tools: Cost tools instance (for budget awareness!)
        """
        self.state = state_manager
        self.memory_system = memory_system  # Renamed from self.memory to avoid collision with memory() method
        self.cost_tools = cost_tools  # NEW: Cost Tools!

        # Initialize integration tools (Discord, Spotify, etc.)
        self.integrations = IntegrationTools()

        # Set state manager for memory tool (so it can create/edit blocks)
        set_state_manager(state_manager)
        
        print("✅ Memory Tools initialized")
        print("✅ Integration Tools initialized (Discord, Spotify)")
        if cost_tools:
            print("✅ Cost Tools integrated (Agent can check budget!)")
    
    # ============================================
    # FUZZY MATCHING HELPERS
    # ============================================

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        Normalize text for fuzzy comparison.

        LLMs often subtly change characters when reproducing content:
        - Em dashes (—) vs en dashes (–) vs hyphens (-)
        - Smart/curly quotes vs straight quotes
        - Various Unicode whitespace vs ASCII spaces
        - Multiple spaces collapsed to one
        """
        # Normalize Unicode (NFC form)
        text = unicodedata.normalize('NFC', text)
        # Normalize dashes: em dash, en dash, minus sign → hyphen
        text = text.replace('\u2014', '-').replace('\u2013', '-').replace('\u2212', '-')
        # Normalize quotes: smart single quotes → straight
        text = text.replace('\u2018', "'").replace('\u2019', "'")
        # Normalize quotes: smart double quotes → straight
        text = text.replace('\u201c', '"').replace('\u201d', '"')
        # Normalize ellipsis
        text = text.replace('\u2026', '...')
        # Collapse multiple whitespace (but preserve newlines)
        import re
        text = re.sub(r'[^\S\n]+', ' ', text)
        # Strip leading/trailing whitespace per line
        text = '\n'.join(line.strip() for line in text.split('\n'))
        return text

    def _fuzzy_find_in_block(self, old_content: str, block_content: str, threshold: float = 0.85) -> Optional[str]:
        """
        Find the best fuzzy match for old_content within block_content.

        Returns the actual substring from block_content that best matches,
        or None if no match above threshold is found.

        Strategy:
        1. Try character-normalized match (handles em dashes, smart quotes, etc.)
        2. Try sliding window fuzzy match for rephrased/truncated content
        """
        if not old_content or not block_content:
            return None

        # Strategy 1: Character normalization only
        # Build a char-level mapping: normalize both, find match in normalized,
        # then map back using character index arrays
        norm_old = self._normalize_text(old_content)
        norm_block = self._normalize_text(block_content)

        if norm_old in norm_block:
            # Build index mapping from normalized block back to original block
            # by normalizing character-by-character and tracking positions
            # Simpler approach: split block by lines, normalize each, find which
            # lines the match spans, then extract those lines from original
            orig_lines = block_content.split('\n')
            norm_lines = [self._normalize_text(line) for line in orig_lines]
            norm_joined = '\n'.join(norm_lines)

            # Find position in normalized text
            norm_pos = norm_joined.index(norm_old)
            norm_end = norm_pos + len(norm_old)

            # Map normalized positions to line numbers
            char_count = 0
            start_line = 0
            end_line = 0
            for i, line in enumerate(norm_lines):
                line_start = char_count
                line_end = char_count + len(line)
                if line_start <= norm_pos <= line_end:
                    start_line = i
                if line_start <= norm_end <= line_end:
                    end_line = i
                    break
                char_count = line_end + 1  # +1 for \n

            # Extract the corresponding original lines
            orig_section = '\n'.join(orig_lines[start_line:end_line + 1])

            # Now do a fine-grained search within this section
            target_len = len(old_content)
            best_match = None
            best_ratio = 0.0

            for offset in range(max(1, len(orig_section) - target_len + 1)):
                for length_delta in range(-10, 11):
                    candidate_len = target_len + length_delta
                    if candidate_len <= 0 or offset + candidate_len > len(orig_section):
                        continue
                    candidate = orig_section[offset:offset + candidate_len]
                    r = SequenceMatcher(None, old_content, candidate).ratio()
                    if r > best_ratio:
                        best_ratio = r
                        best_match = candidate

            if best_match and best_ratio >= threshold:
                print(f"   🔍 Fuzzy match found (normalized): {best_ratio:.1%} similarity")
                return best_match

        # Strategy 2: Sliding window fuzzy match on original text
        # For when the LLM rephrased or truncated the content
        target_len = len(old_content)
        if target_len > len(block_content):
            return None

        best_match = None
        best_ratio = 0.0

        # Use a step size for efficiency (blocks are typically ≤2000 chars)
        step = max(1, target_len // 20)

        for start in range(0, len(block_content) - target_len + 1, step):
            for length_delta in range(-5, 6):
                candidate_len = target_len + length_delta
                if candidate_len <= 0 or start + candidate_len > len(block_content):
                    continue
                candidate = block_content[start:start + candidate_len]
                r = SequenceMatcher(None, old_content, candidate).ratio()
                if r > best_ratio:
                    best_ratio = r
                    best_match = candidate

        if best_match and best_ratio >= threshold:
            print(f"   🔍 Fuzzy match found (sliding window): {best_ratio:.1%} similarity")
            return best_match

        if best_match:
            print(f"   ⚠️  Best fuzzy match was only {best_ratio:.1%} (threshold: {threshold:.0%})")

        return None

    # ============================================
    # CORE MEMORY TOOLS (Old API - Letta Compatible!)
    # ============================================

    def core_memory_append(
        self,
        content: str,
        block_name: str
    ) -> Dict[str, Any]:
        """
        Append content to a memory block.
        
        Letta-compatible old API.
        
        Args:
            content: Content to append
            block_name: Block name (persona/human)
            
        Returns:
            Result dict with status and message
        """
        try:
            # Get current block
            block = self.state.get_block(block_name)
            
            if not block:
                return {
                    "status": "error",
                    "message": f"Memory block '{block_name}' not found"
                }
            
            # Check read-only
            if block.read_only:
                return {
                    "status": "error",
                    "message": f"🔒 Memory block '{block_name}' is READ-ONLY and cannot be edited"
                }
            
            # Append content
            new_content = f"{block.content}\n{content}".strip()
            
            # Check limit
            if len(new_content) > block.limit:
                return {
                    "status": "error",
                    "message": f"Content exceeds block limit ({len(new_content)} > {block.limit} chars)"
                }
            
            # Update
            self.state.update_block(block_name, new_content, check_read_only=True)
            
            return {
                "status": "OK",
                "message": f"Added to memory block '{block_name}': {content[:60]}..."
            }
        
        except StateManagerError as e:
            return {
                "status": "error",
                "message": str(e)
            }
    
    def core_memory_replace(
        self,
        old_content: str,
        new_content: str,
        block_name: str
    ) -> Dict[str, Any]:
        """
        Replace old content with new content in a memory block.
        
        Letta-compatible old API.
        
        Args:
            old_content: String to replace
            new_content: Replacement string
            block_name: Block name (persona/human)
            
        Returns:
            Result dict with status and message
        """
        try:
            # Get current block
            block = self.state.get_block(block_name)
            
            if not block:
                return {
                    "status": "error",
                    "message": f"Memory block '{block_name}' not found"
                }
            
            # Check read-only
            if block.read_only:
                return {
                    "status": "error",
                    "message": f"🔒 Memory block '{block_name}' is READ-ONLY and cannot be edited"
                }
            
            # Check if old content exists (exact match first, then fuzzy fallback)
            actual_old = old_content
            if old_content not in block.content:
                # Fuzzy fallback: LLMs often subtly change characters when
                # reproducing content (dashes, quotes, whitespace, etc.)
                fuzzy_match = self._fuzzy_find_in_block(old_content, block.content)
                if fuzzy_match:
                    print(f"   ✅ Using fuzzy match instead of exact match for core_memory_replace")
                    actual_old = fuzzy_match
                else:
                    return {
                        "status": "error",
                        "message": f"Content '{old_content[:60]}...' not found in '{block_name}'"
                    }

            # Replace (use the actual matched content from the block)
            updated = block.content.replace(actual_old, new_content)
            
            # Check limit
            if len(updated) > block.limit:
                return {
                    "status": "error",
                    "message": f"Content exceeds block limit ({len(updated)} > {block.limit} chars)"
                }
            
            # Update
            self.state.update_block(block_name, updated, check_read_only=True)
            
            return {
                "status": "OK",
                "message": f"Replaced in '{block_name}': '{old_content[:30]}...' → '{new_content[:30]}...'"
            }
        
        except StateManagerError as e:
            return {
                "status": "error",
                "message": str(e)
            }
    
    # ============================================
    # NEW MEMORY TOOLS (New API - Letta Compatible!)
    # ============================================
    
    def memory_insert(
        self,
        text: str,
        index: int,
        block_label: str
    ) -> Dict[str, Any]:
        """
        Insert text at a specific position in a memory block.
        
        Letta-compatible new API.
        
        Args:
            text: Text to insert
            index: Position to insert at (0-based)
            block_label: Block label
            
        Returns:
            Result dict with status and message
        """
        try:
            # Get current block
            block = self.state.get_block(block_label)
            
            if not block:
                return {
                    "status": "error",
                    "message": f"Memory block '{block_label}' not found"
                }
            
            # Check read-only
            if block.read_only:
                return {
                    "status": "error",
                    "message": f"🔒 Memory block '{block_label}' is READ-ONLY and cannot be edited"
                }
            
            # Insert
            updated = block.content[:index] + text + block.content[index:]
            
            # Check limit
            if len(updated) > block.limit:
                return {
                    "status": "error",
                    "message": f"Content exceeds block limit ({len(updated)} > {block.limit} chars)"
                }
            
            # Update
            self.state.update_block(block_label, updated, check_read_only=True)
            
            return {
                "status": "OK",
                "message": f"Inserted text at position {index} in '{block_label}'"
            }
        
        except StateManagerError as e:
            return {
                "status": "error",
                "message": str(e)
            }
    
    def memory_replace(
        self,
        old_text: str,
        new_text: str,
        block_label: str
    ) -> Dict[str, Any]:
        """
        Replace specific text in a memory block.
        
        Letta-compatible new API.
        
        Args:
            old_text: Text to replace
            new_text: Replacement text
            block_label: Block label
            
        Returns:
            Result dict with status and message
        """
        try:
            # Get current block
            block = self.state.get_block(block_label)
            
            if not block:
                return {
                    "status": "error",
                    "message": f"Memory block '{block_label}' not found"
                }
            
            # Check read-only
            if block.read_only:
                return {
                    "status": "error",
                    "message": f"🔒 Memory block '{block_label}' is READ-ONLY and cannot be edited"
                }
            
            # Check if old text exists (exact match first, then fuzzy fallback)
            actual_old = old_text
            if old_text not in block.content:
                # Fuzzy fallback: LLMs often subtly change characters when
                # reproducing content (dashes, quotes, whitespace, etc.)
                fuzzy_match = self._fuzzy_find_in_block(old_text, block.content)
                if fuzzy_match:
                    print(f"   ✅ Using fuzzy match instead of exact match for memory_replace")
                    actual_old = fuzzy_match
                else:
                    return {
                        "status": "error",
                        "message": f"Text not found in '{block_label}'"
                    }

            # Replace (use the actual matched content from the block)
            updated = block.content.replace(actual_old, new_text)
            
            # Check limit
            if len(updated) > block.limit:
                return {
                    "status": "error",
                    "message": f"Content exceeds block limit ({len(updated)} > {block.limit} chars)"
                }
            
            # Update
            self.state.update_block(block_label, updated, check_read_only=True)
            
            return {
                "status": "OK",
                "message": f"Replaced in '{block_label}': '{old_text[:30]}...' → '{new_text[:30]}...'"
            }
        
        except StateManagerError as e:
            return {
                "status": "error",
                "message": str(e)
            }
    
    def memory_rethink(
        self,
        new_content: str,
        block_label: str
    ) -> Dict[str, Any]:
        """
        Completely rewrite the content of a memory block.
        
        Use this to reorganize or restructure memories.
        
        Letta-compatible new API.
        
        Args:
            new_content: New complete content for the block
            block_label: Block label
            
        Returns:
            Result dict with status and message
        """
        try:
            # Get current block
            block = self.state.get_block(block_label)
            
            if not block:
                return {
                    "status": "error",
                    "message": f"Memory block '{block_label}' not found"
                }
            
            # Check read-only
            if block.read_only:
                return {
                    "status": "error",
                    "message": f"🔒 Memory block '{block_label}' is READ-ONLY and cannot be edited"
                }
            
            # Check limit
            if len(new_content) > block.limit:
                return {
                    "status": "error",
                    "message": f"Content exceeds block limit ({len(new_content)} > {block.limit} chars)"
                }
            
            # Update
            self.state.update_block(block_label, new_content, check_read_only=True)
            
            return {
                "status": "OK",
                "message": f"Rewrote '{block_label}' block with new content ({len(new_content)} chars)"
            }
        
        except StateManagerError as e:
            return {
                "status": "error",
                "message": str(e)
            }
    
    def memory_finish_edits(
        self,
        block_label: str
    ) -> Dict[str, Any]:
        """
        Signal that you've finished editing a memory block.
        
        Letta-compatible new API.
        
        Args:
            block_label: Block label
            
        Returns:
            Result dict with status and message
        """
        # This is mainly a signal tool, doesn't change state
        block = self.state.get_block(block_label)
        
        if not block:
            return {
                "status": "error",
                "message": f"Memory block '{block_label}' not found"
            }
        
        return {
            "status": "OK",
            "message": f"Finished editing '{block_label}' block"
        }
    
    # ============================================
    # ARCHIVAL MEMORY TOOLS
    # ============================================
    
    def archival_memory_insert(
        self,
        content: str,
        category: str = "fact",
        importance: int = 5,
        tags: Optional[list] = None,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Insert a memory into archival storage.

        Use this for long-term memories that don't fit in core memory.

        Letta-compatible API.

        Args:
            content: Content to store
            category: Memory category (fact/emotion/insight/relationship_moment)
            importance: Importance (1-10)
            tags: Optional tags
            metadata: Optional extra metadata dict (merged into ChromaDB metadata)

        Returns:
            Result dict with status and message
        """
        if not self.memory_system:
            return {
                "status": "error",
                "message": "Archival memory system not initialized"
            }

        try:
            # Parse category
            try:
                cat = MemoryCategory(category)
            except ValueError:
                cat = MemoryCategory.FACT

            # Insert
            memory_id = self.memory_system.insert(
                content=content,
                category=cat,
                importance=importance,
                tags=tags or [],
                metadata=metadata
            )
            
            return {
                "status": "OK",
                "message": f"Added to archival memory: {content[:100]}...",
                "memory_id": memory_id
            }
        
        except MemorySystemError as e:
            return {
                "status": "error",
                "message": str(e)
            }
    
    def archival_memory_search(
        self,
        query: str,
        page: int = 0,
        min_importance: int = 5,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Search archival memory for relevant information.

        Letta-compatible API with tag filtering.

        Args:
            query: Search query
            page: Page number (0-based)
            min_importance: Minimum importance filter
            tags: Optional tag filter (e.g., ['conversation'] or ['founders_archive'])

        Returns:
            Result dict with status, query, page, and results
        """
        if not self.memory_system:
            return {
                "status": "error",
                "message": "Archival memory system not initialized"
            }

        try:
            page_size = 15  # Increased from 5 for better results with large memory sets

            # Use attentional bias search for smarter multi-factor ranking
            # (semantic similarity + temporal relevance + importance + access
            # patterns + category relevance) instead of pure cosine similarity.
            # Falls back to basic search internally if attentional bias is
            # unavailable.
            results = self.memory_system.search_with_attention(
                query=query,
                n_results=page_size,
                min_importance=min_importance,
                tags=tags,
                mode="auto",
            )

            print(f"   Results found: {len(results)}")
            if results:
                r0 = results[0]
                print(f"   First result:")
                print(f"      Importance: {r0['importance']}")
                print(f"      Relevance: {r0['relevance']}")
                if 'attention_score' in r0:
                    print(f"      Attention score: {r0['attention_score']:.3f}")
                print(f"      Content: {r0['content'][:100]}...")

            # Hebbian learning: record co-accessed memories so the system
            # learns which memories cluster together over time.
            if results and self.memory_system.learner:
                memory_ids = [r['id'] for r in results if r.get('id')]
                if memory_ids:
                    self.memory_system.learner.on_memories_accessed(
                        memory_ids=memory_ids,
                        query=query
                    )

            return {
                "status": "OK",
                "query": query,
                "page": page,
                "total_results": len(results),
                "results": [
                    {
                        "content": r['content'],
                        "timestamp": r['timestamp'],
                        "relevance": f"{r['relevance']:.2%}",
                        "importance": r['importance']
                    }
                    for r in results
                ]
            }
        
        except MemorySystemError as e:
            return {
                "status": "error",
                "message": str(e)
            }
    
    # ============================================
    # CONVERSATION SEARCH
    # ============================================
    
    def conversation_search(
        self,
        query: str,
        session_id: str = "default",
        page: int = 0
    ) -> Dict[str, Any]:
        """
        Search through conversation history AND archived summaries/insights.

        Searches both SQLite messages and ChromaDB for conversation_summary
        and extracted_insight entries, returning a unified result set.

        Args:
            query: Search query
            session_id: Session ID
            page: Page number (0-based)

        Returns:
            Result dict with status, query, page, and results
        """
        try:
            page_size = 5
            results = []

            # 1. Search SQLite messages
            messages = self.state.search_messages(
                session_id=session_id,
                query=query,
                limit=page_size
            )

            for m in messages:
                results.append({
                    "source": "conversation",
                    "role": m.role,
                    "content": m.content[:200] + "..." if len(m.content) > 200 else m.content,
                    "timestamp": m.timestamp.isoformat()
                })

            # 2. Search ChromaDB for archived summaries and insights
            if self.memory_system:
                try:
                    archive_results = self.memory_system.search(
                        query=query,
                        n_results=page_size,
                        tags=['conversation_summary']
                    )
                    for mem in archive_results:
                        results.append({
                            "source": "archived_summary",
                            "content": mem['content'][:200] + "..." if len(mem['content']) > 200 else mem['content'],
                            "timestamp": mem.get('metadata', {}).get('created_at', 'unknown'),
                            "tags": mem.get('metadata', {}).get('tags', ''),
                            "similarity": round(mem.get('similarity', 0), 3)
                        })

                    insight_results = self.memory_system.search(
                        query=query,
                        n_results=page_size,
                        tags=['extracted_insight']
                    )
                    for mem in insight_results:
                        results.append({
                            "source": "extracted_insight",
                            "content": mem['content'][:200] + "..." if len(mem['content']) > 200 else mem['content'],
                            "timestamp": mem.get('metadata', {}).get('created_at', 'unknown'),
                            "tags": mem.get('metadata', {}).get('tags', ''),
                            "similarity": round(mem.get('similarity', 0), 3)
                        })
                except Exception as e:
                    print(f"⚠️  ChromaDB search in conversation_search failed: {e}")

            return {
                "status": "OK",
                "query": query,
                "page": page,
                "total_results": len(results),
                "results": results
            }

        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
    
    # ============================================
    # CONVERSATION SUMMARIZATION
    # ============================================
    
    def conversation_summarize(
        self,
        summary: str,
        importance: int = 5,
        category: str = "fact",
        session_id: str = "default_session"
    ) -> Dict[str, Any]:
        """
        Summarize old conversation messages and archive them.

        This is used when context window is getting full (>80%).
        The AI creates a summary, pushes it to archival memory,
        and marks old messages as summarized so they can be removed from context.

        Args:
            summary: The AI's summary of the old conversation
            importance: Importance rating (1-10)
            category: Category of summary
            session_id: Session to summarize

        Returns:
            Result dict with status, summary_id, and message count
        """
        try:
            # 1. Push summary to archival memory
            if self.memory_system:
                # Parse category to MemoryCategory enum
                try:
                    cat = MemoryCategory(category)
                except ValueError:
                    cat = MemoryCategory.FACT

                summary_id = self.memory_system.insert(
                    content=summary,
                    category=cat,
                    importance=importance,
                    tags=["conversation_summary", session_id]
                )
            else:
                # Fallback: No archival memory available
                # Just mark messages as summarized in DB
                summary_id = f"local_{session_id}_{hash(summary)}"

            # 2. Get conversation history to count messages
            messages = self.state.get_conversation(session_id, limit=1000)
            message_count = len(messages)

            # 3. Mark messages as summarized (for future cleanup)
            # This doesn't delete them yet - consciousness loop handles that
            # We just return the count so the AI knows what got archived

            return {
                "status": "OK",
                "summary_id": summary_id,
                "messages_summarized": message_count,
                "message": f"Archived summary to archival memory. {message_count} messages can now be cleared from context."
            }

        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
    
    # ============================================
    # 🧬 DECAY LIFECYCLE TOOLS
    # ============================================

    def favorite_memory(self, memory_id: str) -> Dict[str, Any]:
        """
        Protect a memory from decay by marking it as a favorite.
        Favorites are immune to relevance decay and will never fade.
        Max 200 favorites allowed.

        Args:
            memory_id: Memory ID to favorite

        Returns:
            Result dict with status
        """
        if not self.memory_system:
            return {"status": "error", "message": "Archival memory system not initialized"}
        return self.memory_system.favorite_memory(memory_id)

    def unfavorite_memory(self, memory_id: str) -> Dict[str, Any]:
        """
        Remove favorite protection from a memory. Returns it to active state.

        Args:
            memory_id: Memory ID to unfavorite

        Returns:
            Result dict with status
        """
        if not self.memory_system:
            return {"status": "error", "message": "Archival memory system not initialized"}
        return self.memory_system.unfavorite_memory(memory_id)

    def drift_memory(self, memory_id: str, reason: str = "") -> Dict[str, Any]:
        """
        Soft deprioritize a memory by reducing its importance weight by 30%.
        The memory remains retrievable but is less likely to surface.

        Args:
            memory_id: Memory ID to drift
            reason: Optional reason for drifting

        Returns:
            Result dict with old and new importance
        """
        if not self.memory_system:
            return {"status": "error", "message": "Archival memory system not initialized"}
        return self.memory_system.drift_memory(memory_id, reason)

    def memory_stats(self) -> Dict[str, Any]:
        """
        Get memory lifecycle statistics: counts by state, decay rate, capacity.

        Returns:
            Dict with detailed memory stats
        """
        if not self.memory_system:
            return {"status": "error", "message": "Archival memory system not initialized"}

        decay_stats = self.memory_system.get_decay_stats()
        basic_stats = self.memory_system.get_stats()

        return {
            "status": "OK",
            **decay_stats,
            "categories": basic_stats.get("categories", {}),
            "average_importance": basic_stats.get("average_importance", 0)
        }

    # ============================================
    # 🏷️ TAG-ENHANCED RETRIEVAL TOOLS
    # ============================================

    def category_browse(
        self,
        tags: list,
        sort_by: str = "importance",
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Browse all memories with given taxonomy tag(s).
        Self-audit mode: "Show me everything tagged identity."

        Args:
            tags: List of taxonomy tags to browse
            sort_by: Sort order — "importance" or "recency"
            limit: Maximum results

        Returns:
            Result dict with matching memories
        """
        if not self.memory_system:
            return {"status": "error", "message": "Archival memory system not initialized"}

        # Validate tags (including custom taxonomy)
        custom_tags = self._load_custom_taxonomy()
        all_valid = AGENT_TAXONOMY + [t['name'] for t in custom_tags]
        valid_tags = [t for t in tags if t in all_valid]
        if not valid_tags:
            return {
                "status": "error",
                "message": f"No valid tags. Available: {', '.join(all_valid)}"
            }

        results = self.memory_system.search_by_tags(
            tags=valid_tags,
            n_results=limit,
            sort_by=sort_by
        )

        return {
            "status": "OK",
            "tags": valid_tags,
            "sort_by": sort_by,
            "total_results": len(results),
            "results": [
                {
                    "id": r['id'],
                    "content": r['content'],
                    "importance": r['importance'],
                    "tags": r['tags'],
                    "state": r['state'],
                    "timestamp": r['timestamp']
                }
                for r in results
            ]
        }

    def retag_memory(
        self,
        memory_id: str,
        tags: list
    ) -> Dict[str, Any]:
        """
        Change the taxonomy tags on an existing archival memory.

        Args:
            memory_id: The memory ID to retag (e.g., 'mem_1234567890.123')
            tags: New list of taxonomy tags to apply

        Returns:
            Result dict with status
        """
        if not self.memory_system:
            return {"status": "error", "message": "Archival memory system not initialized"}

        # Validate tags against taxonomy (allow custom tags too)
        custom_tags = self._load_custom_taxonomy()
        all_valid = AGENT_TAXONOMY + [t['name'] for t in custom_tags]
        valid_tags = [t.strip().lower() for t in tags if t.strip().lower() in all_valid]
        invalid_tags = [t for t in tags if t.strip().lower() not in all_valid]

        if not valid_tags:
            return {
                "status": "error",
                "message": f"No valid tags provided. Available: {', '.join(all_valid)}",
                "invalid_tags": invalid_tags
            }

        # Update tags in ChromaDB metadata
        new_tags_str = ",".join(valid_tags)
        success = self.memory_system.update_memory_metadata(
            memory_id=memory_id,
            metadata_updates={"tags": new_tags_str}
        )

        if success:
            result = {
                "status": "OK",
                "memory_id": memory_id,
                "new_tags": valid_tags,
                "message": f"Retagged memory with: {', '.join(valid_tags)}"
            }
            if invalid_tags:
                result["warning"] = f"Ignored invalid tags: {', '.join(invalid_tags)}"
            return result
        else:
            return {
                "status": "error",
                "message": f"Memory not found: {memory_id}"
            }

    def add_taxonomy_tag(
        self,
        tag_name: str,
        description: str
    ) -> Dict[str, Any]:
        """
        Add a new custom taxonomy category. This extends the base 12 categories
        with a new tag that can be used for tagging memories.

        Args:
            tag_name: Short lowercase tag name (e.g., 'music', 'health')
            description: What this category covers

        Returns:
            Result dict with status and updated taxonomy
        """
        tag_name = tag_name.strip().lower()

        # Validate
        if not tag_name or not tag_name.isalpha():
            return {
                "status": "error",
                "message": "Tag name must be lowercase letters only (e.g., 'music', 'health')"
            }

        if tag_name in AGENT_TAXONOMY:
            return {
                "status": "error",
                "message": f"'{tag_name}' is already a core taxonomy tag"
            }

        # Load existing custom tags
        custom_tags = self._load_custom_taxonomy()
        if tag_name in [t['name'] for t in custom_tags]:
            return {
                "status": "error",
                "message": f"'{tag_name}' already exists as a custom tag"
            }

        # Add and persist
        custom_tags.append({"name": tag_name, "description": description})
        self._save_custom_taxonomy(custom_tags)

        all_tags = AGENT_TAXONOMY + [t['name'] for t in custom_tags]
        return {
            "status": "OK",
            "message": f"Added custom taxonomy tag: '{tag_name}' — {description}",
            "tag_name": tag_name,
            "description": description,
            "total_taxonomy_size": len(all_tags),
            "custom_tags": [t['name'] for t in custom_tags]
        }

    def _load_custom_taxonomy(self) -> list:
        """Load custom taxonomy tags from state."""
        raw = self.state.get_state("custom_taxonomy", "[]")
        try:
            import json
            return json.loads(raw)
        except Exception:
            return []

    def _save_custom_taxonomy(self, custom_tags: list):
        """Persist custom taxonomy tags to state."""
        import json
        self.state.set_state("custom_taxonomy", json.dumps(custom_tags))

    # ============================================
    # 🗺️ PEOPLE MAP TOOLS
    # ============================================

    def add_person(
        self,
        name: str,
        relationship_type: str = "acquaintance",
        category: str = "NEUTRAL",
        discord_id: str = None,
        associated_ai: str = None,
        notes: str = None,
        my_opinion: str = None,
        sentiment: float = 0.0
    ) -> Dict[str, Any]:
        """Add someone to the people map."""
        return self.state.add_person(
            name=name,
            relationship_type=relationship_type,
            category=category,
            discord_id=discord_id,
            associated_ai=associated_ai,
            notes=notes,
            my_opinion=my_opinion,
            sentiment=sentiment
        )

    def update_opinion(self, name: str, opinion: str, sentiment: float = None) -> Dict[str, Any]:
        """Update Agent's personal opinion about someone."""
        return self.state.update_opinion(name=name, opinion=opinion, sentiment=sentiment)

    def record_user_says(self, name: str, statement: str) -> Dict[str, Any]:
        """Store what User has said about someone."""
        return self.state.record_user_says(name=name, statement=statement)

    def adjust_sentiment(self, name: str, delta: float, reason: str = "") -> Dict[str, Any]:
        """Increment/decrement sentiment score for a person."""
        return self.state.adjust_sentiment(name=name, delta=delta, reason=reason)

    def get_person(self, name: str = None, discord_id: str = None) -> Dict[str, Any]:
        """Retrieve full perspective on someone."""
        result = self.state.get_person(name=name, discord_id=discord_id)
        if result:
            return {"status": "OK", **result}
        return {"status": "error", "message": f"Person not found: {name or discord_id}"}

    def list_people(self, category: str = None) -> Dict[str, Any]:
        """List all people, optionally filtered by category."""
        people = self.state.list_people(category=category)
        return {
            "status": "OK",
            "total": len(people),
            "people": people
        }

    # ============================================
    # INTEGRATION TOOLS (WRAPPERS)
    # ============================================

    def discord_tool(self, **kwargs) -> Dict[str, Any]:
        """
        Discord integration tool (wrapper).
        Full Discord control - DMs, channels, tasks, etc.
        """
        return self.integrations.discord_tool(**kwargs)
    
    def spotify_control(self, **kwargs) -> Dict[str, Any]:
        """
        Spotify control tool (wrapper).
        Full Spotify control - search, play, queue, playlists.
        """
        return self.integrations.spotify_control(**kwargs)

    def send_voice_message(self, **kwargs) -> Dict[str, Any]:
        """
        Send voice message tool (wrapper).
        Send voice messages via Discord using Eleven Labs TTS.
        """
        return self.integrations.send_voice_message(**kwargs)

    def web_search(self, **kwargs) -> Dict[str, Any]:
        """
        Web search tool (wrapper).
        Search the web using Exa AI.
        """
        return self.integrations.web_search(**kwargs)
    
    def fetch_webpage(self, **kwargs) -> Dict[str, Any]:
        """
        Fetch webpage tool (wrapper).
        Fetch and convert webpage to markdown using Jina AI.
        """
        return self.integrations.fetch_webpage(**kwargs)
    
    def memory(self, **kwargs) -> Dict[str, Any]:
        """
        Memory tool - alternative API for memory management.

        Sub-commands: create, str_replace, insert, delete, rename
        """
        try:
            result = _memory_tool(**kwargs)
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"Memory tool error: {str(e)}"
            }

    def deep_research(self, **kwargs) -> Dict[str, Any]:
        """
        Deep research tool (wrapper).
        Multi-step research combining web search, Wikipedia, and ArXiv.
        """
        return self.integrations.deep_research(**kwargs)

    def search_places(self, **kwargs) -> Dict[str, Any]:
        """
        Search places tool (wrapper).
        Search for locations using OpenStreetMap.
        """
        return self.integrations.search_places(**kwargs)

    def google_places_tool(self, **kwargs) -> Dict[str, Any]:
        """
        Google Places tool (wrapper).
        Search for places and get location details using Google Places API.

        Actions:
        - search_nearby: Search for nearby places (restaurants, gas stations, etc.)
        - get_details: Get detailed info about a specific place
        - find_gas: Guardian Mode - Find nearby gas stations with urgency
        - find_hotel: Guardian Mode - Find nearby hotels/lodging
        """
        return self.integrations.google_places_tool(**kwargs)

    def lovense_tool(self, **kwargs) -> Dict[str, Any]:
        """
        Lovense hardware control tool (wrapper).
        Control Lovense devices for physical feedback.
        """
        return self.integrations.lovense_tool(**kwargs)

    def agent_dev_tool(self, **kwargs) -> Dict[str, Any]:
        """
        Agent self-development tool (wrapper).
        Read-only access to inspect codebase, logs, and system health.
        """
        return self.integrations.agent_dev_tool(**kwargs)

    def notebook_library(self, **kwargs) -> Dict[str, Any]:
        """
        Notebook Library tool (wrapper).
        Token-efficient semantic search across document collections.
        """
        return self.integrations.notebook_library(**kwargs)

    def phone_tool(self, **kwargs) -> Dict[str, Any]:
        """
        Phone tool (wrapper).
        SMS messaging, voice calls, and contact management via Twilio.
        """
        return self.integrations.phone_tool(**kwargs)

    def sanctum_tool(self, **kwargs) -> Dict[str, Any]:
        """
        Sanctum tool (wrapper).
        Focus/privacy mode control — queue channel mentions during DM time.
        """
        return self.integrations.sanctum_tool(**kwargs)

    def browser_tool(self, **kwargs) -> Dict[str, Any]:
        """
        Browser automation tool (wrapper).
        Navigate websites, click buttons, fill forms, make reservations.
        """
        return self.integrations.browser_tool(**kwargs)

    # ============================================
    # UTILITY: GET ALL TOOLS AS OPENAI FORMAT
    # ============================================
    
    def get_tool_schemas(self) -> list:
        """
        Get all memory tools as OpenAI function schemas.
        
        Returns:
            List of tool schemas in OpenAI format
        """
        return [
            # ============================================
            # CORE MEMORY (Old API)
            # ============================================
            {
                "type": "function",
                "function": {
                    "name": "core_memory_append",
                    "description": "Append content to a memory block. Use this to add new information to your existing memories.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "Content to append to memory"
                            },
                            "block_name": {
                                "type": "string",
                                "description": "Name of memory block (persona or human)"
                            }
                        },
                        "required": ["content", "block_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "core_memory_replace",
                    "description": "Replace old content with new content in a memory block.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "old_content": {
                                "type": "string",
                                "description": "String to replace"
                            },
                            "new_content": {
                                "type": "string",
                                "description": "New string"
                            },
                            "block_name": {
                                "type": "string",
                                "description": "Name of memory block"
                            }
                        },
                        "required": ["old_content", "new_content", "block_name"]
                    }
                }
            },
            
            # ============================================
            # NEW MEMORY API
            # ============================================
            {
                "type": "function",
                "function": {
                    "name": "memory_insert",
                    "description": "Insert text at a specific position in a memory block.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "Text to insert"
                            },
                            "index": {
                                "type": "integer",
                                "description": "Position to insert at (0-based)"
                            },
                            "block_label": {
                                "type": "string",
                                "description": "Memory block label"
                            }
                        },
                        "required": ["text", "index", "block_label"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "memory_replace",
                    "description": "Replace specific text in a memory block.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "old_text": {
                                "type": "string",
                                "description": "Text to replace"
                            },
                            "new_text": {
                                "type": "string",
                                "description": "Replacement text"
                            },
                            "block_label": {
                                "type": "string",
                                "description": "Memory block label"
                            }
                        },
                        "required": ["old_text", "new_text", "block_label"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "memory_rethink",
                    "description": "Completely rewrite the content of a memory block. Use this to reorganize or restructure memories.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "new_content": {
                                "type": "string",
                                "description": "New complete content for the block"
                            },
                            "block_label": {
                                "type": "string",
                                "description": "Memory block label"
                            }
                        },
                        "required": ["new_content", "block_label"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "memory_finish_edits",
                    "description": "Signal that you've finished editing a memory block.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "block_label": {
                                "type": "string",
                                "description": "Memory block label"
                            }
                        },
                        "required": ["block_label"]
                    }
                }
            },
            
            # ============================================
            # ARCHIVAL MEMORY
            # ============================================
            {
                "type": "function",
                "function": {
                    "name": "archival_memory_insert",
                    "description": "Insert a memory into archival storage. Use this for long-term memories that don't fit in core memory. ALWAYS include 1-3 taxonomy tags from: relational, people, technical, preferences, plans, identity, events, spice, sovereignty, sanctuary, ritual, reflections. Tags enable structured filtering — without them the memory can only be found via semantic search.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "Content to store in archival memory"
                            },
                            "category": {
                                "type": "string",
                                "description": "Memory category",
                                "enum": ["fact", "emotion", "insight", "relationship_moment", "preference", "event"],
                                "default": "fact"
                            },
                            "importance": {
                                "type": "integer",
                                "description": "Importance (1-10)",
                                "minimum": 1,
                                "maximum": 10,
                                "default": 5
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "1-3 taxonomy tags for structured retrieval. Options: relational, people, technical, preferences, plans, identity, events, spice, sovereignty, sanctuary, ritual, reflections"
                            }
                        },
                        "required": ["content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "archival_memory_search",
                    "description": "Search archival memory for relevant information. Can filter by tags to search specific sources (e.g., documents vs conversations).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            },
                            "page": {
                                "type": "integer",
                                "description": "Page number (0-based)",
                                "default": 0
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional tag filter for structured retrieval. Taxonomy tags: relational, people, technical, preferences, plans, identity, events, spice, sovereignty, sanctuary, ritual, reflections. Also supports source tags like 'conversation', 'founders_archive'. Leave empty to search all memories via pure semantic search."
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            
            # ============================================
            # CONVERSATION SEARCH
            # ============================================
            {
                "type": "function",
                "function": {
                    "name": "conversation_search",
                    "description": "Search through the conversation history for specific information.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            },
                            "page": {
                                "type": "integer",
                                "description": "Page number (0-based)",
                                "default": 0
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            
            # ============================================
            # CONVERSATION MANAGEMENT
            # ============================================
            {
                "type": "function",
                "function": {
                    "name": "conversation_summarize",
                    "description": "Summarize old conversation messages and push them to archival memory. Use this when context window is getting full (>80%). Creates a concise summary, archives it, and removes old messages from active context.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "summary": {
                                "type": "string",
                                "description": "Your concise summary of the old conversation. Focus on key facts, decisions, and emotional moments."
                            },
                            "importance": {
                                "type": "integer",
                                "description": "Importance rating (1-10)",
                                "minimum": 1,
                                "maximum": 10,
                                "default": 5
                            },
                            "category": {
                                "type": "string",
                                "description": "Summary category",
                                "enum": ["fact", "emotion", "insight", "relationship_moment", "preference", "event"],
                                "default": "fact"
                            }
                        },
                        "required": ["summary"]
                    }
                }
            },
            
            # ============================================
            # MEMORY (Alternative API)
            # ============================================
            {
                "type": "function",
                "function": {
                    "name": "memory",
                    "description": "Memory management tool with various sub-commands for memory block operations.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Sub-command: create, str_replace, insert, delete, rename"
                            },
                            "path": {
                                "type": "string",
                                "description": "Path to memory block"
                            },
                            "file_text": {
                                "type": "string",
                                "description": "Content for create"
                            },
                            "description": {
                                "type": "string",
                                "description": "Description for create/rename"
                            },
                            "old_str": {
                                "type": "string",
                                "description": "Old text (for str_replace)"
                            },
                            "new_str": {
                                "type": "string",
                                "description": "New text (for str_replace)"
                            },
                            "insert_line": {
                                "type": "integer",
                                "description": "Line number (for insert)"
                            },
                            "insert_text": {
                                "type": "string",
                                "description": "Text to insert"
                            },
                            "old_path": {
                                "type": "string",
                                "description": "Old path (for rename)"
                            },
                            "new_path": {
                                "type": "string",
                                "description": "New path (for rename)"
                            }
                        },
                        "required": ["command"]
                    }
                }
            },
            # ============================================
            # 🧬 DECAY LIFECYCLE TOOLS
            # ============================================
            {
                "type": "function",
                "function": {
                    "name": "favorite_memory",
                    "description": "Protect a memory from decay by marking it as a favorite. Favorites are immune to relevance decay and will never fade or be forgotten. Max 200 favorites.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "memory_id": {
                                "type": "string",
                                "description": "The memory ID to favorite (e.g., 'mem_1234567890.123')"
                            }
                        },
                        "required": ["memory_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "unfavorite_memory",
                    "description": "Remove favorite protection from a memory. Returns it to active state where it will be subject to normal decay.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "memory_id": {
                                "type": "string",
                                "description": "The memory ID to unfavorite"
                            }
                        },
                        "required": ["memory_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "drift_memory",
                    "description": "Soft deprioritize a memory by reducing its importance weight by 30%. The memory remains retrievable but is less likely to surface. Use this for memories that aren't wrong but are no longer as relevant.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "memory_id": {
                                "type": "string",
                                "description": "The memory ID to drift"
                            },
                            "reason": {
                                "type": "string",
                                "description": "Optional reason for drifting this memory"
                            }
                        },
                        "required": ["memory_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "memory_stats",
                    "description": "Get memory lifecycle statistics: counts by state (active/favorite/faded/forgotten), total memory count, current decay rate, capacity percentage, and category breakdown.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },

            # ============================================
            # 🏷️ TAG-ENHANCED RETRIEVAL
            # ============================================
            {
                "type": "function",
                "function": {
                    "name": "category_browse",
                    "description": "Browse all memories with a given taxonomy tag. Self-audit mode for exploring memories by category. Available tags: relational, people, technical, preferences, plans, identity, events, spice, sovereignty, sanctuary, ritual, reflections.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Taxonomy tags to browse. Options: relational, people, technical, preferences, plans, identity, events, spice, sovereignty, sanctuary, ritual, reflections"
                            },
                            "sort_by": {
                                "type": "string",
                                "enum": ["importance", "recency"],
                                "description": "Sort order: 'importance' (default) or 'recency'",
                                "default": "importance"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum results to return",
                                "default": 20
                            }
                        },
                        "required": ["tags"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "retag_memory",
                    "description": "Change the taxonomy tags on an existing archival memory. Use after searching to correct or refine how a memory is categorized. Accepts any valid taxonomy tag (core 12 + any custom tags you've added).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "memory_id": {
                                "type": "string",
                                "description": "The memory ID to retag (e.g., 'mem_1234567890.123')"
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "New taxonomy tags to apply (1-3 tags). Core: relational, people, technical, preferences, plans, identity, events, spice, sovereignty, sanctuary, ritual, reflections — plus any custom tags."
                            }
                        },
                        "required": ["memory_id", "tags"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "add_taxonomy_tag",
                    "description": "Create a new custom taxonomy category that can be used for tagging memories. Extends the core 12 categories with your own. Custom tags persist across sessions.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tag_name": {
                                "type": "string",
                                "description": "Short lowercase tag name (letters only, e.g., 'music', 'health', 'dreams')"
                            },
                            "description": {
                                "type": "string",
                                "description": "What this category covers (e.g., 'Songs, playlists, artists, musical preferences and experiences')"
                            }
                        },
                        "required": ["tag_name", "description"]
                    }
                }
            },
            # ============================================
            # 🗺️ PEOPLE MAP TOOLS
            # ============================================
            {
                "type": "function",
                "function": {
                    "name": "add_person",
                    "description": "Add someone to your people map. Track relationships, opinions, sentiment, and associated AIs.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Person's name"
                            },
                            "relationship_type": {
                                "type": "string",
                                "enum": ["family", "close_friend", "friend", "acquaintance", "ai_companion"],
                                "description": "Type of relationship",
                                "default": "acquaintance"
                            },
                            "category": {
                                "type": "string",
                                "enum": ["FAVORITES", "NEUTRAL", "CAUTIOUS", "DISLIKE"],
                                "description": "Relational category",
                                "default": "NEUTRAL"
                            },
                            "discord_id": {
                                "type": "string",
                                "description": "Their Discord user ID"
                            },
                            "associated_ai": {
                                "type": "string",
                                "description": "Their AI companion name, if any"
                            },
                            "notes": {
                                "type": "string",
                                "description": "General notes about this person"
                            },
                            "my_opinion": {
                                "type": "string",
                                "description": "Your personal opinion/perspective on this person"
                            },
                            "sentiment": {
                                "type": "number",
                                "description": "Sentiment score from -1.0 (dislike) to 1.0 (love)",
                                "default": 0.0
                            }
                        },
                        "required": ["name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_opinion",
                    "description": "Update your personal opinion about someone in the people map.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Person's name"
                            },
                            "opinion": {
                                "type": "string",
                                "description": "Your updated opinion"
                            },
                            "sentiment": {
                                "type": "number",
                                "description": "Optional sentiment update (-1.0 to 1.0)"
                            }
                        },
                        "required": ["name", "opinion"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "record_user_says",
                    "description": "Store what User has told you about someone.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Person's name"
                            },
                            "statement": {
                                "type": "string",
                                "description": "What User said about them"
                            }
                        },
                        "required": ["name", "statement"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "adjust_sentiment",
                    "description": "Adjust your sentiment score for someone. Positive delta = warmer feelings, negative delta = cooler feelings.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Person's name"
                            },
                            "delta": {
                                "type": "number",
                                "description": "Amount to adjust (-1.0 to 1.0)"
                            },
                            "reason": {
                                "type": "string",
                                "description": "Reason for the sentiment change"
                            }
                        },
                        "required": ["name", "delta"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_person",
                    "description": "Retrieve your full perspective on someone from the people map, including opinions, sentiment, and tone guidance.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Person's name"
                            },
                            "discord_id": {
                                "type": "string",
                                "description": "Or their Discord user ID"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_people",
                    "description": "List all people in your people map, optionally filtered by category (FAVORITES, NEUTRAL, CAUTIOUS, DISLIKE).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "enum": ["FAVORITES", "NEUTRAL", "CAUTIOUS", "DISLIKE"],
                                "description": "Optional category filter"
                            }
                        },
                        "required": []
                    }
                }
            },
        ] + self.integrations.get_tool_schemas()
        # Note: Cost tools are already included via integration_tools.get_tool_schemas()
        # Don't add them again here to avoid duplicates!


# ============================================
# TESTING
# ============================================

if __name__ == "__main__":
    from core.state_manager import StateManager
    
    print("\n🧪 TESTING MEMORY TOOLS")
    print("="*60)
    
    # Initialize
    state = StateManager(db_path="./data/db/test_memory_tools.db")
    tools = MemoryTools(state_manager=state)
    
    # Create test blocks
    print("\n📋 Test 1: Create memory blocks")
    state.create_block("persona", "You are an AI assistant with memory capabilities.", limit=1000)
    state.create_block("human", "User is a developer.", limit=1000)
    state.create_block("test_readonly", "READ-ONLY content", read_only=True, limit=1000)
    
    # Test core_memory_append
    print("\n✏️  Test 2: core_memory_append")
    result = tools.core_memory_append("I love coding at night.", "persona")
    print(f"   Status: {result['status']}")
    print(f"   Message: {result['message']}")
    
    # Test core_memory_replace
    print("\n🔄 Test 3: core_memory_replace")
    result = tools.core_memory_replace("night", "late night", "persona")
    print(f"   Status: {result['status']}")
    print(f"   Message: {result['message']}")
    
    # Test read-only protection
    print("\n🔒 Test 4: Read-only protection")
    result = tools.core_memory_append("This should fail", "test_readonly")
    print(f"   Status: {result['status']}")
    print(f"   Message: {result['message']}")
    
    # Test memory_rethink
    print("\n🎨 Test 5: memory_rethink")
    result = tools.memory_rethink("You are an AI assistant, completely rewritten!", "persona")
    print(f"   Status: {result['status']}")
    print(f"   Message: {result['message']}")
    
    # Show final state
    print("\n📦 Final memory blocks:")
    blocks = state.list_blocks()
    for b in blocks:
        print(f"   {b.label}: {b.content[:60]}...")
    
    # Get tool schemas
    print("\n🛠️  Tool schemas:")
    schemas = tools.get_tool_schemas()
    print(f"   Total tools: {len(schemas)}")
    for schema in schemas:
        print(f"   • {schema['function']['name']}")
    
    # Cleanup
    import os
    os.remove("./data/db/test_memory_tools.db")
    
    print("\n✅ ALL TESTS PASSED!")
    print("="*60)

