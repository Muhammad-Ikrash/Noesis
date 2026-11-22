# Noesis architecture

Nov 22, 2026 · @coconut. This updates *Noesis architecture.docx* (Nov 12) with Flashcards, Slides, ingestion progress, the retrieval threshold, embedding device and CPU tuning, and the Windows scripts.

## Overview

Noesis is a local study assistant. An Angular app calls a FastAPI backend, which stores PDFs on disk and in Postgres with pgvector, embeds text locally with Qwen3, and asks Groq for cited answers, quizzes, flashcards and slide decks.

- **Frontend:** `Frontend/Noesis/src/app` (Angular 22, standalone components, signals)
- **Backend:** `Backend/src/backend` (FastAPI, SQLAlchemy 2, Alembic). Paths below are relative to these two folders unless written in full.
- **Database:** Postgres 17 + pgvector in Docker (`Backend/docker-compose.yml`). Schema in `Backend/alembic/versions/0001`–`0006`.
- **Auth is off:** every request acts as one local user, created in `api/dependencies.py` (`get_current_user`).

### What changed since Nov 12

| Area | Change | Where |
|---|---|---|
| Ingestion | Progress (`progress_done` / `progress_total`) committed per batch, shown as a progress bar | migration `0003`, `services/ingestion.py` |
| Retrieval | `RETRIEVAL_MIN_SCORE` drops weak matches (cosine similarity below 0.3) | `services/retrieval.py` |
| Embeddings | GPU checked with a real CUDA op before use; falls back to CPU. fp16 on GPU, fp32/bf16 on CPU, thread count calibrated once per machine | `rag/providers/embeddings/qwen3.py`, `cpu_tuning.py` |
| Flashcards | New feature: decks, cards, per-card progress | migration `0004`, `services/flashcard_service.py`, `features/flashcards/` |
| Slides | New feature: decks, slides, design, AI revision, PPTX export | migrations `0005`, `0006`, `services/slides_service.py`, `slides_export.py`, `features/slides/` |
| Slide viewer | Type size follows each slide's text density, then a measured auto-fit shrinks text that would overflow 16:9; thumbnails drawn in the deck's theme | `features/slides/slide-design.ts` (`slideDensity`), `slides-viewer-page.ts` (`fitSlide`) |
| Quizzes | Difficulty (easy, medium, hard) and question types (single choice, multiple choice, true/false); multiple choice is graded as an exact set; "Retry N missed" makes a new quiz from an attempt's wrong and skipped questions | migration `0007`, `services/quiz_service.py`, `rag/prompts/quiz.py`, `features/quiz/` |
| Frontend | Library search/filter/sort, quiz history and drafts, study filter and export, reader search and resume | `features/*`, `shared/local-store.ts`, `shared/download.ts` |
| Tooling | `setup.bat` (one-time install), `run-noesis.bat` (one-click start) | repo root |

---

## Components

Each layer only calls the one below it: pages call API services, routes call services, services call providers and the database.

```mermaid
flowchart TB
  subgraph FE["Angular frontend (Frontend/Noesis/src/app)"]
    Pages["Pages<br/>features/*"] --> ApiSvc["API services<br/>core/services/*"]
    ApiSvc --> Interceptors["authInterceptor, errorInterceptor<br/>core/auth, core/http"]
    Pages --> Viewer["PdfViewer<br/>shared/ui/pdf-viewer.ts"]
    Pages --> Local["localStorage helpers<br/>shared/local-store.ts"]
  end
  Interceptors -->|"HTTP /api/v1 (dev proxy)"| Routes
  subgraph BE["FastAPI backend (Backend/src/backend)"]
    Routes["Routes<br/>api/routes/*"] --> Deps["Dependencies<br/>api/dependencies.py"]
    Routes --> Services["Services<br/>services/*"]
    Services --> RAG["RAG pipeline + prompts<br/>rag/pipeline.py, rag/prompts"]
    Services --> Providers["Providers<br/>rag/providers/*"]
    Services --> Export["PPTX export<br/>services/slides_export.py"]
  end
  Providers --> Qwen["Qwen3-Embedding-0.6B<br/>local GPU/CPU"]
  Providers --> Groq["Groq API"]
  Services --> DB[("Postgres + pgvector")]
  Services --> Disk[("STORAGE_DIR<br/>copied PDFs")]
```

