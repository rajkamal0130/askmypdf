"""FastAPI backend + browser UI.

Step 1: PDFs are uploaded from the browser (/upload), saved to pdfs/ and indexed into FAISS.
Step 2: questions are answered by OpenAI from chunks fetched out of FAISS (/ask).
The HTML chat UI in frontend/html/ is served at /; the Streamlit UI (frontend/streamlit/) calls the same API.
"""
from contextlib import asynccontextmanager
from pathlib import Path

import openai
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import embedder, llm
from backend.config import FRONTEND_DIR, MAX_UPLOAD_MB, PDF_DIR, TOP_K
from backend.ingest import IngestError, list_pdfs, prepare_chunks, store_chunks, sync_folder
from backend.vector_store import VectorStore

store: VectorStore | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global store
    store = VectorStore(embedder.dimension())  # loads embedding model + saved index
    sync_folder(store)  # pick up any PDFs already in the folder
    yield


app = FastAPI(title="PageCite API", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str
    top_k: int = TOP_K


def _retrieve(question: str, top_k: int) -> list[dict]:
    if not question.strip():
        raise HTTPException(400, "Question is empty")
    return store.search(embedder.embed([question]), top_k)


def _public(chunks: list[dict]) -> list[dict]:
    return [
        {"text": c["text"], "source": c["source"], "page": c["page"], "score": round(c["score"], 4)}
        for c in chunks
    ]


def _pdf_path(name: str) -> Path:
    """Resolve a PDF name inside PDF_DIR, refusing anything that escapes it."""
    path = (PDF_DIR / name).resolve()
    if path.parent != PDF_DIR.resolve():
        raise HTTPException(404, "PDF not found")
    return path


@app.get("/health")
def health():
    return {"status": "ok", "vectors": store.total}


# ---------- Step 1: upload & manage PDFs ----------
@app.get("/pdfs")
def pdfs():
    counts = store.chunk_counts()
    return {
        "folder": str(PDF_DIR),
        "pdfs": [
            {
                "name": p.name,
                "size_kb": round(p.stat().st_size / 1024, 1),
                "indexed": p.name in counts,
                "chunks": counts.get(p.name, 0),
            }
            for p in list_pdfs()
        ],
        "total_vectors": store.total,
    }


@app.post("/upload")
def upload(files: list[UploadFile] = File(...)):
    """Save uploaded PDFs and index them. Each file succeeds or fails on its own."""
    results = []
    for f in files:
        name = Path(f.filename or "").name
        data = f.file.read()

        def fail(reason: str):
            results.append({"file": name or "(unnamed)", "ok": False, "reason": reason})

        if not name.lower().endswith(".pdf"):
            fail("Only PDF files are supported")
            continue
        if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
            fail(f"File is larger than {MAX_UPLOAD_MB} MB")
            continue
        if not data.startswith(b"%PDF"):
            fail("Not a valid PDF file")
            continue

        try:
            chunks = prepare_chunks(name, data)
        except IngestError as e:
            fail(str(e))
            continue

        replaced = _pdf_path(name).exists()
        _pdf_path(name).write_bytes(data)
        store_chunks(store, name, chunks)
        results.append({
            "file": name,
            "ok": True,
            "status": "replaced" if replaced else "added",
            "chunks": len(chunks),
            "pages": max(c["page"] for c in chunks),
        })

    return {"results": results, "total_vectors": store.total}


@app.get("/pdfs/{name}")
def view_pdf(name: str):
    path = _pdf_path(name)
    if not path.is_file():
        raise HTTPException(404, "PDF not found")
    return FileResponse(path, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{path.name}"'})


@app.delete("/pdfs/{name}")
def delete_pdf(name: str):
    path = _pdf_path(name)
    if not path.is_file():
        raise HTTPException(404, "PDF not found")
    path.unlink()
    store.remove_source(path.name)
    return {"status": "deleted", "file": path.name, "total_vectors": store.total}


@app.post("/sync")
def sync():
    """Re-scan the pdfs/ folder (for PDFs copied in by hand)."""
    return sync_folder(store)


# ---------- Step 2: search via vector DB + LLM ----------
@app.post("/query")
def query(req: AskRequest):
    """Retrieval only - the raw chunks FAISS returns."""
    return {"question": req.question, "results": _public(_retrieve(req.question, req.top_k))}


@app.post("/ask")
def ask(req: AskRequest):
    """Retrieve chunks from FAISS, then have the LLM answer from them."""
    chunks = _retrieve(req.question, req.top_k)
    try:
        text = llm.answer(req.question, chunks)
    except openai.AuthenticationError:
        raise HTTPException(401, "LLM auth failed: check OPENAI_API_KEY and restart the backend")
    except openai.RateLimitError:
        raise HTTPException(429, "LLM rate limited or out of quota - try again shortly")
    except openai.APIStatusError as e:
        raise HTTPException(502, f"LLM error ({e.status_code}): {e.message}")
    except openai.APIConnectionError:
        raise HTTPException(503, "Could not reach the LLM API - check the network")
    except openai.OpenAIError:
        # Raised before any request when no API key is configured
        raise HTTPException(401, "LLM auth failed: set OPENAI_API_KEY before starting the backend")
    return {"question": req.question, "answer": text, "sources": _public(chunks)}


@app.delete("/reset")
def reset():
    store.reset()
    return {"status": "index cleared"}


# ---------- Browser UI (mounted last so the API routes above take priority) ----------
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="ui")
