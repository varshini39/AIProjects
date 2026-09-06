import os
import fitz           # pymupdf
import base64
import pytesseract
import ollama
from PIL import Image
import io

MATERIALS_DIR = os.environ.get(
    "MATERIALS_DIR",
    os.path.expanduser("~/Documents/Materials")
)

# Thresholds
TEXT_THRESHOLD    = 100   # chars — below this, page is image-based
OCR_THRESHOLD     = 50    # chars — below this, OCR found nothing useful → use vision


def page_to_pil_image(page) -> Image.Image:
    """Render a PDF page as a PIL image at 2x resolution."""
    mat = fitz.Matrix(2, 2)       # 2x zoom = better OCR + vision accuracy
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    return Image.open(io.BytesIO(img_bytes))


def page_to_base64(pil_image: Image.Image) -> str:
    """Convert PIL image to base64 string for vision model."""
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def run_ocr(pil_image: Image.Image) -> str:
    """Extract text from an image using Tesseract OCR."""
    return pytesseract.image_to_string(pil_image).strip()


def run_vision(pil_image: Image.Image, page_num: int) -> str:
    """Describe a diagram or visual page using a vision LLM."""
    img_b64 = page_to_base64(pil_image)

    response = ollama.chat(
        model="llava:7b",
        messages=[{
            "role": "user",
            "content": """You are analyzing a page from a technical study material.
Describe what you see in detail:
- If it's a diagram or architecture drawing: describe the components, connections, and what it illustrates
- If it's a chart or graph: describe the data, axes, and key insights
- If it's a flowchart: describe the steps and decision points
- If it contains code: transcribe it
- If it contains a table: describe the structure and content
Be specific and technical. Your description will be used for search.""",
            "images": [img_b64]
        }]
    )
    description = response["message"]["content"]
    return f"[Visual page {page_num}]: {description}"


def process_page(page, page_num: int, total: int) -> str:
    """
    Process a single PDF page through the full pipeline:
    1. Try direct text extraction
    2. Fall back to OCR for scanned text
    3. Fall back to vision for diagrams/charts
    """
    # Step 1 — direct text extraction (fastest)
    text = page.get_text().strip()
    if len(text) >= TEXT_THRESHOLD:
        return text

    # Page is image-based — render it
    print(f"    Page {page_num}/{total} is image-based, processing...")
    pil_image = page_to_pil_image(page)

    # Step 2 — OCR (for scanned text pages)
    ocr_text = run_ocr(pil_image)
    if len(ocr_text) >= OCR_THRESHOLD:
        print(f"    → OCR succeeded ({len(ocr_text)} chars)")
        return f"[OCR page {page_num}]: {ocr_text}"

    # Step 3 — Vision LLM (for diagrams, charts, visuals)
    print(f"    → OCR found little text, using vision model...")
    return run_vision(pil_image, page_num)


def read_pdf(filepath: str) -> str:
    """Read a PDF using the full pipeline: text → OCR → vision."""
    doc = fitz.open(filepath)
    total = len(doc)
    pages = []

    for i, page in enumerate(doc):
        result = process_page(page, i + 1, total)
        if result:
            pages.append(result)

    doc.close()
    return "\n\n".join(pages)


def read_text_file(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def load_all_materials(directory: str):
    documents = []

    for root, dirs, files in os.walk(directory):
        for filename in files:
            filepath = os.path.join(str(root), str(filename))
            label = os.path.relpath(filepath, str(directory))

            if filename.endswith(".pdf"):
                print(f"Reading PDF: {label}")
                text = read_pdf(filepath)
                documents.append({"filename": label, "text": text})

            elif filename.endswith((".md", ".txt")):
                print(f"Reading note: {label}")
                text = read_text_file(filepath)
                documents.append({"filename": label, "text": text})

    return documents


if __name__ == "__main__":
    docs = load_all_materials(MATERIALS_DIR)

    print(f"\n--- Loaded {len(docs)} documents ---\n")
    for doc in docs:
        preview = doc["text"][:300].replace("\n", " ")
        print(f"[{doc['filename']}] ({len(doc['text'])} chars)")
        print(f"  Preview: {preview}...")
        print()