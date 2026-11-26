# Noesis

An AI study assistant grounded in your own documents. Upload your PDFs, then ask questions and get answers that cite the exact page they came from. Noesis can also turn the same material into quizzes, flashcards and slide decks.

PDF text is embedded **locally** (Qwen3-Embedding-0.6B), so documents are never sent anywhere to be indexed. Only the question, recent chat history and the few retrieved passages are sent to the LLM (Groq).

---

## Features

| Area | What you can do |
|---|---|
| **Library** | Drag-and-drop PDF upload with live processing progress, duplicate detection, search, status filter, sorting |
| **Study** | Chat with one PDF, several, or your whole library. *Basic* mode answers only from your PDFs. *Extensive* mode adds clearly labelled extra explanation. Every claim links to its page. Copy answers with sources, export a session to Markdown, prompt starters |
| **Reader** | pdf.js viewer that opens on the cited page and highlights the quote. Search inside the document, resume where you left off, download |
| **Quizzes** | Quizzes from your PDFs, optionally on a topic, at *easy*, *medium* or *hard* difficulty. Mix single-choice, multiple-choice (select all that apply) and true/false questions. Graded attempts with explanations and sources, attempt history, resumable drafts |
| **Flashcards** | Generated decks with flip-card study, "Got it / Still learning" progress saved per card, reset |
| **Slides** | Generated decks with speaker notes and citations. Text sizes itself to each slide and never gets cut off. Edit slides, change the design (theme, accent, fonts, bullets), ask AI to revise one slide or the whole deck, export to PowerPoint (.pptx) |

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Angular 22 (standalone components, signals), pdf.js, SCSS design tokens, Vitest |
| Backend | Python 3.13, FastAPI, SQLAlchemy 2, Alembic, Pydantic Settings |
| Database | PostgreSQL 17 + pgvector (HNSW index, cosine distance) in Docker |
| Embeddings | `Qwen/Qwen3-Embedding-0.6B` via sentence-transformers (CUDA, fp16 or CPU) |
| LLM | Groq through its OpenAI-compatible API |
| PDF | PyMuPDF + pymupdf4llm (text per page, tables kept as Markdown) |
| Export | python-pptx |

---

## Quick start (Windows)

You need **Docker Desktop**, **Node.js 22.22+ or 24.15+** (the Angular CLI refuses older versions), **uv** and a free **Groq API key** (https://console.groq.com).

1. **Run `setup.bat`** once. It checks the tools (and offers to install missing ones with winget), creates `Backend\.env`, installs the Python and npm packages, prepares the database and downloads the embedding model (about 1.2 GB).
2. **Open `Backend\.env`** and set `LLM_API_KEY=` to your Groq key.
3. **Run `run-noesis.bat`.** It starts Docker Desktop if needed, then the database, backend and frontend, and opens http://localhost:4200.

To stop Noesis, close the *Noesis backend* and *Noesis frontend* windows. The database keeps running in Docker:

```powershell
docker compose -f Backend\docker-compose.yml stop db
```

### Manual start (any OS)

```bash
# Backend
cd Backend
cp .env.example .env              # then set LLM_API_KEY
docker compose up -d db
uv sync
uv run alembic upgrade head
uv run backend                    # http://127.0.0.1:8000, API docs at /docs

# Frontend (second terminal)
cd Frontend/Noesis
npm ci
npm start                         # http://localhost:4200, proxies /api to the backend
```

---

## Configuration

Everything is set in `Backend/.env` (see `Backend/.env.example`). These are the settings you're most likely to change:

| Variable | Default | Meaning |
|---|---|---|
| `LLM_API_KEY` | none (required) | Groq API key |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | Any Groq chat model |
| `EMBEDDING_DEVICE` | `auto` | `auto` uses the GPU if it actually works, otherwise the CPU |
| `EMBEDDING_CPU_THREADS` | `0` | `0` measures the fastest thread count once per machine |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1800` / `200` | Characters per chunk. Chunks never cross a page |
| `RETRIEVAL_TOP_K` | `8` | Passages sent to the LLM per question |
| `RETRIEVAL_MIN_SCORE` | `0.3` | Passages less similar than this are dropped |
| `MAX_UPLOAD_MB` | `50` | Upload size limit |

---

## Tests

```bash
# Backend: unit tests always run, integration tests need the db container
cd Backend
uv run pytest

# Frontend
cd Frontend/Noesis
npm test -- --watch=false
```

Backend tests use fake LLM and embedding providers, so they need no API key, GPU or model download.

---

## Project layout

```
Noesis/
├── Backend/                FastAPI app (see Backend/README.md for the full API)
│   ├── src/backend/
│   │   ├── api/routes/     HTTP endpoints
│   │   ├── services/       business logic (ingestion, retrieval, quizzes, flashcards, slides)
│   │   ├── rag/            prompts, answer validation, LLM and embedding providers
│   │   ├── models/         SQLAlchemy tables
│   │   └── schemas/        request and response shapes
│   ├── alembic/versions/   database migrations
│   └── tests/              unit and integration tests
├── Frontend/Noesis/        Angular app
│   └── src/app/
│       ├── core/           API services, auth placeholders, error handling
│       ├── features/       library, workspace (study), reader, quiz, flashcards, slides
│       └── shared/         PDF viewer and shared UI
├── docs/architecture.md    architecture, data model and request flows
├── setup.bat               one-time install
└── run-noesis.bat          one-click start
```

See **[docs/architecture.md](docs/architecture.md)** for diagrams of the components, data model and request flows.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| *Docker Desktop could not be found* | Start Docker Desktop yourself, then run the script again |
| `uv sync` fails with *Missing expected target directory for Python minor version link* | The scripts retry automatically using the downloaded interpreter. By hand: `uv sync --python "%APPDATA%\uv\python\cpython-3.13.<x>-windows-x86_64-none\python.exe"` |
| A PDF ends up *failed* with no text | Scanned PDFs need OCR, which isn't supported yet |
| Embedding is slow or the GPU errors out | Set `EMBEDDING_DEVICE=cpu`, or try `EMBEDDING_CPU_DTYPE=bf16` on CPUs that support it |
| Answers say the PDFs don't cover the question | Attach more PDFs, switch the scope to *Library*, or lower `RETRIEVAL_MIN_SCORE` |

---

## Status

Local, single-user. Authentication is stubbed out: every request acts as one local user, and the schema already keeps `owner_id` on every table so login can be added later.
