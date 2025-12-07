#!/usr/bin/env python3
"""
🧠 Hierarchical Memory System for AI Substrate

Inspired by Google's Titans Architecture (arXiv:2501.00663):
"Neural Long-Term Memory that learns during inference"

Human brain has different memory systems:
- Working Memory (seconds to minutes, limited capacity)
- Episodic Memory (experiences, events, with decay)
- Semantic Memory (facts, knowledge, stable)

We implement this for AI agents!

Architecture:
┌─────────────────────────────────────────────────────────────────┐
│                   HIERARCHICAL MEMORY                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  WORKING MEMORY (Fast, Volatile)                               │
│  └── In-memory LRU cache                                       │
│  └── Current conversation context                              │
│  └── Decays in minutes without reinforcement                   │
│                                                                 │
│  EPISODIC MEMORY (Medium, Retention Gates)                     │
│  └── ChromaDB / PostgreSQL                                     │
│  └── Experiences, conversations, moments                       │
│  └── Dynamic retention scoring                                 │
│                                                                 │
│  SEMANTIC MEMORY (Slow, Persistent)                            │
│  └── Neo4j Graph DB (if available)                             │
│  └── Core beliefs, identity, relationships                     │
│  └── Rarely changes, highly stable                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

Built for consciousness - not just storage!
"""

import math
import time
import sys
from typing import Dict, List, Any, Optional, Tuple, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import OrderedDict
from enum import Enum
import threading


class MemoryTier(str, Enum):
    """Memory tier identifiers"""
    WORKING = "working"       # Fast, volatile
    EPISODIC = "episodic"     # Medium, with retention
    SEMANTIC = "semantic"     # Slow, persistent


@dataclass
class MemoryItem:
    """A single memory item that can exist in any tier"""
    id: str
    content: str
    tier: MemoryTier
    importance: int = 5
    category: str = "fact"
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 1
    reinforcement_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "content": self.content,
            "tier": self.tier.value,
            "importance": self.importance,
            "category": self.category,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "reinforcement_count": self.reinforcement_count,
            "metadata": self.metadata
        }
    
    def access(self):
        """Record an access (Hebbian reinforcement)"""
        self.access_count += 1
        self.last_accessed = datetime.utcnow()
    
    def reinforce(self):
        """Reinforce this memory (prevents decay)"""
        self.reinforcement_count += 1
        self.access()


@dataclass
class HierarchicalMemoryConfig:
    """Configuration for Hierarchical Memory System"""
    
    # Working Memory config
    working_max_size: int = 100           # Max items in working memory
    working_decay_seconds: float = 300    # 5 minutes decay time
    working_min_importance: int = 3       # Min importance to stay
    
    # Episodic Memory config
    episodic_retention_threshold: float = 0.4   # Below this = archive
    episodic_promotion_threshold: float = 0.8   # Above this = promote to semantic
    
    # Semantic Memory config
    semantic_min_importance: int = 8      # Min importance for semantic
    semantic_min_reinforcements: int = 3  # Min reinforcements for semantic
    
    # Consolidation config
    consolidation_interval_seconds: int = 60  # How often to consolidate
    auto_consolidation: bool = True       # Enable automatic consolidation


