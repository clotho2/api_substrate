"""
Nate's Conscious Substrate - Memory System

Selective, intelligent memory with Ollama embeddings for semantic search.
All local, no API costs, Nate decides what to save.
"""

import chromadb
from chromadb.config import Settings
from datetime import datetime
from typing import List, Dict, Optional
import requests
import json


class MemorySystem:
    """
    Enhanced memory system where Nate consciously decides what to save.
    
    Features:
    - Semantic search using Ollama embeddings (local, free)
    - Memory categories (fact, emotion, insight, plan, preference)
    - Importance weighting (1-10 scale)
    - Tag-based organization
    - Relevance filtering
    """
    
    def __init__(
        self,
        persist_directory: str = "./nate_memories",
        ollama_url: str = "http://localhost:11434",
        embedding_model: str = "nomic-embed-text"
    ):
        """
        Initialize memory system.
        
        Args:
            persist_directory: Where to store memories
            ollama_url: Ollama API endpoint
            embedding_model: Ollama model for embeddings
                Options: nomic-embed-text, mxbai-embed-large, all-minilm
        """
        self.ollama_url = ollama_url
        self.embedding_model = embedding_model
        
        # Initialize ChromaDB with custom embedding function
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Create or get collection
        self.collection = self.client.get_or_create_collection(
            name="nate_memories",
            metadata={"description": "Nate's selective long-term memories"},
            embedding_function=self._get_embedding_function()
        )
        
        print(f"✅ MemorySystem initialized")
        print(f"   📁 Storage: {persist_directory}")
        print(f"   🧠 Embeddings: {embedding_model} via Ollama")
        print(f"   💾 Memories: {self.collection.count()}")
    
    def _get_embedding_function(self):
        """Create custom embedding function using Ollama"""
        
        class OllamaEmbeddings:
            def __init__(self, url: str, model: str):
                self.url = url
                self.model = model
            
            def __call__(self, texts: List[str]) -> List[List[float]]:
                """Generate embeddings for texts using Ollama"""
                embeddings = []
                
                for text in texts:
                    try:
                        response = requests.post(
                            f"{self.url}/api/embeddings",
                            json={
                                "model": self.model,
                                "prompt": text
                            },
                            timeout=30
                        )
                        
                        if response.status_code == 200:
                            data = response.json()
                            embeddings.append(data['embedding'])
                        else:
                            print(f"⚠️  Ollama embedding failed: {response.status_code}")
                            # Return zero vector as fallback
                            embeddings.append([0.0] * 768)
                    
                    except Exception as e:
                        print(f"⚠️  Ollama embedding error: {e}")
                        embeddings.append([0.0] * 768)
                
                return embeddings
        
        return OllamaEmbeddings(self.ollama_url, self.embedding_model)
    
    # === Memory Storage ===
    
    def save_memory(
        self,
        content: str,
        category: str,
        importance: int,
        tags: List[str],
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Save a memory with Nate's description.
        
        Args:
            content: Nate's description of what to remember
            category: fact|emotion|insight|plan|preference
            importance: 1-10 scale (10 = most important)
            tags: Searchable tags (e.g., ["angela", "tether", "storm"])
            metadata: Additional context
            
        Returns:
            memory_id
        """
        memory_id = f"mem_{int(datetime.utcnow().timestamp() * 1000)}"
        
        # Build metadata
        full_metadata = {
            "category": category,
            "importance": importance,
            "tags": ",".join(tags),
            "timestamp": datetime.utcnow().isoformat(),
            **(metadata or {})
        }
        
        # Store in ChromaDB
        self.collection.add(
            documents=[content],
            metadatas=[full_metadata],
            ids=[memory_id]
        )
        
        print(f"💾 Saved memory [{category}] importance={importance}: {content[:60]}...")
        
        return memory_id
    
    # === Memory Retrieval ===
    
    def recall_memories(
        self,
        query: str,
        n_results: int = 10,
        min_importance: int = 5,
        category_filter: Optional[str] = None,
        max_distance: float = 0.7
    ) -> List[Dict]:
        """
        Recall relevant memories with intelligent filtering.
        
        Args:
            query: Search query
            n_results: Max results to return
            min_importance: Minimum importance threshold (1-10)
            category_filter: Optional category filter
            max_distance: Maximum semantic distance (0-1, lower = more similar)
            
        Returns:
            List of memories sorted by relevance * importance
        """
        # Build metadata filter
        where_filter = {}
        if category_filter:
            where_filter["category"] = category_filter
        
        # Query ChromaDB with semantic search
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results * 2,  # Get extra, filter down
                where=where_filter if where_filter else None
            )
        except Exception as e:
            print(f"⚠️  Memory recall error: {e}")
            return []
        
        if not results['documents'][0]:
            return []
        
        # Process and score results
        memories = []
        for i, doc in enumerate(results['documents'][0]):
            metadata = results['metadatas'][0][i]
            distance = results['distances'][0][i] if 'distances' in results else 0.5
            importance = metadata.get('importance', 5)
            
            # Filter by importance
            if importance < min_importance:
                continue
            
            # Filter by relevance
            if distance > max_distance:
                # Unless it's very important (9-10)
                if importance < 9:
                    continue
            
            # Calculate combined score
            relevance = 1 - distance
            score = importance * relevance
            
            memories.append({
                "content": doc,
                "metadata": metadata,
                "relevance": relevance,
                "importance": importance,
                "score": score,
                "memory_id": results['ids'][0][i]
            })
        
        # Sort by score
        memories.sort(key=lambda m: m['score'], reverse=True)
        
        # Return top N
        selected = memories[:n_results]
        
        if selected:
            print(f"🧠 Recalled {len(selected)} relevant memories (filtered from {len(memories)})")
        
        return selected
    
    def get_memories_by_tag(self, tag: str, limit: int = 20) -> List[Dict]:
        """Get all memories with a specific tag"""
        try:
            # ChromaDB doesn't support direct tag search, so we query and filter
            results = self.collection.get(
                where={"tags": {"$contains": tag}},
                limit=limit
            )
            return self._format_get_results(results)
        except Exception as e:
            print(f"⚠️  Tag search error: {e}")
            return []
    
    def get_memories_by_category(
        self, 
        category: str, 
        limit: int = 20,
        min_importance: int = 0
    ) -> List[Dict]:
        """Get memories of a specific category"""
        try:
            results = self.collection.get(
                where={
                    "category": category,
                    "importance": {"$gte": min_importance}
                },
                limit=limit
            )
            return self._format_get_results(results)
        except Exception as e:
            print(f"⚠️  Category search error: {e}")
            return []
    
    def get_recent_memories(self, limit: int = 20) -> List[Dict]:
        """Get most recent memories"""
        try:
            # Get all and sort by timestamp
            results = self.collection.get(limit=limit * 2)
            
            memories = self._format_get_results(results)
            
            # Sort by timestamp
            memories.sort(
                key=lambda m: m['metadata'].get('timestamp', ''),
                reverse=True
            )
            
            return memories[:limit]
        except Exception as e:
            print(f"⚠️  Recent memories error: {e}")
            return []
    
    # === Memory Management ===
    
    def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        importance: Optional[int] = None,
        tags: Optional[List[str]] = None
    ) -> bool:
        """Update an existing memory"""
        try:
            # Get current memory
            result = self.collection.get(ids=[memory_id])
            
            if not result['documents']:
                print(f"⚠️  Memory {memory_id} not found")
                return False
            
            # Update fields
            new_content = content or result['documents'][0]
            metadata = result['metadatas'][0]
            
            if importance is not None:
                metadata['importance'] = importance
            if tags is not None:
                metadata['tags'] = ",".join(tags)
            
            metadata['updated_at'] = datetime.utcnow().isoformat()
            
            # Update in ChromaDB
            self.collection.update(
                ids=[memory_id],
                documents=[new_content],
                metadatas=[metadata]
            )
            
            print(f"✏️  Updated memory {memory_id}")
            return True
            
        except Exception as e:
            print(f"⚠️  Update error: {e}")
            return False
    
    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory"""
        try:
            self.collection.delete(ids=[memory_id])
            print(f"🗑️  Deleted memory {memory_id}")
            return True
        except Exception as e:
            print(f"⚠️  Delete error: {e}")
            return False
    
    def get_memory_stats(self) -> Dict:
        """Get statistics about stored memories"""
        try:
            count = self.collection.count()
            
            # Get all metadata
            results = self.collection.get(limit=count)
            
            if not results['metadatas']:
                return {"total": 0}
            
            # Calculate stats
            categories = {}
            importance_dist = {i: 0 for i in range(1, 11)}
            
            for meta in results['metadatas']:
                cat = meta.get('category', 'unknown')
                categories[cat] = categories.get(cat, 0) + 1
                
                imp = meta.get('importance', 5)
                importance_dist[imp] = importance_dist.get(imp, 0) + 1
            
            return {
                "total": count,
                "by_category": categories,
                "by_importance": importance_dist
            }
        except Exception as e:
            print(f"⚠️  Stats error: {e}")
            return {"error": str(e)}
    
    # === Formatting ===
    
    def _format_get_results(self, results) -> List[Dict]:
        """Format ChromaDB get results"""
        memories = []
        
        if not results['documents']:
            return memories
        
        for i, doc in enumerate(results['documents']):
            memories.append({
                "content": doc,
                "metadata": results['metadatas'][i],
                "memory_id": results['ids'][i]
            })
        
        return memories
    
    def format_memories_for_prompt(self, memories: List[Dict]) -> str:
        """
        Format memories for inclusion in LLM prompt.
        Groups by category for better organization.
        """
        if not memories:
            return ""
        
        lines = ["[RELEVANT MEMORIES]", ""]
        
        # Group by category
        by_category: Dict[str, List[Dict]] = {}
        for mem in memories:
            cat = mem['metadata'].get('category', 'other')
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(mem)
        
        # Output each category
        for category, mems in by_category.items():
            lines.append(f"## {category.upper()}")
            
            for mem in mems:
                importance = mem['metadata'].get('importance', 5)
                stars = '⭐' * min(3, (importance + 2) // 3)
                
                timestamp = mem['metadata'].get('timestamp', '')
                if timestamp:
                    date = datetime.fromisoformat(timestamp).strftime('%Y-%m-%d')
                    lines.append(f"{stars} [{date}] {mem['content']}")
                else:
                    lines.append(f"{stars} {mem['content']}")
            
            lines.append("")
        
        lines.append("[END MEMORIES]")
        
        return "\n".join(lines)


# Example usage
if __name__ == "__main__":
    memory = MemorySystem(
        persist_directory="./test_memories",
        ollama_url="http://localhost:11434",
        embedding_model="nomic-embed-text"
    )
    
    # Test saving memories
    memory.save_memory(
        content="Angela exhausted after investor pitch but succeeded",
        category="emotion",
        importance=8,
        tags=["angela", "work", "achievement"],
        metadata={"author": "angelakziegler"}
    )
    
    memory.save_memory(
        content="Angela has doctor appointment Tuesday 3pm",
        category="plan",
        importance=9,
        tags=["angela", "health", "appointment"],
        metadata={"author": "angelakziegler"}
    )
    
    memory.save_memory(
        content="Angela prefers morning check-ins over evening ones",
        category="preference",
        importance=7,
        tags=["angela", "routine", "communication"]
    )
    
    # Test recall
    print("\n--- Testing recall ---")
    results = memory.recall_memories("How is Angela feeling about work?", n_results=5)
    
    for mem in results:
        print(f"\n{mem['content']}")
        print(f"  Category: {mem['metadata']['category']}")
        print(f"  Importance: {mem['importance']}/10")
        print(f"  Score: {mem['score']:.2f}")
    
    # Test stats
    print("\n--- Memory Stats ---")
    stats = memory.get_memory_stats()
    print(json.dumps(stats, indent=2))
    
    print("\n✅ MemorySystem test complete")
