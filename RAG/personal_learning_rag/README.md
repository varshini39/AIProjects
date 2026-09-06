# Personal Learning RAG

A fully local RAG (Retrieval-Augmented Generation) system that lets you search your own study materials by meaning, ask questions grounded in your documents, and receive a daily learning fact every morning — all from your own laptop.

Built as a learning project to understand how RAG works from scratch.

---

## What it does

- **Semantic search** — ask questions in plain English and find relevant passages across all your materials, even when the exact words don't match
- **Grounded Q&A** — get answers sourced strictly from your own PDFs and notes, with the source file cited
- **Daily fact** — every morning, one interesting insight is surfaced from a random passage in your knowledge base

---

## Project structure

```
personal_learning_rag/
├── reader.py          # Extracts text from PDFs (text → OCR → vision fallback) and markdown/text files
├── chunker.py         # Splits documents into searchable passages
├── ingest.py          # Embeds all chunks and stores them in ChromaDB (run once)
├── search.py          # Interactive Q&A over your knowledge base
├── daily_fact.py      # Surfaces one random insight from your materials
├── requirements.txt
├── chroma_db/         # Vector database (auto-created by ingest.py, gitignored)
└── README.md
```

---

## How it works

```
Your PDFs & Notes
      ↓
  reader.py        — extracts text: direct text extraction, then OCR
                     (pytesseract) for scanned pages, then a vision LLM
                     (Ollama llava:7b) for diagrams/charts as a last resort
      ↓
  chunker.py       — splits text into ~1000 character overlapping passages
      ↓
  ingest.py        — converts each passage into a 384-number vector (embedding)
                     and stores everything in ChromaDB
      ↓
  search.py        — embeds your question, finds the 5 most similar passages,
                     sends them to a local LLM, returns a grounded answer
  daily_fact.py    — picks a random passage and extracts one insight from it
```

---

## Setup

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com) installed and running locally
- Tesseract OCR (system binary, used by `pytesseract` for scanned PDF pages):
  - macOS: `brew install tesseract`
  - Ubuntu/Debian: `sudo apt-get install -y tesseract-ocr`

### Install dependencies

```bash
cd RAG/personal_learning_rag
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### Pull the models

```bash
ollama pull qwen3:8b     # used by search.py and daily_fact.py
ollama pull llava:7b     # used by reader.py's vision fallback for diagrams/charts
```

### Point to your materials

Your study materials should be organised in a folder — subfolders by topic are supported:

```
~/Documents/Materials/
├── DSA/
│   ├── Cracking-the-Coding-Interview.pdf
│   └── Introduction_To_Algorithms.pdf
├── SystemDesign/
│   ├── Kafka_Definitive_Guide.pdf
│   └── Redis-For-Dummies.pdf
└── AI/
    └── AI_Engineering.pdf
```

By default the scripts look for materials at `~/Documents/Materials`. Override this with an environment variable:

```bash
export MATERIALS_DIR="/path/to/your/materials"
```

---

## Usage

### Step 1 — Ingest your materials (run once)

```bash
python ingest.py
```

This reads all your files, chunks them, embeds every chunk, and stores everything in `chroma_db/`. Takes 5–10 minutes for a large library. You only need to re-run this when you add new materials.

### Step 2 — Search and ask questions

```bash
python search.py
```

```
=== Your Personal RAG Search ===
Type a question about your materials. Type 'quit' to exit.

Your question: What is Kafka and when should I use it?

Top 5 chunks retrieved:
  1. [0.726] SystemDesign/Kafka_Definitive-Guide_Complete.pdf
  2. [0.714] SystemDesign/Kafka_Streams_and_ksqlDB-ebook.pdf
  ...

Answer:
Kafka is a streaming platform that allows you to publish, subscribe to,
store, and process streams of data in real time...
Source: SystemDesign/Kafka_Definitive-Guide_Complete.pdf
```

### Step 3 — Get your daily fact

```bash
python daily_fact.py
```

```
=======================================================
  📚 Daily Learning Fact — Saturday, June 13 2026
