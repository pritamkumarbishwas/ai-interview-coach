from urllib.parse import urlsplit

import fitz  # PyMuPDF

from app.services.parsers.text_cleaner import clean_text

_SAFE_LINK_SCHEMES = {"http", "https", "mailto"}


def _extract_page_links(page, number: int) -> list[dict[str, object]]:
    """Read hyperlink annotations, which are not part of the page text."""
    links: list[dict[str, object]] = []
    seen: set[str] = set()
    for link in page.get_links():
        url = str(link.get("uri") or "").strip()
        if not url or urlsplit(url).scheme.lower() not in _SAFE_LINK_SCHEMES:
            continue
        key = url.rstrip("/").casefold()
        if key in seen:
            continue
        label = ""
        top = 0.0
        rect = link.get("from")
        if rect is not None:
            top = float(rect.y0)
            try:
                label = clean_text(page.get_textbox(rect))
            except Exception:
                label = ""
        seen.add(key)
        links.append(
            {
                "label": label,
                "url": url,
                "page": number,
                "top": round(top, 2),
            }
        )
    return links


def validate_pdf(file_bytes: bytes) -> None:
    """Open the document once so corrupt/encrypted PDFs are rejected early."""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ValueError("PDF is password protected")
        if doc.page_count == 0:
            raise ValueError("PDF contains no pages")
        doc.load_page(0)


def parse_pdf_pages(file_bytes: bytes) -> list[dict]:
    """Extract page text and block text without flattening the document."""
    pages: list[dict] = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ValueError("PDF is password protected")
        for number, page in enumerate(doc, start=1):
            text = clean_text(page.get_text("text"))
            blocks = [
                clean_text(block[4])
                for block in page.get_text("blocks")
                if len(block) >= 5 and block[4].strip()
            ]
            pages.append(
                {
                    "number": number,
                    "text": text,
                    "blocks": blocks,
                    "links": _extract_page_links(page, number),
                    "width": round(float(page.rect.width), 2),
                    "height": round(float(page.rect.height), 2),
                    "method": "text_layer" if text else "none",
                }
            )
    return pages


def parse_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF file using PyMuPDF."""
    return clean_text("\n\n".join(page["text"] for page in parse_pdf_pages(file_bytes)))