| Layer | Folder | Job |
|---|---|---|
| Pages | `features/` | Screen state (signals), user actions |
| API services | `core/services/` | One HttpClient call per endpoint, no logic |
| Routes | `api/routes/` | Validate input, call a service, map errors to HTTP codes |
| Services | `services/` | Business logic and database work |
| RAG | `rag/` | Prompts, answer normalising, provider interfaces and implementations |
| Models | `models/` | SQLAlchemy tables |
| Schemas | `schemas/` | Pydantic request and response shapes |

---

## Data model

A user owns documents, conversations, quizzes, flashcard decks and slide decks. Every generated item (citation, quiz question, flashcard, slide) keeps a **snapshot** of its source (filename and page), so it still works after the PDF is deleted.

```mermaid
classDiagram
  class User { id: UUID; email: str; default_retrieval_scope }
  class Document { filename; sha256; status; page_count; progress_done; progress_total; error_message }
  class DocumentPage { page_number; char_count; needs_ocr }
  class DocumentChunk { page_number; kind; text; embedding: vector(1024) }
  class Conversation { title; mode; retrieval_scope }
  class Message { role; content; answer_status; supplementary }
  class MessageSource { position; filename; page_number; quote }
  class Quiz { title; topic; difficulty }
  class QuizQuestion { kind; prompt; options; correct_indices; explanation }
  class QuizAttempt { answers; score }
  class FlashcardDeck { title; topic }
  class Flashcard { position; front; back; known; reviewed_at; filename; page_number }
  class SlideDeck { title; subtitle; topic; design: JSONB }
  class Slide { position; title; bullets: JSONB; notes; sources: JSONB }
  User "1" --> "*" Document
  User "1" --> "*" Conversation
  User "1" --> "*" Quiz
  User "1" --> "*" FlashcardDeck
  User "1" --> "*" SlideDeck
  Document "1" *-- "*" DocumentPage
  Document "1" *-- "*" DocumentChunk
  Conversation "*" -- "*" Document : conversation_documents
  Conversation "1" *-- "*" Message
  Message "1" *-- "*" MessageSource
  Quiz "1" *-- "*" QuizQuestion
  Quiz "1" *-- "*" QuizAttempt
  FlashcardDeck "1" *-- "*" Flashcard
  SlideDeck "1" *-- "*" Slide
  FlashcardDeck ..> Conversation : optional
  SlideDeck ..> Conversation : optional
  Flashcard ..> DocumentChunk : snapshot of
```

| Class | File | Holds |
|---|---|---|
| User | `models/user.py` | The local user and the default scope setting |
| Document, DocumentPage | `models/document.py` | One uploaded PDF, its status and progress; per-page stats |
| DocumentChunk | `models/document_chunk.py` | A chunk of one page plus its 1024-dim vector (HNSW index) |
| Conversation, Message, MessageSource | `models/conversation.py`, `models/message.py` | Chats, answers and citation snapshots |
| Quiz, QuizQuestion, QuizAttempt | `models/quiz.py` | Quizzes with a difficulty; questions with a kind (`single`, `multiple`, `true_false`) and every correct option; graded attempts (an answer is an index, a list of indexes, or null) |
| FlashcardDeck, Flashcard | `models/flashcard.py` | Decks and cards with `known` / `reviewed_at` progress |
| SlideDeck, Slide | `models/slides.py` | Decks with a JSON `design`; slides with bullets, notes and source snapshots |

---

## Providers

