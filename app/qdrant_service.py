"""
qdrant_service.py — Gemini Embedding & Qdrant Integration

Handles vector embedding generation via Google GenAI SDK
and batch upsert operations to Qdrant vector database.
"""

import os
import uuid
import logging
from typing import Generator

from google import genai
from google.genai import types
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
)
from dotenv import load_dotenv

from .chunker import Chunk

load_dotenv()

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
VECTOR_SIZE = 3072
EMBEDDING_BATCH_SIZE = 100  # Gemini supports up to 100 texts per batch

# ── Clients ────────────────────────────────────────────────────────────────
genai_client = genai.Client(api_key=GEMINI_API_KEY)

qdrant_client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY if QDRANT_API_KEY else None,
    timeout=60,
)


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a list of texts using Gemini Embedding API.
    Handles batching internally for large text lists.

    Args:
        texts: List of text strings to embed.

    Returns:
        List of embedding vectors (each 3072 dimensions).
    """
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[i : i + EMBEDDING_BATCH_SIZE]
        response = genai_client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=batch,
            config=types.EmbedContentConfig(
                output_dimensionality=VECTOR_SIZE,
            ),
        )
        for embedding in response.embeddings:
            all_embeddings.append(embedding.values)

    return all_embeddings


def ensure_collection(collection_name: str) -> bool:
    """
    Create a Qdrant collection if it does not already exist.

    Args:
        collection_name: Name of the collection to ensure.

    Returns:
        True if collection was created, False if it already existed.
    """
    existing = [c.name for c in qdrant_client.get_collections().collections]

    if collection_name in existing:
        logger.info(f"Collection '{collection_name}' already exists")
        return False

    qdrant_client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=VECTOR_SIZE,
            distance=Distance.COSINE,
        ),
    )
    logger.info(f"Created collection '{collection_name}' (size={VECTOR_SIZE}, cosine)")
    return True


def format_chunk_with_context(
    chunk_text: str,
    document_title: str,
    category: str = "",
    section_title: str = "",
) -> str:
    """
    Prepend document identity context header to chunk text.
    E.g.: '[Parts Catalog S16RPTAS | Mitsubishi | P3780-362 OIL SYSTEM PARTS]\n...'
    """
    parts = [p.strip() for p in [document_title, category, section_title] if p and p.strip()]
    if parts:
        context_header = f"[{' | '.join(parts)}]\n"
        return context_header + chunk_text
    return chunk_text


def upsert_chunks(
    collection_name: str,
    chunks: list[Chunk],
    document_title: str,
    category: str = "",
    custom_metadata: dict | None = None,
    batch_size: int = 50,
) -> Generator[dict, None, None]:
    """
    Generate embeddings and upsert chunks to Qdrant in batches.
    Yields progress events for SSE streaming.

    Args:
        collection_name: Target Qdrant collection.
        chunks: List of Chunk objects from the chunker.
        document_title: Document title for payload.
        category: Optional category/machine type.
        custom_metadata: Optional extra key-value metadata.
        batch_size: Number of chunks per upsert batch.

    Yields:
        Dict events with type, message, and progress data.
    """
    total_chunks = len(chunks)

    yield {
        "type": "embedding_start",
        "message": f"🧠 Memulai embedding {total_chunks} chunks menggunakan {EMBEDDING_MODEL}...",
    }

    for batch_start in range(0, total_chunks, batch_size):
        batch_end = min(batch_start + batch_size, total_chunks)
        batch_chunks = chunks[batch_start:batch_end]

        # Inject context header (document title, category, section title) into chunk text
        batch_final_texts = [
            format_chunk_with_context(
                chunk_text=c.text,
                document_title=document_title,
                category=category,
                section_title=c.section_title,
            )
            for c in batch_chunks
        ]

        # Generate embeddings for this batch
        yield {
            "type": "embedding_progress",
            "message": f"🔄 Embedding batch {batch_start // batch_size + 1}: chunks {batch_start + 1}-{batch_end} / {total_chunks}",
            "progress": round(batch_start / total_chunks * 50),
        }

        embeddings = get_embeddings(batch_final_texts)

        # Build Qdrant points
        points: list[PointStruct] = []
        for i, (chunk, final_text, embedding) in enumerate(
            zip(batch_chunks, batch_final_texts, embeddings)
        ):
            payload = {
                "source_text": final_text,
                "document_title": document_title,
                "category": category,
                "chunk_index": chunk.chunk_index,
                "total_chunks": total_chunks,
                "section_title": chunk.section_title,
            }
            # Merge custom metadata if provided
            if custom_metadata:
                payload.update(custom_metadata)

            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding,
                    payload=payload,
                )
            )

        # Upsert batch to Qdrant
        yield {
            "type": "upsert_progress",
            "message": f"📤 Upserting batch {batch_start // batch_size + 1} ke Qdrant ({len(points)} points)...",
            "progress": round(50 + (batch_end / total_chunks * 50)),
        }

        qdrant_client.upsert(
            collection_name=collection_name,
            points=points,
        )

        yield {
            "type": "batch_complete",
            "message": f"✅ Batch {batch_start // batch_size + 1} selesai ({batch_end}/{total_chunks} chunks)",
            "progress": round(50 + (batch_end / total_chunks * 50)),
        }

    yield {
        "type": "complete",
        "message": f"🎉 Semua {total_chunks} chunks berhasil di-embed dan di-upsert ke collection '{collection_name}'!",
        "progress": 100,
        "total_chunks": total_chunks,
    }


def list_collections() -> list[str]:
    """List all available Qdrant collections."""
    return [c.name for c in qdrant_client.get_collections().collections]
