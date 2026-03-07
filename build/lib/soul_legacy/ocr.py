"""
OCR layer — extract text from PDFs, images, Word docs.

Local:   pdfplumber (PDFs) + pytesseract (images) — lightweight, no GPU
Cloud:   Azure Form Recognizer — best quality for mixed/scanned docs

Auto-detects file type and picks best extractor.
"""
import os
from typing import Tuple


def extract_text(file_path: str, config: dict = None) -> Tuple[str, str]:
    """
    Extract text from any document.
    Returns (text, method_used)
    """
    config = config or {}
    ext    = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return _extract_pdf(file_path, config)
    elif ext in (".jpg", ".jpeg", ".png", ".tiff", ".bmp", ".webp"):
        return _extract_image(file_path, config)
    elif ext in (".docx", ".doc"):
        return _extract_word(file_path)
    elif ext == ".txt":
        return open(file_path).read(), "plaintext"
    else:
        # Try PDF pipeline as fallback
        return _extract_pdf(file_path, config)


def _extract_pdf(path: str, config: dict) -> Tuple[str, str]:
    """Try pdfplumber first (text PDFs), fall back to OCR (scanned)"""
    # Cloud override
    if config.get("ocr_mode") == "azure":
        return _extract_azure(path, config)

    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
        text = "\n\n".join(pages).strip()
        if len(text) > 100:          # good extraction
            return text, "pdfplumber"
        # Fall through to OCR — likely a scanned PDF
    except ImportError:
        pass

    # Scanned PDF → convert pages to images → OCR
    return _ocr_pdf_pages(path, config)


def _ocr_pdf_pages(path: str, config: dict) -> Tuple[str, str]:
    """Convert PDF pages to images then OCR each"""
    if config.get("ocr_mode") == "azure":
        return _extract_azure(path, config)
    try:
        from pdf2image import convert_from_path
        import pytesseract
        images = convert_from_path(path, dpi=200)
        pages  = [pytesseract.image_to_string(img) for img in images]
        return "\n\n".join(pages).strip(), "tesseract"
    except ImportError:
        raise ImportError(
            "For scanned PDFs install: pip install pdf2image pytesseract\n"
            "And system: brew install tesseract poppler\n"
            "Or set ocr_mode=azure in config to use Azure Form Recognizer."
        )


def _extract_image(path: str, config: dict) -> Tuple[str, str]:
    """OCR an image file"""
    if config.get("ocr_mode") == "azure":
        return _extract_azure(path, config)
    try:
        import pytesseract
        from PIL import Image
        text = pytesseract.image_to_string(Image.open(path))
        return text.strip(), "tesseract"
    except ImportError:
        raise ImportError(
            "For image OCR install: pip install pytesseract pillow\n"
            "And system: brew install tesseract\n"
            "Or set ocr_mode=azure in config."
        )


def _extract_word(path: str) -> Tuple[str, str]:
    try:
        from docx import Document
        doc   = Document(path)
        paras = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paras), "python-docx"
    except ImportError:
        raise ImportError("Install: pip install python-docx")


def _extract_azure(path: str, config: dict) -> Tuple[str, str]:
    """Azure Form Recognizer — best quality, handles scanned + structured forms"""
    import requests
    endpoint = config.get("azure_endpoint") or os.getenv("AZURE_OPENAI_ENDPOINT", "")
    api_key  = config.get("azure_key")      or os.getenv("AZURE_OPENAI_KEY", "")

    # Use Document Intelligence (formerly Form Recognizer)
    # Endpoint format is different from OpenAI — use dedicated DI endpoint if set
    di_endpoint = config.get("azure_di_endpoint", endpoint)
    url = f"{di_endpoint}/formrecognizer/documentModels/prebuilt-read:analyze?api-version=2023-07-31"

    with open(path, "rb") as f:
        content = f.read()
    headers = {"api-key": api_key, "Content-Type": "application/octet-stream"}
    r = requests.post(url, headers=headers, data=content, timeout=30)

    if r.status_code == 202:
        # Poll for result
        import time
        op_url = r.headers.get("Operation-Location")
        for _ in range(30):
            time.sleep(2)
            result = requests.get(op_url, headers={"api-key": api_key}).json()
            if result.get("status") == "succeeded":
                content_ = result["analyzeResult"]["content"]
                return content_, "azure-form-recognizer"
        raise TimeoutError("Azure Form Recognizer timed out")

    r.raise_for_status()
    return "", "azure-form-recognizer"
