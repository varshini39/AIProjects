"""
app.py
======
Gradio UI for the PDF RAG pipeline.

Lets you:
  1. Upload 2-3 PDF files and index them (chunk -> embed -> FAISS)
  2. See chunking metrics (total chunks, average chunk size)
  3. Ask questions in a chat box and get answers grounded only in the uploaded PDFs

Run from this folder:
    python app.py
Then open the local URL Gradio prints (usually http://127.0.0.1:7860).
"""

import os
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------
# Load only this project's own .env — an unqualified load_dotenv() walks up
# parent directories and would pick up an unrelated .env elsewhere in the repo.
load_dotenv(Path(__file__).resolve().parent / ".env")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError(
        "OPENAI_API_KEY not found. Create a .env file in the project root "
        "with OPENAI_API_KEY=<your key>, or set it as an environment variable."
    )

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
EMBEDDING_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4o-mini"

embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)
llm = ChatOpenAI(model=CHAT_MODEL, temperature=0, api_key=OPENAI_API_KEY)
splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

PROMPT = ChatPromptTemplate.from_template(
    """Answer the question using only the context below, which comes from the
uploaded PDF documents.

If the answer is not available in the context, say:
"I could not find this information in the uploaded documents."

Context:
{context}

Question:
{question}
"""
)
PARSER = StrOutputParser()

# Global state set once the user indexes documents.
# (fine for a single-user local Gradio app; use gr.State for multi-user deployments)
retriever = None


# -------------------------------------------------------------------
# Step 1 + 2 + 3: Load, chunk, embed, store in FAISS
# -------------------------------------------------------------------
def process_pdfs(pdf_files):
    global retriever

    if not pdf_files:
        return "Please upload at least 2 PDF files.", []

    all_documents = []
    file_names = []
    for pdf_path in pdf_files:
        docs = PyPDFLoader(pdf_path).load()
        for d in docs:
            d.metadata["source"] = os.path.basename(pdf_path)
        all_documents.extend(docs)
        file_names.append(os.path.basename(pdf_path))

    chunks = splitter.split_documents(all_documents)
    total_chunks = len(chunks)
    avg_chunk_size = sum(len(c.page_content) for c in chunks) / total_chunks

    vectorstore = FAISS.from_documents(chunks, embeddings)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

    status = (
        f"Indexed {len(file_names)} PDF(s): {', '.join(file_names)}\n\n"
        f"Total pages loaded   : {len(all_documents)}\n"
        f"Total chunks stored  : {total_chunks}\n"
        f"Average chunk size   : {avg_chunk_size:.0f} characters\n\n"
        "You can now ask questions in the chat box below."
    )
    return status, []  # second value clears the chat history on re-index


# -------------------------------------------------------------------
# Step 4: Retrieval-augmented answer
# -------------------------------------------------------------------
def ask_question(question, history):
    if retriever is None:
        answer = "Please upload and index your PDFs first (Step 1)."
    elif not question or not question.strip():
        answer = "Please type a question."
    else:
        docs = retriever.invoke(question)
        context = "\n\n".join(d.page_content for d in docs)
        answer = (PROMPT | llm | PARSER).invoke({"context": context, "question": question})

        sources = ", ".join(sorted({d.metadata.get("source", "unknown") for d in docs}))
        answer += f"\n\nSources: {sources}"

    history = history + [
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer},
    ]
    return history, ""


# -------------------------------------------------------------------
# Gradio UI
# -------------------------------------------------------------------
with gr.Blocks(title="PDF RAG Assistant") as demo:
    gr.Markdown(
        "## PDF RAG Assistant\n"
        "Upload 2-3 PDF documents, index them, then ask questions. "
        "Answers are generated using GPT + FAISS retrieval, grounded only in your documents."
    )

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### Step 1 - Upload & Index PDFs")
            pdf_input = gr.File(
                label="Upload PDF files (2-3)",
                file_types=[".pdf"],
                file_count="multiple",
                type="filepath",
            )
            index_btn = gr.Button("Index Documents", variant="primary")
            index_status = gr.Textbox(label="Status / Metrics", lines=8, interactive=False)

        with gr.Column(scale=2):
            gr.Markdown("### Step 2 - Ask Questions")
            chatbot = gr.Chatbot(label="Chat", height=400)
            question_input = gr.Textbox(
                label="Your question",
                placeholder="e.g. What does this document say about the return policy?",
                lines=2,
            )
            ask_btn = gr.Button("Ask", variant="primary")

    index_btn.click(fn=process_pdfs, inputs=pdf_input, outputs=[index_status, chatbot])
    ask_btn.click(fn=ask_question, inputs=[question_input, chatbot], outputs=[chatbot, question_input])
    question_input.submit(fn=ask_question, inputs=[question_input, chatbot], outputs=[chatbot, question_input])

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft())