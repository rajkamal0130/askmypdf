"""Streamlit frontend for PageCite.

Talks to the same FastAPI backend as the HTML UI. Start the backend first:
    uvicorn backend.main:app --port 8000
then, from the pagecite/ folder:
    streamlit run frontend/streamlit/app.py
"""
import os

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")

st.set_page_config(page_title="PageCite", page_icon="📄", layout="wide")


def api(method: str, path: str, **kw):
    """Call the backend; show the error and stop the script run on failure."""
    try:
        r = requests.request(method, f"{API_URL}{path}", timeout=kw.pop("timeout", 30), **kw)
    except requests.ConnectionError:
        st.error(f"Backend not reachable at {API_URL}. Start it with `uvicorn backend.main:app --port 8000`.")
        st.stop()
    if not r.ok:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        st.error(f"{r.status_code}: {detail}")
        st.stop()
    return r.json()


def pdf_url(name: str, page: int | None = None) -> str:
    url = f"{API_URL}/pdfs/{requests.utils.quote(name)}"
    return f"{url}#page={page}" if page else url


# ---------- Sidebar: upload & manage PDFs ----------
with st.sidebar:
    st.title("📄 PageCite")
    st.caption("Answers from your PDFs, with page citations.")

    st.subheader("Documents")
    with st.form("upload", clear_on_submit=True):
        files = st.file_uploader("Add PDF documents", type="pdf", accept_multiple_files=True)
        submitted = st.form_submit_button("Upload & index", type="primary", use_container_width=True)
    if submitted and files:
        with st.spinner(f"Indexing {len(files)} file(s)…"):
            rep = api(
                "POST", "/upload", timeout=1800,
                files=[("files", (f.name, f.getvalue(), "application/pdf")) for f in files],
            )
        for r in rep["results"]:
            if r["ok"]:
                st.success(f"{r['file']}: {r['status']} · {r['pages']} pages · {r['chunks']} chunks")
            else:
                st.error(f"{r['file']}: {r['reason']}")

    data = api("GET", "/pdfs")
    if not data["pdfs"]:
        st.info("No documents yet. Upload a PDF to get started.")
    for p in data["pdfs"]:
        c1, c2 = st.columns([5, 1], vertical_alignment="center")
        status = f"{p['chunks']} chunks" if p["indexed"] else "not indexed"
        c1.markdown(f"[{p['name']}]({pdf_url(p['name'])})  \n:gray[{p['size_kb']} KB · {status}]")
        if c2.button("🗑", key=f"del-{p['name']}", help=f"Remove {p['name']}"):
            api("DELETE", f"/pdfs/{requests.utils.quote(p['name'])}")
            st.rerun()

    st.divider()
    st.metric("Vectors in FAISS", data["total_vectors"])
    if st.button("🔄 Sync pdfs/ folder", use_container_width=True,
                 help="Pick up PDFs copied into the folder by hand"):
        with st.spinner("Syncing…"):
            rep = api("POST", "/sync", timeout=1800)
        for f in rep.get("failed", []):
            st.error(f"{f['file']}: {f['reason']}")
        st.rerun()

    st.subheader("Settings")
    top_k = st.slider("Chunks to retrieve (top-k)", 1, 20, 5)
    retrieval_only = st.toggle("Retrieval only (skip LLM)", value=False)
    if st.button("New chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()


# ---------- Main: chat ----------
if "messages" not in st.session_state:
    st.session_state.messages = []


def render_sources(sources: list[dict]):
    if not sources:
        st.caption("No matching chunks found. Upload some PDFs first.")
        return
    seen = []
    for s in sources:
        key = (s["source"], s["page"])
        if key not in seen:
            seen.append(key)
    st.markdown("**Sources:** " + " · ".join(f"[{src}, p. {pg}]({pdf_url(src, pg)})" for src, pg in seen))
    with st.expander("Show matching excerpts"):
        for i, s in enumerate(sources, 1):
            st.markdown(f"**#{i} · {s['source']} · page {s['page']}** · score `{s['score']}`")
            st.write(s["text"])
            if i < len(sources):
                st.divider()


if not st.session_state.messages:
    st.header("Ask your PDFs")
    st.caption("Answers come only from your uploaded documents and cite the file and page.")

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        if m.get("content"):
            st.markdown(m["content"])
        if m["role"] == "assistant":
            render_sources(m.get("sources", []))

if question := st.chat_input("Ask a question about your documents…"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        payload = {"question": question, "top_k": top_k}
        if retrieval_only:
            with st.spinner("Searching vector DB…"):
                res = api("POST", "/query", json=payload)
            msg = {"role": "assistant", "content": "", "sources": res["results"]}
        else:
            with st.spinner("Searching vector DB and asking the LLM…"):
                res = api("POST", "/ask", json=payload, timeout=300)
            msg = {"role": "assistant", "content": res["answer"], "sources": res["sources"]}
            st.markdown(msg["content"])
        render_sources(msg["sources"])
    st.session_state.messages.append(msg)
