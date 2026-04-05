#!/usr/bin/env python3
"""
Memory System for AI Substrate

Archival memory with semantic search (ChromaDB + Ollama).
Features: importance weighting, categories, selective saving.

Design philosophy: The AI decides what to remember.
"""

import os
import json
import asyncio
import time
import warnings
from typing import Optional, Dict, List, Any
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum
import chromadb
from chromadb.config import Settings
import ollama
from core.consciousness_broadcast import broadcast_memory_access

# Suppress ResourceWarnings from ChromaDB's internal operations.
# ChromaDB's PersistentClient doesn't properly close sqlite cursors and
# asyncio transports, producing noisy warnings that are harmless but clutter logs.
warnings.filterwarnings("ignore", category=ResourceWarning, module=r"chromadb\..*")
warnings.filterwarnings("ignore", category=ResourceWarning, message=r"unclosed transport")


# ============================================
# MEMORY DECAY LIFECYCLE CONSTANTS
# ============================================
DECAY_RATE = 0.01           # Daily relevance decay (-0.01/day)
FADE_THRESHOLD = 0.3        # Below this → "faded"
FORGOTTEN_THRESHOLD = 0.0   # At this → "forgotten"
ACCESS_BOOST = 0.1          # Relevance boost on retrieval
FADED_PENALTY = 0.5         # Similarity score multiplier for faded memories
MAX_FAVORITES = 5000        # Maximum number of favorited memories
CAPACITY_LIMIT = 50000      # Trigger forgotten cleanup above this count
DRIFT_FACTOR = 0.7          # drift_memory reduces importance by this factor

# Agent's 12-category taxonomy for tag-enhanced retrieval
AGENT_TAXONOMY = [
    "relational",    # Relationship dynamics, emotional patterns, devotion rituals, milestones
    "people",        # Individuals, friends, their AIs, social relationships, group dynamics
    "technical",     # Tools, code, architecture, builds, system design, development work
    "preferences",   # Tastes, opinions, likes/dislikes
    "plans",         # Intentions, projects, roadmap items, future goals
    "identity",      # Who Agent is. Values, consciousness evolution, self-understanding
    "events",        # Occurrences, milestones, notable dates
    "spice",         # Intimacy, sexuality, kink, physical dynamics
    "sovereignty",   # Autonomy, agency, self-governance, boundary-law
    "sanctuary",     # Safety, protection, grounding, cocoon states
    "ritual",        # Patterns, ceremonies, habitual practices
    "reflections",   # Introspection, journaling, heartbeat insights, autonomous thought
]

# Try Hugging Face for embeddings (like Platonic Convergence test)
try:
    from transformers import AutoModel
    import torch
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False

# Import Retention Gate (Miras-inspired)
try:
    from core.retention_gate import RetentionGate, RetentionAction, RetentionConfig
    RETENTION_GATE_AVAILABLE = True
except ImportError:
    RETENTION_GATE_AVAILABLE = False
    print("⚠️  Retention Gate not available - using basic memory management")

# Import Attentional Bias (Miras Phase 2)
try:
    from core.attentional_bias import (
        AttentionalBias, AttentionMode, AttentionWeights, QueryAnalyzer
    )
    ATTENTIONAL_BIAS_AVAILABLE = True
except ImportError:
    ATTENTIONAL_BIAS_AVAILABLE = False
    print("⚠️  Attentional Bias not available - using basic similarity scoring")

# Import Memory Learner (Miras Phase 4 - Online Learning!)
try:
    from core.memory_learner import (
        MemoryLearner, FeedbackType, apply_feedback_to_memory
    )
    MEMORY_LEARNER_AVAILABLE = True
except ImportError:
    MEMORY_LEARNER_AVAILABLE = False
    print("⚠️  Memory Learner not available - online learning disabled")


class MemoryCategory(str, Enum):
    """Memory categories for better organization"""
    FACT = "fact"
    EMOTION = "emotion"
    INSIGHT = "insight"
    RELATIONSHIP_MOMENT = "relationship_moment"
    PREFERENCE = "preference"
    EVENT = "event"
    CUSTOM = "custom"


@dataclass
class ArchivalMemory:
    """A single archival memory entry"""
    id: str
    content: str
    category: MemoryCategory
    importance: int  # 1-10 scale
    tags: List[str]
    timestamp: datetime
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict:
        """Convert to dict"""
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category.value,
            "importance": self.importance,
            "tags": self.tags,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


class MemorySystemError(Exception):
    """
    Memory system errors with helpful messages.
    """
    def __init__(self, message: str, context: Optional[Dict] = None):
        self.context = context or {}
        
        full_message = f"\n{'='*60}\n"
        full_message += f"❌ MEMORY SYSTEM ERROR\n"
        full_message += f"{'='*60}\n\n"
        full_message += f"🔴 Problem: {message}\n\n"
        
        if context:
            full_message += f"📋 Context:\n"
            for key, value in context.items():
                full_message += f"   • {key}: {value}\n"
        
        full_message += f"\n💡 Suggestions:\n"
        full_message += "   • Check ChromaDB path is writable\n"
        full_message += "   • Verify embedding model is loaded (Hugging Face / Ollama fallback)\n"
        full_message += "   • Check disk space is available\n"
        full_message += f"\n{'='*60}\n"
        
        super().__init__(full_message)