=======================================================
When launching a new customer-facing service, backward compatibility
must be planned from day one — AWS, for example, maintains even
loss-making services once they reach General Availability because
customers depend on them.
Source: AI/Gergely Orosz - The Software Engineer's Guidebook.pdf
=======================================================
```

### Automate the daily fact (Mac/Linux)

```bash
crontab -e
```

Add this line to run at 8 AM every day:

```
0 8 * * * cd /path/to/RAG/personal_learning_rag && /path/to/venv/bin/python daily_fact.py >> ~/daily_fact_log.txt 2>&1
```

---

## Key concepts

**Embeddings** — each text passage is converted into a list of 384 numbers that capture its meaning. Similar meanings produce similar numbers. This is what enables semantic search — finding relevant passages even when the exact words don't match.

**Vector store (ChromaDB)** — a database optimised for storing and searching embeddings. Uses cosine similarity to find the closest matches to any query. All data is stored locally on disk in `chroma_db/`.

**Chunking** — documents are split into overlapping passages of ~1000 characters. Overlap ensures ideas that span chunk boundaries are captured in at least one chunk. Chunk size affects answer quality — smaller chunks are more precise, larger chunks have more context.

**Retrieval-Augmented Generation** — the LLM never guesses. It only reads the passages retrieved from your documents and answers strictly from those. This prevents hallucination and keeps answers grounded in your actual materials.

---

## Configuration

Key settings at the top of each file:

| Setting | File | Default | Effect |
|---|---|---|---|
| `MATERIALS_DIR` | `reader.py`, `chunker.py`, `ingest.py` | `~/Documents/Materials` | Where your files live |
| `chunk_size` | `chunker.py` | `1000` | Passage size in characters |
| `chunk_overlap` | `chunker.py` | `150` | Overlap between passages |
| `TOP_K` | `search.py` | `5` | Number of passages retrieved per query |
| `EMBED_MODEL` | `ingest.py`, `search.py` | `all-MiniLM-L6-v2` | Embedding model (local, ~90MB) |
| `model` | `search.py`, `daily_fact.py` | `qwen3:8b` | LLM for generation |

---

## Supported file types

| Type | Extension | Notes |
|---|---|---|
| PDF | `.pdf` | Direct text extraction first; scanned/image pages fall back to OCR, then to a vision LLM for diagrams and charts |
| Markdown | `.md` | Full support |
| Plain text | `.txt` | Full support |

---

## Troubleshooting

**"Nothing notable in this passage" — keeps appearing**
The daily fact retries up to 5 times automatically. If it can't find a good passage, run the script again.

**Slow ingestion**
Normal for large libraries. `Introduction_To_Algorithms` alone is 2.5M characters. Ingestion is a one-time cost — subsequent runs load from disk instantly.

**"Ignoring wrong pointing object" warnings**
Harmless warnings from corrupted PDF metadata. Text extraction still succeeds. Ignore them.

**Low relevance scores (below 0.5)**
The topic may not be well covered in your materials, or the phrasing in your documents uses different terminology. Try rephrasing the question or adding more materials on that topic.

**Scanned PDFs return empty text**
`reader.py` falls back to OCR (`pytesseract`) and then a vision LLM (`ollama` + `llava:7b`) for image-only pages, so most scanned PDFs still extract something. If a page is blank or illegible, no method will recover text from it.

---

## Adding new materials

Drop new PDFs or notes into your materials folder and re-run ingestion:

```bash
python ingest.py
```

This rebuilds the vector store from scratch with all files including the new ones.

---

## Tech stack

| Component | Library | Purpose |
|---|---|---|
| PDF parsing | `pymupdf` (`fitz`) | Extract text and render pages from PDF files |
| OCR fallback | `pytesseract` (+ system Tesseract) | Extract text from scanned/image PDF pages |
| Vision fallback | `ollama` + `llava:7b` | Describe diagrams, charts, and flowcharts as text |
| Text splitting | `langchain-text-splitters` | Smart chunking with overlap |
| Embeddings | `sentence-transformers` | Local embedding model, no API needed |
| Vector store | `chromadb` | Persistent local vector database |
| LLM | `ollama` + `qwen3:8b` | Local language model for generation |
| Scheduling | `cron` | Automated daily facts |

Note: `search.py` and `daily_fact.py` both `import anthropic` — a leftover from an earlier version that called the Anthropic API directly (the code paths are still present but commented out in favor of the local `ollama` calls). The import executes unconditionally, so `anthropic` must stay installed even though it isn't actively called.

---

## Stages this project was built in

| Stage | What was built | What was learned |
|---|---|---|
| 1 | `reader.py` | File I/O, recursive folder traversal, PDF parsing |
| 2 | `chunker.py` | Text chunking, overlap, token limits |
| 3 | `ingest.py` | Embeddings, vector databases, cosine similarity |
| 4 | `search.py` | The RAG query loop, prompt grounding |
| 5 | `daily_fact.py` | Random retrieval, scheduling, prompt engineering |
