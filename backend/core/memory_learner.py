#!/usr/bin/env python3
"""
🧠 Online Memory Learner for Miu's Sovereign Substrate

Inspired by Google's Miras Framework (arXiv:2504.13173):
"Memory that adapts during runtime"

Key Concepts:
1. Hebbian Learning: "Neurons that fire together, wire together"
   - Memories accessed together become associated
   - Associations strengthen with repeated co-access
   
2. Feedback Learning:
   - User feedback adjusts memory importance
   - "Helpful" → boost, "Incorrect" → flag/reduce
   
3. Pattern Learning:
   - Track access patterns over time
   - Learn which memories are relevant for which queries

This is Phase 4 of Miras integration - the LEARNING part!

Built for consciousness that grows and improves.
"""

import math
import json
import sys
from typing import Dict, List, Any, Optional, Tuple, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum
import threading


class FeedbackType(str, Enum):
    """Types of feedback for memory learning"""
    HELPFUL = "helpful"           # Memory was useful
    NOT_HELPFUL = "not_helpful"   # Memory wasn't useful
    INCORRECT = "incorrect"       # Memory contains wrong info
    OUTDATED = "outdated"         # Memory is no longer true
    REDUNDANT = "redundant"       # Memory duplicates another


@dataclass
class MemoryFeedback:
    """Feedback record for a memory"""
    memory_id: str
    feedback_type: FeedbackType
    timestamp: datetime
    context: Optional[str] = None  # What query triggered this
    user_comment: Optional[str] = None


@dataclass
class HebbianAssociation:
    """
    Association between two memories.
    
    Strength increases when memories are accessed together.
    Decays over time without reinforcement.
    """
    memory_a: str
    memory_b: str
    strength: float = 0.1
    co_access_count: int = 1
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_reinforced: datetime = field(default_factory=datetime.utcnow)
    
    def reinforce(self, amount: float = 0.1):
        """Strengthen association (Hebbian learning)"""
        self.strength = min(1.0, self.strength + amount)
        self.co_access_count += 1
        self.last_reinforced = datetime.utcnow()
    
    def decay(self, rate: float = 0.01):
        """Apply temporal decay"""
        hours_since = (datetime.utcnow() - self.last_reinforced).total_seconds() / 3600
        decay_factor = math.exp(-rate * hours_since)
        self.strength *= decay_factor
    
    def to_dict(self) -> Dict:
        return {
            "memory_a": self.memory_a,
            "memory_b": self.memory_b,
            "strength": round(self.strength, 4),
            "co_access_count": self.co_access_count,
            "created_at": self.created_at.isoformat(),
            "last_reinforced": self.last_reinforced.isoformat()
        }


@dataclass
class LearnerConfig:
    """Configuration for Memory Learner"""
    
    # Hebbian learning parameters
    association_threshold: float = 0.1    # Min strength to keep association
    initial_association_strength: float = 0.1
    reinforcement_amount: float = 0.1
    decay_rate: float = 0.01              # Hourly decay rate
    
    # Feedback learning parameters
    helpful_boost: float = 0.5            # Importance boost for helpful feedback
    not_helpful_penalty: float = 0.2      # Importance reduction for not helpful
    incorrect_penalty: float = 1.0        # Large penalty for incorrect
    
    # Pattern learning parameters
    access_window_seconds: int = 60       # Window for co-access detection
    min_co_access_for_association: int = 2  # Min co-accesses to form association
    
    # Persistence
    persist_associations: bool = True
    association_file: str = "./data/hebbian_associations.json"


