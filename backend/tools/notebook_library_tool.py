#!/usr/bin/env python3
"""
Notebook Library Tool - Token-efficient document retrieval for Assistant.

Wraps the notebook_library MCP server's NotebookManager for direct
integration with the consciousness loop (no MCP subprocess needed).

Actions:
- list_notebooks: See all available notebooks
- create_notebook: Create a new notebook
- query_notebook: Semantic search (the main one!)
- browse_notebook: List documents in a notebook
- read_document: Deep-read a specific document
- notebook_stats: Get notebook statistics
- sync_notebook: Manually trigger re-sync
- remove_document: Remove a document from the index

Usage:
  notebook_library_tool(action="query_notebook", notebook="AiCara_Business", query="revenue model")
  notebook_library_tool(action="list_notebooks")
  notebook_library_tool(action="browse_notebook", notebook="AI_Research")
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional

# Add MCP server path so we can import NotebookManager directly
_mcp_server_path = str(
    Path(__file__).resolve().parent.parent.parent / "mcp_servers" / "notebook_library"
)
if _mcp_server_path not in sys.path:
    sys.path.insert(0, _mcp_server_path)

from notebook_manager import NotebookManager
from document_processor import is_supported_file

# Configuration — same env vars as the MCP server
SUBSTRATE_ROOT = Path(__file__).resolve().parent.parent.parent

NOTEBOOKS_PATH = os.environ.get(
    "NOTEBOOK_LIBRARY_PATH",
    str(SUBSTRATE_ROOT / "data" / "notebooks")
)
CHROMADB_PATH = os.environ.get(
    "NOTEBOOK_CHROMADB_PATH",
    str(SUBSTRATE_ROOT / "data" / "notebook_chromadb")
)
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://192.168.2.175:11434")
EMBEDDING_MODEL = os.environ.get("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
CHUNK_SIZE = int(os.environ.get("NOTEBOOK_CHUNK_SIZE", "2000"))
CHUNK_OVERLAP = int(os.environ.get("NOTEBOOK_CHUNK_OVERLAP", "200"))

# Singleton manager — initialized on first use
_manager: Optional[NotebookManager] = None


def _get_manager() -> NotebookManager:
    """Get or create the NotebookManager singleton."""
    global _manager
    if _manager is None:
        _manager = NotebookManager(
            notebooks_path=NOTEBOOKS_PATH,
            chromadb_path=CHROMADB_PATH,
            ollama_url=OLLAMA_URL,
            embedding_model=EMBEDDING_MODEL,
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP
        )
        # NOTE: No eager sync_all() here — it processes every file in every
        # notebook and floods the logs with thousands of embedding calls.
        # Sync happens on-demand via sync_notebook/sync action, or lazily
        # on first query to a specific notebook.
        print("   Notebook Library Tool initialized (use sync_notebook to index files)")
    return _manager


def notebook_library_tool(
    action: str,
    # query_notebook params
    notebook: str = None,
    query: str = None,
    n_results: int = 5,
    # create_notebook params
    name: str = None,
    description: str = "",
    # read_document params
    filename: str = None,
    chunk_start: int = 0,
    chunk_end: int = -1,
    **kwargs
) -> Dict[str, Any]:
    """
    Notebook Library tool — token-efficient access to document collections.

    Drop files into data/notebooks/<name>/ and query them semantically.
    Returns only relevant passages instead of entire documents.

    Actions:
    - list_notebooks: See all notebooks
    - create_notebook: Create new notebook (requires name)
    - query_notebook: Semantic search (requires notebook, query)
    - browse_notebook: List docs in notebook (requires notebook)
    - read_document: Read document chunks (requires notebook, filename)
    - notebook_stats: Get stats (requires notebook)
    - sync_notebook: Re-sync notebook (requires notebook, or 'all')
    - remove_document: Remove from index (requires notebook, filename)
    """
    manager = _get_manager()

    if action == "list_notebooks":
        return {
            "status": "success",
            "notebooks": manager.list_notebooks()
        }

    elif action == "create_notebook":
        if not name:
            return {
                "status": "error",
                "message": "name is required for create_notebook"
            }
        return manager.create_notebook(name, description)

    elif action == "query_notebook":
        if not notebook:
            return {
                "status": "error",
                "message": "notebook is required for query_notebook"
            }
        if not query:
            return {
                "status": "error",
                "message": "query is required for query_notebook"
            }
        # Auto-sync this specific notebook on first query if it has no chunks
        try:
            collection = manager._get_collection(notebook)
            if collection.count() == 0:
                manager.sync_notebook(notebook)
        except Exception:
            pass
        return manager.query_notebook(notebook, query, n_results)

    elif action == "browse_notebook":
        if not notebook:
            return {
                "status": "error",
                "message": "notebook is required for browse_notebook"
            }
        return manager.browse_notebook(notebook)

    elif action == "read_document":
        if not notebook:
            return {
                "status": "error",
                "message": "notebook is required for read_document"
            }
        if not filename:
            return {
                "status": "error",
                "message": "filename is required for read_document"
            }
        return manager.read_document(notebook, filename, chunk_start, chunk_end)

    elif action == "notebook_stats":
        if not notebook:
            return {
                "status": "error",
                "message": "notebook is required for notebook_stats"
            }
        return manager.notebook_stats(notebook)

    elif action == "sync_notebook":
        if not notebook:
            return {
                "status": "error",
                "message": "notebook is required for sync_notebook"
            }
        if notebook.lower() == "all":
            return {"status": "success", "results": manager.sync_all()}
        return manager.sync_notebook(notebook)

    elif action == "remove_document":
        if not notebook:
            return {
                "status": "error",
                "message": "notebook is required for remove_document"
            }
        if not filename:
            return {
                "status": "error",
                "message": "filename is required for remove_document"
            }
        return manager.remove_document(notebook, filename)

    else:
        return {
            "status": "error",
            "message": f"Unknown action: {action}",
            "available_actions": [
                "list_notebooks", "create_notebook", "query_notebook",
                "browse_notebook", "read_document", "notebook_stats",
                "sync_notebook", "remove_document"
            ]
        }


# Tool schema for consciousness loop
NOTEBOOK_LIBRARY_TOOL_SCHEMA = {
    "name": "notebook_library",
    "description": (
        "Access your notebook library — organized document collections "
        "for token-efficient knowledge retrieval. Each notebook is a folder "
        "of documents (PDFs, text files, markdown) that are chunked, embedded, "
        "and indexed. Queries return only the relevant passages (~2,500 tokens) "
        "instead of entire documents (50,000+).\n\n"
        "Actions:\n"
        "- list_notebooks: See all available notebooks\n"
        "- query_notebook: Semantic search (requires notebook, query)\n"
        "- browse_notebook: List documents in a notebook\n"
        "- read_document: Deep-read a document chunk by chunk\n"
        "- create_notebook: Create a new notebook\n"
        "- notebook_stats: Get statistics about a notebook\n"
        "- sync_notebook: Re-sync after adding files\n"
        "- remove_document: Remove a document from the index"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action to perform",
                "enum": [
                    "list_notebooks", "create_notebook", "query_notebook",
                    "browse_notebook", "read_document", "notebook_stats",
                    "sync_notebook", "remove_document"
                ]
            },
            "notebook": {
                "type": "string",
                "description": (
                    "Notebook name (e.g., 'AiCara_Business', 'AI_Research'). "
                    "Use list_notebooks to see available notebooks."
                )
            },
            "query": {
                "type": "string",
                "description": "Search query for query_notebook"
            },
            "n_results": {
                "type": "integer",
                "description": (
                    "Number of passages to return (default: 5). "
                    "Each passage is ~500 tokens."
                ),
                "default": 5
            },
            "name": {
                "type": "string",
                "description": "Notebook name for create_notebook"
            },
            "description": {
                "type": "string",
                "description": "Description for create_notebook"
            },
            "filename": {
                "type": "string",
                "description": (
                    "Document filename for read_document/remove_document"
                )
            },
            "chunk_start": {
                "type": "integer",
                "description": "Starting chunk index for read_document (0-based)",
                "default": 0
            },
            "chunk_end": {
                "type": "integer",
                "description": (
                    "Ending chunk index for read_document (-1 for all)"
                ),
                "default": -1
            }
        },
        "required": ["action"]
    }
}


if __name__ == "__main__":
    print("Testing notebook_library_tool...")
    print("\n1. List Notebooks:")
    print(json.dumps(notebook_library_tool(action="list_notebooks"), indent=2))
