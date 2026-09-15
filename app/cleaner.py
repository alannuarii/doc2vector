"""
cleaner.py — Text Cleaning Pipeline

Custom regex pipeline to remove noise, artifacts, and HTML tags
from extracted document text before chunking.
"""

import re


def remove_unicode_artifacts(text: str) -> str:
    """Remove unicode replacement characters and other common artifacts."""
    # Remove unicode replacement character
    text = text.replace("\uFFFD", "")
    # Remove zero-width characters
    text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)
    # Remove other common broken unicode sequences
    text = re.sub(r"\\uFFFD", "", text)
    return text


def strip_html_tags(text: str) -> str:
    """Remove residual HTML tags from PDF conversion output."""
    # Remove specific inline HTML tags commonly left by converters
    tags_to_remove = [
        r"</?mark[^>]*>",
        r"</?u[^>]*>",
        r"</?br\s*/?>",
        r"</?span[^>]*>",
        r"</?div[^>]*>",
        r"</?p[^>]*>",
        r"</?em[^>]*>",
        r"</?strong[^>]*>",
        r"</?b[^>]*>",
        r"</?i[^>]*>",
        r"</?a[^>]*>",
        r"</?font[^>]*>",
        r"</?sup[^>]*>",
        r"</?sub[^>]*>",
    ]
    for tag_pattern in tags_to_remove:
        text = re.sub(tag_pattern, "", text, flags=re.IGNORECASE)
    return text


def remove_page_markers(text: str) -> str:
    """Remove page number patterns and watermarks."""
    # "Page X of Y" patterns
    text = re.sub(r"Page\s+\d+\s+of\s+\d+", "", text, flags=re.IGNORECASE)
    # Standalone page numbers (line containing only digits)
    text = re.sub(r"^\s*\d{1,4}\s*$", "", text, flags=re.MULTILINE)
    # Common watermark patterns
    text = re.sub(r"(?i)(confidential|draft|watermark)", "", text)
    return text


def remove_recurring_footer_metadata(text: str) -> str:
    """
    Remove recurring dates, page markers, and document internal serials.

    1. Tanggal (e.g. 2019-03-14)
    2. Nomor halaman berulang (e.g. - 72-, -173-, - C1 -)
    3. Kode serial internal dokumen (e.g. 000003-02, P3780390001000000D0SN1)
    """
    # 1. Hapus tanggal (e.g. 2019-03-14)
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "", text)

    # 2. Hapus nomor halaman berulang (e.g. - 72-, -173-, - C1 -)
    # Gunakan lookaround agar tidak memotong nomor part seperti P3780-390-01
    text = re.sub(r"(?<!\S)-\s*([A-Z]?\d+)\s*-(?!\S)", "", text)

    # 3. Hapus kode serial internal dokumen (e.g. 000003-02, P3780390001000000D0SN1)
    text = re.sub(r"\b\d{6}-\d{2}\b", "", text)
    text = re.sub(r"\bP\w{18,}\b", "", text)

    return text


def normalize_attached_tokens(text: str) -> str:
    """
    Separate tokens stuck together without spaces caused by narrow PDF columns.
    E.g.: 'BOLT,W/WASHERB/W, T=0.50' -> 'BOLT, W/WASHERB/W, T = 0.50'
    """
    # Tambahkan spasi setelah koma jika menempel dengan huruf/simbol berikutnya
    # (hindari memecah format angka ribuan seperti 1,000)
    text = re.sub(r",([^\s0-9])", r", \1", text)
    text = re.sub(r"([A-Za-z]),([0-9])", r"\1, \2", text)

    # Tambahkan spasi di sekitar tanda '=' (misal: T=0.50 -> T = 0.50)
    text = re.sub(r"([A-Za-z])=([0-9A-Za-z])", r"\1 = \2", text)

    return text


def normalize_whitespace(text: str) -> str:
    """Normalize excessive whitespace and blank lines."""
    # Replace multiple spaces (not newlines) with single space
    text = re.sub(r"[^\S\n]+", " ", text)
    # Replace 3+ consecutive newlines with 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip trailing whitespace per line
    text = re.sub(r" +\n", "\n", text)
    return text.strip()


def clean(text: str) -> str:
    """
    Run the full cleaning pipeline on extracted text.

    Pipeline order:
    1. Remove unicode artifacts
    2. Strip HTML tags
    3. Remove page markers and watermarks
    4. Remove recurring footer and metadata noise
    5. Normalize attached tokens without spaces
    6. Normalize whitespace
    """
    text = remove_unicode_artifacts(text)
    text = strip_html_tags(text)
    text = remove_page_markers(text)
    text = remove_recurring_footer_metadata(text)
    text = normalize_attached_tokens(text)
    text = normalize_whitespace(text)
    return text