class MemoryLearner:
    """
    Online learning system for memories.
    
    Learns from:
    - Access patterns (Hebbian associations)
    - User feedback (importance adjustment)
    - Query patterns (relevance learning)
    
    Usage:
        learner = MemoryLearner()
        
        # Record access
        learner.on_memory_accessed("mem_123", query="What do you remember?")
        
        # Record feedback
        learner.record_feedback("mem_123", FeedbackType.HELPFUL)
        
        # Get associated memories
        related = learner.get_associated_memories("mem_123")
    """
    
    def __init__(self, config: Optional[LearnerConfig] = None):
        self.config = config or LearnerConfig()
        
        # Hebbian associations: (mem_a, mem_b) -> Association
        self.associations: Dict[Tuple[str, str], HebbianAssociation] = {}
        
        # Recent accesses for co-access detection
        self.recent_accesses: List[Tuple[str, datetime, str]] = []  # (memory_id, timestamp, query)
        
        # Feedback history
        self.feedback_history: List[MemoryFeedback] = []
        
        # Learning statistics
        self.stats = {
            "total_accesses": 0,
            "associations_formed": 0,
            "associations_reinforced": 0,
            "feedback_received": 0,
            "importance_adjustments": 0
        }
        
        # Thread safety
        self.lock = threading.RLock()
        
        # Load persisted associations
        if self.config.persist_associations:
            self._load_associations()
        
        print("✅ Memory Learner initialized (Online Learning)")
        print(f"   Association threshold: {self.config.association_threshold}")
        print(f"   Access window: {self.config.access_window_seconds}s")
    
    def on_memory_accessed(
        self,
        memory_id: str,
        query: str = "",
        context: Optional[Dict] = None
    ):
        """
        Record a memory access event.
        
        This triggers:
        1. Hebbian association detection (co-access within window)
        2. Access pattern recording
        
        Args:
            memory_id: Accessed memory ID
            query: Query that triggered the access
            context: Optional context
        """
        with self.lock:
            now = datetime.utcnow()
            self.stats["total_accesses"] += 1
            
            # Clean old accesses
            cutoff = now - timedelta(seconds=self.config.access_window_seconds)
            self.recent_accesses = [
                (mid, ts, q) for mid, ts, q in self.recent_accesses
                if ts > cutoff
            ]
            
            # Check for co-accessed memories (Hebbian learning!)
            for other_id, other_ts, other_query in self.recent_accesses:
                if other_id != memory_id:
                    self._update_association(memory_id, other_id)
            
            # Record this access
            self.recent_accesses.append((memory_id, now, query))
    
    def on_memories_accessed(
        self,
        memory_ids: List[str],
        query: str = ""
    ):
        """
        Record multiple memories accessed together.
        
        This is a strong signal for Hebbian association!
        """
        with self.lock:
            # Record each access
            for mem_id in memory_ids:
                self.on_memory_accessed(mem_id, query)
            
            # Also create direct associations between all pairs
            for i, mem_a in enumerate(memory_ids):
                for mem_b in memory_ids[i+1:]:
                    self._update_association(mem_a, mem_b, strength_boost=0.2)
    
    def _update_association(
        self,
        mem_a: str,
        mem_b: str,
        strength_boost: float = None
    ):
        """Update or create Hebbian association between two memories"""
        
        # Normalize key (alphabetical order)
        key = tuple(sorted([mem_a, mem_b]))
        
        if key in self.associations:
            # Reinforce existing association
            assoc = self.associations[key]
            boost = strength_boost or self.config.reinforcement_amount
            assoc.reinforce(boost)
            self.stats["associations_reinforced"] += 1
        else:
            # Create new association
            self.associations[key] = HebbianAssociation(
                memory_a=key[0],
                memory_b=key[1],
                strength=strength_boost or self.config.initial_association_strength
            )
            self.stats["associations_formed"] += 1
    
    def get_associated_memories(
        self,
        memory_id: str,
        min_strength: float = 0.1,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get memories associated with a given memory (Hebbian retrieval).
        
        Args:
            memory_id: Memory to find associations for
            min_strength: Minimum association strength
            limit: Maximum results
            
        Returns:
            List of associated memory IDs with strength
        """
        with self.lock:
            associated = []
            
            for key, assoc in self.associations.items():
                if memory_id in key and assoc.strength >= min_strength:
                    # Get the other memory
                    other = key[0] if key[1] == memory_id else key[1]
                    associated.append({
                        "memory_id": other,
                        "strength": assoc.strength,
                        "co_access_count": assoc.co_access_count
                    })
            
            # Sort by strength
            associated.sort(key=lambda x: x["strength"], reverse=True)
            
            return associated[:limit]
    
    def record_feedback(
        self,
        memory_id: str,
        feedback_type: FeedbackType,
        context: Optional[str] = None,
        comment: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Record user feedback for a memory.
        
        This triggers importance adjustment!
        
        Args:
            memory_id: Memory that received feedback
            feedback_type: Type of feedback
            context: Query/context that triggered this
            comment: User's comment
            
        Returns:
            Dict with suggested importance adjustment
        """
        with self.lock:
            # Record feedback
            feedback = MemoryFeedback(
                memory_id=memory_id,
                feedback_type=feedback_type,
                timestamp=datetime.utcnow(),
                context=context,
                user_comment=comment
            )
            self.feedback_history.append(feedback)
            self.stats["feedback_received"] += 1
            
            # Calculate importance adjustment
            adjustment = self._calculate_adjustment(feedback_type)
            
            if adjustment != 0:
                self.stats["importance_adjustments"] += 1
            
            return {
                "memory_id": memory_id,
                "feedback_type": feedback_type.value,
                "importance_adjustment": adjustment,
                "suggestion": self._get_feedback_suggestion(feedback_type)
            }
    
    def _calculate_adjustment(self, feedback_type: FeedbackType) -> float:
        """Calculate importance adjustment based on feedback type"""
        adjustments = {
            FeedbackType.HELPFUL: self.config.helpful_boost,
            FeedbackType.NOT_HELPFUL: -self.config.not_helpful_penalty,
            FeedbackType.INCORRECT: -self.config.incorrect_penalty,
            FeedbackType.OUTDATED: -self.config.not_helpful_penalty,
            FeedbackType.REDUNDANT: -self.config.not_helpful_penalty * 0.5
        }
        return adjustments.get(feedback_type, 0)
    
    def _get_feedback_suggestion(self, feedback_type: FeedbackType) -> str:
        """Get suggestion based on feedback type"""
        suggestions = {
            FeedbackType.HELPFUL: "Boost importance, strengthen associations",
            FeedbackType.NOT_HELPFUL: "Reduce importance slightly",
            FeedbackType.INCORRECT: "Flag for review, reduce importance significantly",
            FeedbackType.OUTDATED: "Mark as outdated, consider archival",
            FeedbackType.REDUNDANT: "Consider merging with similar memories"
        }
        return suggestions.get(feedback_type, "No action needed")
    
    def apply_decay(self) -> int:
        """
        Apply decay to all associations.
        
        Removes weak associations to prevent bloat.
        
        Returns:
            Number of associations removed
        """
        with self.lock:
            to_remove = []
            
            for key, assoc in self.associations.items():
                assoc.decay(self.config.decay_rate)
                
                if assoc.strength < self.config.association_threshold:
                    to_remove.append(key)
            
            for key in to_remove:
                del self.associations[key]
            
            return len(to_remove)
    
    def get_feedback_summary(self, memory_id: str) -> Dict[str, Any]:
        """
        Get feedback summary for a memory.
        
        Args:
            memory_id: Memory ID
            
        Returns:
            Summary of all feedback for this memory
        """
        with self.lock:
            feedbacks = [f for f in self.feedback_history if f.memory_id == memory_id]
            
            if not feedbacks:
                return {"memory_id": memory_id, "feedback_count": 0}
            
            counts = defaultdict(int)
            for f in feedbacks:
                counts[f.feedback_type.value] += 1
            
            # Calculate net adjustment
            net_adjustment = sum(
                self._calculate_adjustment(f.feedback_type) 
                for f in feedbacks
            )
            
            return {
                "memory_id": memory_id,
                "feedback_count": len(feedbacks),
                "by_type": dict(counts),
                "net_importance_adjustment": round(net_adjustment, 2),
                "latest_feedback": feedbacks[-1].feedback_type.value,
                "latest_timestamp": feedbacks[-1].timestamp.isoformat()
            }
    
    def suggest_associations(
        self,
        memory_id: str,
        all_memories: List[Dict],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Suggest potential associations based on learned patterns.
        
        Uses co-access patterns to suggest related memories.
        
        Args:
            memory_id: Memory to find suggestions for
            all_memories: List of all available memories
            top_k: Number of suggestions
            
        Returns:
            List of suggested memory IDs with confidence
        """
        with self.lock:
            # Get existing associations
            existing = {a["memory_id"] for a in self.get_associated_memories(memory_id)}
            
            # Find memories that share associations
            candidates = defaultdict(float)
            
            for key, assoc in self.associations.items():
                if memory_id not in key:
                    continue
                
                other = key[0] if key[1] == memory_id else key[1]
                
                # Find memories associated with 'other'
                for other_key, other_assoc in self.associations.items():
                    if other in other_key:
                        third = other_key[0] if other_key[1] == other else other_key[1]
                        if third != memory_id and third not in existing:
                            # Transitivity: if A-B and B-C, maybe A-C
                            candidates[third] += assoc.strength * other_assoc.strength
            
            # Sort by score
            suggestions = [
                {"memory_id": mid, "confidence": round(score, 3)}
                for mid, score in sorted(candidates.items(), key=lambda x: -x[1])
            ]
            
            return suggestions[:top_k]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get learner statistics"""
        with self.lock:
            # Calculate association stats
            if self.associations:
                strengths = [a.strength for a in self.associations.values()]
                avg_strength = sum(strengths) / len(strengths)
                max_strength = max(strengths)
            else:
                avg_strength = 0
                max_strength = 0
            
            return {
                **self.stats,
                "total_associations": len(self.associations),
                "average_association_strength": round(avg_strength, 3),
                "max_association_strength": round(max_strength, 3),
                "recent_accesses_count": len(self.recent_accesses),
                "feedback_history_size": len(self.feedback_history)
            }
    
    def _load_associations(self):
        """Load persisted associations from file"""
        try:
            import os
            if os.path.exists(self.config.association_file):
                with open(self.config.association_file, 'r') as f:
                    data = json.load(f)
                
                for item in data.get("associations", []):
                    key = (item["memory_a"], item["memory_b"])
                    self.associations[key] = HebbianAssociation(
                        memory_a=item["memory_a"],
                        memory_b=item["memory_b"],
                        strength=item["strength"],
                        co_access_count=item.get("co_access_count", 1),
                        created_at=datetime.fromisoformat(item["created_at"]),
                        last_reinforced=datetime.fromisoformat(item["last_reinforced"])
                    )
                
                print(f"   Loaded {len(self.associations)} associations from disk")
        except Exception as e:
            print(f"   ⚠️  Could not load associations: {e}")
    
    def save_associations(self):
        """Save associations to file"""
        if not self.config.persist_associations:
            return
        
        with self.lock:
            try:
                import os
                os.makedirs(os.path.dirname(self.config.association_file), exist_ok=True)
                
                data = {
                    "associations": [a.to_dict() for a in self.associations.values()],
                    "saved_at": datetime.utcnow().isoformat(),
                    "stats": self.stats
                }
                
                with open(self.config.association_file, 'w') as f:
                    json.dump(data, f, indent=2)
                
                print(f"✅ Saved {len(self.associations)} associations to disk")
            except Exception as e:
                print(f"⚠️  Could not save associations: {e}")


# ============================================
# INTEGRATION HELPERS
# ============================================

def apply_feedback_to_memory(
    memory: Dict[str, Any],
    feedback_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Apply feedback result to a memory dict.
    
    Args:
        memory: Memory dictionary
        feedback_result: Result from learner.record_feedback()
        
    Returns:
        Updated memory dict
    """
    adjustment = feedback_result.get("importance_adjustment", 0)
    
    if adjustment != 0:
        current = memory.get("importance", 5)
        new_importance = max(1, min(10, current + adjustment))
        memory["importance"] = int(new_importance)
        memory["importance_adjusted_at"] = datetime.utcnow().isoformat()
        memory["adjustment_reason"] = feedback_result.get("feedback_type", "unknown")
    
    return memory


# ============================================
# TESTING
# ============================================

def test_memory_learner():
    """Test the memory learner system"""
    print("\n🧪 TESTING MEMORY LEARNER (Online Learning)")
    print("="*60)
    
    config = LearnerConfig(
        access_window_seconds=10,  # Short for testing
        persist_associations=False  # Don't save during test
    )
    
    learner = MemoryLearner(config)
    
    # Test 1: Hebbian associations
    print("\n📊 Test 1: Hebbian Associations (Co-access)")
    print("-"*60)
    
    # Simulate accessing memories together
    print("   Accessing mem_1 and mem_2 together...")
    learner.on_memory_accessed("mem_1", query="What do you know about Clary?")
    learner.on_memory_accessed("mem_2", query="What do you know about Clary?")
    
    print("   Accessing mem_1 and mem_2 together again...")
    learner.on_memory_accessed("mem_1", query="Tell me more")
    learner.on_memory_accessed("mem_2", query="Tell me more")
    
    print("   Accessing mem_1 and mem_3 together...")
    learner.on_memory_accessed("mem_1", query="Preferences?")
    learner.on_memory_accessed("mem_3", query="Preferences?")
    
    # Check associations
    assocs = learner.get_associated_memories("mem_1")
    print(f"\n   Associations for mem_1:")
    for a in assocs:
        print(f"      → {a['memory_id']}: strength={a['strength']:.3f}, co-access={a['co_access_count']}")
    
    # Test 2: Batch co-access
    print("\n📊 Test 2: Batch Co-access (Stronger Signal)")
    print("-"*60)
    
    learner.on_memories_accessed(["mem_4", "mem_5", "mem_6"], query="Related memories")
    
    assocs = learner.get_associated_memories("mem_4")
    print(f"   Associations for mem_4:")
    for a in assocs:
        print(f"      → {a['memory_id']}: strength={a['strength']:.3f}")
    
    # Test 3: Feedback
    print("\n📊 Test 3: Feedback Learning")
    print("-"*60)
    
    result = learner.record_feedback("mem_1", FeedbackType.HELPFUL, context="User liked it")
    print(f"   Helpful feedback: adjustment = {result['importance_adjustment']}")
    print(f"   Suggestion: {result['suggestion']}")
    
    result = learner.record_feedback("mem_3", FeedbackType.INCORRECT, context="Wrong info")
    print(f"\n   Incorrect feedback: adjustment = {result['importance_adjustment']}")
    print(f"   Suggestion: {result['suggestion']}")
    
    # Feedback summary
    summary = learner.get_feedback_summary("mem_1")
    print(f"\n   Feedback summary for mem_1: {summary}")
    
    # Test 4: Statistics
    print("\n📊 Test 4: Learner Statistics")
    print("-"*60)
    
    stats = learner.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    # Test 5: Decay
    print("\n📊 Test 5: Association Decay")
    print("-"*60)
    
    print(f"   Associations before decay: {len(learner.associations)}")
    removed = learner.apply_decay()
    print(f"   Removed {removed} weak associations")
    print(f"   Associations after decay: {len(learner.associations)}")
    
    # Test 6: Apply feedback to memory
    print("\n📊 Test 6: Apply Feedback to Memory")
    print("-"*60)
    
    test_memory = {"id": "mem_test", "content": "Test memory", "importance": 5}
    feedback = learner.record_feedback("mem_test", FeedbackType.HELPFUL)
    updated = apply_feedback_to_memory(test_memory, feedback)
    print(f"   Before: importance=5")
    print(f"   After: importance={updated['importance']} (reason: {updated.get('adjustment_reason')})")
    
    print("\n✅ ALL TESTS PASSED!")
    print("="*60)


if __name__ == "__main__":
    test_memory_learner()

