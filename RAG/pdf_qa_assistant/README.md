# PDF Q&A Assistant

A Gradio app that lets you upload PDF documents, indexes them (chunk →
embed → FAISS vector store), and answers questions grounded only in the
uploaded documents. If the answer isn't in the documents, it says so
instead of guessing.

Two sample PDFs are included so you can try it immediately:
`Company_Employee_Handbook_1.pdf` and `IT_Support_Guide.pdf`.

## How it works

1. **Load** — each uploaded PDF is loaded page-by-page with `PyPDFLoader`.
2. **Chunk** — pages are split into ~1000-character chunks (150-character
   overlap) with `RecursiveCharacterTextSplitter`.
3. **Embed + index** — chunks are embedded with OpenAI's
   `text-embedding-3-small` and stored in an in-memory FAISS vector store.
4. **Retrieve + answer** — each question retrieves the top 3 matching
   chunks, which are passed as context to `gpt-4o-mini` along with a
   prompt that instructs it to answer only from that context and to say
   so plainly if the answer isn't there. The chatbot response also lists
   which source document(s) the answer came from.

## Stack

LangChain (`langchain-openai`, `langchain-community`,
`langchain-text-splitters`), FAISS, Gradio, OpenAI.

## Setup & run

```bash
cd RAG/pdf_qa_assistant
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # then edit .env with your real key

python app.py
```

Open the local URL Gradio prints (usually `http://127.0.0.1:7860`):

1. Upload 2–3 PDFs and click **Index Documents** — you'll see chunk counts
   and average chunk size.
2. Ask questions in the chat box. Answers are grounded in the uploaded
   PDFs only, with sources cited.

## Notes

- Indexing is in-memory and resets each time you re-index or restart the
  app — there's no persistent vector store.
- The app is single-user by design (module-level `retriever` global); for
  a multi-user deployment, move that state into `gr.State`.
- `app.py` loads `.env` from this folder explicitly, so it only ever
  reads this project's own config, never a `.env` elsewhere in the repo.
