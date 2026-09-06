# AIProjects

A collection of small, independent AI/agentic projects, grouped by the
framework or pattern they explore (RAG, multi-agent orchestration with
CrewAI, AutoGen-style microservices + n8n). Each top-level folder is a
category that can hold multiple projects; every project lives in its own
subfolder with its own `requirements.txt`, its own README, and no shared
dependencies, so it can be run entirely on its own.

## Repository layout

```
AIProjects/
├── RAG/
│   ├── pdf_qa_assistant/         # PDF Q&A app — LangChain + FAISS + Gradio
│   └── personal_learning_rag/    # Local semantic search + daily-fact RAG over your own study materials
├── CrewAI/
│   └── agentic_rag_router/       # Agentic router/retriever RAG system (Jupyter notebook)
└── AutoGen/
    └── linkedin_automation/      # AutoGen-style FastAPI microservice + n8n workflow
```

To add a new project, create a new subfolder under the relevant category
(`RAG/`, `CrewAI/`, `AutoGen/`, or a new category folder if it doesn't fit
any of these) with its own code, `requirements.txt`, and README, then add
a section for it below.

## Prerequisites

- Python 3.10+
- pip
- An OpenAI API key — required by `RAG/pdf_qa_assistant` and
  `CrewAI/agentic_rag_router`; optional for AutoGen, which can run fully
  offline in mock mode; not needed at all for `RAG/personal_learning_rag`
  (fully local via Ollama)
- [Tavily](https://tavily.com) API key (free tier) — only for CrewAI's web
  search path
- [Ollama](https://ollama.com) + Tesseract OCR — only for
  `RAG/personal_learning_rag`, see its own README for setup

Each project keeps its own `requirements.txt` and its own virtual
environment, since they don't share dependencies. From the repo root:

```bash
cd <project-folder>
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## RAG / `pdf_qa_assistant` — PDF Q&A Assistant

**What it is:** A Gradio app that lets you upload PDF documents, indexes
them (chunk → embed → FAISS vector store), and answers questions grounded
only in the uploaded documents (no hallucinated answers outside the PDFs).
Two sample PDFs (`Company_Employee_Handbook_1.pdf`, `IT_Support_Guide.pdf`)
are included to try it out. See
[`RAG/pdf_qa_assistant/README.md`](RAG/pdf_qa_assistant/README.md) for
how it works internally.

**Stack:** LangChain, OpenAI (`gpt-4o-mini` + `text-embedding-3-small`),
FAISS, Gradio.

**Run it:**
```bash
cd RAG/pdf_qa_assistant
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # then edit .env with your real key

python app.py
```
Open the local URL Gradio prints (usually `http://127.0.0.1:7860`), upload
2–3 PDFs, click **Index Documents**, then ask questions in the chat box.

---

## RAG / `personal_learning_rag` — Personal Learning RAG

**What it is:** A fully local RAG pipeline over your own study materials
(PDFs, markdown, text notes) — semantic search, grounded Q&A, and a daily
"learning fact" pulled from a random passage in your library. No cloud
API required: embeddings, the vector store, and generation all run on
your machine via Ollama. See
[`RAG/personal_learning_rag/README.md`](RAG/personal_learning_rag/README.md)
for the full pipeline, configuration options, and troubleshooting.

**Stack:** PyMuPDF + `pytesseract` + a local vision LLM (`llava:7b`) for
PDF text extraction with OCR/vision fallback, `langchain-text-splitters`,
`sentence-transformers` for embeddings, ChromaDB as the vector store,
Ollama (`qwen3:8b`) for generation.

**Run it:**
```bash
cd RAG/personal_learning_rag
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

ollama pull qwen3:8b
ollama pull llava:7b

export MATERIALS_DIR="/path/to/your/materials"   # defaults to ~/Documents/Materials

python ingest.py      # one-time: chunk, embed, and store your materials
python search.py      # ask questions grounded in your materials
python daily_fact.py  # surface one random insight
```

---

## CrewAI / `agentic_rag_router` — Agentic Router/Retriever RAG

**What it is:** A CrewAI-based multi-agent system that routes each
question to the retrieval path best suited to answer it — a PDF vector
search, a live web search (Tavily), or a direct LLM answer with no
retrieval — via a Router Agent, then a Retriever Agent (scoped to exactly
one tool) and an Answer Generation Agent. Every run's routing decision and
per-agent reasoning is logged to `outputs/reasoning_trace_log.csv`.
See [`CrewAI/agentic_rag_router/README.md`](CrewAI/agentic_rag_router/README.md)
for the full architecture, design rationale, and challenges.

**Stack:** CrewAI, `crewai-tools` (`PDFSearchTool`), LangChain community
Tavily wrapper, OpenAI.

**Run it:**
```bash
cd CrewAI/agentic_rag_router
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # then edit .env with your real keys

jupyter notebook AgenticRAG_Project.ipynb
```
Run all cells top to bottom. The demo section runs 5 sample questions
(PDF-routed, web-routed, direct, and out-of-scope) and prints each agent's
reasoning, then saves the trace table to `outputs/reasoning_trace_log.csv`.

---

## AutoGen / `linkedin_automation` — LinkedIn Content Automation

**What it is:** A FastAPI microservice that mimics an AutoGen/AG2
group-chat pipeline (Ideation → Drafting → Hashtags → Review/Scoring) for
generating LinkedIn posts, orchestrated end-to-end by an n8n workflow that
adds scheduling, a human approval gate, Slack review, and logging to
Google Sheets. Full architecture diagram, error-handling notes, and a
testing walkthrough are in
[`AutoGen/linkedin_automation/README.md`](AutoGen/linkedin_automation/README.md).

**Stack:** FastAPI, Pydantic, AG2 (AutoGen) for the real-LLM mode, n8n for
orchestration.

**Run it:**
```bash
cd AutoGen/linkedin_automation
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # USE_MOCK=true works out of the box, no API key needed
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
Test it:
```bash
curl -s http://localhost:8000/health
curl -s -X POST http://localhost:8000/linkedin \
  -H "Content-Type: application/json" \
  -d @sample_request.json | python3 -m json.tool
```
`USE_MOCK=true` (the default) runs fully offline deterministic agents — no
OpenAI key required — so you can exercise the whole pipeline before
switching to real AG2 agents with `USE_MOCK=false`.

The n8n workflow (`n8n/FinEdge_LinkedIn_Automation.json`) can be imported
into a local n8n instance (`npm install -g n8n && n8n start`) to drive the
microservice with scheduling, Slack approval, and logging — see the
project's own README for the full setup and testing steps.

---

## Notes

- Each project has its own `.env.example` next to its code — copy it to
  `.env` in that same folder and fill in real values. Each project's code
  loads its `.env` from its own folder explicitly, so it never reads
  config from another project or from a `.env` elsewhere in the repo.
- Each project's `.env` / API keys are excluded from git via `.gitignore`
  — never commit real API keys.
- `venv/`, `__pycache__/`, `.DS_Store`, and runtime-generated logs
  (`*.log.jsonl`) are also excluded.
