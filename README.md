# PageCite

Ask questions about your PDFs and get answers that cite the file and page they came from.

PageCite is a small retrieval-augmented generation (RAG) app. It splits your PDFs into chunks and embeds them locally with `sentence-transformers`. The vectors are stored in a FAISS index. When you ask a question, it finds the most relevant chunks and has an OpenAI model answer **only** from them, with citations like `[paddy_schemes.pdf, p. 4]`.

## How it works

```
upload (browser) ─► pdfs/*.pdf ─► load (pypdf) ─► split (800 chars, 100 overlap) ─► embed (all-MiniLM-L6-v2) ─► FAISS index (data/)

question ─► embed ─► FAISS top-k search ─► OpenAI LLM ─► answer with [file, p. N] citations
```

- **Backend**: FastAPI (`backend/`). Indexes the `pdfs/` folder and answers questions.
- **Frontend**: two interchangeable UIs talking to the same backend API. Use whichever you prefer:
  - **HTML** (`frontend/html/`, plain HTML/CSS/JS): served by the backend at http://localhost:8000.
  - **Streamlit** (`frontend/streamlit/app.py`): runs separately at http://localhost:8501.

## Project structure

```
askmypdf/
├── README.md
├── .gitignore
└── pagecite/
    ├── backend/
    │   ├── main.py          # FastAPI app, endpoints, serves the UI
    │   ├── config.py        # Paths, chunk size, top-k, model names
    │   ├── ingest.py        # Indexes uploaded PDFs; syncs the pdfs/ folder
    │   ├── loader.py        # PDF → one text segment per page
    │   ├── splitter.py      # Recursive text splitter with overlap
    │   ├── embedder.py      # Local sentence-transformers embeddings
    │   ├── vector_store.py  # FAISS index + metadata, saved to disk
    │   └── llm.py           # OpenAI call with the grounding prompt
    ├── frontend/
    │   ├── html/            # HTML UI, served by the backend at /
    │   │   ├── index.html   # Chat UI: sidebar upload + chat
    │   │   ├── styles.css
    │   │   └── app.js
    │   └── streamlit/
    │       └── app.py       # Streamlit UI (same features, separate process)
    ├── pdfs/                # Uploaded PDFs are saved here (git-ignored)
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

PageCite has one backend and two UIs. Always start the backend first, then use either UI, or both at once. They share the same documents and index.

| UI | Folder | URL | Extra command? |
|---|---|---|---|
| HTML | `frontend/html/` | http://localhost:8000 | No, the backend serves it |
| Streamlit | `frontend/streamlit/` | http://localhost:8501 | Yes, `streamlit run …` |

### Step 1: Start the backend (always required)

```bash
cd askmypdf/pagecite
source .venv/bin/activate          # Windows: .venv\Scripts\activate
export OPENAI_API_KEY="sk-..."     # Windows (PowerShell): $env:OPENAI_API_KEY="sk-..."
uvicorn backend.main:app --port 8000
```

Wait until you see `Application startup complete`. The first start downloads the embedding model, so it takes longer.

### Step 2a: HTML UI

Open **http://localhost:8000** in your browser. You don't need to run anything else.

### Step 2b: Streamlit UI

Keep the backend running. Open a **second terminal** and run:

```bash
cd askmypdf/pagecite
source .venv/bin/activate
streamlit run frontend/streamlit/app.py
```

It opens at **http://localhost:8501**. If the backend runs somewhere other than `http://localhost:8000`, set `API_URL` before starting Streamlit, for example `export API_URL="http://127.0.0.1:9000"`.

### Stopping

Press `Ctrl+C` in each terminal.

## Using the app

Both UIs work the same way. The steps below describe the HTML UI; in Streamlit, upload from the sidebar, use the 🗑 button to remove a document, and set top-k or *Retrieval only* under **Settings**.

1. In the sidebar, click **Add PDF documents** (or drag PDFs onto it). You can pick several at once.
   - Each PDF is saved to `pagecite/pdfs/` and indexed. A message confirms the upload and shows how many pages and chunks were indexed.
   - Uploading a file with the same name replaces the old version.
   - Hover over a document and click the bin icon to remove it.
2. Type a question in the chat box, or click one of the suggestions. The answer cites its sources. Click a source chip to open the PDF at that page, or expand **Show matching excerpts** to see the exact text used.
3. **New chat** clears the conversation. Your documents stay.

You can still copy PDFs straight into `pagecite/pdfs/`. They are picked up when the backend starts, or when you call `POST /sync`.

Scanned PDFs that contain only images have no text to extract, so the upload is rejected with a message saying so.

## Configuration

| Setting | Where | Default |
|---|---|---|
| `OPENAI_API_KEY` | environment variable | *(required)* |
| `LLM_MODEL` | environment variable | `gpt-5.5` |
| `EMBED_MODEL` | `backend/config.py` | `all-MiniLM-L6-v2` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `backend/config.py` | `800` / `100` |
| `MAX_UPLOAD_MB` (per file) | `backend/config.py` | `50` |
| `TOP_K` (chunks per question) | `backend/config.py` | `5` |

If you change `EMBED_MODEL`, `CHUNK_SIZE` or `CHUNK_OVERLAP`, rebuild the index. To do that, delete `pagecite/data/faiss_index/` or call `DELETE /reset`, then upload your PDFs again or call `POST /sync`.

## API endpoints

Interactive docs are at http://localhost:8000/docs while the backend is running.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Status and number of stored vectors |
| `GET` | `/pdfs` | Lists the PDFs in `pdfs/` and shows whether each is indexed |
| `POST` | `/upload` | Uploads one or more PDFs (multipart field `files`) and indexes them |
| `GET` | `/pdfs/{name}` | Serves a PDF for viewing |
| `DELETE` | `/pdfs/{name}` | Deletes a PDF and removes it from the index |
| `POST` | `/sync` | Syncs the `pdfs/` folder into the index (for files copied in by hand) |
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
| Streamlit says "Backend not reachable" | Start the backend first, or set `API_URL` to where it runs. |
| Page doesn't load, or "Backend offline" in the sidebar | Start the backend with `uvicorn backend.main:app --port 8000`. |
| `401 LLM auth failed` | Set `OPENAI_API_KEY` in the backend's terminal, then restart the backend. |
| `429 rate limited` | Your OpenAI quota or rate limit was hit. Wait and try again. |
| An upload fails | The PDF is encrypted, corrupt or scanned (no text layer), or larger than 50 MB. |
| Answers say nothing was found | Check that the PDF is listed in the sidebar with a chunk count. |