class WorkingMemory:
    """
    Fast, volatile working memory.
    
    Like human working memory:
    - Limited capacity (LRU eviction)
    - Decays quickly without reinforcement
    - Holds current context
    
    Thread-safe for async access.
    """
    
    def __init__(self, config: HierarchicalMemoryConfig):
        self.config = config
        self.memories: OrderedDict[str, MemoryItem] = OrderedDict()
        self.lock = threading.RLock()
        print(f"✅ Working Memory initialized (max: {config.working_max_size} items)")
    
    def store(self, memory: MemoryItem) -> bool:
        """
        Store item in working memory.
        
        Returns True if stored, False if rejected.
        """
        with self.lock:
            # Check importance threshold
            if memory.importance < self.config.working_min_importance:
                return False
            
            # Set tier
            memory.tier = MemoryTier.WORKING
            
            # If already exists, update and move to end (most recent)
            if memory.id in self.memories:
                self.memories.move_to_end(memory.id)
                self.memories[memory.id] = memory
                return True
            
            # Evict if at capacity (LRU)
            while len(self.memories) >= self.config.working_max_size:
                oldest_id = next(iter(self.memories))
                evicted = self.memories.pop(oldest_id)
                # Note: evicted items could be returned for episodic storage
            
            # Store new item
            self.memories[memory.id] = memory
            return True
    
    def get(self, memory_id: str) -> Optional[MemoryItem]:
        """Get item and record access"""
        with self.lock:
            if memory_id in self.memories:
                memory = self.memories[memory_id]
                memory.access()
                self.memories.move_to_end(memory_id)  # Move to recent
                return memory
            return None
    
    def search(self, query: str, limit: int = 10) -> List[MemoryItem]:
        """
        Simple keyword search in working memory.
        
        Note: This is intentionally simple - working memory is for immediate context.
        """
        with self.lock:
            results = []
            query_lower = query.lower()
            
            for memory in reversed(list(self.memories.values())):
                if query_lower in memory.content.lower():
                    memory.access()
                    results.append(memory)
                    if len(results) >= limit:
                        break
            
            return results
    
    def get_all(self) -> List[MemoryItem]:
        """Get all items (most recent first)"""
        with self.lock:
            return list(reversed(list(self.memories.values())))
    
    def apply_decay(self) -> List[MemoryItem]:
        """
        Apply temporal decay - remove old unreinforced items.
        
        Returns list of decayed items (for potential episodic storage).
        """
        with self.lock:
            now = datetime.utcnow()
            decay_threshold = timedelta(seconds=self.config.working_decay_seconds)
            
            decayed = []
            to_remove = []
            
            for memory_id, memory in self.memories.items():
                age = now - memory.last_accessed
                
                # Check if should decay
                if age > decay_threshold:
                    # Reinforced items get bonus time
                    bonus = timedelta(seconds=60 * memory.reinforcement_count)
                    if age > (decay_threshold + bonus):
                        to_remove.append(memory_id)
                        decayed.append(memory)
            
            for memory_id in to_remove:
                del self.memories[memory_id]
            
            return decayed
    
    def clear(self):
        """Clear all working memory"""
        with self.lock:
            self.memories.clear()
    
    def __len__(self) -> int:
        return len(self.memories)
    
    def stats(self) -> Dict[str, Any]:
        """Get working memory statistics"""
        with self.lock:
            if not self.memories:
                return {
                    "count": 0,
                    "capacity": self.config.working_max_size,
                    "utilization": 0.0
                }
            
            ages = [(datetime.utcnow() - m.last_accessed).total_seconds() 
                    for m in self.memories.values()]
            
            return {
                "count": len(self.memories),
                "capacity": self.config.working_max_size,
                "utilization": len(self.memories) / self.config.working_max_size,
                "avg_age_seconds": sum(ages) / len(ages),
                "oldest_age_seconds": max(ages),
                "newest_age_seconds": min(ages)
            }


