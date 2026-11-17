"""Pipeline 1: mirror the pdfs/ folder into FAISS (load -> split -> embed -> store)."""
import hashlib

from backend import embedder
from backend.config import PDF_DIR
from backend.loader import load_pdf
from backend.splitter import split_segments
from backend.vector_store import VectorStore


def list_pdfs():
    return sorted(
        (p for p in PDF_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"),
        key=lambda p: p.name.lower(),
    )


def sync_folder(store: VectorStore) -> dict:
    """Index new/changed PDFs and drop PDFs that were removed from the folder."""
    on_disk = {p.name: p for p in list_pdfs()}
    indexed = store.file_hashes()
    report = {"added": [], "updated": [], "removed": [], "unchanged": [], "failed": []}

    for name in sorted(set(indexed) - set(on_disk)):
        store.remove_source(name)
        report["removed"].append(name)

    for name, path in on_disk.items():
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if indexed.get(name) == file_hash:
            report["unchanged"].append(name)
            continue

        is_update = name in indexed
        try:
            chunks = split_segments(load_pdf(path))
        except Exception as e:  # corrupt / encrypted PDF
            report["failed"].append({"file": name, "reason": str(e)})
            continue
        if not chunks:
            report["failed"].append({"file": name, "reason": "No extractable text (scanned PDF?)"})
            continue

        if is_update:
            store.remove_source(name)
        for c in chunks:
            c["file_hash"] = file_hash
        store.add(embedder.embed([c["text"] for c in chunks]), chunks)
        report["updated" if is_update else "added"].append(name)

    report["total_vectors"] = store.total
    return report
