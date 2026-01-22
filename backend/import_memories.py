#!/usr/bin/env python3
"""
Generic memory import entry point.

Supported formats:
- JSON (.json)
- CSV (.csv)
- Text (.txt, .md)
- Letta agent file (.af)
"""

import argparse
from pathlib import Path

from core.state_manager import StateManager
from import_nate_memories import MemoryImporter

try:
    from core.memory_system import MemorySystem
except ImportError:
    MemorySystem = None


def _choose_format(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".json", ".jsonl"}:
        return "json"
    if ext in {".txt", ".md"}:
        return "text"
    if ext == ".csv":
        return "csv"
    if ext == ".af":
        return "letta"
    raise ValueError(f"Unsupported file extension: {ext}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import memories into substrate")
    parser.add_argument("--file", required=True, help="Path to memory file")
    parser.add_argument(
        "--format",
        choices=["json", "text", "csv", "letta"],
        help="Override format detection"
    )
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    state = StateManager()
    memory = MemorySystem() if MemorySystem else None
    importer = MemoryImporter(state, memory)

    fmt = args.format or _choose_format(file_path)

    if fmt == "json":
        importer.import_from_json(str(file_path))
    elif fmt == "text":
        importer.import_from_text(str(file_path))
    elif fmt == "csv":
        importer.import_from_csv(str(file_path))
    elif fmt == "letta":
        importer.import_from_letta(str(file_path))


if __name__ == "__main__":
    main()
