# Startup Matchmaker

A DBMS project that matches startups with suitable investors. Startups upload
a PDF pitch deck; the deck is OCR'd, split into section-aware chunks and
embedded into a vector store. Each startup is then scored against every
investor's preferences using both structured data (MySQL) and semantic
similarity (ChromaDB).

## Tech stack

| Layer      | Technology                                             |
|------------|--------------------------------------------------------|
| Frontend   | Next.js (React, TypeScript, Tailwind)                  |
| Backend    | FastAPI (Python), JWT authentication, Argon2 passwords |
| Relational | MySQL - users, startups, investors, decks, matches     |
| Vector     | ChromaDB + `all-MiniLM-L6-v2` sentence embeddings      |
| PDF / OCR  | PyMuPDF + Tesseract                                    |

## How matching works

`matching_engine.py` computes a weighted compatibility score (0-100) for each
investor preference:

| Dimension           | Weight | Rule                                                  |
|---------------------|--------|-------------------------------------------------------|
| Industry            | 30     | startup industry equals investor's preferred industry |
| Stage               | 20     | startup stage equals preferred stage                  |
| Investment          | 20     | funding required is within investor's check size      |
| Location            | 10     | startup location equals preferred location            |
| Semantic similarity | 20     | pitch-deck chunks vs. an investor-thesis query        |

If a dimension cannot be computed (missing data) it is excluded and the
remaining weights are re-normalised. Results are stored in `match_results`.

## Project structure

```
backend/                FastAPI app (main.py), auth, DB connection, deck processing
frontend/               Next.js UI
database/schema.sql     MySQL schema
matching_engine.py      Scoring / ranking logic (also runnable from the CLI)
pdf_processor.py        Standalone OCR script for the sample PDF
store_pitch_deck.py     Standalone script: sample text -> ChromaDB chunks
test_chroma.py          Small ChromaDB semantic-search demo
sample_pdfs/            Example pitch deck
```

## Prerequisites

- Python 3.10+
- MySQL 8
- Node.js 20+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed

## Setup

### 1. Backend

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env              # then edit .env with your values
```

Create the database and tables:

```bash
mysql -u root -p < database/schema.sql
```

Create your first user, then set its password (stored as an Argon2 hash):

```sql
INSERT INTO users (name, email, password_hash, role)
VALUES ('Admin', 'admin@example.com', 'temporary', 'Admin');
```

```bash
python -m backend.set_user_password
```

Check the database connection and start the API:

```bash
python -m backend.test_connection
uvicorn backend.main:app --reload
```

The API runs at http://127.0.0.1:8000 (interactive docs at `/docs`).

> The first pitch-deck upload downloads the embedding model, so it needs an
> internet connection and may take a moment.

### 2. Frontend

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000 and log in.

## Configuration

| Variable          | Where     | Purpose                                              |
|-------------------|-----------|------------------------------------------------------|
| `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | `.env` | MySQL connection |
| `JWT_SECRET_KEY`  | `.env`    | Secret used to sign login tokens (required)          |
| `TESSERACT_CMD`   | `.env`    | Path to Tesseract if it is not on your PATH          |
| `CORS_ORIGINS`    | `.env`    | Comma-separated allowed frontend origins             |
| `NEXT_PUBLIC_API_URL` | `frontend/.env.local` | Backend URL (default `http://127.0.0.1:8000`) |

## API overview

All endpoints except `/`, `/health` and `/auth/login` require a
`Authorization: Bearer <token>` header. Startup users can only access their
own startup's decks and matches; Admins can access all.

| Method | Endpoint                                      | Description                        |
|--------|-----------------------------------------------|------------------------------------|
| POST   | `/auth/login`                                 | Log in, returns a JWT              |
| GET    | `/auth/me`                                    | Current user                       |
| GET    | `/startups`, `/startups/{id}`                 | List / get startups                |
| GET    | `/investors`                                  | List investors                     |
| POST   | `/upload-pitch-deck`                          | Upload and analyse a PDF (max 15 MB) |
| GET    | `/pitch-decks/{startup_id}`                   | All decks for a startup            |
| GET    | `/pitch-decks/{startup_id}/latest`            | Latest deck                        |
| GET    | `/pitch-decks/{startup_id}/analysis/{deck_id}`| Extracted sections and chunks      |
| POST   | `/generate-matches/{startup_id}`              | Compute and store investor matches |
| GET    | `/matches/{startup_id}`                       | Stored matches, best first         |

You can also run the matching engine from the command line:

```bash
python matching_engine.py 6          # print ranking for startup 6 (no DB writes)
python matching_engine.py 6 --save   # also save results to MySQL
```
