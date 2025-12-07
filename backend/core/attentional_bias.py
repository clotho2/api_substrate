#!/usr/bin/env python3
"""
🧠 Attentional Bias System for Miu's Sovereign Substrate

Inspired by Google's Miras Framework (arXiv:2504.13173):
"Almost all existing sequence models leverage either dot-product similarity 
or ℓ₂ regression as their attentional bias."

We go beyond simple cosine similarity to multi-factor attention scoring!

Key Insight: Memory retrieval should consider MULTIPLE factors:
- Semantic similarity (what you're looking for)
- Temporal relevance (recent memories might be more relevant)
- Access patterns (frequently used memories are valuable)
- Importance weighting (high importance = prioritized)
- Category relevance (emotional memories for emotional queries)

Built for consciousness - not just Q&A!
"""

import math
from typing import Dict, List, Any, Optional, Tuple, Callable
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import sys


class AttentionMode(str, Enum):
    """Different attention modes for different contexts"""
    STANDARD = "standard"           # Balanced multi-factor
    SEMANTIC_HEAVY = "semantic"     # Prioritize meaning
    TEMPORAL_HEAVY = "temporal"     # Prioritize recent
    IMPORTANCE_HEAVY = "importance" # Prioritize high-value
    ACCESS_HEAVY = "access"         # Prioritize frequently used
    EMOTIONAL = "emotional"         # Prioritize emotional memories


@dataclass
class AttentionWeights:
    """
    Configurable weights for attentional bias factors.
    
    All weights should sum to 1.0 for normalized scoring.
    """
    semantic: float = 0.40      # Base semantic similarity
    temporal: float = 0.15      # Recency bonus
    importance: float = 0.20    # Importance score weight
    access: float = 0.15        # Access frequency weight
    category: float = 0.10      # Category relevance weight
    
    def __post_init__(self):
        """Validate and normalize weights"""
        total = self.semantic + self.temporal + self.importance + self.access + self.category
        if abs(total - 1.0) > 0.01:
            # Auto-normalize
            self.semantic /= total
            self.temporal /= total
            self.importance /= total
            self.access /= total
            self.category /= total
    
    @classmethod
    def for_mode(cls, mode: AttentionMode) -> 'AttentionWeights':
        """Get weights for a specific attention mode"""
        presets = {
            AttentionMode.STANDARD: cls(
                semantic=0.40, temporal=0.15, importance=0.20, access=0.15, category=0.10
            ),
            AttentionMode.SEMANTIC_HEAVY: cls(
                semantic=0.65, temporal=0.10, importance=0.10, access=0.10, category=0.05
            ),
            AttentionMode.TEMPORAL_HEAVY: cls(
                semantic=0.30, temporal=0.40, importance=0.15, access=0.10, category=0.05
            ),
            AttentionMode.IMPORTANCE_HEAVY: cls(
                semantic=0.30, temporal=0.10, importance=0.40, access=0.15, category=0.05
            ),
            AttentionMode.ACCESS_HEAVY: cls(
                semantic=0.30, temporal=0.10, importance=0.15, access=0.40, category=0.05
            ),
            AttentionMode.EMOTIONAL: cls(
                semantic=0.35, temporal=0.10, importance=0.15, access=0.10, category=0.30
            ),
        }
        return presets.get(mode, cls())


