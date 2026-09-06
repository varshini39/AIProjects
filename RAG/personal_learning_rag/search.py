import chromadb
from sentence_transformers import SentenceTransformer
import ollama

DB_DIR = "chroma_db"
COLLECTION_NAME = "my_knowledge"
EMBED_MODEL = "all-MiniLM-L6-v2"
TOP_K = 5  # how many chunks to retrieve per query

# Load once, reuse for every question
client = chromadb.PersistentClient(path=DB_DIR)
collection = client.get_collection(COLLECTION_NAME)
model = SentenceTransformer(EMBED_MODEL)


def search(query: str) -> list[dict]:
    query_embedding = model.encode(query).tolist()

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=TOP_K,
        include=["documents", "metadatas", "distances"]
    )

    chunks = []
    for i in range(len(results["documents"][0])):
        chunks.append({
            "text": results["documents"][0][i],
            "source": results["metadatas"][0][i]["source"],
            "score": round(1 - results["distances"][0][i], 3)  # cosine: 1=identical, 0=unrelated
        })
    return chunks


# Using normal API
# def ask(question: str) -> str:
#     print(f"\nSearching for: '{question}'")
#     chunks = search(question)
#
#     # Build context from retrieved chunks
#     context = "\n\n---\n\n".join([
#         f"[Source: {c['source']}]\n{c['text']}" for c in chunks
#     ])
#
#     # Show what was retrieved
#     print(f"\nTop {TOP_K} chunks retrieved:")
#     for i, c in enumerate(chunks):
#         print(f"  {i+1}. [{c['score']}] {c['source']}")
#
#     # Build the prompt
#     prompt = f"""You are a helpful learning assistant. Answer the question using ONLY the context provided below.
# If the answer isn't in the context, say "I couldn't find this in your materials."
# Always mention which source the answer came from.
#
# Context:
# {context}
#
# Question: {question}
#
# Answer:"""
#
#     # Call the Anthropic API
#     import urllib.request, json
#     payload = json.dumps({
#         "model": "claude-sonnet-4-6",
#         "max_tokens": 1000,
#         "messages": [{"role": "user", "content": prompt}]
#     }).encode()
#
#     api_key = os.environ.get("ANTHROPIC_API_KEY", "")
#     if not api_key:
#         return "ERROR: ANTHROPIC_API_KEY not set. Add it to your run configuration."
#
#     req = urllib.request.Request(
#         "https://api.anthropic.com/v1/messages",
#         data=payload,
#         headers={
#             "content-type": "application/json",
#             "x-api-key": api_key,
#             "anthropic-version": "2023-06-01"
#         }
#     )
#     with urllib.request.urlopen(req) as resp:
#         data = json.loads(resp.read())
#         return data["content"][0]["text"]

# Anthropic/llama methods used
def ask(question: str) -> str:
    import anthropic

    print(f"\nSearching for: '{question}'")
    chunks = search(question)

    context = "\n\n---\n\n".join([
        f"[Source: {c['source']}]\n{c['text']}" for c in chunks
    ])

    print(f"\nTop {TOP_K} chunks retrieved:")
    for i, c in enumerate(chunks):
        print(f"  {i+1}. [{c['score']}] {c['source']}")

    prompt = f"""You are a helpful learning assistant. Answer the question using ONLY the context provided below.
If the answer isn't in the context, say "I couldn't find this in your materials."
Always mention which source the answer came from.

Context:
{context}

Question: {question}

Answer:"""

    # client = anthropic.Anthropic()  # picks up ANTHROPIC_API_KEY automatically
    # message = client.messages.create(
    #     model="claude-sonnet-4-6",
    #     max_tokens=1000,
    #     messages=[{"role": "user", "content": prompt}]
    # )
    # return message.content[0].text

    # response = ollama.chat(
    #     model="llama3.2",
    #     messages=[{"role": "user", "content": prompt}]
    # )

    response = ollama.chat(
        model="qwen3:8b",
        messages=[{"role": "user", "content": prompt}],
        # options={"think": False}   # disables thinking mode, much faster
    )
    return response["message"]["content"]

if __name__ == "__main__":
    print("=== Your Personal RAG Search ===")
    print("Type a question about your materials. Type 'quit' to exit.\n")

    while True:
        question = input("Your question: ").strip()
        if question.lower() in ("quit", "exit", "q"):
            break
        if not question:
            continue

        answer = ask(question)
        print(f"\nAnswer:\n{answer}\n")
        print("-" * 60)