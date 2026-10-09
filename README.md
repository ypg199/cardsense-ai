# CardSense AI

> Upload your Indian credit card statements. Score your benefit utilization. Find a better card.

**Stack:** Python 3.12 · FastAPI · LangGraph · Gemini Flash/Pro · MongoDB Atlas · React 18 (Vite) · Playwright · Docker Compose

---

## Quick Start

### 1. Prerequisites

- Docker + Docker Compose v2
- MongoDB Atlas cluster (free tier works)
- Google Gemini API key ([get one here](https://aistudio.google.com/))

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in MONGODB_URI and GEMINI_API_KEY
```

### 3. Start all services

```bash
docker compose up --build
```

| Service | URL |
|---------|-----|
| API (FastAPI) | http://localhost:8000 |
| Frontend (React) | http://localhost:3000 |
| API Docs (Swagger) | http://localhost:8000/docs |

### 4. Seed test data

The `crawler` service seeds 5 test cards automatically on startup.
To re-run manually:

```bash
docker compose run --rm api python -m crawler.run --seed-only
```

### 5. Create MongoDB Atlas Vector Search index

In the Atlas UI, create a vector search index on the `cardsense.credit_cards` collection:

```json
{
  "fields": [{
    "type": "vector",
    "path": "embedding",
    "numDimensions": 768,
    "similarity": "cosine"
  }]
}
```

Index name: `credit_cards_embedding_index`

---

## Development (without Docker)

```bash
# Backend
pip install -r requirements.txt
playwright install chromium
uvicorn api.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev

# Run crawler once to populate cards
python -m crawler.run --seed-only    # just seed 5 test cards
python -m crawler.run                # full crawl (needs GEMINI_API_KEY)
```

---

## Project Structure

```
cardsense/
├── agents/          # LangGraph nodes + pipeline
│   ├── state.py     # AnalysisState TypedDict
│   ├── pdf_node.py  # PDF extraction + decryption
│   ├── parse_node.py    # Gemini Flash transaction parser
│   ├── question_node.py # Utilization quiz generator
│   ├── cashback_node.py # Cashback + utilization score calc
│   ├── compare_node.py  # Vector search + Gemini Pro ranker
│   └── graph.py     # LangGraph pipeline wiring
├── api/             # FastAPI routes
│   ├── main.py      # App + lifespan + CORS
│   ├── models.py    # Pydantic request/response models
│   └── routes/      # session, cards, crawl
├── crawler/         # Playwright card data crawler
│   ├── card_crawler.py  # Core crawl logic
│   ├── sources.py   # URLs + CSS selectors
│   ├── tasks.py     # on-demand crawl task (POST /crawl)
│   └── run.py       # one-shot entrypoint (python -m crawler.run)
├── db/              # MongoDB layer
│   ├── connection.py    # Motor singleton
│   ├── schemas.py   # Document shape docs
│   ├── setup_indexes.py # Index creation (run once)
│   └── seed.py      # 5 test cards
├── frontend/        # React 18 + Vite
│   └── src/
│       ├── pages/   # UploadPage, UtilizationPage, ResultsPage
│       └── components/  # CardSelector, PdfDropZone, UtilizationMeter, etc.
├── tests/           # 157 offline pytest tests (Gemini and MongoDB mocked)
└── docker/          # Dockerfiles
```

---

## How It Works

1. **Upload** — Select card(s), drop PDF statements (multiple months supported), handle encrypted PDFs
2. **Parse** — Gemini Flash extracts every transaction, categorises against 16 standard categories
3. **Quiz** — Smart YES/NO questions (auto-detected from statement merchants where possible)
4. **Score** — Utilization Score 0-100: `(actual_earned / theoretical_max) × 100`
5. **Compare** — Atlas Vector Search → rule filter → Gemini Pro ranking of top 3 alternatives

## Security & Privacy

- **Statement data expires.** Each session carries an `expires_at` date, and a MongoDB TTL index (created on API startup) deletes it after `SESSION_TTL_HOURS` (default 24).
- **PDF passwords are never stored.** A password is used only for the request that supplies it. Encrypted PDF bytes are kept only while the session waits for a password.
- **Uploads are validated.** Only real PDFs (checked by file signature) up to `MAX_UPLOAD_MB` each, with at most `MAX_FILES_PER_REQUEST` per request.
- **Admin endpoints need a key.** `POST /crawl` and `GET /crawl/jobs` require an `X-Admin-Key` header matching `ADMIN_API_KEY`, and are disabled when it is unset.
- **Internal errors stay internal.** Clients get generic messages, while full tracebacks go to the server log.

---

## Running Tests

All tests run offline: Gemini, MongoDB and Playwright are mocked, so no API keys are needed.

```bash
pip install -r requirements-dev.txt
pytest                                  # all 157 tests
pytest tests/test_cashback_node.py      # one suite
ruff check . && ruff format --check .   # lint + formatting
```

---

## Atlas Vector Search Setup

After `docker compose up`, run the index setup script once:

```bash
docker compose exec api python -m db.setup_indexes
```

Then create the vector search index manually in the Atlas UI as described above.
The `compare_node` automatically falls back to category filtering if the index is not yet configured.
