import fitz  # PyMuPDF

from app.services.parsers.text_cleaner import clean_text


def parse_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF file using PyMuPDF."""
    pages: list[str] = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            pages.append(page.get_text())
    return clean_text("\n\n".join(pages))
