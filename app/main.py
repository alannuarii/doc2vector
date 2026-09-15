"""
main.py — FastAPI Application Entry Point

Routes, SSE streaming ingestion pipeline, health check,
and static file serving for the web UI.
"""

import json
import logging
import traceback

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from . import extractor, cleaner, chunker, qdrant_service

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("doc2vector")

# ── App ────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="doc2vector",
    description="Document to Vector Embedding Pipeline",
    version="1.0.0",
)

# ── Constants ──────────────────────────────────────────────────────────────
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS = {"pdf", "md", "markdown", "txt"}
STATIC_DIR = Path(__file__).parent / "static"


# ── Helper ─────────────────────────────────────────────────────────────────
def sse_event(data: dict, event: str = "message") -> str:
    """Format a dict as an SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def validate_collection_name(name: str) -> str:
    """Validate collection name: alphanumeric + underscores only."""
    import re
    if not re.match(r"^[a-zA-Z0-9_]+$", name):
        raise ValueError(
            "Collection name hanya boleh mengandung huruf, angka, dan underscore."
        )
    return name


# ── Routes ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """Health check endpoint for Docker and load balancer probes."""
    return {"status": "healthy", "service": "doc2vector"}


@app.get("/api/collections")
async def list_collections():
    """List all available Qdrant collections."""
    try:
        collections = qdrant_service.list_collections()
        return {"collections": collections}
    except Exception as e:
        logger.error(f"Failed to list collections: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ingest")
async def ingest_document(
    file: UploadFile = File(...),
    collection_name: str = Form(...),
    document_title: str = Form(...),
    category: str = Form(""),
    chunk_size: int = Form(1500),
    chunk_overlap: int = Form(250),
    custom_metadata: str = Form(""),
):
    """
    Main ingestion endpoint. Processes document through the full pipeline:
    Extract → Clean → Chunk → Embed → Upsert

    Streams progress updates via Server-Sent Events (SSE).
    """
    # ── Validate inputs ────────────────────────────────────────────────
    try:
        collection_name = validate_collection_name(collection_name)
    except ValueError as e:
        return StreamingResponse(
            iter([sse_event({"type": "error", "message": str(e)})]),
            media_type="text/event-stream",
        )

    # Validate file extension
    filename = file.filename or "unknown"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return StreamingResponse(
            iter([sse_event({
                "type": "error",
                "message": f"Format file .{ext} tidak didukung. Gunakan: {', '.join(ALLOWED_EXTENSIONS)}",
            })]),
            media_type="text/event-stream",
        )

    # Read file bytes
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        return StreamingResponse(
            iter([sse_event({
                "type": "error",
                "message": f"File terlalu besar ({len(file_bytes) / 1024 / 1024:.1f} MB). Maksimum 50 MB.",
            })]),
            media_type="text/event-stream",
        )

    # Parse custom metadata
    metadata_dict = None
    if custom_metadata.strip():
        try:
            metadata_dict = json.loads(custom_metadata)
            if not isinstance(metadata_dict, dict):
                raise ValueError("Custom metadata harus berupa JSON object (key-value).")
        except (json.JSONDecodeError, ValueError) as e:
            return StreamingResponse(
                iter([sse_event({"type": "error", "message": f"Custom metadata tidak valid: {e}"})]),
                media_type="text/event-stream",
            )

    # ── Pipeline generator ─────────────────────────────────────────────
    def pipeline():
        try:
            # Step 1: Extract
            yield sse_event({
                "type": "extract_start",
                "message": f"📄 Mengekstrak file '{filename}' ({len(file_bytes) / 1024:.1f} KB)...",
                "progress": 0,
            })

            raw_text = extractor.extract(filename, file_bytes)
            yield sse_event({
                "type": "extract_done",
                "message": f"✅ Ekstraksi selesai — {len(raw_text):,} karakter diekstrak.",
                "progress": 10,
            })

            # Step 2: Clean
            yield sse_event({
                "type": "clean_start",
                "message": "🧹 Membersihkan teks dari artefak dan noise...",
                "progress": 15,
            })

            cleaned_text = cleaner.clean(raw_text)
            chars_removed = len(raw_text) - len(cleaned_text)
            yield sse_event({
                "type": "clean_done",
                "message": f"✅ Pembersihan selesai — {chars_removed:,} karakter noise dihapus ({len(cleaned_text):,} karakter bersih).",
                "progress": 25,
            })

            # Step 3: Chunk
            yield sse_event({
                "type": "chunk_start",
                "message": f"✂️ Memotong teks (chunk_size={chunk_size}, overlap={chunk_overlap})...",
                "progress": 30,
            })

            chunks = chunker.chunk_text(cleaned_text, chunk_size, chunk_overlap)
            yield sse_event({
                "type": "chunk_done",
                "message": f"✅ Chunking selesai — {len(chunks)} chunks dihasilkan.",
                "progress": 40,
            })

            if not chunks:
                yield sse_event({
                    "type": "error",
                    "message": "⚠️ Tidak ada teks yang dapat diproses setelah cleaning.",
                })
                return

            # Step 4: Ensure collection
            yield sse_event({
                "type": "collection_check",
                "message": f"📦 Memverifikasi collection '{collection_name}'...",
                "progress": 45,
            })

            created = qdrant_service.ensure_collection(collection_name)
            if created:
                yield sse_event({
                    "type": "collection_created",
                    "message": f"✅ Collection '{collection_name}' berhasil dibuat (3072-dim, Cosine).",
                    "progress": 48,
                })
            else:
                yield sse_event({
                    "type": "collection_exists",
                    "message": f"ℹ️ Collection '{collection_name}' sudah ada, melanjutkan upsert...",
                    "progress": 48,
                })

            # Step 5: Embed + Upsert (streamed from qdrant_service)
            for event in qdrant_service.upsert_chunks(
                collection_name=collection_name,
                chunks=chunks,
                document_title=document_title,
                category=category,
                custom_metadata=metadata_dict,
            ):
                yield sse_event(event)

        except Exception as e:
            logger.error(f"Pipeline error: {traceback.format_exc()}")
            yield sse_event({
                "type": "error",
                "message": f"❌ Error: {str(e)}",
            })

    return StreamingResponse(
        pipeline(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Static Files & SPA Fallback ───────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def serve_index():
    """Serve the main web UI."""
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/favicon.svg")
async def serve_favicon():
    """Serve favicon."""
    favicon_path = STATIC_DIR / "favicon.svg"
    if favicon_path.exists():
        return FileResponse(str(favicon_path), media_type="image/svg+xml")
    return JSONResponse(status_code=404, content={"detail": "Not found"})
