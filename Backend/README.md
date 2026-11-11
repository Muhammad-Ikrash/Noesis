# Noesis Backend

FastAPI + PostgreSQL/pgvector RAG backend for the Noesis study assistant. See `AGENTS.md` for the full spec.

Current phase: **local-only, no authentication**. Every request acts as a single local user
(`local@noesis.local`, created on first request). The schema keeps `owner_id` everywhere so auth can be added later.

## Decisions

| Area | Choice |
|---|---|
| LLM | Groq free tier through the OpenAI-compatible API (`LLM_*`). Questions, recent history and retrieved passages are sent to Groq. |
| Embeddings | `Qwen/Qwen3-Embedding-0.6B`, local via sentence-transformers, **1024 dims**, fp32. PDF text never leaves the machine for embedding. |
| PDFs per chat | Many. A student's PDFs form a persistent library; chats attach any subset. |
| Retrieval scope (the slider) | `session` = only PDFs attached to the chat; `library` = every completed PDF the student owns. Past chat answers are never searched. |
| Deletion | Explicit API call only. No filesystem watcher: uploads are copied into `STORAGE_DIR`, so deleting the original file in the OS changes nothing. |
| Images / scanned pages | No OCR yet. Pages with no text are flagged `needs_ocr`; fully scanned PDFs fail with a clear message. |
| Tables | Extracted as Markdown via `pymupdf4llm` and kept as single, never-split chunks. |

## Running locally

```bash
cp .env.example .env          # then set LLM_API_KEY
docker compose up -d db       # Postgres 17 + pgvector, also creates noesis_test
uv sync
uv run alembic upgrade head
uv run backend                # http://127.0.0.1:8000, docs at /docs
```

The backend runs on the host so it can use the GPU (`EMBEDDING_DEVICE=auto` picks CUDA if available).
The first ingestion downloads the Qwen3 model (~1.2 GB) into the Hugging Face cache.

### Tests

```bash
uv run pytest            # unit tests always run; integration tests need the db container
uv run ruff check src tests
```

Tests use deterministic fake LLM/embedding providers: no API key, GPU or model download needed.

## API (`/api/v1`)

### Documents (the library)
| Method | Path | Notes |
|---|---|---|
| POST | `/documents` | multipart `file`. 201 + ingestion in background; 200 with `created=false` if the identical PDF already exists. 413 too large, 415 not a PDF. |
| GET | `/documents` | All of the student's PDFs with `status`: `pending`, `processing`, `completed`, `failed`, `missing`. |
| GET | `/documents/{id}` | Adds per-page info and `ocr_pages` (pages with no extractable text). |
| DELETE | `/documents/{id}` | Removes file, chunks/embeddings and chat attachments. Past answers keep their citation filename/page (with `document_id: null`). |

### Conversations
| Method | Path | Notes |
|---|---|---|
| POST | `/conversations` | `{title?, document_ids[], mode, retrieval_scope?}`; scope defaults to the user setting. |
| GET | `/conversations` | List. |
| GET | `/conversations/{id}` | Includes attached documents and all messages with sources. |
| PATCH | `/conversations/{id}` | `{title?, mode?, retrieval_scope?, document_ids?}` (`document_ids` replaces the set). |
| DELETE | `/conversations/{id}` | |

### Chat
`POST /conversations/{id}/messages`

```json
{ "question": "Why do mitochondria need oxygen?", "mode": "basic", "retrieval_scope": "library" }
```

`mode` is required (`basic` | `extensive`). `retrieval_scope` is optional; when given it is saved on the chat.

Response (abridged):

```json
{
  "answer_status": "answered | insufficient_context | needs_clarification | error",
  "answer": "Mitochondria use oxygen in respiration [1].",
  "supplementary": "Extensive mode only: explanation NOT from the PDF",
  "needs_clarification": false,
  "clarification_question": null,
  "sources": [{ "position": 1, "filename": "Bio.pdf", "page_number": 12, "document_id": "...", "chunk_id": "...", "quote": "..." }],
  "retrieved": [{ "filename": "Bio.pdf", "page_number": 12, "score": 0.71, "...": "..." }],
  "retrieval_scope": "library",
  "searched_document_count": null
}
```

`[n]` markers in `answer` refer to `sources[].position`. Citations the model invents are discarded; in basic mode an
answer with no valid citation becomes `insufficient_context`.

### Settings
`GET/PUT /settings` — `{ "default_retrieval_scope": "session" | "library" }`: default slider position for new chats.

## Adding OCR later

1. Implement `OCRProvider.extract_page_text(page)` (`src/backend/rag/interfaces.py`).
2. Pass it to `ingest_document(..., ocr=...)` in `api/dependencies.py:get_ingestor`.

Pages under `MIN_PAGE_CHARS` are then sent through it, and recorded with `extraction_method = "ocr"`.
Re-ingest affected documents by re-uploading them (failed documents are reprocessed on re-upload).

## Changing the embedding model

The vector column is fixed at 1024 dims. A different model or dimension needs a new Alembic migration and re-embedding of
every document; startup refuses a mismatched `EMBEDDING_DIMENSION`.
