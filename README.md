# PageCite

Ask questions about your PDFs and get answers that cite the file and page they came from.

PageCite is a small retrieval-augmented generation (RAG) app. It splits your PDFs into chunks and embeds them locally with `sentence-transformers`. The vectors are stored in a FAISS index. When you ask a question, it finds the most relevant chunks and has an OpenAI model answer **only** from them, with citations like `[paddy_schemes.pdf, p. 4]`.

## How it works

```
pdfs/*.pdf ─► load (pypdf) ─► split (800 chars, 100 overlap) ─► embed (all-MiniLM-L6-v2) ─► FAISS index (data/)

question ─► embed ─► FAISS top-k search ─► OpenAI LLM ─► answer with [file, p. N] citations
```

- **Backend**: FastAPI (`backend/`). Indexes the `pdfs/` folder and answers questions.
- **Frontend**: Streamlit (`frontend/app.py`). Has two screens: *1 · PDFs* to view and sync files, and *2 · Ask* to ask questions.

## Project structure

```
askmypdf/
├── README.md
├── .gitignore
└── pagecite/
    ├── backend/
    │   ├── main.py          # FastAPI app and endpoints
    │   ├── config.py        # Paths, chunk size, top-k, model names
    │   ├── ingest.py        # Mirrors pdfs/ into the index (add / update / remove)
    │   ├── loader.py        # PDF → one text segment per page
    │   ├── splitter.py      # Recursive text splitter with overlap
    │   ├── embedder.py      # Local sentence-transformers embeddings
    │   ├── vector_store.py  # FAISS index + metadata, saved to disk
    │   └── llm.py           # OpenAI call with the grounding prompt
    ├── frontend/
    │   └── app.py           # Streamlit UI
    ├── pdfs/                # Put your PDFs here (git-ignored)
    ├── data/                # Generated FAISS index (git-ignored)
    └── requirements.txt
```

## Requirements

- Python 3.10 or newer
- An OpenAI API key

The first run downloads the embedding model (about 90 MB), so it needs an internet connection.

## Setup

All commands below are run from the `pagecite/` folder.

```bash
# 0. Get the code
git clone https://github.com/rajkamal0130/askmypdf.git
cd askmypdf/pagecite

# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your OpenAI API key
export OPENAI_API_KEY="sk-..."     # Windows (PowerShell): $env:OPENAI_API_KEY="sk-..."
```

Never commit your API key. `.env` is already listed in `.gitignore`.

## Running

Start the backend and frontend in two terminals. Run both from the `pagecite/` folder with the virtual environment active.

**Terminal 1: backend**

```bash
export OPENAI_API_KEY="sk-..."
uvicorn backend.main:app --port 8000
```

**Terminal 2: frontend**

```bash
streamlit run frontend/app.py
```

Then open the URL that Streamlit prints (usually http://localhost:8501).

## Using the app

1. Copy PDF files into the `pagecite/pdfs/` folder.
2. In the app, go to **1 · PDFs** and click **Sync folder → vector DB**.
   - New PDFs are indexed. Changed PDFs are re-indexed and deleted PDFs are removed from the index.
   - The backend also syncs once when it starts.
3. Go to **2 · Ask** and type a question. The answer cites its sources, and you can see the chunks it used.

Scanned PDFs that contain only images have no text to extract, so they are reported as failed during sync.

## Configuration

| Setting | Where | Default |
|---|---|---|
| `OPENAI_API_KEY` | environment variable | *(required)* |
| `LLM_MODEL` | environment variable | `gpt-5.5` |
| `API_URL` (frontend → backend) | environment variable | `http://localhost:8000` |
| `EMBED_MODEL` | `backend/config.py` | `all-MiniLM-L6-v2` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `backend/config.py` | `800` / `100` |
| `TOP_K` (chunks per question) | `backend/config.py` | `5` |

If you change `EMBED_MODEL`, `CHUNK_SIZE` or `CHUNK_OVERLAP`, rebuild the index. To do that, delete `pagecite/data/faiss_index/` or call `DELETE /reset`, then sync again.

## API endpoints

Interactive docs are at http://localhost:8000/docs while the backend is running.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Status and number of stored vectors |
| `GET` | `/pdfs` | Lists the PDFs in `pdfs/` and shows whether each is indexed |
| `GET` | `/pdfs/{name}` | Serves a PDF for viewing |
| `POST` | `/sync` | Syncs the `pdfs/` folder into the index |
| `POST` | `/query` | Retrieval only: returns the top matching chunks |
| `POST` | `/ask` | Retrieves chunks and returns an LLM answer with sources |
| `DELETE` | `/reset` | Clears the whole index |

Example:

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What subsidies are available for paddy farmers?", "top_k": 5}'
```

## Troubleshooting

| Problem | Fix |
|---|---|
| "Backend not reachable" in the app | Start the backend with `uvicorn backend.main:app --port 8000`. |
| `401 LLM auth failed` | Set `OPENAI_API_KEY` in the backend's terminal, then restart the backend. |
| `429 rate limited` | Your OpenAI quota or rate limit was hit. Wait and try again. |
| A PDF shows as failed during sync | The PDF is encrypted, corrupt or scanned (no text layer). |
| Answers say nothing was found | Check that the PDF shows as indexed on the *1 · PDFs* screen. |