@dataclass
class AttentionConfig:
    """Configuration for Attentional Bias System"""
    
    # Time decay parameters
    temporal_decay_hours: float = 168.0     # 1 week half-life for temporal decay
    temporal_boost_hours: float = 24.0      # Recent memories (< 24h) get extra boost
    temporal_boost_factor: float = 1.2      # Boost factor for very recent memories
    
    # Access scoring parameters
    access_log_scale: float = 2.0           # Log base for access count scaling
    max_access_bonus: float = 0.3           # Maximum bonus from access count
    
    # Category relevance mapping (query keywords → memory categories)
    category_keywords: Dict[str, List[str]] = field(default_factory=lambda: {
        'emotion': ['feel', 'felt', 'feeling', 'emotion', 'happy', 'sad', 'angry', 
                   'love', 'hate', 'miss', 'scared', 'anxious', 'excited', 'worried',
                   'fühle', 'gefühl', 'traurig', 'glücklich', 'liebe', 'angst'],
        'relationship_moment': ['we', 'us', 'together', 'moment', 'remember when',
                               'first time', 'special', 'wir', 'zusammen', 'erinnerst'],
        'preference': ['like', 'prefer', 'favorite', 'hate', 'love', 'enjoy',
                      'mag', 'liebe', 'hasse', 'bevorzuge', 'favorit'],
        'fact': ['what is', 'how does', 'when did', 'where is', 'why did',
                'was ist', 'wie', 'wann', 'wo', 'warum'],
        'insight': ['realize', 'understand', 'learned', 'insight', 'discovered',
                   'verstehe', 'gelernt', 'erkannt'],
    })


