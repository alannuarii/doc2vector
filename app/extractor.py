"""
extractor.py — Document Extraction Module

Handles PDF extraction via pymupdf4llm and native Markdown/text file reading.
"""

import io
import pymupdf4llm


def extract_pdf(file_bytes: bytes) -> str:
    """
    Extract PDF content to Markdown format using pymupdf4llm.
    Preserves tables and structural formatting.
    """
    doc = pymupdf4llm.to_markdown(io.BytesIO(file_bytes))
    return doc


def extract_markdown(file_bytes: bytes) -> str:
    """
    Read Markdown/text file content with UTF-8 decoding.
    Falls back to latin-1 if UTF-8 decoding fails.
    """
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1", errors="replace")


def extract(filename: str, file_bytes: bytes) -> str:
    """
    Route extraction based on file extension.

    Supported formats:
    - .pdf → pymupdf4llm Markdown extraction
    - .md, .markdown, .txt → native UTF-8 reading

    Raises:
        ValueError: If file extension is not supported.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        return extract_pdf(file_bytes)
    elif ext in ("md", "markdown", "txt"):
        return extract_markdown(file_bytes)
    else:
        raise ValueError(f"Unsupported file format: .{ext}")
