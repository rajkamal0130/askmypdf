import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Step 1: drop your PDFs into this folder manually
PDF_DIR = BASE_DIR / "pdfs"

INDEX_DIR = BASE_DIR / "data" / "faiss_index"
INDEX_FILE = INDEX_DIR / "index.faiss"
META_FILE = INDEX_DIR / "metadata.json"

# Embeddings (local, free, 384-dim)
EMBED_MODEL = "all-MiniLM-L6-v2"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
TOP_K = 5

# LLM (OpenAI) - needs OPENAI_API_KEY in the environment
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5.5")

PDF_DIR.mkdir(parents=True, exist_ok=True)
INDEX_DIR.mkdir(parents=True, exist_ok=True)
