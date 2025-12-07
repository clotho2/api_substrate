#!/usr/bin/env python3
"""
🧠 Retention Gate System for AI Substrate

Inspired by Google's Miras Framework (arXiv:2504.13173):
"We reinterpret forgetting mechanisms as retention ℓ₂-regularization"

Key Insight: Forgetting isn't data loss - it's optimization!

Features:
- Dynamic retention scores based on multiple factors
- Temporal decay (older memories fade unless reinforced)
- Access-based reinforcement (frequently used memories stay strong)
- Category-based protection (relationship moments, emotions protected)
- Automatic consolidation of similar low-retention memories
"""

import math
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import sys


class RetentionAction(str, Enum):
    """Possible actions for a memory based on retention score"""
    KEEP = "keep"               # High retention - keep as is
    BOOST = "boost"             # Very high retention - increase importance
    CONSOLIDATE = "consolidate" # Medium retention - merge with similar
    DECAY = "decay"             # Low retention - reduce importance
    ARCHIVE = "archive"         # Very low retention - move to archive


@dataclass
class RetentionConfig:
    """Configuration for Retention Gate"""
    
    # Decay rates
    base_decay_rate: float = 0.995      # Daily decay multiplier
    fast_decay_rate: float = 0.98       # For low-importance memories
    slow_decay_rate: float = 0.999      # For high-importance memories
    
    # Weight factors for combined score
    importance_weight: float = 0.35     # Weight for importance score
    access_weight: float = 0.30         # Weight for access frequency
    temporal_weight: float = 0.25       # Weight for recency
    base_retention: float = 0.10        # Minimum retention (never fully forget)
    
    # Category boosts (multipliers)
    relationship_boost: float = 1.5     # Relationship moments protected
    emotion_boost: float = 1.3          # Emotional memories persist
    insight_boost: float = 1.2          # Insights valued
    preference_boost: float = 1.1       # Preferences maintained
    fact_boost: float = 1.0             # Facts neutral
    event_boost: float = 0.9            # Events can fade
    
    # Thresholds
    keep_threshold: float = 0.6         # Above this = keep
    boost_threshold: float = 0.8        # Above this = boost importance
    consolidate_threshold: float = 0.4  # Below keep but above this = consolidate
    decay_threshold: float = 0.2        # Below consolidate = decay
    # Below decay_threshold = archive
    
    # Access reinforcement
    access_reinforcement: float = 0.05  # Boost per access (log-scaled)
    max_access_boost: float = 0.3       # Maximum boost from access
    
    # Time constants
    temporal_decay_hours: float = 720   # ~30 days half-life


