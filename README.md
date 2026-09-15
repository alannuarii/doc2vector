# doc2vector

> Document to Vector Embedding Pipeline untuk knowledge base RAG **tahuna-preventive-app**.

Aplikasi monolitik berbasis Python (FastAPI) untuk memproses dokumen teknis/manual book (`.pdf`, `.md`), membersihkan teks dari noise, memotong secara semantik, menghasilkan vector embedding via Google Gemini API, dan menyimpan ke Qdrant.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, Uvicorn
- **PDF Processing**: pymupdf4llm
- **Embedding**: Google Gemini API (`text-embedding-004`, 3072-dim)
- **Vector DB**: Qdrant
- **Frontend**: HTML5, Tailwind CSS, Vanilla JS (SSE realtime)

## Quick Start

### Prerequisites

- Python 3.11+
- Qdrant instance
- Google Gemini API key

### Setup

```bash
# Clone & install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your credentials

# Run
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Buka browser di `http://localhost:8000`.

### Docker

```bash
docker compose up -d
```

Aplikasi berjalan di `http://localhost:3017`.

## Environment Variables

| Variable | Deskripsi | Contoh |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini API key | `AI...` |
| `QDRANT_URL` | URL Qdrant instance | `http://localhost:6333` |
| `QDRANT_API_KEY` | Qdrant API key (opsional) | `secret-key` |

## API Endpoints

| Method | Path | Deskripsi |
|---|---|---|
| `GET` | `/` | Web UI |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/collections` | List Qdrant collections |
| `POST` | `/api/ingest` | Ingest dokumen (SSE streaming) |

## Pipeline

1. **Extract** — PDF → Markdown (pymupdf4llm) atau native `.md` reading
2. **Clean** — Hapus unicode artifacts, HTML tags, page markers
3. **Chunk** — Header-aware semantic chunking (`#`, `##`, `###`)
4. **Embed** — Google Gemini `text-embedding-004` (3072-dim)
5. **Upsert** — Batch upsert ke Qdrant dengan payload metadata
