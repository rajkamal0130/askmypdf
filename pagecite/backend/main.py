"""FastAPI backend.

Step 1: PDFs dropped into pdfs/ are listed, viewable and indexed into FAISS (/pdfs, /sync).
Step 2: questions are answered by OpenAI from chunks fetched out of FAISS (/ask).
"""
from contextlib import asynccontextmanager

import openai
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend import embedder, llm
from backend.config import PDF_DIR, TOP_K
from backend.ingest import list_pdfs, sync_folder
from backend.vector_store import VectorStore

store: VectorStore | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global store
    store = VectorStore(embedder.dimension())  # loads embedding model + saved index
    sync_folder(store)  # pick up any PDFs already in the folder
    yield


app = FastAPI(title="PDF-Vector RAG API", lifespan=lifespan)


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


@app.get("/health")
def health():
    return {"status": "ok", "vectors": store.total}


# ---------- Step 1: PDFs in the project folder ----------
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


@app.get("/pdfs/{name}")
def view_pdf(name: str):
    path = (PDF_DIR / name).resolve()
    if path.parent != PDF_DIR.resolve() or not path.is_file():
        raise HTTPException(404, "PDF not found")
    return FileResponse(path, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{path.name}"'})


@app.post("/sync")
def sync():
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
