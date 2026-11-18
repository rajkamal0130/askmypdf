"""Pipeline 1: PDFs -> FAISS (load -> split -> embed -> store).

PDFs arrive two ways: uploaded from the browser (/upload) or copied into the
pdfs/ folder by hand (picked up by sync_folder at startup or via /sync).
"""
import hashlib

from backend import embedder
from backend.config import PDF_DIR
from backend.loader import load_pdf
from backend.splitter import split_segments
from backend.vector_store import VectorStore


class IngestError(ValueError):
    """The PDF can't be indexed (corrupt, encrypted or no text layer)."""


def list_pdfs():
    return sorted(
        (p for p in PDF_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"),
        key=lambda p: p.name.lower(),
    )


def prepare_chunks(name: str, data: bytes) -> list[dict]:
    """Load + split a PDF. Raises IngestError if it has no usable text."""
    try:
        chunks = split_segments(load_pdf(data, name))
    except Exception as e:  # corrupt / encrypted PDF
        raise IngestError(f"Could not read PDF: {e}") from e
    if not chunks:
        raise IngestError("No extractable text (scanned PDF?)")
    file_hash = hashlib.sha256(data).hexdigest()
    for c in chunks:
        c["file_hash"] = file_hash
    return chunks


def store_chunks(store: VectorStore, name: str, chunks: list[dict]) -> None:
    """Embed chunks and replace any previous version of this PDF in the index."""
    vectors = embedder.embed([c["text"] for c in chunks])
    store.remove_source(name)
    store.add(vectors, chunks)


def sync_folder(store: VectorStore) -> dict:
    """Index new/changed PDFs and drop PDFs that were removed from the folder."""
    on_disk = {p.name: p for p in list_pdfs()}
    indexed = store.file_hashes()
    report = {"added": [], "updated": [], "removed": [], "unchanged": [], "failed": []}

    for name in sorted(set(indexed) - set(on_disk)):
        store.remove_source(name)
        report["removed"].append(name)

    for name, path in on_disk.items():
        data = path.read_bytes()
        if indexed.get(name) == hashlib.sha256(data).hexdigest():
            report["unchanged"].append(name)
            continue
        try:
            store_chunks(store, name, prepare_chunks(name, data))
        except IngestError as e:
            report["failed"].append({"file": name, "reason": str(e)})
            continue
        report["updated" if name in indexed else "added"].append(name)

    report["total_vectors"] = store.total
    return report
