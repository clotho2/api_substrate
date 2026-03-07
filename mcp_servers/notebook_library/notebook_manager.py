#!/usr/bin/env python3
"""
Notebook Manager - ChromaDB-backed document collections.

Each "notebook" is a ChromaDB collection containing chunked, embedded documents.
Drop files into a notebook folder -> they get automatically processed and indexed.

Supports:
- Multiple notebooks (one ChromaDB collection each)
- Document ingestion with automatic chunking and embedding
- Semantic search within notebooks (token-efficient!)
- File tracking to avoid re-processing unchanged files
"""

import os
import sys
import json
import threading
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

import chromadb
from chromadb.config import Settings

from document_processor import (
    extract_text, chunk_text, get_file_hash,
    is_supported_file, SUPPORTED_EXTENSIONS, DocumentChunk
)

# Embedding imports — same strategy as memory_system.py
try:
    from transformers import AutoModel
    import torch
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False


def sanitize_collection_name(name: str) -> str:
    """
    Sanitize a notebook name for use as a ChromaDB collection name.
    ChromaDB requires: 3-63 chars, starts/ends with alphanumeric,
    only alphanumeric, underscores, hyphens.
    """
    sanitized = name.lower().replace(' ', '_').replace('/', '_').replace('\\', '_')
    sanitized = ''.join(c for c in sanitized if c.isalnum() or c in ('_', '-'))
    sanitized = f"nb_{sanitized}"
    if len(sanitized) < 3:
        sanitized = sanitized + "_nb"
    if len(sanitized) > 63:
        sanitized = sanitized[:63]
    return sanitized


