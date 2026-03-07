#!/usr/bin/env python3
"""
Notebook Library MCP Server

Gives Assistant access to organized document collections ("notebooks").
Each notebook is a folder of documents that get chunked, embedded, and indexed
for token-efficient semantic search.

Usage:
  1. Drop files into folders under data/notebooks/
     (e.g., data/notebooks/AI_Consciousness/paper.pdf)
  2. The server auto-ingests new files via file watcher
  3. Assistant queries notebooks and gets back only relevant passages

Tools:
  - list_notebooks:    See all available notebooks
  - create_notebook:   Create a new notebook
  - query_notebook:    Semantic search within a notebook (the main one!)
  - browse_notebook:   List documents in a notebook
  - read_document:     Deep-read a specific document chunk by chunk
  - notebook_stats:    Get detailed statistics
  - sync_notebook:     Manually trigger re-sync
  - remove_document:   Remove a document from the index

Token Efficiency:
  A query returns ~5 relevant passages (~2,500 tokens) instead of
  reading entire documents (50,000+ tokens). That's a 95%+ reduction.
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from typing import Dict, Any

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent))

from notebook_manager import NotebookManager
from file_watcher import NotebookWatcher
from document_processor import is_supported_file, SUPPORTED_EXTENSIONS

# MCP imports
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print(
        "ERROR: MCP library not available. Install with: pip install mcp",
        file=sys.stderr
    )


# ============================================
# CONFIGURATION
# ============================================

SUBSTRATE_ROOT = Path(__file__).parent.parent.parent.resolve()

# Configurable via environment variables
NOTEBOOKS_PATH = os.environ.get(
    "NOTEBOOK_LIBRARY_PATH",
    str(SUBSTRATE_ROOT / "data" / "notebooks")
)
CHROMADB_PATH = os.environ.get(
    "NOTEBOOK_CHROMADB_PATH",
    str(SUBSTRATE_ROOT / "data" / "notebook_chromadb")
)
OLLAMA_URL = os.environ.get(
    "OLLAMA_BASE_URL", "http://192.168.2.175:11434"
)
EMBEDDING_MODEL = os.environ.get(
    "OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"
)
CHUNK_SIZE = int(os.environ.get("NOTEBOOK_CHUNK_SIZE", "2000"))
CHUNK_OVERLAP = int(os.environ.get("NOTEBOOK_CHUNK_OVERLAP", "200"))


# ============================================
# GLOBAL MANAGER (initialized on startup)
# ============================================

manager: NotebookManager = None
watcher: NotebookWatcher = None


def init_manager():
    """Initialize the notebook manager and file watcher."""
    global manager, watcher

    manager = NotebookManager(
        notebooks_path=NOTEBOOKS_PATH,
        chromadb_path=CHROMADB_PATH,
        ollama_url=OLLAMA_URL,
        embedding_model=EMBEDDING_MODEL,
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP
    )

    # Initial sync of all notebooks
    print(f"   Syncing all notebooks...", file=sys.stderr)
    sync_results = manager.sync_all()
    for nb_name, result in sync_results.items():
        ingested = result.get("ingested", 0)
        skipped = result.get("skipped", 0)
        if ingested > 0:
            print(
                f"     {nb_name}: ingested {ingested} new files",
                file=sys.stderr
            )
        else:
            print(
                f"     {nb_name}: up to date ({skipped} files)",
                file=sys.stderr
            )

    # Start file watcher for auto-ingestion
    def on_file_change(notebook_name, filename, event_type, file_path):
        """Handle file changes detected by watcher."""
        if event_type in ("created", "modified"):
            if is_supported_file(file_path):
                print(
                    f"   Auto-ingesting: {notebook_name}/{filename}",
                    file=sys.stderr
                )
                result = manager.ingest_file(notebook_name, file_path)
                print(
                    f"     {result.get('message', result.get('status'))}",
                    file=sys.stderr
                )
        elif event_type == "deleted":
            print(
                f"   Removing from index: {notebook_name}/{filename}",
                file=sys.stderr
            )
            manager.remove_document(notebook_name, filename)

    watcher = NotebookWatcher(NOTEBOOKS_PATH, on_file_change)
    watcher.start()


# ============================================
# MCP SERVER
# ============================================

def create_server():
    """Create and configure the MCP server."""
    if not MCP_AVAILABLE:
        print("ERROR: MCP library not available", file=sys.stderr)
        sys.exit(1)

    server = Server("notebook-library")

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name="list_notebooks",
                description=(
                    "List all available notebooks in your library. "
                    "Shows notebook names, document counts, and indexing status. "
                    "Use this to see what knowledge collections are available."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            Tool(
                name="create_notebook",
                description=(
                    "Create a new notebook (knowledge collection). "
                    "This creates a folder where documents can be added. "
                    "Use descriptive names like 'AI_Consciousness' or "
                    "'AiCara_Business'."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": (
                                "Notebook name (becomes a folder name)"
                            )
                        },
                        "description": {
                            "type": "string",
                            "description": (
                                "Brief description of what this notebook "
                                "contains"
                            ),
                            "default": ""
                        }
                    },
                    "required": ["name"]
                }
            ),
            Tool(
                name="query_notebook",
                description=(
                    "Search a notebook for information relevant to your "
                    "question. Returns the most relevant document passages "
                    "with source citations. This is token-efficient: only "
                    "retrieves the specific passages you need, not entire "
                    "documents. Use this as your primary way to access "
                    "notebook knowledge."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "notebook": {
                            "type": "string",
                            "description": "Notebook name to search"
                        },
                        "query": {
                            "type": "string",
                            "description": (
                                "Your question or search topic"
                            )
                        },
                        "n_results": {
                            "type": "integer",
                            "description": (
                                "Number of passages to return (default: 5)"
                            ),
                            "default": 5
                        }
                    },
                    "required": ["notebook", "query"]
                }
            ),
            Tool(
                name="browse_notebook",
                description=(
                    "List all documents in a notebook with their metadata. "
                    "Use this to see what's available before querying, or "
                    "to explore a notebook's contents."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "notebook": {
                            "type": "string",
                            "description": "Notebook name to browse"
                        }
                    },
                    "required": ["notebook"]
                }
            ),
            Tool(
                name="read_document",
                description=(
                    "Read a specific document from a notebook, chunk by "
                    "chunk. Use this for deep reading — studying a paper "
                    "section by section rather than searching for specific "
                    "info. Specify chunk_start and chunk_end to read "
                    "specific sections."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "notebook": {
                            "type": "string",
                            "description": "Notebook name"
                        },
                        "filename": {
                            "type": "string",
                            "description": (
                                "Document filename (from browse_notebook)"
                            )
                        },
                        "chunk_start": {
                            "type": "integer",
                            "description": (
                                "Starting chunk index (0-based, default: 0)"
                            ),
                            "default": 0
                        },
                        "chunk_end": {
                            "type": "integer",
                            "description": (
                                "Ending chunk index (-1 for all remaining, "
                                "default: -1)"
                            ),
                            "default": -1
                        }
                    },
                    "required": ["notebook", "filename"]
                }
            ),
            Tool(
                name="notebook_stats",
                description=(
                    "Get detailed statistics about a notebook: document "
                    "count, chunk count, total characters, estimated tokens, "
                    "and per-document breakdown."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "notebook": {
                            "type": "string",
                            "description": "Notebook name"
                        }
                    },
                    "required": ["notebook"]
                }
            ),
            Tool(
                name="sync_notebook",
                description=(
                    "Manually trigger a sync of a notebook. Ingests any "
                    "new or changed files and removes deleted ones from "
                    "the index. Normally this happens automatically via "
                    "the file watcher, but use this to force a refresh. "
                    "Pass 'all' to sync every notebook."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "notebook": {
                            "type": "string",
                            "description": (
                                "Notebook name to sync, or 'all'"
                            )
                        }
                    },
                    "required": ["notebook"]
                }
            ),
            Tool(
                name="remove_document",
                description=(
                    "Remove a document from a notebook's search index. "
                    "The actual file is not deleted — only the indexed "
                    "chunks are removed. The file will be re-indexed on "
                    "next sync if it still exists in the folder."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "notebook": {
                            "type": "string",
                            "description": "Notebook name"
                        },
                        "filename": {
                            "type": "string",
                            "description": (
                                "Document filename to remove from index"
                            )
                        }
                    },
                    "required": ["notebook", "filename"]
                }
            )
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """Handle tool calls."""
        try:
            if name == "list_notebooks":
                result = manager.list_notebooks()
            elif name == "create_notebook":
                result = manager.create_notebook(
                    arguments["name"],
                    arguments.get("description", "")
                )
            elif name == "query_notebook":
                result = manager.query_notebook(
                    arguments["notebook"],
                    arguments["query"],
                    arguments.get("n_results", 5)
                )
            elif name == "browse_notebook":
                result = manager.browse_notebook(arguments["notebook"])
            elif name == "read_document":
                result = manager.read_document(
                    arguments["notebook"],
                    arguments["filename"],
                    arguments.get("chunk_start", 0),
                    arguments.get("chunk_end", -1)
                )
            elif name == "notebook_stats":
                result = manager.notebook_stats(arguments["notebook"])
            elif name == "sync_notebook":
                notebook = arguments["notebook"]
                if notebook.lower() == "all":
                    result = manager.sync_all()
                else:
                    result = manager.sync_notebook(notebook)
            elif name == "remove_document":
                result = manager.remove_document(
                    arguments["notebook"],
                    arguments["filename"]
                )
            else:
                result = {
                    "status": "error",
                    "message": f"Unknown tool: {name}"
                }
        except Exception as e:
            result = {
                "status": "error",
                "message": f"Tool error: {str(e)}"
            }

        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]

    return server


async def main():
    """Run the MCP server."""
    # Initialize manager and file watcher
    init_manager()

    # Start MCP server
    server = create_server()
    print(f"Notebook Library MCP Server starting...", file=sys.stderr)
    print(f"   Notebooks: {NOTEBOOKS_PATH}", file=sys.stderr)
    print(
        f"   Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        file=sys.stderr
    )

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
