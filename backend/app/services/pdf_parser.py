"""
Parse PDFs to plain text.

Strategy:
1. Try pypdf first (fast, free, works for text-layer PDFs)
2. If a page extracts < 50 chars (scanned/image page), use Claude vision
   on that specific page to OCR it.
"""
import base64
import io
from pathlib import Path

import anthropic
from pypdf import PdfReader

from ..config import settings

_anthropic = anthropic.Anthropic(api_key=settings.anthropic_api_key)

MIN_TEXT_CHARS = 50


def _page_to_base64(reader: PdfReader, page_index: int) -> str:
    """Render a single PDF page to PNG bytes using pypdf's built-in rasterizer."""
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_page(reader.pages[page_index])
    buf = io.BytesIO()
    writer.write(buf)
    return base64.b64encode(buf.getvalue()).decode()


def _ocr_page_with_claude(pdf_bytes_b64: str) -> str:
    """Send a single-page PDF to Claude vision to extract text."""
    msg = _anthropic.messages.create(
        model=settings.reasoning_model,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_bytes_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extract all text from this document page verbatim. "
                            "Preserve headings, numbering, and paragraph breaks. "
                            "Output only the extracted text, nothing else."
                        ),
                    },
                ],
            }
        ],
    )
    return msg.content[0].text


def parse_pdf(content: bytes, filename: str = "document.pdf") -> str:
    """
    Parse PDF content to plain text.
    Falls back to Claude vision for pages with insufficient text (scanned).
    """
    reader = PdfReader(io.BytesIO(content))
    pages: list[str] = []

    full_pdf_b64: str | None = None

    for i, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if len(text) >= MIN_TEXT_CHARS:
            pages.append(text)
        else:
            # Scanned page — send to Claude vision
            if full_pdf_b64 is None:
                full_pdf_b64 = base64.b64encode(content).decode()
            # Pass the full PDF but note which page we need
            # Claude handles single-page PDFs well; for multi-page scan, extract page
            try:
                page_b64 = _page_to_base64(reader, i)
            except Exception:
                page_b64 = full_pdf_b64
            ocr_text = _ocr_page_with_claude(page_b64)
            pages.append(ocr_text)

    return "\n\n".join(pages)


def parse_text_file(content: bytes) -> str:
    return content.decode("utf-8", errors="replace")
