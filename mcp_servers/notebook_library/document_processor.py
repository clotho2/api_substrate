#!/usr/bin/env python3
"""
Document Processor - Extract text from files and chunk for vector storage.

Supported formats:
- PDF (via PyMuPDF)
- Plain text (.txt)
- Markdown (.md)

Chunking strategy:
- Split by paragraphs, then combine into chunks of target size
- Overlap between chunks for context continuity
"""

import os
import hashlib
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass

# PDF support
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

SUPPORTED_EXTENSIONS = {'.pdf', '.txt', '.md', '.text', '.markdown'}


@dataclass
class DocumentChunk:
    """A chunk of a document ready for embedding."""
    text: str
    chunk_index: int
    total_chunks: int
    source_file: str
    document_title: str
    char_start: int
    char_end: int


def get_file_hash(file_path: str) -> str:
    """Get MD5 hash of a file for change detection."""
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        for block in iter(lambda: f.read(8192), b''):
            hasher.update(block)
    return hasher.hexdigest()


def is_supported_file(file_path: str) -> bool:
    """Check if a file type is supported for ingestion."""
    return Path(file_path).suffix.lower() in SUPPORTED_EXTENSIONS


def extract_text(file_path: str) -> str:
    """
    Extract text from a file.

    Args:
        file_path: Path to the file

    Returns:
        Extracted text content

    Raises:
        ValueError: If file type is not supported
        FileNotFoundError: If file doesn't exist
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = path.suffix.lower()

    if ext == '.pdf':
        return _extract_pdf(file_path)
    elif ext in {'.txt', '.md', '.text', '.markdown'}:
        return _extract_text_file(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def _extract_pdf(file_path: str) -> str:
    """Extract text from PDF using PyMuPDF."""
    if not PYMUPDF_AVAILABLE:
        raise RuntimeError("PyMuPDF not installed. Run: pip install PyMuPDF")

    doc = fitz.open(file_path)
    text_parts = []

    for page in doc:
        text_parts.append(page.get_text())

    doc.close()
    return '\n\n'.join(text_parts)


def _extract_text_file(file_path: str) -> str:
    """Read plain text or markdown file."""
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


def chunk_text(
    text: str,
    chunk_size: int = 2000,
    chunk_overlap: int = 200,
    source_file: str = "",
    document_title: str = ""
) -> List[DocumentChunk]:
    """
    Split text into overlapping chunks, respecting paragraph boundaries.

    Args:
        text: Full document text
        chunk_size: Target size per chunk in characters
        chunk_overlap: Overlap between consecutive chunks
        source_file: Source file path for metadata
        document_title: Document title for metadata

    Returns:
        List of DocumentChunk objects
    """
    if not text.strip():
        return []

    # Split into paragraphs
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    # If no paragraph breaks, split by single newlines
    if len(paragraphs) <= 1 and len(text) > chunk_size:
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]

    # If still one giant block, force-split by character count
    if len(paragraphs) <= 1 and len(text) > chunk_size:
        paragraphs = _force_split(text, chunk_size)

    chunks = []
    current_chunk = ""
    current_start = 0
    running_pos = 0

    for para in paragraphs:
        # If adding this paragraph exceeds chunk size, finalize current chunk
        if current_chunk and len(current_chunk) + len(para) + 2 > chunk_size:
            chunks.append(DocumentChunk(
                text=current_chunk.strip(),
                chunk_index=len(chunks),
                total_chunks=0,  # Set after all chunks created
                source_file=source_file,
                document_title=document_title,
                char_start=current_start,
                char_end=current_start + len(current_chunk)
            ))

            # Start new chunk with overlap from end of current
            if len(current_chunk) > chunk_overlap:
                overlap_text = current_chunk[-chunk_overlap:]
            else:
                overlap_text = current_chunk
            current_start = current_start + len(current_chunk) - len(overlap_text)
            current_chunk = overlap_text + "\n\n" + para
        else:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para

    # Don't forget the last chunk
    if current_chunk.strip():
        chunks.append(DocumentChunk(
            text=current_chunk.strip(),
            chunk_index=len(chunks),
            total_chunks=0,
            source_file=source_file,
            document_title=document_title,
            char_start=current_start,
            char_end=current_start + len(current_chunk)
        ))

    # Set total_chunks on all
    total = len(chunks)
    for chunk in chunks:
        chunk.total_chunks = total

    return chunks


def _force_split(text: str, chunk_size: int) -> List[str]:
    """Force-split text that has no natural break points."""
    parts = []
    for i in range(0, len(text), chunk_size):
        part = text[i:i + chunk_size]
        # Try to break at a sentence boundary
        last_period = part.rfind('. ')
        if last_period > chunk_size // 2:
            parts.append(part[:last_period + 1])
        else:
            parts.append(part)
    return parts