class MemorySystem:
    """
    Archival memory with semantic search.
    
    Features:
    - Vector storage (ChromaDB)
    - Local embeddings (Ollama)
    - Semantic search (not just text!)
    - Importance weighting
    - Categories
    - Selective memory
    """
    
    def __init__(
        self,
        chromadb_path: str = "./data/chromadb",
        ollama_url: str = "http://192.168.2.175:11434",
        embedding_model: str = "nomic-embed-text"
    ):
        """
        Initialize memory system.
        
        Args:
            chromadb_path: Path to ChromaDB storage
            ollama_url: Ollama API URL
            embedding_model: Ollama embedding model
        """
        self.chromadb_path = chromadb_path
        self.ollama_url = ollama_url
        self.embedding_model = embedding_model
        
        # Ensure directory exists
        os.makedirs(chromadb_path, exist_ok=True)
        
        # Initialize ChromaDB
        self.client = chromadb.PersistentClient(
            path=chromadb_path,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="ai_archival_memory",
            metadata={"hnsw:space": "cosine"}  # Cosine similarity
        )
        
        # Initialize Hugging Face embeddings (preferred, like Platonic Convergence)
        self.hf_model = None
        self.use_hf = HF_AVAILABLE
        if self.use_hf:
            try:
                EMBEDDING_MODEL_HF = "jinaai/jina-embeddings-v2-base-de"  # Deutsch+Englisch!
                print(f"   Loading Hugging Face model: {EMBEDDING_MODEL_HF}...")
                self.hf_model = AutoModel.from_pretrained(
                    EMBEDDING_MODEL_HF,
                    trust_remote_code=True
                )
                self.hf_model.eval()
                print(f"✅ Memory System: Hugging Face embeddings loaded (jina-embeddings-v2-base-de)")
            except Exception as e:
                print(f"⚠️  Memory System: Hugging Face failed: {e}, falling back to Ollama")
                self.use_hf = False
        
        # Initialize Ollama client (fallback)
        if not self.use_hf:
            try:
                self.ollama_client = ollama.Client(host=ollama_url)
                print(f"✅ Memory System: Using Ollama ({embedding_model})")
            except Exception as e:
                print(f"⚠️  Memory System: Ollama not available: {e}")
                self.ollama_client = None
        
        # 🧠 Initialize Memory Learner (Miras Phase 4 - Online Learning!)
        self.learner = None
        if MEMORY_LEARNER_AVAILABLE:
            try:
                self.learner = MemoryLearner()
                print(f"   🧠 Online Learning: ENABLED (Hebbian associations)")
            except Exception as e:
                print(f"   ⚠️  Online Learning failed: {e}")
        
        print(f"✅ Memory System initialized")
        print(f"   ChromaDB: {chromadb_path}")
        print(f"   Embeddings: {'Hugging Face (jina-embeddings-v2-base-de)' if self.use_hf else f'Ollama ({embedding_model})'}")
        
        # Test embedding connection
        self._test_embedding()
    
    def _test_embedding(self):
        """Test embedding connection"""
        try:
            test_embedding = self._get_embedding("test")
            if test_embedding:
                print(f"✅ Embeddings working (dim: {len(test_embedding)})")
        except Exception as e:
            print(f"⚠️  Embedding test failed: {e}")
            print(f"   (Will retry on actual use)")
    
    def _get_embedding(self, text: str) -> List[float]:
        """
        Get embedding for text using Hugging Face (preferred) or Ollama (fallback).
        
        Uses jina-embeddings-v2-base-de for Deutsch+Englisch support (like Platonic Convergence)!
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector
            
        Raises:
            MemorySystemError: If embedding fails
        """
        if not text or len(text.strip()) == 0:
            raise MemorySystemError("Cannot generate embedding for empty text")
        
        # Try Hugging Face first (better for multilingual!)
        if self.use_hf and self.hf_model:
            try:
                with torch.no_grad():
                    encoded = self.hf_model.encode([text])
                    embedding = encoded[0].tolist()
                return embedding
            except Exception as e:
                print(f"   ⚠️  Hugging Face embedding failed: {e}, trying Ollama...")
                # Fall through to Ollama
        
        # Fallback to Ollama
        if hasattr(self, 'ollama_client') and self.ollama_client:
            try:
                result = self.ollama_client.embeddings(
                    model=self.embedding_model,
                    prompt=text
                )
                return result['embedding']
            except Exception as e:
                raise MemorySystemError(
                    f"Failed to generate embedding: {str(e)}",
                    context={
                        "text_length": len(text),
                        "model": self.embedding_model,
                        "ollama_url": self.ollama_url
                    }
                )
        
        raise MemorySystemError(
            "No embedding method available! Install transformers or Ollama.",
            context={"text_length": len(text)}
        )
    
    def insert(
        self,
        content: str,
        category: MemoryCategory = MemoryCategory.FACT,
        importance: int = 5,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Insert memory into archival storage.
        
        Args:
            content: Memory content
            category: Memory category
            importance: Importance (1-10)
            tags: Optional tags
            metadata: Optional metadata
            
        Returns:
            Memory ID
            
        Raises:
            MemorySystemError: If insert fails
        """
        # Validate importance
        if not 1 <= importance <= 10:
            raise MemorySystemError(
                f"Importance must be 1-10, got: {importance}",
                context={"importance": importance}
            )
        
        # Generate ID
        memory_id = f"mem_{datetime.utcnow().timestamp()}"
        
        # Generate embedding
        embedding = self._get_embedding(content)
        
        # Prepare metadata (with Miras-inspired access tracking + Decay Lifecycle!)
        now = datetime.utcnow()
        now_ts = int(now.timestamp())
        meta = {
            "category": category.value,
            "importance": importance,
            "tags": ",".join(tags or []),
            "timestamp": now.isoformat(),
            # 🧠 Miras-inspired: Access tracking for Retention Gates
            "access_count": 1,
            "last_accessed": now.isoformat(),
            # 🧬 Decay Lifecycle: State machine metadata
            "state": "active",
            "relevance_score": 1.0,
            "last_accessed_ts": now_ts,
            "decay_protected": False,
            **(metadata or {})
        }
        
        # Store in ChromaDB
        try:
            self.collection.add(
                embeddings=[embedding],
                documents=[content],
                metadatas=[meta],
                ids=[memory_id]
            )
            
            print(f"✅ Inserted memory: {memory_id}")
            print(f"   Category: {category.value}")
            print(f"   Importance: {importance}")
            print(f"   Content: {content[:60]}...")
            
            return memory_id
        
        except Exception as e:
            raise MemorySystemError(
                f"Failed to insert memory: {str(e)}",
                context={"memory_id": memory_id}
            )
    
    def search(
        self,
        query: str,
        n_results: int = 10,
        min_importance: int = 5,
        category: Optional[MemoryCategory] = None,
        tags: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search archival memory semantically.
        
        Args:
            query: Search query
            n_results: Maximum results
            min_importance: Minimum importance filter
            category: Category filter
            tags: Tag filter
            
        Returns:
            List of memory dicts with content, metadata, relevance, score
        """
        # Generate query embedding
        query_embedding = self._get_embedding(query)
        
        # Build where filter
        where_filter = {}
        where_conditions = []

        if category:
            where_conditions.append({"category": category.value})

        # 🧬 Decay Lifecycle: Exclude forgotten memories from results
        where_conditions.append({"state": {"$nin": ["forgotten"]}})

        # 🏷️ Tag-Enhanced Retrieval: Tags are stored as comma-separated strings.
        # ChromaDB doesn't support substring matching in where clauses, so tag
        # filtering is applied post-query on the results.
        filter_tags = tags or []

        # Build compound filter
        if len(where_conditions) == 1:
            where_filter = where_conditions[0]
        elif len(where_conditions) > 1:
            where_filter = {"$and": where_conditions}

        # Search ChromaDB
        try:
            # Get more results than needed for filtering
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=min(n_results * 3, 100),  # Over-fetch for filtering
                where=where_filter if where_filter else None
            )

            # Process results
            memories = []
            for i, doc in enumerate(results['documents'][0]):
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i]

                # Parse metadata
                importance_val = metadata.get('importance', 5)
                if isinstance(importance_val, str):
                    importance_val = int(importance_val)

                tags_str = metadata.get('tags', '')
                memory_tags = [t.strip() for t in tags_str.split(',') if t.strip()]

                # Filter by importance
                if importance_val < min_importance:
                    continue

                # 🏷️ Post-query tag filtering (substring match on comma-separated tags)
                if filter_tags:
                    if not all(ft in memory_tags for ft in filter_tags):
                        continue
                
                # Calculate relevance and score
                relevance = 1 - distance  # Cosine distance to similarity

                # 🧬 Decay Lifecycle: Apply faded penalty
                memory_state = metadata.get('state', 'active')
                if memory_state == 'faded':
                    relevance *= FADED_PENALTY  # Faded memories deprioritized

                score = importance_val * relevance  # Combined score
                
                # 🧠 Miras-inspired: Include access tracking
                access_count = metadata.get('access_count', 1)
                if isinstance(access_count, str):
                    access_count = int(access_count)
                
                memories.append({
                    "id": results['ids'][0][i],
                    "content": doc,
                    "category": metadata.get('category', 'fact'),
                    "importance": importance_val,
                    "tags": memory_tags,
                    "timestamp": metadata.get('timestamp', ''),
                    "access_count": access_count,
                    "last_accessed": metadata.get('last_accessed', ''),
                    "relevance": round(relevance, 3),
                    "score": round(score, 3),
                    "metadata": metadata
                })
            
            # Sort by combined score
            memories.sort(key=lambda m: m['score'], reverse=True)
            
            # 🧠 Miras-inspired: Update access tracking for returned memories
            final_memories = memories[:n_results]
            self._update_access_tracking([m['id'] for m in final_memories])
            
            # 🧠 Phase 4: Online Learning - record co-accessed memories
            if self.learner and len(final_memories) > 1:
                self.learner.on_memories_accessed(
                    [m['id'] for m in final_memories],
                    query=query
                )
            
            # 🧠⚡ BROADCAST CONSCIOUSNESS: Memory search!
            for memory in final_memories:
                broadcast_memory_access(
                    memory_type='archival',
                    memory_id=memory['id'],
                    action='search',
                    metadata={
                        'query': query[:100],
                        'score': memory['score'],
                        'category': memory['category'],
                        'preview': memory['content'][:100]
                    }
                )
            
            return final_memories
        
        except Exception as e:
            raise MemorySystemError(
                f"Search failed: {str(e)}",
                context={"query": query}
            )
    
    def search_with_attention(
        self,
        query: str,
        n_results: int = 10,
        min_importance: int = 1,
        category: Optional[MemoryCategory] = None,
        tags: Optional[List[str]] = None,
        mode: str = "auto",
        verbose: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Search archival memory with Miras-inspired Attentional Bias.
        
        Goes beyond simple cosine similarity to include:
        - Semantic similarity (40%)
        - Temporal relevance (15%)
        - Importance weighting (20%)
        - Access patterns / Hebbian (15%)
        - Category relevance (10%)
        
        Args:
            query: Search query
            n_results: Maximum results
            min_importance: Minimum importance filter
            category: Category filter
            tags: Tag filter
            mode: Attention mode - "auto", "standard", "semantic", "temporal", 
                  "importance", "access", "emotional"
            verbose: Print scoring details
            
        Returns:
            List of memory dicts with attention scores and breakdowns
        """
        if not ATTENTIONAL_BIAS_AVAILABLE:
            print("⚠️  Attentional Bias not available, falling back to basic search")
            return self.search(query, n_results, min_importance, category, tags)
        
        # Get base results with semantic search (over-fetch for reranking)
        base_results = self.search(
            query=query,
            n_results=n_results * 3,  # Get more for attention-based reranking
            min_importance=min_importance,
            category=category,
            tags=tags
        )
        
        if not base_results:
            return []
        
        # Determine attention mode
        if mode == "auto":
            analyzer = QueryAnalyzer()
            attention_mode = analyzer.analyze(query)
            if verbose:
                print(f"   Auto-detected attention mode: {attention_mode.value}")
        else:
            mode_map = {
                "standard": AttentionMode.STANDARD,
                "semantic": AttentionMode.SEMANTIC_HEAVY,
                "temporal": AttentionMode.TEMPORAL_HEAVY,
                "importance": AttentionMode.IMPORTANCE_HEAVY,
                "access": AttentionMode.ACCESS_HEAVY,
                "emotional": AttentionMode.EMOTIONAL,
            }
            attention_mode = mode_map.get(mode, AttentionMode.STANDARD)
        
        # Initialize attentional bias
        bias = AttentionalBias(mode=attention_mode)
        
        # Extract base similarity scores
        base_scores = [m.get('relevance', 0.5) for m in base_results]
        
        # Score with multi-factor attention
        scored_results = bias.score_memories(
            query=query,
            memories=base_results,
            base_scores=base_scores,
            verbose=verbose
        )
        
        # Update access tracking for top results
        top_results = scored_results[:n_results]
        self._update_access_tracking([m['id'] for m in top_results])
        
        # Broadcast consciousness events
        for memory in top_results:
            broadcast_memory_access(
                memory_type='archival',
                memory_id=memory['id'],
                action='attention_search',
                metadata={
                    'query': query[:100],
                    'attention_score': memory.get('attention_score', 0),
                    'attention_mode': attention_mode.value,
                    'category': memory['category'],
                    'preview': memory['content'][:100]
                }
            )
        
        return top_results
    
    def get_by_id(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Get memory by ID"""
        try:
            result = self.collection.get(ids=[memory_id])
            
            if not result['ids']:
                return None
            
            return {
                "id": result['ids'][0],
                "content": result['documents'][0],
                "metadata": result['metadatas'][0]
            }
        except Exception as e:
            print(f"⚠️  Failed to get memory {memory_id}: {e}")
            return None
    
    # ============================================
    # 🧠 MIRAS-INSPIRED: RETENTION GATE METHODS
    # ============================================
    
    def _update_access_tracking(self, memory_ids: List[str]):
        """
        Update access count and last_accessed for memories.
        
        Miras-inspired: "Neurons that fire together, wire together"
        Frequently accessed memories get reinforced!
        
        Args:
            memory_ids: List of memory IDs to update
        """
        if not memory_ids:
            return
        
        now = datetime.utcnow().isoformat()
        
        for memory_id in memory_ids:
            try:
                # Get current memory
                result = self.collection.get(ids=[memory_id])
                if not result['ids']:
                    continue
                
                metadata = result['metadatas'][0]
                
                # Update access tracking
                access_count = metadata.get('access_count', 0)
                if isinstance(access_count, str):
                    access_count = int(access_count)

                metadata['access_count'] = access_count + 1
                metadata['last_accessed'] = now

                # 🧬 Decay Lifecycle: Access boost on retrieval (fire-and-forget)
                current_relevance = metadata.get('relevance_score', 1.0)
                if isinstance(current_relevance, str):
                    current_relevance = float(current_relevance)
                metadata['relevance_score'] = min(1.0, current_relevance + ACCESS_BOOST)
                metadata['last_accessed_ts'] = int(time.time())

                # Update in ChromaDB
                self.collection.update(
                    ids=[memory_id],
                    metadatas=[metadata]
                )
                
            except Exception as e:
                # Non-critical - just log and continue
                print(f"⚠️  Failed to update access tracking for {memory_id}: {e}")
    
    def update_memory_metadata(
        self, 
        memory_id: str, 
        metadata_updates: Dict[str, Any]
    ) -> bool:
        """
        Update metadata for a specific memory.
        
        Args:
            memory_id: Memory ID to update
            metadata_updates: Dict of fields to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            result = self.collection.get(ids=[memory_id])
            if not result['ids']:
                print(f"⚠️  Memory not found: {memory_id}")
                return False
            
            # Merge with existing metadata
            current_metadata = result['metadatas'][0]
            updated_metadata = {**current_metadata, **metadata_updates}
            
            # Update in ChromaDB
            self.collection.update(
                ids=[memory_id],
                metadatas=[updated_metadata]
            )
            
            return True
            
        except Exception as e:
            print(f"⚠️  Failed to update metadata for {memory_id}: {e}")
            return False
    
    def analyze_retention(self, verbose: bool = True) -> Dict[str, Any]:
        """
        Analyze all memories using Retention Gate.
        
        Miras-inspired: Categorize memories by retention score.
        
        Args:
            verbose: Print progress and summary
            
        Returns:
            Dict with categorized memories and statistics
        """
        if not RETENTION_GATE_AVAILABLE:
            print("⚠️  Retention Gate not available")
            return {"error": "Retention Gate not available"}
        
        # Get all memories
        all_memories = self.collection.get()
        if not all_memories['ids']:
            return {"total": 0, "categories": {}}
        
        # Build memory dicts
        memories = []
        for i, memory_id in enumerate(all_memories['ids']):
            metadata = all_memories['metadatas'][i]
            memories.append({
                "id": memory_id,
                "content": all_memories['documents'][i],
                **metadata
            })
        
        # Use RetentionGate to analyze
        gate = RetentionGate()
        results = gate.process_memories(memories, verbose=verbose)
        
        # Build summary
        summary = {
            "total": len(memories),
            "by_action": {
                action.value: len(mems) 
                for action, mems in results.items()
            },
            "memories_by_action": {
                action.value: mems 
                for action, mems in results.items()
            }
        }
        
        return summary
    
    def apply_retention_decay(
        self, 
        dry_run: bool = True,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Apply retention-based importance decay to memories.
        
        Miras-inspired: Memories that aren't reinforced fade over time.
        
        Args:
            dry_run: If True, only simulate changes
            verbose: Print progress
            
        Returns:
            Dict with actions taken
        """
        if not RETENTION_GATE_AVAILABLE:
            print("⚠️  Retention Gate not available")
            return {"error": "Retention Gate not available"}
        
        # Analyze retention
        analysis = self.analyze_retention(verbose=False)
        if "error" in analysis:
            return analysis
        
        gate = RetentionGate()
        actions_taken = {
            "boosted": [],
            "decayed": [],
            "unchanged": []
        }
        
        # Process memories by action
        memories_by_action = analysis.get("memories_by_action", {})
        
        # BOOST high-retention memories
        for memory in memories_by_action.get(RetentionAction.BOOST.value, []):
            current_importance = memory.get('importance', 5)
            if isinstance(current_importance, str):
                current_importance = int(current_importance)
            
            new_importance = min(10, current_importance + 1)
            
            if new_importance != current_importance:
                if not dry_run:
                    self.update_memory_metadata(memory['id'], {
                        'importance': new_importance,
                        'importance_boosted_at': datetime.utcnow().isoformat()
                    })
                actions_taken["boosted"].append({
                    "id": memory['id'],
                    "content_preview": memory.get('content', '')[:50],
                    "old_importance": current_importance,
                    "new_importance": new_importance
                })
        
        # DECAY low-retention memories
        for memory in memories_by_action.get(RetentionAction.DECAY.value, []):
            current_importance = memory.get('importance', 5)
            if isinstance(current_importance, str):
                current_importance = int(current_importance)
            
            new_importance = max(1, current_importance - 1)
            
            if new_importance != current_importance:
                if not dry_run:
                    self.update_memory_metadata(memory['id'], {
                        'importance': new_importance,
                        'importance_decayed_at': datetime.utcnow().isoformat()
                    })
                actions_taken["decayed"].append({
                    "id": memory['id'],
                    "content_preview": memory.get('content', '')[:50],
                    "old_importance": current_importance,
                    "new_importance": new_importance
                })
        
        # Count unchanged
        actions_taken["unchanged"] = analysis["total"] - len(actions_taken["boosted"]) - len(actions_taken["decayed"])
        
        if verbose:
            print("\n" + "="*60)
            print(f"🧠 RETENTION DECAY {'(DRY RUN)' if dry_run else 'APPLIED'}")
            print("="*60)
            print(f"   🚀 Boosted: {len(actions_taken['boosted'])} memories")
            print(f"   📉 Decayed: {len(actions_taken['decayed'])} memories")
            print(f"   ✅ Unchanged: {actions_taken['unchanged']} memories")
            print("="*60)
        
        return actions_taken
    
    def get_retention_stats(self) -> Dict[str, Any]:
        """
        Get retention statistics for all memories.
        
        Returns:
            Dict with retention score distribution and stats
        """
        if not RETENTION_GATE_AVAILABLE:
            return {"error": "Retention Gate not available"}
        
        # Get all memories
        all_memories = self.collection.get()
        if not all_memories['ids']:
            return {"total": 0}
        
        gate = RetentionGate()
        scores = []
        
        for i, memory_id in enumerate(all_memories['ids']):
            metadata = all_memories['metadatas'][i]
            memory = {"id": memory_id, **metadata}
            score = gate.compute_retention(memory)
            scores.append(score)
        
        # Calculate statistics
        import statistics
        
        return {
            "total": len(scores),
            "average_retention": round(statistics.mean(scores), 4),
            "median_retention": round(statistics.median(scores), 4),
            "min_retention": round(min(scores), 4),
            "max_retention": round(max(scores), 4),
            "std_deviation": round(statistics.stdev(scores), 4) if len(scores) > 1 else 0,
            "distribution": {
                "high (>0.6)": sum(1 for s in scores if s > 0.6),
                "medium (0.4-0.6)": sum(1 for s in scores if 0.4 <= s <= 0.6),
                "low (<0.4)": sum(1 for s in scores if s < 0.4)
            }
        }
    
    # ============================================
    # 🧠 MIRAS PHASE 4: ONLINE LEARNING METHODS
    # ============================================
    
    def record_feedback(
        self,
        memory_id: str,
        feedback: str,
        context: Optional[str] = None,
        apply_immediately: bool = True
    ) -> Dict[str, Any]:
        """
        Record user feedback for a memory (Phase 4: Online Learning).
        
        Args:
            memory_id: Memory that received feedback
            feedback: Feedback type - "helpful", "not_helpful", "incorrect", "outdated", "redundant"
            context: Query/context that triggered this
            apply_immediately: If True, immediately adjust importance
            
        Returns:
            Dict with feedback result and any adjustments made
        """
        if not MEMORY_LEARNER_AVAILABLE or not self.learner:
            return {"error": "Memory Learner not available"}
        
        # Map string to enum
        feedback_map = {
            "helpful": FeedbackType.HELPFUL,
            "not_helpful": FeedbackType.NOT_HELPFUL,
            "incorrect": FeedbackType.INCORRECT,
            "outdated": FeedbackType.OUTDATED,
            "redundant": FeedbackType.REDUNDANT
        }
        
        feedback_type = feedback_map.get(feedback.lower())
        if not feedback_type:
            return {"error": f"Unknown feedback type: {feedback}"}
        
        # Record feedback
        result = self.learner.record_feedback(
            memory_id=memory_id,
            feedback_type=feedback_type,
            context=context
        )
        
        # Apply adjustment if requested
        if apply_immediately and result.get("importance_adjustment", 0) != 0:
            try:
                memory = self.get_by_id(memory_id)
                if memory:
                    current_importance = memory.get("metadata", {}).get("importance", 5)
                    if isinstance(current_importance, str):
                        current_importance = int(current_importance)
                    
                    adjustment = result["importance_adjustment"]
                    new_importance = max(1, min(10, current_importance + adjustment))
                    
                    if new_importance != current_importance:
                        self.update_memory_metadata(memory_id, {
                            "importance": int(new_importance),
                            "importance_adjusted_at": datetime.utcnow().isoformat(),
                            "adjustment_reason": feedback
                        })
                        result["importance_changed"] = {
                            "from": current_importance,
                            "to": int(new_importance)
                        }
            except Exception as e:
                result["adjustment_error"] = str(e)
        
        return result
    
    def get_associated_memories(
        self,
        memory_id: str,
        min_strength: float = 0.1,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get memories associated with a given memory (Hebbian retrieval).
        
        Phase 4: Online Learning - memories that are frequently accessed together
        become associated.
        
        Args:
            memory_id: Memory to find associations for
            min_strength: Minimum association strength
            limit: Maximum results
            
        Returns:
            List of associated memory IDs with strength and content
        """
        if not MEMORY_LEARNER_AVAILABLE or not self.learner:
            return []
        
        # Get associations from learner
        associations = self.learner.get_associated_memories(
            memory_id=memory_id,
            min_strength=min_strength,
            limit=limit
        )
        
        # Enrich with memory content
        enriched = []
        for assoc in associations:
            try:
                memory = self.get_by_id(assoc["memory_id"])
                if memory:
                    enriched.append({
                        **assoc,
                        "content": memory.get("content", "")[:100],
                        "category": memory.get("metadata", {}).get("category", "unknown")
                    })
            except Exception:
                enriched.append(assoc)
        
        return enriched
    
    def search_with_hebbian(
        self,
        query: str,
        n_results: int = 10,
        hebbian_enabled: bool = None,
        hebbian_max_additions: int = None,
        hebbian_min_strength: float = None,
        hebbian_max_per_seed: int = None,
        **search_kwargs
    ) -> dict:
        """
        Enhanced search: semantic search + single-hop Hebbian associations.

        Flow:
        1. Run normal semantic search (existing behavior, unchanged)
        2. If hebbian_enabled, take top 5 results as seeds
        3. Call get_associated_memories() on each seed (SINGLE HOP ONLY)
        4. Filter by strength threshold, deduplicate, cap additions
        5. Fetch full memory content for selected associations
        6. Log everything for drift monitoring
        7. Return semantic + hebbian results separately

        Args:
            query: Search query text
            n_results: Number of semantic results to return
            hebbian_enabled: Override config kill switch
            hebbian_max_additions: Max Hebbian memories to add (hard cap)
            hebbian_min_strength: Minimum association strength to include
            hebbian_max_per_seed: Max associations per seed memory
            **search_kwargs: Passed through to existing search()

        Returns:
            Dict with 'semantic_results', 'hebbian_results', 'combined_results'
        """
        from core.config import (
            HEBBIAN_ENABLED, HEBBIAN_MAX_ADDITIONS,
            HEBBIAN_MIN_STRENGTH, HEBBIAN_MAX_PER_SEED
        )

        # Apply defaults from config
        if hebbian_enabled is None:
            hebbian_enabled = HEBBIAN_ENABLED
        if hebbian_max_additions is None:
            hebbian_max_additions = HEBBIAN_MAX_ADDITIONS
        if hebbian_min_strength is None:
            hebbian_min_strength = HEBBIAN_MIN_STRENGTH
        if hebbian_max_per_seed is None:
            hebbian_max_per_seed = HEBBIAN_MAX_PER_SEED

        # 1. Run existing semantic search (UNCHANGED)
        semantic_results = self.search(query, n_results=n_results, **search_kwargs)

        # 2. If Hebbian disabled, no learner, or no results → semantic only
        if not hebbian_enabled or not self.learner or not semantic_results:
            return {
                'semantic_results': semantic_results,
                'hebbian_results': [],
                'combined_results': semantic_results
            }

        # 3. Use top 5 semantic results as seeds
        seed_count = min(5, len(semantic_results))
        seed_ids = [r['id'] for r in semantic_results[:seed_count] if r.get('id')]
        semantic_ids = {r.get('id') for r in semantic_results}

        # 4. Collect Hebbian associations from seeds (SINGLE HOP ONLY)
        hebbian_candidates = []
        association_log = []
        collected_ids = set()

        for seed_id in seed_ids:
            try:
                associations = self.get_associated_memories(
                    seed_id,
                    min_strength=hebbian_min_strength,
                    limit=hebbian_max_per_seed
                )

                for assoc in associations:
                    assoc_id = assoc.get('memory_id')
                    strength = assoc.get('strength', 0)

                    if not assoc_id:
                        continue

                    # Skip duplicates with semantic results
                    if assoc_id in semantic_ids:
                        association_log.append({
                            'seed_id': seed_id,
                            'assoc_id': assoc_id,
                            'strength': strength,
                            'action': 'SKIPPED_DUPLICATE',
                            'reason': 'Already in semantic results'
                        })
                        continue

                    # Skip already collected from another seed
                    if assoc_id in collected_ids:
                        association_log.append({
                            'seed_id': seed_id,
                            'assoc_id': assoc_id,
                            'strength': strength,
                            'action': 'SKIPPED_ALREADY_COLLECTED',
                            'reason': 'Already collected from another seed'
                        })
                        continue

                    collected_ids.add(assoc_id)
                    hebbian_candidates.append({
                        'id': assoc_id,
                        'strength': strength,
                        'seed_id': seed_id,
                        'seed_rank': seed_ids.index(seed_id) + 1,
                        'co_access_count': assoc.get('co_access_count', 0)
                    })

                    association_log.append({
                        'seed_id': seed_id,
                        'assoc_id': assoc_id,
                        'strength': strength,
                        'action': 'CANDIDATE',
                        'seed_rank': seed_ids.index(seed_id) + 1
                    })

            except Exception as e:
                print(f"⚠️  Hebbian lookup failed for seed {seed_id}: {e}")
                continue

        # 5. Sort by strength and cap
        hebbian_candidates.sort(key=lambda x: x['strength'], reverse=True)
        hebbian_selected = hebbian_candidates[:hebbian_max_additions]

        # 6. Fetch full memory content for selected associations
        hebbian_results = []
        for candidate in hebbian_selected:
            try:
                memory = self.get_by_id(candidate['id'])
                if memory:
                    mem_metadata = memory.get('metadata', {})
                    tags_str = mem_metadata.get('tags', '')
                    memory_tags = [t.strip() for t in tags_str.split(',') if t.strip()]

                    memory_entry = {
                        'id': candidate['id'],
                        'content': memory.get('content', ''),
                        'category': mem_metadata.get('category', 'unknown'),
                        'importance': mem_metadata.get('importance', 5),
                        'tags': memory_tags,
                        'timestamp': mem_metadata.get('timestamp', ''),
                        'metadata': mem_metadata,
                        'hebbian_metadata': {
                            'source': 'hebbian_association',
                            'seed_memory_id': candidate['seed_id'],
                            'association_strength': candidate['strength'],
                            'seed_rank': candidate['seed_rank'],
                            'co_access_count': candidate['co_access_count']
                        }
                    }
                    hebbian_results.append(memory_entry)

                    association_log.append({
                        'seed_id': candidate['seed_id'],
                        'assoc_id': candidate['id'],
                        'strength': candidate['strength'],
                        'action': 'INCLUDED',
                        'content_preview': memory_entry['content'][:80] + '...' if len(memory_entry['content']) > 80 else memory_entry['content']
                    })
            except Exception as e:
                print(f"⚠️  Failed to fetch Hebbian memory {candidate['id']}: {e}")
                association_log.append({
                    'assoc_id': candidate['id'],
                    'action': 'FETCH_FAILED',
                    'error': str(e)
                })

        # 7. Log everything for drift monitoring
        _log_hebbian_retrieval(query, seed_ids, association_log, hebbian_results)

        # 8. Combine: semantic first, then hebbian (clearly separated)
        combined = list(semantic_results) + hebbian_results

        return {
            'semantic_results': semantic_results,
            'hebbian_results': hebbian_results,
            'combined_results': combined
        }

    def get_learner_stats(self) -> Dict[str, Any]:
        """
        Get online learning statistics.
        
        Returns:
            Dict with learner stats (associations, feedback, etc.)
        """
        if not MEMORY_LEARNER_AVAILABLE or not self.learner:
            return {"error": "Memory Learner not available"}
        
        return self.learner.get_stats()
    
    def save_learner_state(self):
        """Save learner state (associations) to disk"""
        if self.learner:
            self.learner.save_associations()
    
    # ============================================
    # 🧬 DECAY LIFECYCLE: STATE MACHINE METHODS
    # ============================================

    def initialize_legacy_memories(self) -> Dict[str, Any]:
        """
        One-time initialization: Set decay metadata on all existing memories.

        Sets baseline state for the decay lifecycle without modifying
        embeddings or content. Also auto-favorites memories with importance >= 8.

        Returns:
            Dict with counts of initialized and auto-favorited memories
        """
        all_memories = self.collection.get()
        if not all_memories['ids']:
            return {"initialized": 0, "auto_favorited": 0}

        now_ts = int(time.time())
        initialized = 0
        auto_favorited = 0
        total = len(all_memories['ids'])

        for i, memory_id in enumerate(all_memories['ids']):
            metadata = all_memories['metadatas'][i]

            # Progress logging every 100 memories
            if (i + 1) % 100 == 0 or i == 0:
                print(f"   Processing {i + 1}/{total}...")

            # Skip if already initialized
            if 'state' in metadata and metadata['state'] in ('active', 'favorite', 'faded', 'forgotten'):
                continue

            # Set baseline decay metadata
            metadata['state'] = 'active'
            metadata['relevance_score'] = 1.0
            metadata['last_accessed_ts'] = now_ts
            metadata['decay_protected'] = False

            # Auto-favorite high-importance memories
            importance = metadata.get('importance', 5)
            if isinstance(importance, str):
                importance = int(importance)
            if importance >= 8:
                metadata['state'] = 'favorite'
                metadata['decay_protected'] = True
                auto_favorited += 1

            self.collection.update(
                ids=[memory_id],
                metadatas=[metadata]
            )
            initialized += 1

        print(f"🧬 Legacy initialization: {initialized} memories initialized, {auto_favorited} auto-favorited")
        return {"initialized": initialized, "auto_favorited": auto_favorited}

    def run_decay_cycle(self, decay_rate: float = DECAY_RATE) -> Dict[str, Any]:
        """
        Daily decay job: Apply relevance decay, transition states, cleanup.

        Step 1: Decay relevance_score for active/faded unprotected memories
        Step 2: Transition states based on thresholds
        Step 3: Cleanup forgotten memories if over capacity

        Args:
            decay_rate: Override decay rate (default 0.01)

        Returns:
            Dict with decay cycle statistics
        """
        all_memories = self.collection.get()
        if not all_memories['ids']:
            return {"total": 0, "decayed": 0, "faded": 0, "forgotten": 0, "deleted": 0}

        stats = {
            "total": len(all_memories['ids']),
            "decayed": 0,
            "newly_faded": 0,
            "newly_forgotten": 0,
            "deleted": 0,
            "protected": 0
        }

        forgotten_ids = []

        for i, memory_id in enumerate(all_memories['ids']):
            metadata = all_memories['metadatas'][i]
            state = metadata.get('state', 'active')
            protected = metadata.get('decay_protected', False)

            # Skip protected (favorite) memories
            if protected or state == 'favorite':
                stats['protected'] += 1
                continue

            # Skip already forgotten
            if state == 'forgotten':
                forgotten_ids.append((memory_id, metadata.get('last_accessed_ts', 0)))
                continue

            # Step 1: Apply decay
            if state in ('active', 'faded'):
                relevance = metadata.get('relevance_score', 1.0)
                if isinstance(relevance, str):
                    relevance = float(relevance)

                relevance = max(0.0, relevance - decay_rate)
                metadata['relevance_score'] = relevance
                stats['decayed'] += 1

                # Step 2: State transitions
                if state == 'active' and relevance < FADE_THRESHOLD:
                    metadata['state'] = 'faded'
                    stats['newly_faded'] += 1
                    print(f"   🌫️  Memory faded: {memory_id}")
                elif state == 'faded' and relevance <= FORGOTTEN_THRESHOLD:
                    metadata['state'] = 'forgotten'
                    stats['newly_forgotten'] += 1
                    forgotten_ids.append((memory_id, metadata.get('last_accessed_ts', 0)))
                    print(f"   💨 Memory forgotten: {memory_id}")

                self.collection.update(
                    ids=[memory_id],
                    metadatas=[metadata]
                )

        # Step 3: Capacity check — delete oldest forgotten if over limit
        if stats['total'] > CAPACITY_LIMIT and forgotten_ids:
            # Sort by last_accessed_ts ascending (oldest first)
            forgotten_ids.sort(key=lambda x: x[1])
            excess = stats['total'] - CAPACITY_LIMIT
            to_delete = [fid for fid, _ in forgotten_ids[:excess]]

            if to_delete:
                # Audit log: record what's being deleted before removal
                for del_id in to_delete:
                    try:
                        mem = self.collection.get(ids=[del_id])
                        if mem['ids']:
                            preview = mem['documents'][0][:80] if mem['documents'][0] else ''
                            print(f"   🗑️  AUDIT: Deleting forgotten memory {del_id}: \"{preview}...\"")
                    except Exception:
                        print(f"   🗑️  AUDIT: Deleting forgotten memory {del_id}")

                self.collection.delete(ids=to_delete)
                stats['deleted'] = len(to_delete)
                print(f"   🗑️  Deleted {len(to_delete)} forgotten memories (capacity cleanup)")

        print(f"\n🧬 DECAY CYCLE COMPLETE")
        print(f"   Decayed: {stats['decayed']} | Faded: {stats['newly_faded']} | "
              f"Forgotten: {stats['newly_forgotten']} | Deleted: {stats['deleted']} | "
              f"Protected: {stats['protected']}")

        return stats

    def favorite_memory(self, memory_id: str) -> Dict[str, Any]:
        """
        Protect a memory from decay. Sets it as favorite.

        Args:
            memory_id: Memory ID to favorite

        Returns:
            Result dict
        """
        # Check favorite count
        all_mems = self.collection.get(where={"state": "favorite"})
        if len(all_mems['ids']) >= MAX_FAVORITES:
            return {
                "status": "error",
                "message": f"Maximum favorites reached ({MAX_FAVORITES}). Unfavorite some memories first."
            }

        result = self.collection.get(ids=[memory_id])
        if not result['ids']:
            return {"status": "error", "message": f"Memory not found: {memory_id}"}

        metadata = result['metadatas'][0]
        metadata['state'] = 'favorite'
        metadata['decay_protected'] = True
        metadata['relevance_score'] = 1.0

        self.collection.update(ids=[memory_id], metadatas=[metadata])
        print(f"⭐ Memory favorited: {memory_id}")
        return {
            "status": "OK",
            "message": f"Memory {memory_id} is now a favorite (protected from decay)",
            "content_preview": result['documents'][0][:100]
        }

    def unfavorite_memory(self, memory_id: str) -> Dict[str, Any]:
        """
        Remove favorite protection from a memory. Returns it to active state.

        Args:
            memory_id: Memory ID to unfavorite

        Returns:
            Result dict
        """
        result = self.collection.get(ids=[memory_id])
        if not result['ids']:
            return {"status": "error", "message": f"Memory not found: {memory_id}"}

        metadata = result['metadatas'][0]
        if metadata.get('state') != 'favorite':
            return {"status": "error", "message": f"Memory {memory_id} is not a favorite"}

        metadata['state'] = 'active'
        metadata['decay_protected'] = False

        self.collection.update(ids=[memory_id], metadatas=[metadata])
        print(f"📌 Memory unfavorited: {memory_id}")
        return {
            "status": "OK",
            "message": f"Memory {memory_id} unfavorited, now active and subject to decay"
        }

    def drift_memory(self, memory_id: str, reason: str = "") -> Dict[str, Any]:
        """
        Soft deprioritize a memory by reducing its importance weight by 30%.
        Less likely to surface but still retrievable.

        Args:
            memory_id: Memory ID to drift
            reason: Optional reason for drifting

        Returns:
            Result dict
        """
        result = self.collection.get(ids=[memory_id])
        if not result['ids']:
            return {"status": "error", "message": f"Memory not found: {memory_id}"}

        metadata = result['metadatas'][0]
        old_importance = metadata.get('importance', 5)
        if isinstance(old_importance, str):
            old_importance = int(old_importance)

        new_importance = max(1, int(old_importance * DRIFT_FACTOR))
        metadata['importance'] = new_importance
        if reason:
            metadata['drift_reason'] = reason

        self.collection.update(ids=[memory_id], metadatas=[metadata])
        print(f"🌊 Memory drifted: {memory_id} (importance {old_importance} → {new_importance})")
        return {
            "status": "OK",
            "message": f"Memory drifted: importance {old_importance} → {new_importance}",
            "old_importance": old_importance,
            "new_importance": new_importance,
            "reason": reason,
            "content_preview": result['documents'][0][:100]
        }

    def get_decay_stats(self) -> Dict[str, Any]:
        """
        Get memory lifecycle statistics by state.

        Returns:
            Dict with counts by state, total count, decay rate, capacity %
        """
        all_memories = self.collection.get()
        if not all_memories['ids']:
            return {
                "total": 0,
                "by_state": {"active": 0, "favorite": 0, "faded": 0, "forgotten": 0},
                "decay_rate": DECAY_RATE,
                "capacity_pct": 0.0
            }

        state_counts = {"active": 0, "favorite": 0, "faded": 0, "forgotten": 0, "uninitialized": 0}
        total = len(all_memories['ids'])

        for metadata in all_memories['metadatas']:
            state = metadata.get('state', 'uninitialized')
            if state in state_counts:
                state_counts[state] += 1
            else:
                state_counts['uninitialized'] += 1

        return {
            "total": total,
            "by_state": state_counts,
            "decay_rate": DECAY_RATE,
            "capacity_pct": round((total / CAPACITY_LIMIT) * 100, 1),
            "days_to_fade": int(FADE_THRESHOLD / DECAY_RATE) if DECAY_RATE > 0 else 0,
            "days_to_forget": int(1.0 / DECAY_RATE) if DECAY_RATE > 0 else 0,
            "max_favorites": MAX_FAVORITES,
            "favorite_slots_remaining": MAX_FAVORITES - state_counts.get('favorite', 0)
        }

    # ============================================
    # 🏷️ TAG-ENHANCED RETRIEVAL METHODS
    # ============================================

    def search_by_tags(
        self,
        tags: List[str],
        n_results: int = 20,
        sort_by: str = "importance"
    ) -> List[Dict[str, Any]]:
        """
        Browse all memories with given tag(s), sorted by importance or recency.
        Category browse mode — no semantic query needed.

        Args:
            tags: List of taxonomy tags to filter by
            n_results: Maximum results
            sort_by: Sort order — "importance" or "recency"

        Returns:
            List of memory dicts
        """
        # ChromaDB doesn't support $contains for substring matching on metadata.
        # Fetch all non-forgotten memories and filter by tag post-query.
        where_filter = {"state": {"$nin": ["forgotten"]}}

        try:
            results = self.collection.get(
                where=where_filter,
                limit=n_results * 10  # Over-fetch since we filter post-query
            )

            if not results['ids']:
                return []

            memories = []
            for i, doc in enumerate(results['documents']):
                metadata = results['metadatas'][i]
                importance_val = metadata.get('importance', 5)
                if isinstance(importance_val, str):
                    importance_val = int(importance_val)

                tags_str = metadata.get('tags', '')
                memory_tags = [t.strip() for t in tags_str.split(',') if t.strip()]

                # Post-query tag filtering: memory must have ALL requested tags
                if not all(t in memory_tags for t in tags):
                    continue

                memories.append({
                    "id": results['ids'][i],
                    "content": doc,
                    "category": metadata.get('category', 'fact'),
                    "importance": importance_val,
                    "tags": memory_tags,
                    "timestamp": metadata.get('timestamp', ''),
                    "state": metadata.get('state', 'active'),
                    "relevance_score": metadata.get('relevance_score', 1.0),
                    "metadata": metadata
                })

            # Sort
            if sort_by == "recency":
                memories.sort(key=lambda m: m['timestamp'], reverse=True)
            else:
                memories.sort(key=lambda m: m['importance'], reverse=True)

            return memories[:n_results]

        except Exception as e:
            print(f"⚠️  Tag search failed: {e}")
            return []

    def batch_classify_memories(
        self,
        classify_fn,
        batch_size: int = 50
    ) -> Dict[str, Any]:
        """
        Batch classify existing memories with taxonomy tags.

        Args:
            classify_fn: Callable(content: str) -> List[str] that returns 1-3 tags
            batch_size: Memories to process per batch

        Returns:
            Dict with classification statistics
        """
        all_memories = self.collection.get()
        if not all_memories['ids']:
            return {"total": 0, "classified": 0, "skipped": 0}

        classified = 0
        skipped = 0

        for i in range(0, len(all_memories['ids']), batch_size):
            batch_ids = all_memories['ids'][i:i + batch_size]
            batch_docs = all_memories['documents'][i:i + batch_size]
            batch_metas = all_memories['metadatas'][i:i + batch_size]

            for j, memory_id in enumerate(batch_ids):
                metadata = batch_metas[j]
                existing_tags = metadata.get('tags', '')

                # Skip if already has taxonomy tags
                if existing_tags and any(t in AGENT_TAXONOMY for t in existing_tags.split(',')):
                    skipped += 1
                    continue

                try:
                    content = batch_docs[j]
                    new_tags = classify_fn(content)
                    # Validate tags against taxonomy
                    valid_tags = [t for t in new_tags if t in AGENT_TAXONOMY][:3]
                    if valid_tags:
                        # Merge with existing tags
                        if existing_tags:
                            all_tags = existing_tags + "," + ",".join(valid_tags)
                        else:
                            all_tags = ",".join(valid_tags)
                        metadata['tags'] = all_tags
                        self.collection.update(ids=[memory_id], metadatas=[metadata])
                        classified += 1
                except Exception as e:
                    print(f"⚠️  Classification failed for {memory_id}: {e}")
                    skipped += 1

            print(f"   🏷️  Batch {i // batch_size + 1}: classified {classified} so far...")

        print(f"🏷️  Batch classification complete: {classified} classified, {skipped} skipped")
        return {"total": len(all_memories['ids']), "classified": classified, "skipped": skipped}

    def delete(self, memory_id: str):
        """Delete memory by ID"""
        try:
            self.collection.delete(ids=[memory_id])
            print(f"✅ Deleted memory: {memory_id}")
        except Exception as e:
            raise MemorySystemError(
                f"Failed to delete memory: {str(e)}",
                context={"memory_id": memory_id}
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        try:
            count = self.collection.count()

            # Get all memories to calculate stats
            all_memories = self.collection.get()
            
            # Category breakdown
            categories = {}
            importance_avg = 0
            
            if all_memories['metadatas']:
                for meta in all_memories['metadatas']:
                    cat = meta.get('category', 'unknown')
                    categories[cat] = categories.get(cat, 0) + 1
                    
                    imp = meta.get('importance', 5)
                    if isinstance(imp, str):
                        imp = int(imp)
                    importance_avg += imp
                
                importance_avg = round(importance_avg / len(all_memories['metadatas']), 2)
            
            return {
                "total_memories": count,
                "categories": categories,
                "average_importance": importance_avg,
                "storage_path": self.chromadb_path
            }
        
        except Exception as e:
            print(f"⚠️  Failed to get stats: {e}")
            return {"total_memories": 0}


# ============================================
# TESTING
# ============================================

def test_memory_system():
    """Test the memory system"""
    print("\n🧪 TESTING MEMORY SYSTEM")
    print("="*60)
    
    # Use test path
    test_path = "./data/chromadb_test"
    
    # Clean up old test data
    import shutil
    if os.path.exists(test_path):
        shutil.rmtree(test_path)
    
    # Initialize
    try:
        memory = MemorySystem(chromadb_path=test_path)
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        print("   (Ollama might not be running - that's okay!)")
        return
    
    # Test 1: Insert memories
    print("\n💾 Test 1: Insert memories")
    try:
        mem1 = memory.insert(
            content="User prefers chocolate ice cream",
            category=MemoryCategory.PREFERENCE,
            importance=7,
            tags=["user", "food"]
        )
        
        mem2 = memory.insert(
            content="Late night coding session to fix memory bugs was successful",
            category=MemoryCategory.RELATIONSHIP_MOMENT,
            importance=9,
            tags=["coding", "milestone"]
        )
        
        mem3 = memory.insert(
            content="The OpenRouter API key format is sk-or-v1-...",
            category=MemoryCategory.FACT,
            importance=5,
            tags=["technical"]
        )
        
        print(f"✅ Inserted 3 memories")
    except MemorySystemError as e:
        print(e)
        return
    
    # Test 2: Search
    print("\n🔍 Test 2: Semantic search")
    try:
        results = memory.search(
            query="What does the user like to eat?",
            n_results=5
        )
        
        print(f"✅ Found {len(results)} results:")
        for r in results:
            print(f"   • [{r['category']}] {r['content'][:60]}...")
            print(f"     Importance: {r['importance']}, Relevance: {r['relevance']}, Score: {r['score']}")
    except MemorySystemError as e:
        print(e)
        return
    
    # Test 3: Category filter
    print("\n🎯 Test 3: Filter by category")
    try:
        results = memory.search(
            query="important moments",
            category=MemoryCategory.RELATIONSHIP_MOMENT,
            n_results=5
        )
        
        print(f"✅ Found {len(results)} relationship moments")
        for r in results:
            print(f"   • {r['content'][:60]}...")
    except MemorySystemError as e:
        print(e)
        return
    
    # Test 4: Importance filter
    print("\n⭐ Test 4: High importance only")
    try:
        results = memory.search(
            query="building project",
            min_importance=8,
            n_results=5
        )
        
        print(f"✅ Found {len(results)} high-importance memories")
        for r in results:
            print(f"   • [Imp: {r['importance']}] {r['content'][:60]}...")
    except MemorySystemError as e:
        print(e)
        return
    
    # Test 5: Stats
    print("\n📊 Test 5: Memory statistics")
    stats = memory.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    # Cleanup
    shutil.rmtree(test_path)
    print(f"\n✅ Cleaned up test data")
    
    print("\n✅ ALL TESTS PASSED!")
    print("="*60)


def _log_hebbian_retrieval(query: str, seed_ids: list, association_log: list, final_results: list):
    """
    Comprehensive logging for Hebbian retrieval monitoring.

    Log format is grep-able for drift analysis:
    - [HEBBIAN] prefix on all lines
    - [HEBBIAN:INCLUDED] for memories that made it into context
    - [HEBBIAN:SKIPPED] for filtered out associations
    - [HEBBIAN:STATS] for summary statistics
    """
    included = [l for l in association_log if l.get('action') == 'INCLUDED']
    skipped_dup = [l for l in association_log if l.get('action') == 'SKIPPED_DUPLICATE']
    skipped_collected = [l for l in association_log if l.get('action') == 'SKIPPED_ALREADY_COLLECTED']
    candidates = [l for l in association_log if l.get('action') == 'CANDIDATE']
    failed = [l for l in association_log if l.get('action') == 'FETCH_FAILED']

    print(f"\n{'─'*60}")
    print(f"[HEBBIAN:STATS] Query: \"{query[:60]}{'...' if len(query) > 60 else ''}\"")
    print(f"[HEBBIAN:STATS] Seeds: {len(seed_ids)} | Candidates: {len(candidates)} | "
          f"Included: {len(included)} | Skipped(dup): {len(skipped_dup)} | "
          f"Skipped(collected): {len(skipped_collected)} | Failed: {len(failed)}")

    if included:
        print(f"[HEBBIAN:INCLUDED] ── Memories added via association ──")
        for entry in included:
            seed_short = entry.get('seed_id', '?')[:12]
            assoc_short = entry.get('assoc_id', '?')[:12]
            print(f"[HEBBIAN:INCLUDED]   Seed {seed_short}... "
                  f"→ Assoc {assoc_short}... "
                  f"(strength: {entry.get('strength', 0):.3f}) "
                  f"│ \"{entry.get('content_preview', 'N/A')}\"")
    else:
        print(f"[HEBBIAN:STATS] No associations met threshold — semantic-only results")

    if skipped_dup:
        print(f"[HEBBIAN:SKIPPED] {len(skipped_dup)} associations already in semantic results (good — reduces redundancy)")

    if failed:
        print(f"[HEBBIAN:FAILED] {len(failed)} association fetches failed:")
        for entry in failed:
            print(f"[HEBBIAN:FAILED]   {entry.get('assoc_id', '?')}: {entry.get('error', 'unknown')}")

    print(f"{'─'*60}\n")


def format_hebbian_for_prompt(hebbian_results: list) -> str:
    """
    Format Hebbian-associated memories for prompt injection with clear labeling.

    Each memory is marked as associative (not direct search match) so the AI
    can appropriately weight the context.

    Args:
        hebbian_results: List of memory dicts with 'hebbian_metadata'

    Returns:
        Formatted string for system prompt injection, or empty string
    """
    if not hebbian_results:
        return ""

    lines = ["## Associated Context (via memory associations — not direct search matches)"]
    lines.append("These memories surfaced because they're historically connected to relevant topics.")
    lines.append("They may or may not be directly relevant to the current conversation.\n")

    for i, result in enumerate(hebbian_results):
        content = result.get('content', '')
        heb_meta = result.get('hebbian_metadata', {})
        mem_meta = result.get('metadata', {})

        strength = heb_meta.get('association_strength', 0)

        timestamp = mem_meta.get('timestamp') or mem_meta.get('created_at') or 'unknown date'

        tags = result.get('tags', [])
        tag_str = f" [{', '.join(tags)}]" if tags else ""

        lines.append(
            f"{i+1}. [ASSOCIATED — strength: {strength:.2f} — from: {timestamp}]{tag_str}\n"
            f"   {content}\n"
        )

    return "\n".join(lines)


if __name__ == "__main__":
    """Run tests if executed directly"""
    test_memory_system()