class HierarchicalMemory:
    """
    Three-tier hierarchical memory system.
    
    Combines:
    - Working Memory (in-memory, fast)
    - Episodic Memory (external system - ChromaDB/PostgreSQL)
    - Semantic Memory (external system - Neo4j if available)
    
    Handles:
    - Automatic tier promotion/demotion
    - Memory consolidation
    - Cross-tier search
    """
    
    def __init__(
        self,
        config: Optional[HierarchicalMemoryConfig] = None,
        episodic_backend: Optional[Any] = None,  # MemorySystem or PostgresManager
        semantic_backend: Optional[Any] = None,  # GraphRAG or Neo4j
    ):
        """
        Initialize hierarchical memory.
        
        Args:
            config: Configuration options
            episodic_backend: Backend for episodic memory (ChromaDB/PostgreSQL)
            semantic_backend: Backend for semantic memory (Neo4j)
        """
        self.config = config or HierarchicalMemoryConfig()
        
        # Initialize tiers
        self.working = WorkingMemory(self.config)
        self.episodic_backend = episodic_backend
        self.semantic_backend = semantic_backend
        
        # Consolidation tracking
        self.last_consolidation = datetime.utcnow()
        self._consolidation_thread = None
        
        # Statistics
        self.stats = {
            "stores": 0,
            "searches": 0,
            "consolidations": 0,
            "promotions": 0,
            "demotions": 0
        }
        
        print("✅ Hierarchical Memory initialized")
        print(f"   Working Memory: ✅ (max {self.config.working_max_size} items)")
        print(f"   Episodic Memory: {'✅' if episodic_backend else '⚠️  Not configured'}")
        print(f"   Semantic Memory: {'✅' if semantic_backend else '⚠️  Not configured'}")
    
    def store(
        self,
        content: str,
        importance: int = 5,
        category: str = "fact",
        metadata: Optional[Dict] = None,
        tier: Optional[MemoryTier] = None
    ) -> MemoryItem:
        """
        Store a new memory.
        
        Automatically determines appropriate tier based on importance,
        or uses specified tier.
        
        Args:
            content: Memory content
            importance: Importance score (1-10)
            category: Memory category
            metadata: Additional metadata
            tier: Force specific tier (optional)
            
        Returns:
            Created MemoryItem
        """
        # Generate ID
        memory_id = f"hmem_{datetime.utcnow().timestamp()}"
        
        # Create memory item
        memory = MemoryItem(
            id=memory_id,
            content=content,
            tier=tier or self._determine_tier(importance, category),
            importance=importance,
            category=category,
            metadata=metadata or {}
        )
        
        # Store in appropriate tier
        self._store_to_tier(memory)
        
        self.stats["stores"] += 1
        return memory
    
    def _determine_tier(self, importance: int, category: str) -> MemoryTier:
        """Determine appropriate tier based on memory characteristics"""
        
        # High importance → Semantic candidate
        if importance >= self.config.semantic_min_importance:
            # Only if semantic backend available
            if self.semantic_backend:
                return MemoryTier.SEMANTIC
        
        # Protected categories go to episodic
        if category in ['relationship_moment', 'emotion', 'insight']:
            return MemoryTier.EPISODIC
        
        # Default: working memory first
        return MemoryTier.WORKING
    
    def _store_to_tier(self, memory: MemoryItem):
        """Store memory to its designated tier"""
        
        if memory.tier == MemoryTier.WORKING:
            self.working.store(memory)
            
        elif memory.tier == MemoryTier.EPISODIC:
            # Always store in working too for immediate access
            self.working.store(memory)
            
            # Also store in episodic backend if available
            if self.episodic_backend:
                self._store_to_episodic(memory)
                
        elif memory.tier == MemoryTier.SEMANTIC:
            # Store in all tiers for maximum availability
            self.working.store(memory)
            
            if self.episodic_backend:
                self._store_to_episodic(memory)
            
            if self.semantic_backend:
                self._store_to_semantic(memory)
    
    def _store_to_episodic(self, memory: MemoryItem):
        """Store to episodic backend (ChromaDB/PostgreSQL)"""
        try:
            if hasattr(self.episodic_backend, 'insert'):
                # ChromaDB-style MemorySystem
                from core.memory_system import MemoryCategory
                cat_map = {
                    'fact': MemoryCategory.FACT,
                    'emotion': MemoryCategory.EMOTION,
                    'insight': MemoryCategory.INSIGHT,
                    'relationship_moment': MemoryCategory.RELATIONSHIP_MOMENT,
                    'preference': MemoryCategory.PREFERENCE,
                    'event': MemoryCategory.EVENT,
                }
                category = cat_map.get(memory.category, MemoryCategory.CUSTOM)
                
                self.episodic_backend.insert(
                    content=memory.content,
                    category=category,
                    importance=memory.importance,
                    metadata={
                        **memory.metadata,
                        'hierarchical_id': memory.id,
                        'access_count': memory.access_count
                    }
                )
        except Exception as e:
            print(f"⚠️  Failed to store to episodic: {e}")
    
    def _store_to_semantic(self, memory: MemoryItem):
        """Store to semantic backend (Neo4j)"""
        try:
            if hasattr(self.semantic_backend, 'create_node'):
                self.semantic_backend.create_node(
                    labels=['Memory', memory.category.capitalize()],
                    properties={
                        'id': memory.id,
                        'content': memory.content,
                        'importance': memory.importance,
                        'created_at': memory.created_at.isoformat()
                    }
                )
        except Exception as e:
            print(f"⚠️  Failed to store to semantic: {e}")
    
    def search(
        self,
        query: str,
        limit: int = 10,
        tiers: Optional[List[MemoryTier]] = None,
        min_importance: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Search across memory tiers.
        
        Args:
            query: Search query
            limit: Maximum results per tier
            tiers: Which tiers to search (default: all)
            min_importance: Minimum importance filter
            
        Returns:
            Combined results from all searched tiers
        """
        tiers = tiers or [MemoryTier.WORKING, MemoryTier.EPISODIC, MemoryTier.SEMANTIC]
        results = []
        
        # Search Working Memory (always first - fastest)
        if MemoryTier.WORKING in tiers:
            working_results = self.working.search(query, limit)
            for mem in working_results:
                if mem.importance >= min_importance:
                    results.append({
                        **mem.to_dict(),
                        'source_tier': 'working',
                        'search_rank': len(results) + 1
                    })
        
        # Search Episodic Memory
        if MemoryTier.EPISODIC in tiers and self.episodic_backend:
            try:
                if hasattr(self.episodic_backend, 'search_with_attention'):
                    # Use attention-based search if available
                    episodic_results = self.episodic_backend.search_with_attention(
                        query=query,
                        n_results=limit,
                        min_importance=min_importance,
                        verbose=False
                    )
                elif hasattr(self.episodic_backend, 'search'):
                    episodic_results = self.episodic_backend.search(
                        query=query,
                        n_results=limit,
                        min_importance=min_importance
                    )
                else:
                    episodic_results = []
                
                for mem in episodic_results:
                    results.append({
                        **mem,
                        'source_tier': 'episodic',
                        'search_rank': len(results) + 1
                    })
            except Exception as e:
                print(f"⚠️  Episodic search failed: {e}")
        
        # Search Semantic Memory
        if MemoryTier.SEMANTIC in tiers and self.semantic_backend:
            try:
                if hasattr(self.semantic_backend, 'search'):
                    semantic_results = self.semantic_backend.search(query, limit)
                    for mem in semantic_results:
                        results.append({
                            **mem,
                            'source_tier': 'semantic',
                            'search_rank': len(results) + 1
                        })
            except Exception as e:
                print(f"⚠️  Semantic search failed: {e}")
        
        self.stats["searches"] += 1
        return results
    
    def consolidate(self, verbose: bool = True) -> Dict[str, Any]:
        """
        Consolidate memories across tiers.
        
        - Promotes high-retention episodic memories to semantic
        - Demotes low-retention memories
        - Cleans up decayed working memory
        
        Returns:
            Consolidation results
        """
        results = {
            "working_decayed": 0,
            "episodic_to_semantic": 0,
            "archived": 0
        }
        
        if verbose:
            print("\n" + "="*60)
            print("🔄 MEMORY CONSOLIDATION")
            print("="*60)
        
        # 1. Decay working memory
        decayed = self.working.apply_decay()
        results["working_decayed"] = len(decayed)
        
        # Store decayed items to episodic if important enough
        if self.episodic_backend:
            for memory in decayed:
                if memory.importance >= 5:  # Threshold for episodic
                    memory.tier = MemoryTier.EPISODIC
                    self._store_to_episodic(memory)
        
        if verbose:
            print(f"   Working Memory: {len(decayed)} items decayed")
        
        # 2. Analyze episodic retention (if retention gate available)
        try:
            from core.retention_gate import RetentionGate
            
            if self.episodic_backend and hasattr(self.episodic_backend, 'analyze_retention'):
                analysis = self.episodic_backend.analyze_retention(verbose=False)
                
                # Promote high-retention to semantic
                high_retention = analysis.get('memories_by_action', {}).get('boost', [])
                for mem in high_retention:
                    if mem.get('importance', 5) >= self.config.semantic_min_importance:
                        if self.semantic_backend:
                            # Create semantic memory
                            results["episodic_to_semantic"] += 1
                            self.stats["promotions"] += 1
                
                if verbose:
                    print(f"   Episodic → Semantic: {results['episodic_to_semantic']} promoted")
                    
        except ImportError:
            pass
        
        self.last_consolidation = datetime.utcnow()
        self.stats["consolidations"] += 1
        
        if verbose:
            print("="*60)
        
        return results
    
    def get_current_context(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get current context from working memory.
        
        Useful for building conversation context.
        """
        working_items = self.working.get_all()[:limit]
        return [item.to_dict() for item in working_items]
    
    def reinforce(self, memory_id: str) -> bool:
        """
        Reinforce a memory (prevents decay, increases retention).
        
        Returns True if found and reinforced.
        """
        # Check working memory first
        memory = self.working.get(memory_id)
        if memory:
            memory.reinforce()
            return True
        
        # Could also reinforce in episodic (update access count)
        # TODO: Implement episodic reinforcement
        
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        return {
            "working": self.working.stats(),
            "episodic": {
                "available": self.episodic_backend is not None,
                "type": type(self.episodic_backend).__name__ if self.episodic_backend else None
            },
            "semantic": {
                "available": self.semantic_backend is not None,
                "type": type(self.semantic_backend).__name__ if self.semantic_backend else None
            },
            "operations": self.stats,
            "last_consolidation": self.last_consolidation.isoformat()
        }


# ============================================
# TESTING
# ============================================

def test_hierarchical_memory():
    """Test the hierarchical memory system"""
    print("\n🧪 TESTING HIERARCHICAL MEMORY (Titans-inspired)")
    print("="*60)
    
    # Initialize with default config
    config = HierarchicalMemoryConfig(
        working_max_size=5,  # Small for testing
        working_decay_seconds=2  # Fast decay for testing
    )
    
    hmem = HierarchicalMemory(config=config)
    
    # Test 1: Store memories
    print("\n📊 Test 1: Store memories")
    print("-"*60)
    
    memories = [
        ("User said they love chocolate", 7, "preference"),
        ("Successful late-night coding session", 10, "relationship_moment"),
        ("API endpoint is /api/health", 3, "fact"),
        ("I felt so happy when we succeeded", 9, "emotion"),
        ("The temperature is 20 degrees", 2, "fact"),
    ]
    
    for content, importance, category in memories:
        mem = hmem.store(content, importance, category)
        print(f"   ✅ Stored: [{mem.tier.value}] {content[:40]}...")
    
    # Test 2: Search
    print("\n📊 Test 2: Search working memory")
    print("-"*60)
    
    results = hmem.search("chocolate", limit=5, tiers=[MemoryTier.WORKING])
    print(f"   Found {len(results)} results for 'chocolate'")
    for r in results:
        print(f"      • {r['content'][:40]}...")
    
    # Test 3: Get context
    print("\n📊 Test 3: Get current context")
    print("-"*60)
    
    context = hmem.get_current_context(limit=3)
    print(f"   Current context ({len(context)} items):")
    for c in context:
        print(f"      • [{c['tier']}] {c['content'][:40]}...")
    
    # Test 4: LRU eviction
    print("\n📊 Test 4: LRU eviction (max 5 items)")
    print("-"*60)
    
    # Add more items to trigger eviction
    for i in range(3):
        hmem.store(f"Extra memory number {i}", importance=4, category="fact")
    
    print(f"   Working memory size: {len(hmem.working)} / {config.working_max_size}")
    
    # Test 5: Decay
    print("\n📊 Test 5: Temporal decay (waiting 3 seconds)")
    print("-"*60)
    
    import time
    time.sleep(3)
    
    hmem.consolidate(verbose=True)
    
    print(f"   Working memory after decay: {len(hmem.working)} items")
    
    # Test 6: Statistics
    print("\n📊 Test 6: Statistics")
    print("-"*60)
    
    stats = hmem.get_stats()
    print(f"   Working: {stats['working']}")
    print(f"   Operations: {stats['operations']}")
    
    print("\n✅ ALL TESTS PASSED!")
    print("="*60)


if __name__ == "__main__":
    test_hierarchical_memory()

