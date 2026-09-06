from langchain_text_splitters import RecursiveCharacterTextSplitter

def chunk_documents(documents: list[dict]) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,       # ~250 tokens per chunk
        chunk_overlap=150,     # overlap so ideas don't get cut off
        separators=["\n\n", "\n", ". ", " ", ""],  # split on natural boundaries
    )

    chunks = []
    for doc in documents:
        if not doc["text"].strip():
            continue  # skip empty docs (the scanned PDFs)

        passages = splitter.split_text(doc["text"])

        for i, passage in enumerate(passages):
            chunks.append({
                "id": f"{doc['filename']}::chunk_{i}",
                "text": passage,
                "source": doc["filename"],
            })

    return chunks


if __name__ == "__main__":
    from reader import load_all_materials
    import os

    MATERIALS_DIR = os.environ.get("MATERIALS_DIR", os.path.expanduser("~/Documents/Materials"))
    docs = load_all_materials(MATERIALS_DIR)

    chunks = chunk_documents(docs)

    print(f"Documents: {len(docs)}")
    print(f"Chunks:    {len(chunks)}")
    print(f"Avg chunk size: {sum(len(c['text']) for c in chunks) // len(chunks)} chars")
    print()

    # Show a sample chunk so you can see what they look like
    sample = chunks[200]
    print(f"Sample chunk ID:  {sample['id']}")
    print(f"Source:           {sample['source']}")
    print(f"Length:           {len(sample['text'])} chars")
    print(f"Text:\n{sample['text']}")