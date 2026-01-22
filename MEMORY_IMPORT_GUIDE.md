# Memory Import Guide

This guide explains how to import memories into the substrate memory system.

## Memory Layers

- **Core memory**: essential, current facts loaded into every request.
- **Archival memory**: long-term storage with semantic search.

## Data Formats

### JSON (recommended)

```json
{
  "core": {
    "persona": "I am a capable, reliable AI assistant.",
    "human": "Primary user. Track preferences and goals.",
    "relationship": "Collaborative partnership focused on clarity and outcomes."
  },
  "notes": {
    "preferences": "Prefers morning strategy sessions."
  },
  "memories": [
    {
      "content": "User mentioned a new project deadline next month.",
      "type": "fact",
      "importance": 6,
      "tags": ["project", "timeline"]
    },
    {
      "content": "User prefers concise summaries.",
      "type": "preference",
      "importance": 7,
      "tags": ["communication", "style"]
    }
  ]
}
```

### CSV (optional)

```csv
content,type,importance,tags
"Prefers morning strategy sessions",preference,7,"work,timing"
"Tracking quarterly goals for the team",fact,6,"work,planning"
```

## Import Workflow

1. Create a JSON file (example above) or a CSV file.
2. Run the import script:

```bash
python backend/import_memories.py --file ./memories.json
```

3. Verify via the API or by inspecting the database (default: `substrate.db`).

## Tips

- Keep core memory short and current.
- Move detailed history to archival memory.
- Tag memories for easy retrieval.
