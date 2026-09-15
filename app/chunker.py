"""
chunker.py — Header-Aware Semantic Chunking

Splits cleaned Markdown text into semantically meaningful chunks
by respecting document structure (headers) and applying size constraints.
"""

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    """Represents a text chunk with its section context."""
    text: str
    section_title: str
    chunk_index: int = 0


def extract_header_title(line: str) -> str | None:
    """
    Check if a line represents a section heading or component title.
    Supports:
    1. Markdown headings (# through ######)
    2. Bold wrapped headings (**###### Title** or **Title**)
    3. Component part group lines (e.g. P3780-362 OIL SYSTEM PARTS, P3780-390-01 OIL COOLER ASSY)
    4. Group / Figure component lines (e.g. 01-01 CRANKCASE ASSY, FIG. 12 OIL PUMP)
    """
    s = line.strip()
    if not s or len(s) < 3:
        return None

    # Strip markdown bold/italic wrapper: **text** or *text*
    s_unwrapped = re.sub(r"^\*{1,3}(.*?)\*{1,3}$", r"\1", s).strip()

    # 1. Standard markdown header (# through ######)
    m = re.match(r"^(#{1,6})\s+(.+)$", s_unwrapped)
    if m:
        return m.group(2).strip()

    # 2. Component / catalog part group codes (e.g. P3780-362 OIL SYSTEM PARTS, P3780-390-01 OIL COOLER ASSY)
    m = re.match(r"^([A-Z]\d{3,5}(?:-\d{2,4}){1,3}\s+[A-Za-z0-9\s/&,._()-]{3,})$", s_unwrapped)
    if m:
        return m.group(1).strip()

    # 3. Numeric part group / section codes (e.g. 01-01 CRANKCASE ASSY, FIG. 12 OIL PUMP)
    m = re.match(r"^(?:FIG(?:URE)?\.?|GROUP|SECTION)?\s*(\d{1,4}[-.]\d{1,4}(?:[-.]\d{1,4})?\s+[A-Z][A-Za-z0-9\s/&,._()-]{3,})$", s_unwrapped, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    return None


def _split_by_headers(text: str) -> list[tuple[str, str]]:
    """
    Split text into sections based on headers and component titles.
    Updates current_heading whenever a closer heading (# through ###### or
    component title e.g. P3780-390-01 OIL COOLER ASSY) is encountered.

    Returns a list of (section_title, section_content) tuples.
    """
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_lines: list[str] = []

    for line in text.splitlines(keepends=True):
        title = extract_header_title(line)
        if title is not None:
            content = "".join(current_lines).strip()
            if content:
                sections.append((current_heading, content))
                current_lines = []
            current_heading = title
            current_lines.append(line)
        else:
            current_lines.append(line)

    content = "".join(current_lines).strip()
    if content:
        sections.append((current_heading, content))

    # If no headers found, return the entire text as one section
    if not sections and text.strip():
        sections.append(("", text.strip()))

    return sections


def _split_section_by_size(
    text: str,
    section_title: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Chunk]:
    """
    Split a section into chunks respecting size limits.
    Uses paragraph boundaries where possible, falling back to sentence
    and then hard character splits.
    """
    if len(text) <= chunk_size:
        return [Chunk(text=text, section_title=section_title)]

    chunks: list[Chunk] = []

    # Split by paragraphs first (double newline)
    paragraphs = re.split(r"\n{2,}", text)
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # If adding this paragraph would exceed chunk_size
        if current_chunk and len(current_chunk) + len(para) + 2 > chunk_size:
            chunks.append(Chunk(text=current_chunk.strip(), section_title=section_title))

            # Apply overlap: take the tail of current chunk
            if chunk_overlap > 0 and len(current_chunk) > chunk_overlap:
                overlap_text = current_chunk[-chunk_overlap:]
                # Try to start overlap at a word boundary
                space_pos = overlap_text.find(" ")
                if space_pos != -1:
                    overlap_text = overlap_text[space_pos + 1:]
                current_chunk = overlap_text + "\n\n" + para
            else:
                current_chunk = para
        else:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para

    # Don't forget the last chunk
    if current_chunk.strip():
        chunks.append(Chunk(text=current_chunk.strip(), section_title=section_title))

    # Handle chunks that are still too large (single massive paragraph)
    final_chunks: list[Chunk] = []
    for chunk in chunks:
        if len(chunk.text) <= chunk_size * 1.5:
            final_chunks.append(chunk)
        else:
            # Hard split by sentences, then by character limit
            sentences = re.split(r"(?<=[.!?])\s+", chunk.text)
            current = ""
            for sentence in sentences:
                if current and len(current) + len(sentence) + 1 > chunk_size:
                    final_chunks.append(
                        Chunk(text=current.strip(), section_title=chunk.section_title)
                    )
                    if chunk_overlap > 0 and len(current) > chunk_overlap:
                        overlap = current[-chunk_overlap:]
                        sp = overlap.find(" ")
                        if sp != -1:
                            overlap = overlap[sp + 1:]
                        current = overlap + " " + sentence
                    else:
                        current = sentence
                else:
                    current = (current + " " + sentence).strip() if current else sentence
            if current.strip():
                final_chunks.append(
                    Chunk(text=current.strip(), section_title=chunk.section_title)
                )

    return final_chunks


MIN_CHUNK_LENGTH = 80


def _merge_or_filter_short_chunks(
    chunks: list[Chunk],
    min_length: int = MIN_CHUNK_LENGTH,
) -> list[Chunk]:
    """
    Filter or merge chunks that are too short (< min_length).
    Prepends short header/title fragments into the next chunk so no context
    is lost, or appends to the previous chunk if at the end of the document.
    """
    if not chunks:
        return []

    merged: list[Chunk] = []
    pending_text = ""
    pending_title = ""

    for chunk in chunks:
        text = chunk.text.strip()
        if not text:
            continue

        if pending_text:
            text = pending_text + "\n\n" + text
            pending_text = ""
            title = chunk.section_title or pending_title
        else:
            title = chunk.section_title

        if len(text) < min_length:
            # Chunk is too short to stand alone; hold as prefix for next chunk
            pending_text = text
            pending_title = title
        else:
            merged.append(Chunk(text=text, section_title=title))

    # If there is remaining short text at the very end
    if pending_text:
        if merged:
            merged[-1].text = merged[-1].text + "\n\n" + pending_text
        elif len(pending_text) >= 20:
            merged.append(Chunk(text=pending_text, section_title=pending_title))

    return merged


def chunk_text(
    text: str,
    chunk_size: int = 1500,
    chunk_overlap: int = 250,
    min_chunk_length: int = MIN_CHUNK_LENGTH,
) -> list[Chunk]:
    """
    Main chunking function: header-aware semantic chunking.

    1. Splits text by Markdown headers (# through ######) and component titles.
    2. For each section, splits further by paragraph boundaries
       if the section exceeds chunk_size.
    3. Applies chunk_overlap between consecutive chunks within a section.
    4. Merges/filters chunks shorter than min_chunk_length (default: 80).
    5. Assigns sequential chunk_index across all chunks.

    Args:
        text: Cleaned Markdown text.
        chunk_size: Target maximum characters per chunk (default: 1500).
        chunk_overlap: Character overlap between consecutive chunks (default: 250).
        min_chunk_length: Minimum character length per chunk (default: 80).

    Returns:
        List of Chunk objects with text, section_title, and chunk_index.
    """
    sections = _split_by_headers(text)
    all_chunks: list[Chunk] = []

    for section_title, section_text in sections:
        section_chunks = _split_section_by_size(
            section_text, section_title, chunk_size, chunk_overlap
        )
        all_chunks.extend(section_chunks)

    # Filter/merge short chunks (< min_chunk_length)
    final_chunks = _merge_or_filter_short_chunks(all_chunks, min_length=min_chunk_length)

    # Assign global chunk indices
    for idx, chunk in enumerate(final_chunks):
        chunk.chunk_index = idx

    return final_chunks