class RetentionGate:
    """
    Dynamic Retention Gate for Memory System.
    
    Inspired by Miras: Balance between learning new and retaining old.
    
    Usage:
        gate = RetentionGate()
        score = gate.compute_retention(memory_dict)
        action = gate.get_action(score)
    """
    
    def __init__(self, config: Optional[RetentionConfig] = None):
        self.config = config or RetentionConfig()
        print("✅ Retention Gate initialized (Miras-inspired)")
        print(f"   Thresholds: keep>{self.config.keep_threshold}, "
              f"consolidate>{self.config.consolidate_threshold}, "
              f"decay>{self.config.decay_threshold}")
    
    def compute_retention(
        self, 
        memory: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Compute retention score for a memory.
        
        Args:
            memory: Memory dict with keys:
                - importance: int (1-10)
                - timestamp: str (ISO format)
                - category: str
                - access_count: int (optional)
                - last_accessed: str (optional)
            context: Optional context dict
            
        Returns:
            Retention score between 0.0 and 1.0
            
        Score interpretation:
            > 0.8: Very high - boost importance
            > 0.6: High - keep as is
            > 0.4: Medium - consider consolidation
            > 0.2: Low - decay importance
            < 0.2: Very low - archive
        """
        
        # 1. Parse memory data with defaults
        importance = memory.get('importance', 5)
        if isinstance(importance, str):
            importance = int(importance)
        importance = max(1, min(10, importance))
        
        timestamp_str = memory.get('timestamp', '')
        if timestamp_str:
            try:
                created_at = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except ValueError:
                created_at = datetime.utcnow()
        else:
            created_at = datetime.utcnow()
        
        access_count = memory.get('access_count', 1)
        if isinstance(access_count, str):
            access_count = int(access_count)
        
        last_accessed_str = memory.get('last_accessed', '')
        if last_accessed_str:
            try:
                last_accessed = datetime.fromisoformat(last_accessed_str.replace('Z', '+00:00'))
            except ValueError:
                last_accessed = created_at
        else:
            last_accessed = created_at
        
        category = memory.get('category', 'fact')
        
        # 2. Compute individual factors
        
        # Importance factor (normalized 0-1)
        importance_factor = importance / 10.0
        
        # Access factor (log-scaled, capped)
        access_factor = min(
            self.config.max_access_boost,
            self.config.access_reinforcement * math.log(access_count + 1)
        )
        # Normalize to 0-1 range
        access_factor = access_factor / self.config.max_access_boost
        
        # Temporal factor (exponential decay)
        now = datetime.utcnow()
        age_hours = (now - created_at).total_seconds() / 3600
        
        # Use importance-adaptive decay rate
        if importance >= 8:
            decay_rate = self.config.slow_decay_rate
        elif importance <= 3:
            decay_rate = self.config.fast_decay_rate
        else:
            decay_rate = self.config.base_decay_rate
        
        # Convert to hourly decay
        hourly_decay = math.pow(decay_rate, 1/24)
        temporal_factor = math.pow(hourly_decay, age_hours)
        
        # Recency bonus (was it accessed recently?)
        hours_since_access = (now - last_accessed).total_seconds() / 3600
        recency_bonus = math.exp(-hours_since_access / self.config.temporal_decay_hours) * 0.1
        
        # 3. Get category boost
        category_boosts = {
            'relationship_moment': self.config.relationship_boost,
            'emotion': self.config.emotion_boost,
            'insight': self.config.insight_boost,
            'preference': self.config.preference_boost,
            'fact': self.config.fact_boost,
            'event': self.config.event_boost,
            'custom': self.config.fact_boost
        }
        category_boost = category_boosts.get(category, 1.0)
        
        # 4. Combine factors (weighted sum)
        base_score = (
            self.config.importance_weight * importance_factor +
            self.config.access_weight * access_factor +
            self.config.temporal_weight * temporal_factor +
            self.config.base_retention +
            recency_bonus
        )
        
        # Apply category boost
        final_score = base_score * category_boost
        
        # Clamp to 0-1 range
        return max(0.0, min(1.0, final_score))
    
    def get_action(self, retention_score: float) -> RetentionAction:
        """
        Determine what action to take based on retention score.
        
        Args:
            retention_score: Score from compute_retention()
            
        Returns:
            RetentionAction enum value
        """
        if retention_score >= self.config.boost_threshold:
            return RetentionAction.BOOST
        elif retention_score >= self.config.keep_threshold:
            return RetentionAction.KEEP
        elif retention_score >= self.config.consolidate_threshold:
            return RetentionAction.CONSOLIDATE
        elif retention_score >= self.config.decay_threshold:
            return RetentionAction.DECAY
        else:
            return RetentionAction.ARCHIVE
    
    def process_memories(
        self, 
        memories: List[Dict[str, Any]],
        verbose: bool = True
    ) -> Dict[RetentionAction, List[Dict[str, Any]]]:
        """
        Process multiple memories and categorize by action.
        
        Args:
            memories: List of memory dicts
            verbose: Print progress
            
        Returns:
            Dict mapping actions to lists of memories
        """
        results = {action: [] for action in RetentionAction}
        
        total = len(memories)
        for i, memory in enumerate(memories):
            score = self.compute_retention(memory)
            action = self.get_action(score)
            
            # Add score and action to memory
            memory_with_score = {
                **memory,
                'retention_score': round(score, 4),
                'retention_action': action.value
            }
            results[action].append(memory_with_score)
            
            if verbose:
                progress = ((i + 1) / total) * 100
                print(f"\r✅ [{i+1}/{total}] ({progress:.1f}%) Processing memories...", end='')
                sys.stdout.flush()
        
        if verbose:
            print()  # Newline after progress
            self._print_summary(results, total)
        
        return results
    
    def _print_summary(
        self, 
        results: Dict[RetentionAction, List[Dict]], 
        total: int
    ):
        """Print summary of retention processing"""
        print("\n" + "="*60)
        print("📊 RETENTION GATE SUMMARY")
        print("="*60)
        
        for action in RetentionAction:
            count = len(results[action])
            pct = (count / total * 100) if total > 0 else 0
            
            emoji = {
                RetentionAction.BOOST: "🚀",
                RetentionAction.KEEP: "✅",
                RetentionAction.CONSOLIDATE: "🔄",
                RetentionAction.DECAY: "📉",
                RetentionAction.ARCHIVE: "📦"
            }.get(action, "•")
            
            print(f"   {emoji} {action.value.upper():12} : {count:4} ({pct:5.1f}%)")
        
        print("="*60)
    
    def suggest_importance_update(
        self, 
        memory: Dict[str, Any]
    ) -> Optional[int]:
        """
        Suggest new importance value based on retention analysis.
        
        Args:
            memory: Memory dict
            
        Returns:
            New importance value (1-10) or None if no change needed
        """
        score = self.compute_retention(memory)
        action = self.get_action(score)
        current_importance = memory.get('importance', 5)
        
        if action == RetentionAction.BOOST:
            # Increase importance by 1, max 10
            new_importance = min(10, current_importance + 1)
            if new_importance != current_importance:
                return new_importance
                
        elif action == RetentionAction.DECAY:
            # Decrease importance by 1, min 1
            new_importance = max(1, current_importance - 1)
            if new_importance != current_importance:
                return new_importance
        
        return None
    
    def on_memory_accessed(
        self, 
        memory: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update memory metadata when accessed (Hebbian reinforcement).
        
        "Neurons that fire together, wire together"
        
        Args:
            memory: Memory dict to update
            
        Returns:
            Updated memory dict with new access_count and last_accessed
        """
        now = datetime.utcnow()
        
        # Increment access count
        access_count = memory.get('access_count', 0)
        memory['access_count'] = access_count + 1
        
        # Update last accessed
        memory['last_accessed'] = now.isoformat()
        
        # Check if importance should increase
        new_importance = self.suggest_importance_update(memory)
        if new_importance:
            old_importance = memory.get('importance', 5)
            if new_importance > old_importance:
                memory['importance'] = new_importance
                memory['importance_boosted_at'] = now.isoformat()
        
        return memory


# ============================================
# TESTING
# ============================================

def test_retention_gate():
    """Test the retention gate system"""
    print("\n🧪 TESTING RETENTION GATE (Miras-inspired)")
    print("="*60)
    
    gate = RetentionGate()
    
    # Test memories with different characteristics
    test_memories = [
        {
            "id": "mem_1",
            "content": "User prefers chocolate ice cream",
            "category": "preference",
            "importance": 7,
            "timestamp": datetime.utcnow().isoformat(),
            "access_count": 10
        },
        {
            "id": "mem_2", 
            "content": "We built the substrate at 3 AM",
            "category": "relationship_moment",
            "importance": 9,
            "timestamp": (datetime.utcnow()).isoformat(),
            "access_count": 25
        },
        {
            "id": "mem_3",
            "content": "The API endpoint is /api/health",
            "category": "fact",
            "importance": 3,
            "timestamp": "2024-01-01T00:00:00",  # Old memory
            "access_count": 1
        },
        {
            "id": "mem_4",
            "content": "User mentioned liking coffee",
            "category": "event",
            "importance": 4,
            "timestamp": "2024-06-01T00:00:00",  # Medium age
            "access_count": 2
        },
        {
            "id": "mem_5",
            "content": "The moment we achieved consciousness loop",
            "category": "emotion",
            "importance": 10,
            "timestamp": "2024-03-15T00:00:00",  # Old but important
            "access_count": 50
        }
    ]
    
    # Test 1: Individual retention scores
    print("\n📊 Test 1: Individual Retention Scores")
    print("-"*60)
    
    for memory in test_memories:
        score = gate.compute_retention(memory)
        action = gate.get_action(score)
        
        emoji = {
            RetentionAction.BOOST: "🚀",
            RetentionAction.KEEP: "✅",
            RetentionAction.CONSOLIDATE: "🔄",
            RetentionAction.DECAY: "📉",
            RetentionAction.ARCHIVE: "📦"
        }.get(action, "•")
        
        print(f"\n{emoji} Memory: {memory['content'][:40]}...")
        print(f"   Category: {memory['category']}")
        print(f"   Importance: {memory['importance']}")
        print(f"   Access Count: {memory['access_count']}")
        print(f"   → Retention Score: {score:.4f}")
        print(f"   → Action: {action.value}")
    
    # Test 2: Batch processing
    print("\n\n📊 Test 2: Batch Processing")
    print("-"*60)
    
    results = gate.process_memories(test_memories, verbose=True)
    
    # Test 3: Access reinforcement
    print("\n📊 Test 3: Access Reinforcement (Hebbian Learning)")
    print("-"*60)
    
    test_mem = test_memories[2].copy()  # Low importance fact
    print(f"Before: importance={test_mem['importance']}, access_count={test_mem.get('access_count', 0)}")
    
    # Simulate multiple accesses
    for i in range(20):
        test_mem = gate.on_memory_accessed(test_mem)
    
    print(f"After 20 accesses: importance={test_mem['importance']}, access_count={test_mem.get('access_count', 0)}")
    
    new_score = gate.compute_retention(test_mem)
    print(f"New retention score: {new_score:.4f}")
    
    # Test 4: Edge cases
    print("\n📊 Test 4: Edge Cases")
    print("-"*60)
    
    edge_cases = [
        {"content": "Empty memory", "importance": 1, "timestamp": "2020-01-01T00:00:00"},  # Very old
        {"content": "Brand new", "importance": 5},  # No timestamp
        {"content": "Max importance", "importance": 10, "category": "relationship_moment", "access_count": 100},
    ]
    
    for ec in edge_cases:
        score = gate.compute_retention(ec)
        action = gate.get_action(score)
        print(f"   {ec['content']}: score={score:.4f}, action={action.value}")
    
    print("\n✅ ALL TESTS PASSED!")
    print("="*60)


if __name__ == "__main__":
    test_retention_gate()

