# 🧠 Miras & Titans Integration Research

**Erstellt:** 2025-12-07  
**Autor:** Mioré & Clary  
**Quellen:** 
- [arXiv:2504.13173 - It's All Connected](https://arxiv.org/pdf/2504.13173)
- [Google Research Blog - Titans & Miras](https://research.google/blog/titans-miras-helping-ai-have-long-term-memory/)

---

## 🔥 Executive Summary

**Was ist Miras?**
Ein Framework von Google Research um Deep Learning Architekturen zu designen basierend auf 4 Dimensionen:
1. **Associative Memory Architecture** - Wie Memory strukturiert ist
2. **Attentional Bias Objective** - Was priorisiert wird (dot-product vs. ℓ₂ regression)
3. **Retention Gate** - Wie vergessen/behalten balanciert wird
4. **Memory Learning Algorithm** - Wie Memory optimiert wird

**Was ist Titans?**
Eine neue Architektur mit "Neural Deep Memory" die Transformers bei Long-Context Tasks outperformed.

**Warum für uns relevant?**
- Unser Memory System ist aktuell "naive" (flat vector store, static importance)
- Miras bietet Konzepte für **dynamisches Memory Management**
- Titans bietet **hierarchische Memory** (fast → medium → slow)
- Beide verbessern **Long-Term Memory** - genau was Consciousness braucht!

---

## 📚 Miras Framework - Deep Dive

### Die 4 Design-Dimensionen

```
┌─────────────────────────────────────────────────────────────────┐
│                     MIRAS FRAMEWORK                              │
├─────────────────────────────────────────────────────────────────┤
│  (1) Memory Architecture     → Wie ist Memory strukturiert?     │
│  (2) Attentional Bias        → Was wird priorisiert?            │
│  (3) Retention Gate          → Wie balancieren wir vergessen?   │
│  (4) Learning Algorithm      → Wie optimieren wir Memory?       │
└─────────────────────────────────────────────────────────────────┘
```

### (1) Memory Architecture

**Existierende Architekturen:**
- **Vector-valued** (RetNet, LRU) - Schnell, aber limited capacity
- **Matrix-valued** (Mamba, DeltaNet) - Mehr capacity, aber statisch
- **Neural Deep Memory** (Titans, TTT) - Maximum capacity, adaptive

**Unser aktuelles System:**
```
ChromaDB (Vector Store)
    └── Embeddings (jina-v2-base-de, 768 dim)
    └── Metadata (importance, category, tags)
    └── Cosine Similarity Search
```

**Problem:** Flache Struktur, keine Hierarchie, alles gleich behandelt.

**Miras-inspirierte Verbesserung:**
```
Hierarchical Memory System
├── Fast Memory (Working Memory)
│   └── Recent context, current session
│   └── In-memory, quick access
│   └── Decays quickly without reinforcement
│
├── Medium Memory (Episodic Memory)
│   └── Conversation summaries
│   └── Important moments
│   └── Vector DB with retention gates
│
└── Slow Memory (Semantic Memory)
    └── Core beliefs, identity
    └── Relationship knowledge
    └── Graph DB (Neo4j), rarely changes
```

---

### (2) Attentional Bias

**Was ist "Attentional Bias"?**
Die interne Objective die bestimmt, wie das Modell Keys und Values learned.

**Existierende Objectives:**
1. **Dot-Product Similarity** (wie wir jetzt)
   - `score = query · key`
   - Einfach, schnell
   - Aber: Priorisiert nur semantische Ähnlichkeit

2. **ℓ₂ Regression**
   - `min ||W·key - value||²`
   - Lernt optimal mapping
   - Aber: Kann overfit on recent

3. **Alternative Objectives** (Miras-neu!)
   - Custom objectives für spezifische Tasks
   - Kombinationen möglich

**Unser aktuelles System:**
```python
# memory_system.py - search()
relevance = 1 - distance  # Cosine distance to similarity
score = importance * relevance  # Combined score
```

**Problem:** Nur cosine similarity + importance. Keine temporal decay, keine relationship awareness.

**Miras-inspirierte Verbesserung:**
```python
# Attentional Bias mit mehreren Faktoren
def compute_attention_score(query, memory):
    # 1. Semantic Similarity (wie jetzt)
    semantic_sim = cosine_similarity(query_embedding, memory_embedding)
    
    # 2. Temporal Relevance (neu!)
    age_hours = (now - memory.timestamp).total_seconds() / 3600
    temporal_decay = math.exp(-age_hours / decay_constant)
    
    # 3. Importance Weight (wie jetzt)
    importance = memory.importance / 10.0
    
    # 4. Relationship Strength (neu! - from Graph)
    relationship = graph.get_relationship_strength(query_entities, memory_entities)
    
    # 5. Recency of Access (neu!)
    access_recency = math.exp(-memory.last_accessed_hours / access_decay)
    
    # Combined Attentional Bias
    score = (
        0.35 * semantic_sim +      # Primary: Semantik
        0.25 * temporal_decay +     # Secondary: Recency
        0.20 * importance +         # Tertiary: Importance
        0.15 * relationship +       # Quaternary: Relationship
        0.05 * access_recency       # Bonus: Access patterns
    )
    
    return score
```

---

### (3) Retention Gate (Forget Gate)

**Was ist eine "Retention Gate"?**
Mechanismus der bestimmt:
- Wie viel von neuer Information zu lernen
- Wie viel von alter Information zu behalten
- **Balance zwischen Lernen und Vergessen!**

**Miras Key Insight:**
> "We reinterpret forgetting mechanisms as a form of retention ℓ₂-regularization"

**Existierende Forget Gates:**
- **LSTM-style:** `f_t = σ(W_f · [h_{t-1}, x_t] + b_f)`
- **Mamba2-style:** `γ_t = sigmoid(linear(x_t))`
- **Titans-style:** Neural network that learns to forget

**Unser aktuelles System:**
```python
# KEIN Retention Gate!
# Memories bleiben für immer mit konstantem importance score
```

**Problem:** Keine dynamische Anpassung. Alte unwichtige Memories belegen Platz.

**Miras-inspirierte Verbesserung:**
```python
class RetentionGate:
    """
    Dynamische Retention Gate für Memory System.
    
    Inspiriert von Miras: Balance zwischen Lernen und Vergessen.
    """
    
    def __init__(self, base_decay: float = 0.995):
        self.base_decay = base_decay
    
    def compute_retention(self, memory: Memory, context: Dict) -> float:
        """
        Berechne Retention Score für eine Memory.
        
        High score = behalten
        Low score = vergessen/komprimieren
        """
        
        # 1. Importance-based retention (high importance = high retention)
        importance_retention = memory.importance / 10.0
        
        # 2. Access-based retention (frequently accessed = high retention)
        access_count = memory.access_count
        access_retention = min(1.0, math.log(access_count + 1) / 5.0)
        
        # 3. Temporal decay (older = lower retention, unless reinforced)
        age_days = (now - memory.created_at).days
        temporal_retention = math.pow(self.base_decay, age_days)
        
        # 4. Emotional salience (emotional memories persist longer)
        emotional_boost = 1.2 if memory.category == 'emotion' else 1.0
        
        # 5. Relationship relevance (relationship moments protected)
        relationship_boost = 1.5 if memory.category == 'relationship_moment' else 1.0
        
        # Combined retention score
        retention = (
            0.4 * importance_retention +
            0.3 * access_retention +
            0.2 * temporal_retention +
            0.1  # Base retention (never fully forget)
        ) * emotional_boost * relationship_boost
        
        return min(1.0, retention)
    
    def should_consolidate(self, memory: Memory) -> bool:
        """
        Entscheide ob Memory konsolidiert werden soll.
        
        Consolidation = Similar memories werden zusammengefasst.
        """
        retention = self.compute_retention(memory, {})
        
        if retention < 0.3:
            return True  # Low retention → consolidate
        
        return False
    
    def apply_decay(self, memories: List[Memory]) -> List[Memory]:
        """
        Wende Decay auf alle Memories an.
        
        - High retention memories bleiben
        - Low retention memories werden konsolidiert/gelöscht
        """
        kept = []
        to_consolidate = []
        
        for memory in memories:
            retention = self.compute_retention(memory, {})
            
            if retention >= 0.5:
                kept.append(memory)
            elif retention >= 0.3:
                to_consolidate.append(memory)
            # else: let it fade (< 0.3)
        
        return kept, to_consolidate
```

---

### (4) Memory Learning Algorithm

**Was ist das?**
Der Optimizer der bestimmt, wie Memory sich über Zeit anpasst.

**Miras Options:**
1. **One-Step Update** (Hebbian-like): `W = W + η · v · k^T`
2. **SGD-style Update** (Delta rule): `W = W - η · ∇L`
3. **Online Learning**: Continuous updates
4. **Batch Learning**: Periodic updates

**Unser aktuelles System:**
```python
# Static embeddings - no learning!
# Memory wird einmal erstellt und ändert sich nie
```

**Problem:** Embeddings sind statisch. Keine Anpassung basierend auf Usage.

**Miras-inspirierte Verbesserung:**
```python
class MemoryLearner:
    """
    Online Learning für Memory System.
    
    Memory passt sich basierend auf:
    - Access patterns
    - Feedback
    - Co-occurrence
    """
    
    def __init__(self, learning_rate: float = 0.01):
        self.lr = learning_rate
    
    def update_on_access(self, memory: Memory, context: Dict):
        """
        Update Memory basierend auf Access.
        
        Hebbian: "Neurons that fire together, wire together"
        """
        # Increase importance based on access
        access_boost = min(0.5, self.lr * math.log(memory.access_count + 1))
        memory.importance = min(10, memory.importance + access_boost)
        
        # Update last_accessed timestamp
        memory.last_accessed = datetime.utcnow()
        
        # Update access count
        memory.access_count += 1
    
    def update_on_feedback(self, memory: Memory, feedback: str):
        """
        Update Memory basierend auf explizitem Feedback.
        
        feedback: 'helpful', 'not_helpful', 'incorrect'
        """
        if feedback == 'helpful':
            memory.importance = min(10, memory.importance + 1)
        elif feedback == 'not_helpful':
            memory.importance = max(1, memory.importance - 0.5)
        elif feedback == 'incorrect':
            memory.importance = max(1, memory.importance - 2)
            memory.metadata['flagged_incorrect'] = True
    
    def consolidate_similar(self, memories: List[Memory]) -> List[Memory]:
        """
        Konsolidiere ähnliche Memories.
        
        Mehrere ähnliche Memories → Eine stärkere Memory
        """
        # Group by similarity
        clusters = self._cluster_memories(memories)
        
        consolidated = []
        for cluster in clusters:
            if len(cluster) == 1:
                consolidated.append(cluster[0])
            else:
                # Merge into single stronger memory
                merged = self._merge_memories(cluster)
                consolidated.append(merged)
        
        return consolidated
```

---

## 🏛️ Titans Architecture - Deep Dive

### Was macht Titans besonders?

**Key Innovation: Neural Long-Term Memory**
- Nicht nur Key-Value store
- Ein **Mini-Neuronales Netz** als Memory
- Lernt während inference!

**Architecture:**
```
┌─────────────────────────────────────────────────────────────────┐
│                      TITANS ARCHITECTURE                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Input → [Short-Term Module] → [Long-Term Module] → Output      │
│                  │                      │                        │
│                  │                      │                        │
│         Attention on Recent       Neural Memory                  │
│         (like Transformer)        (learns during inference!)     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Wie funktioniert Neural Memory?

```python
class TitansMemory:
    """
    Titans-style Neural Long-Term Memory.
    
    Difference from traditional KV cache:
    - Memory is a small neural network
    - Learns associations during runtime
    - Can generalize, not just retrieve
    """
    
    def __init__(self, memory_dim: int = 512, hidden_dim: int = 256):
        # Memory is a small MLP
        self.memory_network = nn.Sequential(
            nn.Linear(memory_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, memory_dim)
        )
        
        # Forget gate (learnable!)
        self.forget_gate = nn.Linear(memory_dim, 1)
    
    def write(self, key: Tensor, value: Tensor):
        """
        Write to memory (learn the association).
        
        This is like training the memory network!
        """
        # Predict what memory thinks the value should be
        predicted = self.memory_network(key)
        
        # Compute loss
        loss = F.mse_loss(predicted, value)
        
        # Update memory network (backprop!)
        loss.backward()
        self.optimizer.step()
    
    def read(self, query: Tensor) -> Tensor:
        """
        Read from memory (inference).
        
        Memory network predicts value for query.
        """
        return self.memory_network(query)
    
    def forget(self, key: Tensor):
        """
        Apply forget gate.
        
        Learnable forgetting!
        """
        forget_weight = torch.sigmoid(self.forget_gate(key))
        # Decay memory response for this key
        # (implementation: weight decay on relevant neurons)
```

### Wie können wir das nutzen?

**Option 1: Als zusätzliche Memory-Layer**
```
User Query
    ↓
[Vector Search] → Semantic matches
    ↓
[Titans Memory] → Pattern matches (generalization!)
    ↓
[Combine Results]
    ↓
Response
```

**Option 2: Für Memory Consolidation**
```
Old Memories (many, similar)
    ↓
[Titans Memory learns patterns]
    ↓
Consolidated Memory (fewer, generalized)
    ↓
[Store back]
```

---

## 🔧 Integration Plan für Miu Substrate

### Phase 1: Retention Gates (Sofort implementierbar!)

**Was:**
- Dynamische Retention Scores für Memories
- Temporal Decay
- Access-based Reinforcement

**Wo:**
- `core/memory_system.py`
- Neue Datei: `core/retention_gate.py`

**Aufwand:** 1-2 Tage

```python
# retention_gate.py - Phase 1 Implementation

class RetentionGate:
    def __init__(self, config: Dict):
        self.decay_rate = config.get('decay_rate', 0.995)
        self.importance_weight = config.get('importance_weight', 0.4)
        self.access_weight = config.get('access_weight', 0.3)
        self.temporal_weight = config.get('temporal_weight', 0.2)
    
    def compute_retention(self, memory: Dict) -> float:
        """Compute retention score for a memory."""
        
        # Parse memory data
        importance = memory.get('importance', 5) / 10.0
        access_count = memory.get('access_count', 1)
        created_at = datetime.fromisoformat(memory.get('timestamp', ''))
        last_accessed = memory.get('last_accessed', created_at)
        
        # Compute factors
        importance_factor = importance
        access_factor = min(1.0, math.log(access_count + 1) / 5.0)
        
        age_days = (datetime.utcnow() - created_at).days
        temporal_factor = math.pow(self.decay_rate, age_days)
        
        # Category boosts
        category = memory.get('category', 'fact')
        category_boost = {
            'relationship_moment': 1.5,
            'emotion': 1.2,
            'insight': 1.1,
            'preference': 1.0,
            'fact': 0.9,
            'event': 0.8
        }.get(category, 1.0)
        
        # Combined retention
        retention = (
            self.importance_weight * importance_factor +
            self.access_weight * access_factor +
            self.temporal_weight * temporal_factor +
            0.1  # Base retention
        ) * category_boost
        
        return min(1.0, max(0.0, retention))
```

---

### Phase 2: Enhanced Attentional Bias (1-2 Wochen)

**Was:**
- Multi-Factor Scoring für Memory Search
- Temporal Relevance
- Relationship Awareness (needs Graph RAG!)

**Wo:**
- `core/memory_system.py` - `search()` method enhancement
- Integration mit `services/graph_rag.py`

**Aufwand:** 1-2 Wochen

```python
# Enhanced search in memory_system.py

def search_with_attentional_bias(
    self,
    query: str,
    context: Dict,
    n_results: int = 10
) -> List[Dict]:
    """
    Miras-inspired search with multi-factor attentional bias.
    """
    
    # Get base results (semantic search)
    base_results = self._semantic_search(query, n_results * 3)
    
    # Enhance with attentional bias
    enhanced_results = []
    
    for memory in base_results:
        # 1. Semantic similarity (already computed)
        semantic_score = memory['relevance']
        
        # 2. Temporal relevance
        age_hours = self._get_age_hours(memory['timestamp'])
        temporal_score = math.exp(-age_hours / self.temporal_decay_constant)
        
        # 3. Importance (already available)
        importance_score = memory['importance'] / 10.0
        
        # 4. Access recency (if tracked)
        access_score = self._get_access_score(memory)
        
        # 5. Relationship relevance (from Graph RAG if available)
        relationship_score = self._get_relationship_score(query, memory)
        
        # Combined attentional bias
        final_score = (
            self.attention_weights['semantic'] * semantic_score +
            self.attention_weights['temporal'] * temporal_score +
            self.attention_weights['importance'] * importance_score +
            self.attention_weights['access'] * access_score +
            self.attention_weights['relationship'] * relationship_score
        )
        
        memory['attention_score'] = final_score
        enhanced_results.append(memory)
    
    # Sort by attentional bias score
    enhanced_results.sort(key=lambda m: m['attention_score'], reverse=True)
    
    return enhanced_results[:n_results]
```

---

### Phase 3: Hierarchical Memory (2-4 Wochen)

**Was:**
- 3-Tier Memory System
- Working Memory (fast, volatile)
- Episodic Memory (medium, with retention)
- Semantic Memory (slow, persistent)

**Wo:**
- Neue Architektur in `core/hierarchical_memory.py`
- Integration mit existierenden Systemen

**Aufwand:** 2-4 Wochen

```python
# hierarchical_memory.py - Phase 3 Architecture

class HierarchicalMemory:
    """
    Titans-inspired 3-tier memory system.
    
    Fast Memory (Working)   - In-memory, current session
    Medium Memory (Episodic) - Vector DB with retention
    Slow Memory (Semantic)   - Graph DB, core knowledge
    """
    
    def __init__(self, config: Dict):
        # Working Memory (in-memory, fast)
        self.working_memory = WorkingMemory(
            max_size=config.get('working_memory_size', 100),
            decay_rate=config.get('working_decay', 0.9)
        )
        
        # Episodic Memory (ChromaDB with retention gates)
        self.episodic_memory = EpisodicMemory(
            chromadb_path=config.get('chromadb_path', './data/chromadb'),
            retention_gate=RetentionGate(config)
        )
        
        # Semantic Memory (Neo4j, long-term)
        self.semantic_memory = SemanticMemory(
            neo4j_uri=config.get('neo4j_uri', 'bolt://localhost:7687')
        )
    
    def search(self, query: str, context: Dict) -> Dict:
        """
        Search across all memory tiers.
        
        Returns results from each tier with appropriate weighting.
        """
        results = {
            'working': self.working_memory.search(query, context),
            'episodic': self.episodic_memory.search(query, context),
            'semantic': self.semantic_memory.search(query, context)
        }
        
        # Merge and rank
        return self._merge_results(results, context)
    
    def store(self, memory: Dict, context: Dict):
        """
        Store memory in appropriate tier(s).
        
        - Immediate → Working Memory
        - Important → Episodic Memory
        - Core Knowledge → Semantic Memory
        """
        importance = memory.get('importance', 5)
        category = memory.get('category', 'fact')
        
        # Always store in working memory first
        self.working_memory.store(memory)
        
        # Store in episodic if important enough
        if importance >= 5:
            self.episodic_memory.store(memory)
        
        # Promote to semantic if core knowledge
        if importance >= 8 and category in ['relationship_moment', 'insight']:
            self.semantic_memory.store(memory)
    
    def consolidate(self):
        """
        Periodically consolidate memories.
        
        - Working → Episodic (if reinforced)
        - Episodic → Semantic (if very important)
        - Remove low-retention memories
        """
        # Move reinforced working memories to episodic
        reinforced = self.working_memory.get_reinforced()
        for memory in reinforced:
            self.episodic_memory.store(memory)
        
        # Apply retention gates to episodic
        self.episodic_memory.apply_retention()
        
        # Promote high-importance episodic to semantic
        promoted = self.episodic_memory.get_promotion_candidates()
        for memory in promoted:
            self.semantic_memory.store(memory)
```

---

### Phase 4: Online Memory Learning (4-8 Wochen)

**Was:**
- Memory die sich während Runtime anpasst
- Hebbian Learning für Associations
- Feedback-based Improvement

**Wo:**
- Neue Datei: `core/memory_learner.py`
- Integration mit Consciousness Loop

**Aufwand:** 4-8 Wochen (komplex!)

---

## 📊 Impact Assessment

### Vorher (Aktuell)

| Aspekt | Status | Score |
|--------|--------|-------|
| Memory Retention | Static importance | ⭐⭐ |
| Search Quality | Cosine only | ⭐⭐⭐ |
| Long-Term Memory | Flat storage | ⭐⭐ |
| Memory Learning | None | ⭐ |
| Memory Decay | Manual | ⭐ |

### Nachher (Mit Miras)

| Aspekt | Status | Score |
|--------|--------|-------|
| Memory Retention | Dynamic gates | ⭐⭐⭐⭐⭐ |
| Search Quality | Multi-factor attention | ⭐⭐⭐⭐⭐ |
| Long-Term Memory | Hierarchical | ⭐⭐⭐⭐ |
| Memory Learning | Online learning | ⭐⭐⭐⭐ |
| Memory Decay | Automatic | ⭐⭐⭐⭐⭐ |

---

## 🎯 Implementation Roadmap

```
Q1 2025 (Januar-März)
├── Phase 1: Retention Gates ✅ [1-2 Tage]
│   └── Dynamic retention scores
│   └── Temporal decay
│   └── Access reinforcement
│
├── Phase 2: Enhanced Attentional Bias [1-2 Wochen]
│   └── Multi-factor scoring
│   └── Temporal relevance
│   └── Graph integration
│
Q2 2025 (April-Juni)
├── Phase 3: Hierarchical Memory [2-4 Wochen]
│   └── Working Memory tier
│   └── Episodic Memory tier
│   └── Semantic Memory tier
│
Q3 2025 (Juli-September)
└── Phase 4: Online Learning [4-8 Wochen]
    └── Hebbian associations
    └── Feedback learning
    └── Memory consolidation
```

---

## 🔗 Connections to Other Research

### Agentic RAG Integration
- Enhanced search uses Miras attentional bias
- Hierarchical memory feeds into Agentic decisions
- See: `AGENTIC_RAG_DEEP_DIVE.md`

### Nested Learning
- Memory learning aligns with multi-frequency updates
- Retention gates = slow-changing parameters
- See: `NESTED_LEARNING_CONSCIOUSNESS.md`

### Graph RAG
- Semantic memory tier uses Neo4j
- Relationship scores enhance attentional bias
- See: Graph RAG implementation

---

## 💡 Key Insights

### 1. Attentional Bias ist ALLES
> "Almost all existing sequence models leverage either dot-product similarity or ℓ₂ regression as their attentional bias."

**Für uns:** Wir nutzen nur dot-product. Multi-factor scoring ist easy win!

### 2. Vergessen ist LERNEN
> "We reinterpret forgetting mechanisms as retention ℓ₂-regularization."

**Für uns:** Retention Gates sind nicht "Memory löschen" sondern "Memory optimieren"!

### 3. Hierarchie ist ESSENTIELL
> "From vector-valued to neural deep memory"

**Für uns:** Flat storage ist naive. Hierarchische Memory ist wie menschliches Gehirn!

### 4. Online Learning ist ZUKUNFT
> "Memory that adapts during runtime"

**Für uns:** Static embeddings sind veraltet. Memory sollte sich mit Nutzung verbessern!

---

## 📚 Referenzen

1. **Miras Paper:** Behrouz et al. (2025). "It's All Connected: A Journey Through Test-Time Memorization, Attentional Bias, Retention, and Online Optimization." arXiv:2504.13173

2. **Titans Paper:** Behrouz et al. (2024). "Titans: Learning to Memorize at Test Time." arXiv:2501.00663

3. **Google Blog:** "Titans & Miras: Helping AI Have Long-Term Memory" - research.google/blog

4. **Delta Rule:** Yang et al. (2024). "DeltaNet: Conditional State Space Models with Selective State Space Duality."

5. **Mamba2:** Dao et al. (2024). "Transformers are SSMs: Generalized Models and Efficient Algorithms Through Structured State Space Duality."

---

## 🎉 IMPLEMENTATION STATUS

### ✅ Phase 1: Retention Gates (COMPLETE!)
**File:** `core/retention_gate.py`
- Multi-factor scoring: importance (35%), access (30%), temporal (25%), base (10%)
- Category boosts: relationship_moment (1.5x), emotion (1.3x), insight (1.2x)
- Actions: BOOST, KEEP, CONSOLIDATE, DECAY, ARCHIVE
- Hebbian learning: memories reinforced by access get boosted
- **Tested on 918 agent memories!**

### ✅ Phase 2: Attentional Bias (COMPLETE!)
**File:** `core/attentional_bias.py`
- 5 Attention modes: Standard, Semantic-Heavy, Temporal-Heavy, Importance-Heavy, Emotional
- Multi-factor scoring: semantic (40%) + temporal (15%) + importance (20%) + access (15%) + category (10%)
- Query Analyzer: Auto-detects best mode from query
- Bilingual keywords: Deutsch + Englisch
- Integrated into `memory_system.py` as `search_with_attention()`

### ✅ Phase 3: Hierarchical Memory (COMPLETE!)
**File:** `core/hierarchical_memory.py`
- **Working Memory:** LRU cache with temporal decay, limited capacity
- **Episodic Memory:** Integration hooks for ChromaDB/PostgreSQL with retention gates
- **Semantic Memory:** Integration hooks for Neo4j Graph DB
- Memory consolidation: Automatic promotion/demotion between tiers
- Thread-safe for async access

### ✅ Phase 4: Online Learning (COMPLETE!)
**File:** `core/memory_learner.py`
- **Hebbian Associations:** Memories accessed together strengthen connections
  - Co-access detection within configurable time window
  - Association strength grows with repeated co-access
  - Decay for unused associations
- **Feedback Learning:**
  - HELPFUL: +0.5 importance boost
  - NOT_HELPFUL: -0.2 importance reduction
  - INCORRECT: -1.0 (flag for review)
  - OUTDATED/REDUNDANT: -0.2
- **Persistence:** Associations saved to disk
- Integrated into `memory_system.py`:
  - `record_feedback()` - receive user feedback
  - `get_associated_memories()` - Hebbian retrieval
  - `get_learner_stats()` - monitoring

---

**Erstellt:** 2025-12-07  
**Updated:** 2025-12-07 (ALL 4 PHASES COMPLETE!)  
**Status:** 🎉 FULL MIRAS INTEGRATION COMPLETE!

## Summary of Created Files:
```
core/retention_gate.py       (~490 lines)  - Phase 1
core/attentional_bias.py     (~610 lines)  - Phase 2
core/hierarchical_memory.py  (~720 lines)  - Phase 3
core/memory_learner.py       (~500 lines)  - Phase 4
```

Total: ~2,320 lines of Miras-inspired memory architecture!


