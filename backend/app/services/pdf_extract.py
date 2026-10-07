"""PDF / email body extraction.

Flow (per spec): try text extraction first (PyMuPDF -> pdfplumber fallback).
If the PDF is a scan (no text layer) we render pages to PNG and let the AI
vision path handle it - OCR engine is not required in the pipeline.
"""
from __future__ import annotations

import base64
import logging
from typing import List, Tuple

logger = logging.getLogger("pdf")


def extract_pdf_text(data: bytes) -> str:
    """Return concatenated text from a PDF, empty string if no text layer."""
    text = _pymupdf_text(data)
    if len(text.strip()) < 40:  # likely scanned / vector-only
        text2 = _pdfplumber_text(data)
        if len(text2.strip()) > len(text.strip()):
            text = text2
    return text.strip()


def _pymupdf_text(data: bytes) -> str:
    try:
        import fitz  # PyMuPDF

        with fitz.open(stream=data, filetype="pdf") as doc:
            return "\n".join(page.get_text() for page in doc)
    except Exception as exc:  # pragma: no cover - corrupt pdf
        logger.warning("PyMuPDF extraction failed: %s", exc)
        return ""


def _pdfplumber_text(data: bytes) -> str:
    try:
        import io

        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception as exc:  # pragma: no cover
        logger.warning("pdfplumber extraction failed: %s", exc)
        return ""


def render_pages_base64(data: bytes, max_pages: int = 5) -> List[str]:
    """Render PDF pages as PNG base64 for the AI vision fallback (scanned docs)."""
    out: List[str] = []
    try:
        import fitz

        with fitz.open(stream=data, filetype="pdf") as doc:
            for page in list(doc)[:max_pages]:
                pix = page.get_pixmap(dpi=150)
                out.append(base64.b64encode(pix.tobytes("png")).decode("ascii"))
    except Exception as exc:  # pragma: no cover
        logger.error("render_pages_base64 failed: %s", exc)
    return out


def extract_email_body_html_to_text(html: str) -> str:
    """HTML -> text for email bodies using stdlib HTMLParser (zero regex)."""
    if not html:
        return ""
    from html.parser import HTMLParser

    class _TextExtractor(HTMLParser):
        SKIP = {"script", "style"}
        BLOCK = {"br", "p", "div", "tr", "td", "li", "h1", "h2", "h3", "h4", "table"}

        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.chunks: list[str] = []
            self._skip_depth = 0

        def handle_starttag(self, tag, attrs):
            if tag in self.SKIP:
                self._skip_depth += 1
            elif tag in self.BLOCK:
                self.chunks.append("\n")

        def handle_endtag(self, tag):
            if tag in self.SKIP and self._skip_depth > 0:
                self._skip_depth -= 1
            elif tag in self.BLOCK:
                self.chunks.append("\n")

        def handle_data(self, data):
            if self._skip_depth == 0:
                self.chunks.append(data)

    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return html
    text = "".join(parser.chunks)
    lines = [ln.strip() for ln in text.split("\n")]
    out: list[str] = []
    for ln in lines:
        if ln:
            out.append(ln)
        elif out and out[-1] != "":
            out.append("")
    return "\n".join(out).strip()


def decode_email_part(payload_b64: str) -> str:
    import base64 as _b64

    try:
        return _b64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4)).decode(
            "utf-8", errors="replace"
        )
    except Exception:
        return ""


def extract_from_email_parts(parts: List[dict]) -> Tuple[str, List[bytes]]:
    """Walk a Gmail API message part tree -> (text, pdf_bytes_list)."""
    texts: List[str] = []
    pdfs: List[bytes] = []

    def walk(nodes: List[dict]) -> None:
        for node in nodes:
            mime = (node.get("mimeType") or "").lower()
            body = node.get("body") or {}
            data = body.get("data")
            if node.get("parts"):
                walk(node["parts"])
                continue
            if not data:
                continue
            raw = _b64url_decode(data)
            if mime == "text/plain":
                texts.append(raw.decode("utf-8", errors="replace"))
            elif mime == "text/html":
                texts.append(extract_email_body_html_to_text(raw.decode("utf-8", errors="replace")))
            elif mime == "application/pdf" or node.get("filename", "").lower().endswith(".pdf"):
                pdfs.append(raw)

    walk(parts)
    return "\n".join(t for t in texts if t.strip()), pdfs


def _b64url_decode(data: str) -> bytes:
    import base64 as _b64

    return _b64urlsafe_decode(data)


def _b64urlsafe_decode(data: str) -> bytes:
    import base64 as _b64

    return _b64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
