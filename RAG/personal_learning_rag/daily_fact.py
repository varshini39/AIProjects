import random
import anthropic
import chromadb
from datetime import date

DB_DIR = "chroma_db"
COLLECTION_NAME = "my_knowledge"


def get_random_chunk() -> dict:
    client = chromadb.PersistentClient(path=DB_DIR)
    collection = client.get_collection(COLLECTION_NAME)
    total = collection.count()

    for _ in range(20):  # try up to 20 random chunks
        random_offset = random.randint(0, total - 1)
        result = collection.get(
            limit=1,
            offset=random_offset,
            include=["documents", "metadatas"]
        )
        text = result["documents"][0]

        # Skip chunks with encoded control character patterns like /ETB /DC4 /SOH /NAK
        import re
        if re.search(r'/[A-Z]{2,3}\b', text):
            continue

        # Skip chunks that look like TOC entries (lots of dots or page numbers)
        dot_sequences = text.count("...") + text.count("....")
        if dot_sequences > 3:
            continue

        # Skip chunks with very few sentences but many short lines (heading lists)
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        avg_line_length = sum(len(l) for l in lines) / max(len(lines), 1)
        if avg_line_length < 50 and len(lines) > 8:
            continue

        # Skip corrupted chunks (too many non-ASCII or special characters)
        non_ascii = sum(1 for c in text if ord(c) > 127 or c in '\x00\x01\x02\x03\x04\x05')
        if non_ascii / max(len(text), 1) > 0.03:  # more than 3% garbage characters
            continue

        # Skip math-heavy chunks
        math_symbols = sum(1 for c in text if c in "∑∫√∂∈∉⊆⊇∀∃≤≥≠≈˚˙")
        if math_symbols > 5:
            continue

        # Skip chunks with control characters (corrupted PDF extraction)
        control_chars = sum(1 for c in text if ord(c) < 32 and c not in '\n\r\t')
        if control_chars > 3:
            continue

        # Skip chunks that are mostly code
        code_lines = sum(1 for line in text.splitlines() if line.strip().startswith(
            ("public ", "private ", "int ", "void ", "return ", "if (", "for (",
             "/*", "//", "}", "{", "class ", "import ", "def ", "print(")
        ))
        total_lines = max(len(text.splitlines()), 1)
        if code_lines / total_lines > 0.4:  # skip if >40% is code
            continue

        # Skip chunks that look like front/back matter
        skip_keywords = [
            "acknowledgement", "thank", "preface", "table of contents",
            "all rights reserved", "isbn", "printed in", "first edition",
            "second edition", "third edition", "www.", "http", "copyright",
            "permission", "appendix", "bibliography", "index"
        ]
        if any(kw in text.lower() for kw in skip_keywords):
            continue

        # Skip chapter conclusions / summaries / intro paragraphs
        summary_keywords = [
            "in this chapter", "in chapter", "we will", "we have seen",
            "as we discussed", "in the next chapter", "conclusion",
            "introduction", "bring this all together", "let's explore",
            "in summary", "this section", "overview"
        ]
        if any(kw in text.lower() for kw in summary_keywords):
            continue

        # Skip chunks that are step-by-step code walkthroughs
        walkthrough_keywords = ["line 1", "line 2", "line 3", "line 4",
                                "step 1", "step 2", "returns null",
                                "head.next", "node.next", "returned_node"]
        if sum(1 for kw in walkthrough_keywords if kw.lower() in text.lower()) > 2:
            continue

        # Skip chunks that are too short to contain a real insight
        if len(text.strip()) < 300:
            continue

        # Skip chunks with too many pronouns without context (this, it, they, these)
        # indicating the chunk depends on surrounding context
        words = text.lower().split()
        context_dependent = sum(1 for w in words if w in ("this", "these", "it", "they", "such"))
        if context_dependent / max(len(words), 1) > 0.05:  # more than 5% context words
            continue

        return {"text": text, "source": result["metadatas"][0]["source"]}

    # fallback if nothing passes filter
    result = collection.get(limit=1, offset=random.randint(0, total - 1),
                            include=["documents", "metadatas"])
    return {"text": result["documents"][0], "source": result["metadatas"][0]["source"]}


# Anthropic method
# def generate_daily_fact(chunk: dict) -> str:
#     prompt = f"""You are a smart learning assistant helping someone review their study materials.
#
# Below is a passage from their notes. Extract the single most interesting, surprising, or practically useful insight from it.
#
# Rules:
# - One insight only — not a summary
# - Make it feel like a "did you know?" moment
# - Keep it under 4 sentences
# - End with a practical tip on when to apply this knowledge
# - Mention the source file at the end
#
# Passage (from {chunk['source']}):
# {chunk['text']}
#
# Daily insight:"""
#
#     client = anthropic.Anthropic()
#     message = client.messages.create(
#         model="claude-sonnet-4-6",
#         max_tokens=300,
#         messages=[{"role": "user", "content": prompt}]
#     )
#     return message.content[0].text
# llama method
def generate_daily_fact(chunk: dict) -> str:
    import ollama

    prompt = f"""You are a learning assistant. Your job is to extract one insight from the passage below.

STRICT RULES:
- Use ONLY information present in the passage. Do not add anything else.
- If the passage is acknowledgements, a table of contents, author credits, or book metadata, say "Nothing notable."
- If the passage is mostly code with little explanation, say "Nothing notable."
- If nothing interesting stands out, say "Nothing notable."
- Do not invent examples, analogies, or tips not mentioned in the passage.
- One insight only, 2-3 sentences max.
- If the passage refers to "this", "it", "they" without defining what they are, say "Nothing notable."
- Always name the specific concept, tool, or topic explicitly — never use "it" or "this" in your insight.
- If the passage is a chapter intro, conclusion, or summary, say "Nothing notable."
- End with: "Source: {chunk['source']}"

Passage:
{chunk['text']}

Insight (strictly from the passage only):"""

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


def show_daily_fact():
    today = date.today().strftime("%A, %B %d %Y")
    print(f"\n{'='*55}")
    print(f"  📚 Daily Learning Fact — {today}")
    print(f"{'='*55}\n")

    max_attempts = 5
    for attempt in range(max_attempts):
        chunk = get_random_chunk()
        fact = generate_daily_fact(chunk)

        if "Nothing notable" in fact:
            print(f"  (Skipping weak chunk, trying again...)")
            continue

        # print(f"Source chunk used:\n{chunk['text'][:400]}...")
        # print(f"\nFact generated:\n{fact}")
        print(fact)
        print(f"\n{'='*55}\n")
        return

    print("Couldn't find a notable fact after 5 attempts. Try running again.")
    print(f"\n{'='*55}\n")


if __name__ == "__main__":
    show_daily_fact()