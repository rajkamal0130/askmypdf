"""Load step: read a PDF into one segment per page."""
from io import BytesIO

from pypdf import PdfReader


def load_pdf(data: bytes, source: str) -> list[dict]:
    """Return a list of {"text", "source", "page"} dicts, one per page."""
    reader = PdfReader(BytesIO(data))
    return [
        {"text": page.extract_text() or "", "source": source, "page": i + 1}
        for i, page in enumerate(reader.pages)
    ]
