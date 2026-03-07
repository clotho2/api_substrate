# Notebook Library MCP Server

Token-efficient document retrieval for substrate AI agents. Drop PDFs, text files, and markdown into notebook folders — they get chunked, embedded, and indexed for semantic search. Queries return only the most relevant passages (~2,500 tokens) instead of loading entire documents (50,000+).

## What It Does

Your AI agent gets a `notebook_library` tool with these actions:

| Action | Description |
|--------|-------------|
| `list_notebooks` | See all available notebooks |
| `create_notebook` | Create a new notebook collection |
| `query_notebook` | Semantic search within a notebook (the main one!) |
| `browse_notebook` | List documents in a notebook |
| `read_document` | Deep-read a specific document chunk by chunk |
| `notebook_stats` | Get statistics about a notebook |
| `sync_notebook` | Re-sync after adding/changing files |
| `remove_document` | Remove a document from the search index |

**Supported file formats:** `.pdf`, `.txt`, `.md`, `.text`, `.markdown`

## Architecture

```
data/
├── notebooks/               # Your document folders
│   ├── Research_Papers/     # Each subfolder = one notebook
│   │   ├── paper1.pdf
│   │   └── notes.md
│   └── Business_Docs/
│       └── plan.txt
└── notebook_chromadb/       # Vector database (auto-created)
    └── manifests/           # File change tracking

mcp_servers/
└── notebook_library/
    ├── server.py              # MCP server (if running standalone)
    ├── notebook_manager.py    # Core: ChromaDB ingestion + search
    ├── document_processor.py  # Text extraction + chunking
    ├── file_watcher.py        # Auto-ingestion on file changes
    └── requirements.txt

backend/tools/
├── notebook_library_tool.py        # Tool wrapper for consciousness loop
└── notebook_library_tool_schema.json  # Tool schema definition
```

**Embedding strategy (multi-tier fallback):**
1. **Hugging Face** (`jinaai/jina-embeddings-v2-base-de`) — local, free, multilingual
2. **Ollama** (`nomic-embed-text`) — local fallback if HF fails

No external API keys needed. Everything runs locally.

## Setup Guide

### 1. Install Dependencies

From your substrate root:

```bash
pip install -r mcp_servers/notebook_library/requirements.txt
```

Key dependencies:
- `chromadb==0.4.18` — vector database
- `transformers` + `torch` — Hugging Face embeddings (primary)
- `ollama` — embedding fallback
- `PyMuPDF` — PDF text extraction
- `watchdog` — file system monitoring

> **Note:** First run will download the Hugging Face embedding model (~270MB). This is a one-time download.

### 2. Create Data Directories

```bash
mkdir -p data/notebooks
mkdir -p data/notebook_chromadb
```

### 3. Copy the MCP Server Files

Copy the entire `mcp_servers/notebook_library/` directory into your substrate:

```
your_substrate/
└── mcp_servers/
    └── notebook_library/
        ├── __init__.py
        ├── server.py
        ├── notebook_manager.py
        ├── document_processor.py
        ├── file_watcher.py
        └── requirements.txt
```

### 4. Copy the Tool Wrapper

Copy these two files into your `backend/tools/` directory:

**`backend/tools/notebook_library_tool.py`** — The tool function your consciousness loop calls. This imports `NotebookManager` directly (no subprocess).

**`backend/tools/notebook_library_tool_schema.json`** — The tool schema so your agent knows how to call it.

### 5. Register the Tool in Your Consciousness Loop

Three integration points:

#### a) Import in `integration_tools.py`

Add to your imports:

```python
from tools.notebook_library_tool import notebook_library_tool as _notebook_library_tool
```

Add the wrapper method to your `IntegrationTools` class:

```python
def notebook_library(self, **kwargs) -> Dict[str, Any]:
    """
    Notebook Library — token-efficient document retrieval.
    """
    try:
        result = _notebook_library_tool(**kwargs)
        return result
    except Exception as e:
        return {
            "status": "error",
            "message": f"Notebook library error: {str(e)}"
        }
```

Add `'notebook_library_tool'` to your tool schema loading list so the JSON schema gets picked up.

#### b) Add tool call handler in `consciousness_loop.py`

In your tool execution block (where you handle `elif tool_name == "..."` cases), add:

```python
elif tool_name == "notebook_library":
    result = self.tools.notebook_library(**arguments)
```

#### c) Verify schema loading

The tool schema file (`notebook_library_tool_schema.json`) must be in `backend/tools/` alongside your other tool schemas. The schema loader should pick it up automatically if it follows the same pattern as your other tools.

### 6. Add Documents

Create notebook folders and drop files in:

```bash
mkdir -p data/notebooks/My_Research
cp ~/some_paper.pdf data/notebooks/My_Research/
cp ~/notes.md data/notebooks/My_Research/
```

Documents are auto-ingested when your agent first queries the notebook, or you can trigger a manual sync via the `sync_notebook` action.

## Environment Variables (Optional)

All have sensible defaults. Override only if needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `NOTEBOOK_LIBRARY_PATH` | `data/notebooks` | Where notebook folders live |
| `NOTEBOOK_CHROMADB_PATH` | `data/notebook_chromadb` | Vector database storage |
| `OLLAMA_BASE_URL` | `http://192.168.2.175:11434` | Ollama server (fallback embeddings) |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Ollama model name |
| `NOTEBOOK_CHUNK_SIZE` | `2000` | Characters per chunk |
| `NOTEBOOK_CHUNK_OVERLAP` | `200` | Overlap between chunks |

**Important:** Update `OLLAMA_BASE_URL` to point to your own Ollama instance if you're using the Ollama fallback. The default points to the original developer's local network.

## How It Works

1. **Ingestion:** Documents are split into chunks (~2000 chars each with 200 char overlap), embedded using Hugging Face or Ollama, and stored in ChromaDB collections (one per notebook).

2. **Querying:** Your agent's query gets embedded with the same model, then ChromaDB finds the most similar chunks via cosine similarity. Only the top N passages are returned (default 5).

3. **File tracking:** A manifest system (MD5 hashes) tracks which files have been ingested. Changed files get re-processed; unchanged files are skipped.

4. **File watching:** A watchdog-based file watcher monitors notebook folders and auto-ingests new/modified files with a 2-second debounce.

## Example Agent Usage

Once integrated, your agent can use it like:

```
# List what's available
notebook_library(action="list_notebooks")

# Search for something specific
notebook_library(action="query_notebook", notebook="Research_Papers", query="transformer attention mechanisms")

# Browse a notebook's contents
notebook_library(action="browse_notebook", notebook="Research_Papers")

# Deep-read a specific document
notebook_library(action="read_document", notebook="Research_Papers", filename="paper1.pdf")

# Create a new notebook
notebook_library(action="create_notebook", name="Meeting_Notes", description="Weekly team meetings")
```

## Troubleshooting

**"No notebooks found"** — Make sure `data/notebooks/` exists and has at least one subfolder with files in it.

**Slow first query** — The first query to a notebook triggers ingestion (chunking + embedding all documents). Subsequent queries are fast. For large collections, run `sync_notebook` first.

**Embedding model download** — First run downloads the Jina embeddings model (~270MB). If this fails behind a firewall, the system falls back to Ollama. Make sure either HF model access or an Ollama instance is available.

**ChromaDB version mismatch** — Pin to `chromadb==0.4.18`. Newer versions may have breaking API changes.

**OLLAMA_BASE_URL** — If you see Ollama connection errors and you're not using Ollama, that's fine — it's just the fallback failing after HF already succeeded. If HF also fails, update this URL to your Ollama instance.