Services depend on two Protocols (`rag/interfaces.py`), not on Qwen3 or Groq directly. `rag/factory.py` picks the implementation from settings and fails at startup if the config is invalid (missing key, or a vector size that doesn't match the database column).

### Embedding device selection

```mermaid
flowchart TD
  Start["EMBEDDING_DEVICE"] -->|auto or cuda| Probe{"Real CUDA op works?<br/>_cuda_usable()"}
  Start -->|cpu| CPU
  Probe -->|yes| GPU["GPU, fp16"]
  Probe -->|"no, auto"| CPU["CPU, fp32 or bf16"]
  Probe -->|"no, cuda"| Err["ConfigurationError<br/>with the reason"]
  CPU --> Threads{"EMBEDDING_CPU_THREADS"}
  Threads -->|">0"| Fixed["Use that many threads"]
  Threads -->|"0"| Cache{"Calibration cached for<br/>this CPU + torch version?"}
  Cache -->|yes| Cached["Use cached count"]
  Cache -->|no| Measure["Time a few runs at different<br/>thread counts, cache the fastest<br/>data/embedding-cpu-calibration.json"]
```

`torch.cuda.is_available()` can return True even when the installed PyTorch has no kernels for the GPU, so the provider runs a small tensor operation first. Thread counts are measured instead of guessed because hybrid P/E-core CPUs can get slower with more threads.

| Class / function | File |
|---|---|
| LLMProvider, EmbeddingProvider, OCRProvider (not implemented) | `rag/interfaces.py` |
| Qwen3EmbeddingProvider, `_cuda_usable` | `rag/providers/embeddings/qwen3.py` |
| CPU thread calibration | `rag/providers/embeddings/cpu_tuning.py` |
| GroqLLMProvider | `rag/providers/llm/groq.py` |
| `build_llm`, `build_embedder` | `rag/factory.py` |
| FakeEmbedder, FakeLLM (tests only) | `Backend/tests/fakes.py` |

---

## Services

Services are plain modules of functions, called by routes with a database session.

```mermaid
classDiagram
  class document_service { upload_document(); delete_document(); mark_missing_files() }
  class ingestion { ingest_document(); pending_document_ids() }
  class retrieval { retrieve(); build_retrieval_query() }
  class answer_service { ask() }
  class pipeline { build_messages(); normalize() }
  class quiz_service { generate_quiz(); submit_attempt() }
  class flashcard_service { generate_deck(); mark_card(); reset_progress() }
  class slides_service { generate_deck(); update_deck(); replace_slides(); revise_deck() }
  class slides_export { build_pptx(); style_for() }
  document_service --> ingestion : schedules
  ingestion --> EmbeddingProvider
  answer_service --> retrieval
  answer_service --> pipeline
  answer_service --> LLMProvider
  quiz_service --> retrieval
  flashcard_service --> retrieval
  slides_service --> retrieval
  quiz_service --> LLMProvider
  flashcard_service --> LLMProvider
  slides_service --> LLMProvider
  slides_export ..> slides_service : reads SlideDeck
```

| Function | File | What it does |
|---|---|---|
| `upload_document` | `services/document_service.py` | Size and PDF header check, sha256 dedupe, saves the file, inserts Document(pending) |
| `ingest_document` | `services/ingestion.py` | Claims the document, extracts, chunks, embeds in batches, reports progress, saves; on error sets failed |
| `extract_pdf` | `services/pdf_extraction.py` | Text and tables per page (pymupdf4llm), flags pages needing OCR |
| `chunk_pages` | `services/chunking.py` | Page-bound chunks (1800 chars, 200 overlap), tables kept whole |
| `retrieve` | `services/retrieval.py` | Embeds the query, cosine search in pgvector, scope filter, `min_score` cut-off |
| `ask` | `services/answer_service.py` | Chat turn: history, retrieval, Groq, citation check, save |
| `normalize` | `rag/pipeline.py` | Validates S# citations, drops invented ones, renumbers to [n] |
| `generate_quiz`, `submit_attempt`, `is_correct` | `services/quiz_service.py` | Builds questions of the requested kinds and difficulty from chunks, drops malformed ones, stores true/false as `[True, False]`; grades answers (multiple choice needs exactly the correct set) |
| `generate_deck` (flashcards) | `services/flashcard_service.py` | Topic → retrieve, or random sample of chunks → Groq → validated cards |
| `mark_card`, `reset_progress` | `services/flashcard_service.py` | Per-card "Got it / Still learning", reset a deck |
| `generate_deck` (slides) | `services/slides_service.py` | Spreads chunks across the PDFs, Groq writes title, slides, notes and refs, keeps takeaways last |
| `revise_deck` | `services/slides_service.py` | Rewrites one slide or the whole deck from an instruction, with fresh sources |
| `build_pptx` | `services/slides_export.py` | Editable PowerPoint in the deck's design, with speaker notes and citations |

---

## Frontend

Pages own screen state as signals and call injectable API services. Every HTTP call passes through the auth and error interceptors. Drafts and reading positions are stored in `localStorage` through `shared/local-store.ts`.

| Route | Page | File |
|---|---|---|
| `/library` | LibraryPage (+ UploadDropzone) | `features/library/` |
| `/study`, `/study/:conversationId` | WorkspacePage (+ Composer, ChatMessage, AttachDialog, PdfViewer) | `features/workspace/` |
| `/read/:documentId` | ReaderPage | `features/reader/reader-page.ts` |
| `/quizzes`, `/quizzes/:id`, `/quizzes/:id/attempts/:attemptId` | QuizListPage, QuizRunnerPage, QuizResultPage | `features/quiz/` |
| `/flashcards`, `/flashcards/:deckId` | DeckListPage, DeckStudyPage | `features/flashcards/` |
| `/slides`, `/slides/:deckId` | SlidesListPage, SlidesViewerPage (+ ReviseDialog) | `features/slides/` |

| Shared piece | File | Job |
|---|---|---|
| API services | `core/services/*.service.ts` | One method per endpoint |
| `apiErrorMessage`, `errorInterceptor` | `core/http/` | Turns API errors into readable messages |
| `formatBytes`, `relativeTime`, `statusClass` | `shared/format.ts` | Display helpers |
| `answerToMarkdown`, `sessionToMarkdown`, `exportFilename` | `shared/answer-text.ts` | Copy and export of answers with sources |
| `readJson`, `writeJson`, `removeKey` | `shared/local-store.ts` | Safe JSON in `localStorage` |
| `downloadBlob`, `copyText` | `shared/download.ts` | Browser downloads and clipboard |
| PdfViewer | `shared/ui/pdf-viewer.ts` | pdf.js rendering, zoom, page jump, quote highlight, search |

---

## Data flow

Uploads return immediately and are processed in the background. Chat, quiz, flashcard and slide calls are synchronous and wait for Groq.

### Upload and ingestion

```mermaid
sequenceDiagram
  actor S as Student
  participant LP as LibraryPage
  participant R as routes/documents.py
  participant Svc as document_service
  participant DB as Postgres
  participant Ing as ingestion
  participant Q as Qwen3EmbeddingProvider
  S->>LP: drop PDF
  LP->>R: POST /documents
  R->>Svc: upload_document()
  alt same file already uploaded
    Svc-->>R: existing document (created=false)
  else new file
    Svc->>DB: INSERT Document(status=pending)
    R-)Ing: background ingest_document(id)
  end
  R-->>LP: 201 DocumentOut(pending)
  Ing->>DB: claim: pending → processing
  Ing->>Ing: extract_pdf() then chunk_pages()
  loop batches
    Ing->>Q: embed_documents(texts)
    Ing->>DB: progress_done / progress_total (own connection)
  end
  Ing->>DB: INSERT pages + chunks, status=completed
  loop every 2.5 s while any PDF is pending/processing
    LP->>R: GET /documents
    R-->>LP: statuses + progress
  end
```

### Asking a question

```mermaid
sequenceDiagram
  actor S as Student
  participant WP as WorkspacePage
  participant A as answer_service.ask
  participant Ret as retrieval
  participant DB as Postgres + pgvector
  participant P as pipeline
  participant G as Groq
  S->>WP: question (mode, scope)
  WP->>A: POST /conversations/{id}/messages
  A->>DB: recent history (HISTORY_MAX_MESSAGES)
  A->>Ret: retrieve(query + last user turns, scope)
  Ret->>DB: cosine search, top 8, score ≥ 0.3
  alt basic mode and no chunks
    A-->>WP: insufficient_context (Groq not called)
  else
    A->>G: system prompt + history + S1..S8 (JSON mode)
    G-->>A: answer citing S# ids
    A->>P: normalize(): drop invented ids, renumber [n]
  end
  A->>DB: INSERT Message + MessageSource snapshots
  A-->>WP: answer + sources
  S->>WP: click [n] → PdfViewer opens page, highlights quote
```

In basic mode an answer with no valid citation becomes `insufficient_context`. In extensive mode uncited text moves to `supplementary` and is labelled as extra explanation.

### Flashcards

```mermaid
sequenceDiagram
  participant DL as DeckListPage
  participant R as routes/flashcards.py
  participant FS as flashcard_service
  participant G as Groq
  participant DB as Postgres
  DL->>R: POST /flashcards (document_ids or conversation_id, topic?, count)
  R->>FS: generate_deck()
  alt topic given
    FS->>DB: retrieve(topic), up to 2×count chunks
  else
    FS->>DB: random sample of chunks
  end
  FS->>G: flashcard prompt (JSON)
  FS->>FS: drop cards without a valid source
  FS->>DB: INSERT FlashcardDeck + Flashcards
  Note over DL,DB: Study page: PATCH /flashcards/{id}/cards/{card} {known}<br/>POST /flashcards/{id}/reset
```

### Slides

```mermaid
sequenceDiagram
  participant SL as SlidesListPage
  participant SV as SlidesViewerPage
  participant R as routes/slides.py
  participant SS as slides_service
  participant G as Groq
  participant X as slides_export
  SL->>R: POST /slides (document_ids, topic?, count)
  R->>SS: generate_deck(): spread chunks across PDFs
  SS->>G: slides prompt (JSON)
  SS->>SS: validate refs, keep takeaways last
  SS-->>SL: SlideDeckOut
  SV->>R: PATCH /slides/{id} (title, design)
  SV->>R: PUT /slides/{id}/slides (manual edits)
  SV->>R: POST /slides/{id}/revise (instruction, slide_id?)
  R->>SS: revise_deck(): fresh sources → Groq → replace slide(s)
  SV->>R: GET /slides/{id}/pptx
  R->>X: build_pptx(deck, design)
  X-->>SV: .pptx download
```

### Document status

```mermaid
stateDiagram-v2
  [*] --> pending: upload_document()
  pending --> processing: ingest_document() claims it
  processing --> completed: chunks + vectors saved
  processing --> failed: extraction or embedding error
  processing --> pending: backend restarted mid-ingest
  failed --> pending: same PDF uploaded again
  completed --> missing: file gone at startup
  missing --> pending: same PDF uploaded again
  completed --> [*]: delete_document()
```

---

## API summary (`/api/v1`)

| Resource | Endpoints |
|---|---|
| Health | `GET /health` |
| Documents | `POST /documents`, `GET /documents`, `GET /documents/{id}`, `GET /documents/{id}/file`, `DELETE /documents/{id}` |
| Conversations | `POST`, `GET`, `GET /{id}`, `PATCH /{id}`, `DELETE /{id}` on `/conversations` |
| Chat | `POST /conversations/{id}/messages` |
| Quizzes | `POST /quizzes`, `GET /quizzes`, `GET /quizzes/{id}`, `DELETE /quizzes/{id}`, `POST /quizzes/{id}/attempts`, `GET /quizzes/{id}/attempts/{attemptId}`, `POST /quizzes/{id}/attempts/{attemptId}/retry` |
| Flashcards | `POST /flashcards`, `GET /flashcards`, `GET /flashcards/{id}`, `DELETE /flashcards/{id}`, `PATCH /flashcards/{id}/cards/{cardId}`, `POST /flashcards/{id}/reset` |
| Slides | `POST /slides`, `GET /slides`, `GET /slides/{id}`, `GET /slides/{id}/pptx`, `PATCH /slides/{id}`, `PUT /slides/{id}/slides`, `POST /slides/{id}/revise`, `DELETE /slides/{id}` |
| Settings | `GET /settings`, `PUT /settings` |

---

## Run and setup scripts (Windows)

```mermaid
flowchart LR
  subgraph setup.bat
    T["Check uv, Node, Docker<br/>(offer winget)"] --> E[".env from example"] --> U["uv sync<br/>(retry with downloaded Python)"] --> D["Pull + start db,<br/>alembic upgrade"] --> N["npm ci / install"] --> M["Download embedding model"]
  end
  subgraph run-noesis.bat
    D2["Start Docker Desktop<br/>if needed"] --> DB2["docker compose up db,<br/>wait pg_isready"] --> U2["uv sync"] --> B["Backend window:<br/>alembic + uv run backend"] --> F["Frontend window:<br/>npm start"] --> O["Open localhost:4200"]
  end
```

Both scripts look for Docker Desktop in the standard install folders, including `%LOCALAPPDATA%\Programs\DockerDesktop`, and otherwise work it out from where `docker.exe` is on PATH.

---

## Tests

| Suite | Location | Covers |
|---|---|---|
| Backend unit | `Backend/tests/unit/` | chunking, config, CPU tuning, PDF extraction, pipeline normalising, quiz, flashcard and slide parsing |
| Backend integration | `Backend/tests/integration/` | API against a real Postgres (`noesis_test`) with fake providers |
| Frontend unit | `Frontend/Noesis/src/app/**/*.spec.ts` | shared helpers (format, answer text, rich text, local store, download), API error handling, services' HTTP calls, interceptors, auth, toast and theme, quiz answer logic, slide density and auto-fit |

Run with `uv run pytest` (backend) and `npm test -- --watch=false` (frontend).