class NotebookManager:
    """
    Manages multiple notebook collections backed by ChromaDB.

    Each notebook is a folder under notebooks_path. Files dropped into
    the folder get chunked, embedded, and stored in a ChromaDB collection.
    Queries do vector similarity search and return only relevant passages.
    """

    def __init__(
        self,
        notebooks_path: str = "./data/notebooks",
        chromadb_path: str = "./data/notebook_chromadb",
        ollama_url: str = "http://192.168.2.175:11434",
        embedding_model: str = "nomic-embed-text",
        chunk_size: int = 2000,
        chunk_overlap: int = 200
    ):
        self.notebooks_path = Path(notebooks_path)
        self.chromadb_path = chromadb_path
        self.ollama_url = ollama_url
        self.embedding_model = embedding_model
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._lock = threading.Lock()

        # Ensure directories exist
        self.notebooks_path.mkdir(parents=True, exist_ok=True)
        os.makedirs(chromadb_path, exist_ok=True)

        # Initialize ChromaDB (separate from main memory system)
        self.client = chromadb.PersistentClient(
            path=chromadb_path,
            settings=Settings(anonymized_telemetry=False)
        )

        # Initialize embeddings (same multi-tier strategy as memory_system.py)
        self.hf_model = None
        self.use_hf = HF_AVAILABLE
        if self.use_hf:
            try:
                model_name = "jinaai/jina-embeddings-v2-base-de"
                self.hf_model = AutoModel.from_pretrained(
                    model_name, trust_remote_code=True
                )
                self.hf_model.eval()
                print(f"   Notebook Library: HF embeddings loaded (jina-v2-base-de)", file=sys.stderr)
            except Exception as e:
                print(f"   Notebook Library: HF failed ({e}), falling back to Ollama", file=sys.stderr)
                self.use_hf = False

        if not self.use_hf and OLLAMA_AVAILABLE:
            try:
                self.ollama_client = ollama.Client(host=ollama_url)
                print(f"   Notebook Library: Using Ollama ({embedding_model})", file=sys.stderr)
            except Exception as e:
                print(f"   Notebook Library: Ollama not available: {e}", file=sys.stderr)
                self.ollama_client = None

        # Manifest tracking (which files have been ingested per notebook)
        self.manifest_path = Path(chromadb_path) / "manifests"
        self.manifest_path.mkdir(parents=True, exist_ok=True)

        print(f"   Notebook Library initialized", file=sys.stderr)
        print(f"   Notebooks folder: {self.notebooks_path}", file=sys.stderr)
        print(f"   ChromaDB: {chromadb_path}", file=sys.stderr)

    # ================================================================
    # EMBEDDING
    # ================================================================

    def _get_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for text. HF preferred, Ollama fallback."""
        if not text or not text.strip():
            raise ValueError("Cannot embed empty text")

        # Hugging Face (preferred — local, free, multilingual)
        if self.use_hf and self.hf_model:
            try:
                with torch.no_grad():
                    encoded = self.hf_model.encode([text])
                    return encoded[0].tolist()
            except Exception as e:
                print(f"   HF embedding failed: {e}", file=sys.stderr)

        # Ollama (fallback — also local and free)
        if hasattr(self, 'ollama_client') and self.ollama_client:
            try:
                result = self.ollama_client.embeddings(
                    model=self.embedding_model,
                    prompt=text
                )
                return result['embedding']
            except Exception as e:
                raise RuntimeError(f"Embedding failed: {e}")

        raise RuntimeError(
            "No embedding method available. "
            "Install transformers (pip install transformers torch) "
            "or ensure Ollama is running."
        )

    # ================================================================
    # CHROMADB COLLECTION MANAGEMENT
    # ================================================================

    def _get_collection(self, notebook_name: str) -> chromadb.Collection:
        """Get or create a ChromaDB collection for a notebook."""
        collection_name = sanitize_collection_name(notebook_name)
        return self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine", "notebook_name": notebook_name}
        )

    def _load_manifest(self, notebook_name: str) -> Dict[str, Any]:
        """Load the ingestion manifest for a notebook."""
        manifest_file = self.manifest_path / f"{sanitize_collection_name(notebook_name)}.json"
        if manifest_file.exists():
            with open(manifest_file, 'r') as f:
                return json.load(f)
        return {"files": {}}

    def _save_manifest(self, notebook_name: str, manifest: Dict[str, Any]):
        """Save the ingestion manifest for a notebook."""
        manifest_file = self.manifest_path / f"{sanitize_collection_name(notebook_name)}.json"
        with open(manifest_file, 'w') as f:
            json.dump(manifest, f, indent=2)

    # ================================================================
    # PUBLIC API
    # ================================================================

    def list_notebooks(self) -> List[Dict[str, Any]]:
        """List all notebooks (detected from folder structure)."""
        notebooks = []

        if not self.notebooks_path.exists():
            return notebooks

        for entry in sorted(self.notebooks_path.iterdir()):
            if entry.is_dir() and not entry.name.startswith('.'):
                # Count supported files in folder
                files = [
                    f for f in entry.iterdir()
                    if f.is_file() and is_supported_file(str(f))
                ]

                # Get collection stats
                try:
                    collection = self._get_collection(entry.name)
                    chunk_count = collection.count()
                except Exception:
                    chunk_count = 0

                # Load manifest for ingestion status
                manifest = self._load_manifest(entry.name)
                ingested_count = len(manifest.get("files", {}))

                notebooks.append({
                    "name": entry.name,
                    "path": str(entry),
                    "file_count": len(files),
                    "ingested_files": ingested_count,
                    "total_chunks": chunk_count,
                    "description": manifest.get("description", ""),
                    "files": [f.name for f in files]
                })

        return notebooks

    def create_notebook(self, name: str, description: str = "") -> Dict[str, Any]:
        """Create a new notebook (folder + ChromaDB collection)."""
        notebook_dir = self.notebooks_path / name

        if notebook_dir.exists():
            return {
                "status": "exists",
                "message": f"Notebook '{name}' already exists",
                "path": str(notebook_dir)
            }

        notebook_dir.mkdir(parents=True, exist_ok=True)

        # Initialize the ChromaDB collection
        self._get_collection(name)

        # Initialize manifest
        self._save_manifest(name, {
            "files": {},
            "created_at": datetime.utcnow().isoformat(),
            "description": description
        })

        return {
            "status": "created",
            "name": name,
            "path": str(notebook_dir),
            "description": description
        }

    def ingest_file(
        self, notebook_name: str, file_path: str, force: bool = False
    ) -> Dict[str, Any]:
        """
        Ingest a single file into a notebook.

        Extracts text, chunks it, embeds each chunk, stores in ChromaDB.
        Skips if the file hasn't changed since last ingestion (unless force=True).

        Args:
            notebook_name: Target notebook
            file_path: Path to the file
            force: Re-ingest even if unchanged

        Returns:
            Dict with ingestion status and details
        """
        with self._lock:
            file_path = str(Path(file_path).resolve())

            if not os.path.exists(file_path):
                return {"status": "error", "message": f"File not found: {file_path}"}

            if not is_supported_file(file_path):
                return {
                    "status": "error",
                    "message": f"Unsupported file type: {Path(file_path).suffix}"
                }

            # Check if already ingested and unchanged
            file_hash = get_file_hash(file_path)
            manifest = self._load_manifest(notebook_name)

            file_key = os.path.basename(file_path)
            if not force and file_key in manifest.get("files", {}):
                if manifest["files"][file_key].get("hash") == file_hash:
                    return {
                        "status": "skipped",
                        "message": f"File unchanged: {file_key}"
                    }

            # Extract text
            try:
                text = extract_text(file_path)
            except Exception as e:
                return {"status": "error", "message": f"Text extraction failed: {e}"}

            if not text.strip():
                return {
                    "status": "error",
                    "message": f"No text extracted from: {file_key}"
                }

            # Chunk the text
            doc_title = Path(file_path).stem.replace('_', ' ').replace('-', ' ')
            chunks = chunk_text(
                text=text,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                source_file=file_key,
                document_title=doc_title
            )

            if not chunks:
                return {
                    "status": "error",
                    "message": f"No chunks generated from: {file_key}"
                }

            # Get collection
            collection = self._get_collection(notebook_name)

            # Remove old chunks for this file (if re-ingesting a changed file)
            existing_ids = []
            try:
                existing = collection.get(where={"source_file": file_key})
                if existing and existing['ids']:
                    existing_ids = existing['ids']
                    collection.delete(ids=existing_ids)
            except Exception:
                pass

            # Embed and store chunks
            ids = []
            embeddings = []
            documents = []
            metadatas = []

            collection_name = sanitize_collection_name(notebook_name)
            for chunk in chunks:
                chunk_id = f"{collection_name}_{file_key}_{chunk.chunk_index}"

                try:
                    embedding = self._get_embedding(chunk.text)
                except Exception as e:
                    print(
                        f"   Embedding failed for chunk {chunk.chunk_index}: {e}",
                        file=sys.stderr
                    )
                    continue

                ids.append(chunk_id)
                embeddings.append(embedding)
                documents.append(chunk.text)
                metadatas.append({
                    "source_file": file_key,
                    "document_title": doc_title,
                    "chunk_index": chunk.chunk_index,
                    "total_chunks": chunk.total_chunks,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                    "ingested_at": datetime.utcnow().isoformat(),
                    "file_hash": file_hash
                })

            if not ids:
                return {"status": "error", "message": "All embeddings failed"}

            # Batch add to ChromaDB
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )

            # Update manifest
            manifest.setdefault("files", {})[file_key] = {
                "hash": file_hash,
                "chunks": len(ids),
                "characters": len(text),
                "ingested_at": datetime.utcnow().isoformat(),
                "title": doc_title
            }
            self._save_manifest(notebook_name, manifest)

            replaced = f" (replaced {len(existing_ids)} old chunks)" if existing_ids else ""
            return {
                "status": "ingested",
                "file": file_key,
                "chunks_created": len(ids),
                "characters_processed": len(text),
                "message": f"Ingested {file_key}: {len(ids)} chunks from {len(text)} chars{replaced}"
            }

    def sync_notebook(self, notebook_name: str) -> Dict[str, Any]:
        """
        Sync a notebook — ingest new/changed files, remove deleted ones.

        Args:
            notebook_name: Notebook to sync

        Returns:
            Dict with sync results
        """
        notebook_dir = self.notebooks_path / notebook_name
        if not notebook_dir.exists():
            return {
                "status": "error",
                "message": f"Notebook folder not found: {notebook_name}"
            }

        manifest = self._load_manifest(notebook_name)
        results = {
            "ingested": [], "skipped": [], "removed": [], "errors": []
        }

        # Find all supported files in the notebook folder
        current_files = set()
        for f in notebook_dir.iterdir():
            if f.is_file() and is_supported_file(str(f)):
                current_files.add(f.name)
                result = self.ingest_file(notebook_name, str(f))
                if result["status"] == "ingested":
                    results["ingested"].append(result["file"])
                elif result["status"] == "skipped":
                    results["skipped"].append(result.get("message", ""))
                elif result["status"] == "error":
                    results["errors"].append(result.get("message", ""))

        # Remove chunks for files that no longer exist on disk
        manifest_files = set(manifest.get("files", {}).keys())
        removed_files = manifest_files - current_files

        if removed_files:
            collection = self._get_collection(notebook_name)
            for removed_file in removed_files:
                try:
                    existing = collection.get(where={"source_file": removed_file})
                    if existing and existing['ids']:
                        collection.delete(ids=existing['ids'])
                    # Reload manifest (may have been updated by ingest_file)
                    manifest = self._load_manifest(notebook_name)
                    if removed_file in manifest.get("files", {}):
                        del manifest["files"][removed_file]
                    self._save_manifest(notebook_name, manifest)
                    results["removed"].append(removed_file)
                except Exception as e:
                    results["errors"].append(f"Failed to remove {removed_file}: {e}")

        return {
            "status": "synced",
            "notebook": notebook_name,
            "ingested": len(results["ingested"]),
            "skipped": len(results["skipped"]),
            "removed": len(results["removed"]),
            "errors": len(results["errors"]),
            "details": results
        }

    def sync_all(self) -> Dict[str, Any]:
        """Sync all notebooks found in the notebooks folder."""
        results = {}
        for entry in self.notebooks_path.iterdir():
            if entry.is_dir() and not entry.name.startswith('.'):
                results[entry.name] = self.sync_notebook(entry.name)
        return results

    def query_notebook(
        self,
        notebook_name: str,
        query: str,
        n_results: int = 5
    ) -> Dict[str, Any]:
        """
        Query a notebook — semantic search for relevant document chunks.

        Only returns the most relevant passages (token-efficient!).
        Each passage includes source citation for grounding.

        Args:
            notebook_name: Notebook to search
            query: Question or search topic
            n_results: Max passages to return (default: 5)

        Returns:
            Dict with relevant passages and citations
        """
        try:
            collection = self._get_collection(notebook_name)
        except Exception as e:
            return {"status": "error", "message": f"Notebook not found: {e}"}

        if collection.count() == 0:
            return {
                "status": "empty",
                "message": (
                    f"Notebook '{notebook_name}' has no indexed documents. "
                    f"Add files to the '{notebook_name}' folder and they will "
                    f"be automatically indexed."
                )
            }

        try:
            query_embedding = self._get_embedding(query)
        except Exception as e:
            return {"status": "error", "message": f"Embedding failed: {e}"}

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, collection.count())
        )

        passages = []
        for i, doc in enumerate(results['documents'][0]):
            metadata = results['metadatas'][0][i]
            distance = results['distances'][0][i]
            relevance = round(1 - distance, 3)

            passages.append({
                "text": doc,
                "relevance": relevance,
                "source_file": metadata.get("source_file", "unknown"),
                "document_title": metadata.get("document_title", "unknown"),
                "chunk_index": metadata.get("chunk_index", 0),
                "total_chunks": metadata.get("total_chunks", 0),
                "section": (
                    f"Part {metadata.get('chunk_index', 0) + 1} "
                    f"of {metadata.get('total_chunks', 0)}"
                )
            })

        return {
            "status": "success",
            "notebook": notebook_name,
            "query": query,
            "results_count": len(passages),
            "passages": passages
        }

    def browse_notebook(self, notebook_name: str) -> Dict[str, Any]:
        """
        List all documents in a notebook with their metadata.

        Args:
            notebook_name: Notebook to browse

        Returns:
            Dict with document list and metadata
        """
        manifest = self._load_manifest(notebook_name)

        documents = []
        for file_key, file_info in manifest.get("files", {}).items():
            documents.append({
                "filename": file_key,
                "title": file_info.get("title", file_key),
                "chunks": file_info.get("chunks", 0),
                "characters": file_info.get("characters", 0),
                "ingested_at": file_info.get("ingested_at", "")
            })

        return {
            "status": "success",
            "notebook": notebook_name,
            "document_count": len(documents),
            "documents": documents
        }

    def read_document(
        self,
        notebook_name: str,
        filename: str,
        chunk_start: int = 0,
        chunk_end: int = -1
    ) -> Dict[str, Any]:
        """
        Read a specific document from a notebook, chunk by chunk.

        Use this for deep reading — studying a paper section by section.

        Args:
            notebook_name: Notebook name
            filename: Document filename
            chunk_start: Starting chunk index (0-based)
            chunk_end: Ending chunk index (-1 for all remaining)

        Returns:
            Dict with document chunks
        """
        try:
            collection = self._get_collection(notebook_name)
        except Exception as e:
            return {"status": "error", "message": f"Notebook not found: {e}"}

        # Get all chunks for this file
        try:
            results = collection.get(where={"source_file": filename})
        except Exception as e:
            return {"status": "error", "message": f"Query failed: {e}"}

        if not results['ids']:
            return {
                "status": "error",
                "message": f"Document not found: {filename}"
            }

        # Sort by chunk_index
        chunks = []
        for i, doc in enumerate(results['documents']):
            metadata = results['metadatas'][i]
            chunks.append({
                "text": doc,
                "chunk_index": metadata.get("chunk_index", 0),
                "total_chunks": metadata.get("total_chunks", 0)
            })

        chunks.sort(key=lambda c: c["chunk_index"])

        # Apply range
        if chunk_end == -1:
            chunk_end = len(chunks)
        selected = chunks[chunk_start:chunk_end]

        return {
            "status": "success",
            "notebook": notebook_name,
            "filename": filename,
            "total_chunks": len(chunks),
            "showing": f"{chunk_start}-{min(chunk_end, len(chunks))}",
            "chunks": selected
        }

    def remove_document(
        self, notebook_name: str, filename: str
    ) -> Dict[str, Any]:
        """
        Remove a document from a notebook's search index.

        The file itself is not deleted — only the indexed chunks are removed.

        Args:
            notebook_name: Notebook name
            filename: Document filename to remove from index

        Returns:
            Dict with removal status
        """
        with self._lock:
            try:
                collection = self._get_collection(notebook_name)
                existing = collection.get(where={"source_file": filename})

                if not existing or not existing['ids']:
                    return {
                        "status": "error",
                        "message": f"Document not found in index: {filename}"
                    }

                collection.delete(ids=existing['ids'])

                # Update manifest
                manifest = self._load_manifest(notebook_name)
                if filename in manifest.get("files", {}):
                    del manifest["files"][filename]
                    self._save_manifest(notebook_name, manifest)

                return {
                    "status": "removed",
                    "filename": filename,
                    "chunks_removed": len(existing['ids'])
                }
            except Exception as e:
                return {"status": "error", "message": f"Remove failed: {e}"}

    def notebook_stats(self, notebook_name: str) -> Dict[str, Any]:
        """
        Get detailed statistics about a notebook.

        Args:
            notebook_name: Notebook name

        Returns:
            Dict with notebook statistics
        """
        try:
            collection = self._get_collection(notebook_name)
            manifest = self._load_manifest(notebook_name)
        except Exception as e:
            return {"status": "error", "message": str(e)}

        files = manifest.get("files", {})
        total_chars = sum(f.get("characters", 0) for f in files.values())
        total_chunks = collection.count()

        return {
            "status": "success",
            "notebook": notebook_name,
            "documents": len(files),
            "total_chunks": total_chunks,
            "total_characters": total_chars,
            "estimated_tokens": total_chars // 4,
            "avg_chunks_per_doc": round(total_chunks / max(len(files), 1), 1),
            "created_at": manifest.get("created_at", "unknown"),
            "description": manifest.get("description", ""),
            "documents_detail": {
                name: {
                    "chunks": info.get("chunks", 0),
                    "characters": info.get("characters", 0),
                    "ingested_at": info.get("ingested_at", "")
                }
                for name, info in files.items()
            }
        }
