import os
import chromadb
from sentence_transformers import SentenceTransformer
from reader import load_all_materials
from chunker import chunk_documents

MATERIALS_DIR = os.environ.get("MATERIALS_DIR", os.path.expanduser("~/Documents/Materials"))
DB_DIR = "chroma_db"
COLLECTION_NAME = "my_knowledge"
EMBED_MODEL = "all-MiniLM-L6-v2"  # fast, good quality, 384 dimensions
BATCH_SIZE = 100  # embed 100 chunks at a time to avoid memory issues


def build_vector_store():
    print("--- Step 1: Loading documents ---")
    docs = load_all_materials(MATERIALS_DIR)
    print(f"Loaded {len(docs)} documents\n")

    print("--- Step 2: Chunking ---")
    chunks = chunk_documents(docs)
    print(f"Created {len(chunks)} chunks\n")

    print("--- Step 3: Loading embedding model ---")
    model = SentenceTransformer(EMBED_MODEL)
    print(f"Model loaded: {EMBED_MODEL}\n")

    print("--- Step 4: Setting up ChromaDB ---")
    client = chromadb.PersistentClient(path=DB_DIR)

    # Delete old collection if re-running, so we don't get duplicates
    existing = [c.name for c in client.list_collections()]
    if COLLECTION_NAME in existing:
        print(f"Deleting existing collection '{COLLECTION_NAME}'...")
        client.delete_collection(COLLECTION_NAME)

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}  # cosine similarity = better for text
    )
    print(f"Collection '{COLLECTION_NAME}' ready\n")

    print("--- Step 5: Embedding & storing chunks ---")
    total = len(chunks)
    for i in range(0, total, BATCH_SIZE):
        batch = chunks[i: i + BATCH_SIZE]

        texts = [c["text"] for c in batch]
        ids = [c["id"] for c in batch]
        metadatas = [{"source": c["source"]} for c in batch]

        embeddings = model.encode(texts, show_progress_bar=False).tolist()

        collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        done = min(i + BATCH_SIZE, total)
        print(f"  Stored {done}/{total} chunks...", end="\r")

    print(f"\n\nDone! {total} chunks stored in '{DB_DIR}/'")
    print("You never need to run this again unless you add new materials.")


if __name__ == "__main__":
    build_vector_store()