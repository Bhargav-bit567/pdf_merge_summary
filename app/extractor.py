"""PDF text extraction utilities using pure-Python pypdf (no external binaries)."""
import io
import re

from pypdf import PdfReader, PdfWriter


def _clean_text(raw: str) -> str:
    """Normalize whitespace and control characters while preserving paragraphs."""
    if not raw:
        return ""
    # Replace non-breaking/zero-width and normalize line breaks
    text = raw.replace(" ", " ").replace("​", "")
    # Collapse multiple blank lines into single paragraph breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract full text from an in-memory PDF (bytes) as clean UTF-8 text.

    Raises ValueError if the file is not a valid PDF or contains no extractable text
    (e.g. a scan with no OCR layer).
    """
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except Exception as exc:  # noqa: BLE001 - surface a friendly message
        raise ValueError("The uploaded file does not appear to be a valid PDF.") from exc

    pages = []
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - skip pages that fail to parse
            page_text = ""
        if page_text.strip():
            pages.append(_clean_text(page_text))

    full_text = "\n\n".join(pages).strip()
    if not full_text:
        raise ValueError(
            "No extractable text found. The PDF may be a scanned image "
            "without a text layer (OCR required)."
        )
    return full_text


def count_pages(file_bytes: bytes) -> int:
    """Return the number of pages in a PDF for progress reporting."""
    try:
        return len(PdfReader(io.BytesIO(file_bytes)).pages)
    except Exception:  # noqa: BLE001
        return 0


def merge_pdfs(pdfs: list[bytes], filename: str) -> bytes:
    """Merge a list of PDF byte streams into a single PDF in memory.

    Args:
        pdfs: List of PDF file bytes (in order).
        filename: Base name for the merged output (extension replaced with .pdf).

    Returns:
        Merged PDF as bytes.
    """
    merger = PdfWriter()
    for data in pdfs:
        merger.append(io.BytesIO(data))

    out = io.BytesIO()
    merger.write(out)
    merger.close()
    out.seek(0)
    return out.read()