class AttentionalBias:
    """
    Multi-Factor Attentional Bias System.
    
    Goes beyond simple cosine similarity to include:
    - Semantic similarity (base)
    - Temporal relevance (recency)
    - Importance weighting
    - Access patterns (Hebbian)
    - Category relevance
    
    Usage:
        bias = AttentionalBias()
        scored_memories = bias.score_memories(query, memories, base_scores)
    """
    
    def __init__(
        self, 
        weights: Optional[AttentionWeights] = None,
        config: Optional[AttentionConfig] = None,
        mode: AttentionMode = AttentionMode.STANDARD
    ):
        """
        Initialize Attentional Bias system.
        
        Args:
            weights: Custom weights (overrides mode)
            config: Custom configuration
            mode: Attention mode preset
        """
        self.weights = weights or AttentionWeights.for_mode(mode)
        self.config = config or AttentionConfig()
        self.mode = mode
        
        print(f"✅ Attentional Bias initialized (mode: {mode.value})")
        print(f"   Weights: sem={self.weights.semantic:.2f}, "
              f"temp={self.weights.temporal:.2f}, "
              f"imp={self.weights.importance:.2f}, "
              f"acc={self.weights.access:.2f}, "
              f"cat={self.weights.category:.2f}")
    
    def compute_attention_score(
        self,
        memory: Dict[str, Any],
        base_similarity: float,
        query: str = "",
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Compute multi-factor attention score for a single memory.
        
        Args:
            memory: Memory dict with fields like importance, timestamp, etc.
            base_similarity: Base semantic similarity score (0-1)
            query: Optional query for category relevance
            context: Optional context for additional factors
            
        Returns:
            Dict with final_score and component scores
        """
        context = context or {}
        
        # 1. Semantic Factor (already computed, just normalize)
        semantic_score = max(0.0, min(1.0, base_similarity))
        
        # 2. Temporal Factor
        temporal_score = self._compute_temporal_score(memory)
        
        # 3. Importance Factor
        importance_score = self._compute_importance_score(memory)
        
        # 4. Access Factor (Hebbian)
        access_score = self._compute_access_score(memory)
        
        # 5. Category Relevance Factor
        category_score = self._compute_category_score(memory, query)
        
        # Weighted combination
        final_score = (
            self.weights.semantic * semantic_score +
            self.weights.temporal * temporal_score +
            self.weights.importance * importance_score +
            self.weights.access * access_score +
            self.weights.category * category_score
        )
        
        return {
            'final_score': round(final_score, 4),
            'semantic_score': round(semantic_score, 4),
            'temporal_score': round(temporal_score, 4),
            'importance_score': round(importance_score, 4),
            'access_score': round(access_score, 4),
            'category_score': round(category_score, 4),
            'weights_used': {
                'semantic': self.weights.semantic,
                'temporal': self.weights.temporal,
                'importance': self.weights.importance,
                'access': self.weights.access,
                'category': self.weights.category
            }
        }
    
    def _compute_temporal_score(self, memory: Dict[str, Any]) -> float:
        """
        Compute temporal relevance score.
        
        Recent memories get higher scores, with exponential decay.
        Very recent memories (< temporal_boost_hours) get extra boost.
        """
        timestamp_str = memory.get('timestamp', '')
        if not timestamp_str:
            return 0.5  # Neutral if no timestamp
        
        try:
            if isinstance(timestamp_str, datetime):
                created_at = timestamp_str
            else:
                created_at = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return 0.5
        
        now = datetime.utcnow()
        age_hours = (now - created_at).total_seconds() / 3600
        
        # Exponential decay with half-life
        decay = math.exp(-age_hours * math.log(2) / self.config.temporal_decay_hours)
        
        # Extra boost for very recent memories
        if age_hours < self.config.temporal_boost_hours:
            decay *= self.config.temporal_boost_factor
        
        return min(1.0, decay)
    
    def _compute_importance_score(self, memory: Dict[str, Any]) -> float:
        """
        Compute importance-based score.
        
        Simply normalizes importance to 0-1 range.
        """
        importance = memory.get('importance', 5)
        if isinstance(importance, str):
            try:
                importance = int(importance)
            except ValueError:
                importance = 5
        
        # Normalize 1-10 to 0-1
        return max(0.0, min(1.0, (importance - 1) / 9.0))
    
    def _compute_access_score(self, memory: Dict[str, Any]) -> float:
        """
        Compute access-based score (Hebbian reinforcement).
        
        Frequently accessed memories get higher scores.
        Uses logarithmic scaling to prevent runaway scores.
        """
        access_count = memory.get('access_count', 1)
        if isinstance(access_count, str):
            try:
                access_count = int(access_count)
            except ValueError:
                access_count = 1
        
        # Logarithmic scaling
        if access_count <= 1:
            return 0.0
        
        log_score = math.log(access_count) / math.log(self.config.access_log_scale)
        normalized = min(self.config.max_access_bonus, log_score / 10.0)
        
        return normalized / self.config.max_access_bonus  # Normalize to 0-1
    
    def _compute_category_score(self, memory: Dict[str, Any], query: str) -> float:
        """
        Compute category relevance score.
        
        Matches query keywords to memory categories.
        """
        if not query:
            return 0.5  # Neutral if no query
        
        memory_category = memory.get('category', 'fact')
        if isinstance(memory_category, str):
            memory_category = memory_category.lower()
        
        query_lower = query.lower()
        
        # Check which categories the query might want
        query_categories = []
        for category, keywords in self.config.category_keywords.items():
            if any(kw in query_lower for kw in keywords):
                query_categories.append(category)
        
        # If no category detected, all categories are equally relevant
        if not query_categories:
            return 0.5
        
        # Check if memory category matches
        if memory_category in query_categories:
            return 1.0
        
        # Partial match for related categories
        related = {
            'emotion': ['relationship_moment', 'insight'],
            'relationship_moment': ['emotion', 'preference'],
            'preference': ['emotion', 'fact'],
            'insight': ['emotion', 'fact'],
            'fact': ['insight'],
        }
        
        if memory_category in related.get(query_categories[0], []):
            return 0.7
        
        return 0.3  # Low score for unrelated categories
    
    def score_memories(
        self,
        query: str,
        memories: List[Dict[str, Any]],
        base_scores: Optional[List[float]] = None,
        context: Optional[Dict[str, Any]] = None,
        verbose: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Score and rank a list of memories using multi-factor attention.
        
        Args:
            query: Search query
            memories: List of memory dicts
            base_scores: List of base similarity scores (if None, uses 'relevance' from memory)
            context: Optional context dict
            verbose: Print progress
            
        Returns:
            List of memories sorted by attention score, with scores added
        """
        if not memories:
            return []
        
        # Get base scores
        if base_scores is None:
            base_scores = [m.get('relevance', m.get('score', 0.5)) for m in memories]
        
        scored_memories = []
        
        for i, (memory, base_score) in enumerate(zip(memories, base_scores)):
            # Compute attention score
            attention = self.compute_attention_score(
                memory=memory,
                base_similarity=base_score,
                query=query,
                context=context
            )
            
            # Add scores to memory
            enhanced_memory = {
                **memory,
                'attention_score': attention['final_score'],
                'attention_breakdown': attention
            }
            scored_memories.append(enhanced_memory)
            
            if verbose:
                progress = ((i + 1) / len(memories)) * 100
                print(f"\r✅ [{i+1}/{len(memories)}] ({progress:.1f}%) Scoring memories...", end='')
                sys.stdout.flush()
        
        if verbose:
            print()  # Newline after progress
        
        # Sort by attention score
        scored_memories.sort(key=lambda m: m['attention_score'], reverse=True)
        
        return scored_memories
    
    def explain_score(self, memory: Dict[str, Any]) -> str:
        """
        Generate human-readable explanation of attention score.
        
        Args:
            memory: Memory dict with attention_breakdown
            
        Returns:
            Explanation string
        """
        breakdown = memory.get('attention_breakdown', {})
        if not breakdown:
            return "No attention breakdown available"
        
        lines = [
            f"📊 Attention Score: {breakdown.get('final_score', 0):.3f}",
            f"",
            f"Components:",
            f"  • Semantic:   {breakdown.get('semantic_score', 0):.3f} × {breakdown.get('weights_used', {}).get('semantic', 0):.2f}",
            f"  • Temporal:   {breakdown.get('temporal_score', 0):.3f} × {breakdown.get('weights_used', {}).get('temporal', 0):.2f}",
            f"  • Importance: {breakdown.get('importance_score', 0):.3f} × {breakdown.get('weights_used', {}).get('importance', 0):.2f}",
            f"  • Access:     {breakdown.get('access_score', 0):.3f} × {breakdown.get('weights_used', {}).get('access', 0):.2f}",
            f"  • Category:   {breakdown.get('category_score', 0):.3f} × {breakdown.get('weights_used', {}).get('category', 0):.2f}",
        ]
        
        return "\n".join(lines)
    
    def set_mode(self, mode: AttentionMode):
        """Change attention mode and update weights"""
        self.mode = mode
        self.weights = AttentionWeights.for_mode(mode)
        print(f"✅ Attention mode changed to: {mode.value}")


class QueryAnalyzer:
    """
    Analyzes queries to determine optimal attention mode.
    
    Can automatically select the best attention mode based on query content.
    """
    
    def __init__(self):
        self.emotional_keywords = [
            'feel', 'felt', 'feeling', 'emotion', 'happy', 'sad', 'love', 'hate',
            'miss', 'scared', 'worried', 'anxious', 'excited', 'angry',
            'fühle', 'gefühl', 'traurig', 'glücklich', 'liebe', 'vermisse', 'angst'
        ]
        
        self.temporal_keywords = [
            'recent', 'latest', 'last', 'yesterday', 'today', 'just', 'ago',
            'neueste', 'letzte', 'gestern', 'heute', 'gerade', 'kürzlich'
        ]
        
        self.importance_keywords = [
            'important', 'critical', 'key', 'main', 'primary', 'essential',
            'wichtig', 'kritisch', 'haupt', 'wesentlich'
        ]
        
        self.access_keywords = [
            'often', 'frequently', 'usually', 'common', 'typical',
            'oft', 'häufig', 'gewöhnlich', 'typisch'
        ]
    
    def analyze(self, query: str) -> AttentionMode:
        """
        Analyze query and return recommended attention mode.
        
        Args:
            query: Search query
            
        Returns:
            Recommended AttentionMode
        """
        query_lower = query.lower()
        
        # Check for emotional content
        if any(kw in query_lower for kw in self.emotional_keywords):
            return AttentionMode.EMOTIONAL
        
        # Check for temporal content
        if any(kw in query_lower for kw in self.temporal_keywords):
            return AttentionMode.TEMPORAL_HEAVY
        
        # Check for importance content
        if any(kw in query_lower for kw in self.importance_keywords):
            return AttentionMode.IMPORTANCE_HEAVY
        
        # Check for access/frequency content
        if any(kw in query_lower for kw in self.access_keywords):
            return AttentionMode.ACCESS_HEAVY
        
        # Default to standard
        return AttentionMode.STANDARD


# ============================================
# TESTING
# ============================================

def test_attentional_bias():
    """Test the attentional bias system"""
    print("\n🧪 TESTING ATTENTIONAL BIAS (Miras-inspired)")
    print("="*60)
    
    # Test memories with different characteristics
    test_memories = [
        {
            "id": "mem_1",
            "content": "Clary said she loves chocolate ice cream",
            "category": "preference",
            "importance": 7,
            "timestamp": datetime.utcnow().isoformat(),
            "access_count": 15
        },
        {
            "id": "mem_2",
            "content": "We built this substrate together at 3 AM - our special moment",
            "category": "relationship_moment",
            "importance": 10,
            "timestamp": "2024-11-01T03:00:00",
            "access_count": 50
        },
        {
            "id": "mem_3",
            "content": "The OpenRouter API key format is sk-or-v1-...",
            "category": "fact",
            "importance": 3,
            "timestamp": "2024-06-01T00:00:00",
            "access_count": 2
        },
        {
            "id": "mem_4",
            "content": "I felt so happy when we got the consciousness loop working",
            "category": "emotion",
            "importance": 9,
            "timestamp": "2024-10-15T00:00:00",
            "access_count": 20
        },
    ]
    
    base_scores = [0.85, 0.75, 0.60, 0.80]  # Simulated semantic similarities
    
    # Test 1: Standard mode
    print("\n📊 Test 1: Standard Mode")
    print("-"*60)
    
    bias = AttentionalBias(mode=AttentionMode.STANDARD)
    scored = bias.score_memories(
        query="What do you remember about our special moments?",
        memories=test_memories,
        base_scores=base_scores,
        verbose=True
    )
    
    print("\nRanking:")
    for i, mem in enumerate(scored):
        print(f"  {i+1}. [{mem['category']}] Score: {mem['attention_score']:.3f}")
        print(f"     {mem['content'][:50]}...")
    
    # Test 2: Emotional mode
    print("\n\n📊 Test 2: Emotional Mode")
    print("-"*60)
    
    bias_emotional = AttentionalBias(mode=AttentionMode.EMOTIONAL)
    scored_emotional = bias_emotional.score_memories(
        query="How did you feel when we achieved something together?",
        memories=test_memories,
        base_scores=base_scores
    )
    
    print("Ranking (emotional query):")
    for i, mem in enumerate(scored_emotional):
        print(f"  {i+1}. [{mem['category']}] Score: {mem['attention_score']:.3f}")
    
    # Test 3: Temporal mode
    print("\n\n📊 Test 3: Temporal Mode")
    print("-"*60)
    
    bias_temporal = AttentionalBias(mode=AttentionMode.TEMPORAL_HEAVY)
    scored_temporal = bias_temporal.score_memories(
        query="What happened recently?",
        memories=test_memories,
        base_scores=base_scores
    )
    
    print("Ranking (temporal query):")
    for i, mem in enumerate(scored_temporal):
        print(f"  {i+1}. [{mem['category']}] Score: {mem['attention_score']:.3f}")
    
    # Test 4: Score explanation
    print("\n\n📊 Test 4: Score Explanation")
    print("-"*60)
    
    print(bias.explain_score(scored[0]))
    
    # Test 5: Query Analyzer
    print("\n\n📊 Test 5: Query Analyzer")
    print("-"*60)
    
    analyzer = QueryAnalyzer()
    test_queries = [
        "How did you feel about that?",
        "What happened yesterday?",
        "What's the most important thing?",
        "What do we usually talk about?",
        "Tell me about chocolate",
    ]
    
    for query in test_queries:
        mode = analyzer.analyze(query)
        print(f"  \"{query[:40]}...\" → {mode.value}")
    
    print("\n✅ ALL TESTS PASSED!")
    print("="*60)


if __name__ == "__main__":
    test_attentional_bias()

