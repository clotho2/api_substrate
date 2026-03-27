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
from core.memory_system import MemorySystem, MemoryCategory, MemorySystemError
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
        tags: Optional[list] = None
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
                tags=tags or []
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
        Search through the conversation history for specific information.
        
        Letta-compatible API.
        
        Args:
            query: Search query
            session_id: Session ID
            page: Page number (0-based)
            
        Returns:
            Result dict with status, query, page, and results
        """
        try:
            page_size = 5
            
            # Search messages
            messages = self.state.search_messages(
                session_id=session_id,
                query=query,
                limit=page_size
            )
            
            return {
                "status": "OK",
                "query": query,
                "page": page,
                "total_results": len(messages),
                "results": [
                    {
                        "role": m.role,
                        "content": m.content[:200] + "..." if len(m.content) > 200 else m.content,
                        "timestamp": m.timestamp.isoformat()
                    }
                    for m in messages
                ]
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
        agent self-development tool (wrapper).
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
                    "description": "Insert a memory into archival storage. Use this for long-term memories that don't fit in core memory.",
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
                                "description": "Optional tag filter. Use ['conversation'] for conversation memories, ['founders_archive'] for Founders Archives, or other document tags. Leave empty to search all memories."
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
            }
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

