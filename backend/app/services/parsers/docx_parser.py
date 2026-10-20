import io

from docx import Document

from app.services.parsers.text_cleaner import clean_text


def validate_docx(file_bytes: bytes) -> None:
    """Open the package once so corrupt/encrypted DOCX files fail early."""
    Document(io.BytesIO(file_bytes))


def parse_docx_links(file_bytes: bytes) -> list[dict[str, str]]:
    """Extract hyperlink targets that are not always present in paragraph text."""
    doc = Document(io.BytesIO(file_bytes))
    links: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_links(paragraphs) -> None:
        for paragraph in paragraphs:
            for hyperlink in paragraph.hyperlinks:
                url = str(hyperlink.address or "").strip()
                key = url.rstrip("/").casefold()
                if not url or key in seen:
                    continue
                seen.add(key)
                links.append(
                    {
                        "label": clean_text(hyperlink.text),
                        "url": url,
                    }
                )

    add_links(doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                add_links(cell.paragraphs)
    for section in doc.sections:
        add_links(section.header.paragraphs)
        add_links(section.footer.paragraphs)
    return links


def parse_docx_blocks(file_bytes: bytes) -> list[dict]:
    """Extract paragraphs, tables, headers and footers as ordered text blocks."""
    doc = Document(io.BytesIO(file_bytes))
    blocks: list[dict] = []

    def add_paragraphs(paragraphs) -> None:
        for paragraph in paragraphs:
            text = clean_text(paragraph.text)
            if text:
                blocks.append({"type": "paragraph", "text": text})

    add_paragraphs(doc.paragraphs)

    for table_index, table in enumerate(doc.tables, start=1):
        rows: list[str] = []
        for row in table.rows:
            cells = [clean_text(cell.text) for cell in row.cells]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            blocks.append(
                {
                    "type": "table",
                    "index": table_index,
                    "text": "\n".join(rows),
                }
            )

    # Headers and footers are part of the resume content. Different sections can
    # share the same header object, so only emit each object once.
    seen_parts: set[int] = set()
    for section in doc.sections:
        for part in (
            section.header,
            section.first_page_header,
            section.even_page_header,
            section.footer,
            section.first_page_footer,
            section.even_page_footer,
        ):
            marker = id(part)
            if marker in seen_parts:
                continue
            seen_parts.add(marker)
            if not part.is_linked_to_previous:
                add_paragraphs(part.paragraphs)
                for table in part.tables:
                    for row in table.rows:
                        cells = [clean_text(cell.text) for cell in row.cells]
                        if any(cells):
                            blocks.append(
                                {"type": "table", "text": " | ".join(cells)}
                            )

    return blocks


def parse_docx(file_bytes: bytes) -> str:
    """Extract text (paragraphs, tables, headers and footers) from a DOCX file."""
    blocks = parse_docx_blocks(file_bytes)
    return clean_text("\n".join(block["text"] for block in blocks))
