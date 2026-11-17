"""Streamlit frontend for PDF-Vector."""
import os

import requests
import streamlit as st
import streamlit.components.v1 as components

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="PDF-Vector", page_icon="📄", layout="wide")
st.title("📄 PDF-Vector")

page = st.sidebar.radio("Step", ["1 · PDFs", "2 · Ask"])


def api(method: str, path: str, **kw):
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
        st.error(detail)
        st.stop()
    return r.json()


# ---------- Step 1: PDFs placed manually in the project folder ----------
if page.startswith("1"):
    st.header("PDFs in the project folder")
    data = api("GET", "/pdfs")
    st.caption(f"Drop PDF files into **{data['folder']}**, then click *Sync folder*.")

    if st.button("🔄 Sync folder → vector DB", type="primary"):
        with st.spinner("Loading, splitting and embedding new PDFs…"):
            rep = api("POST", "/sync", timeout=1800)
        for key, label in [("added", "Indexed"), ("updated", "Re-indexed"), ("removed", "Removed")]:
            if rep[key]:
                st.success(f"{label}: {', '.join(rep[key])}")
        for f in rep["failed"]:
            st.error(f"{f['file']}: {f['reason']}")
        if not any(rep[k] for k in ("added", "updated", "removed", "failed")):
            st.info("Everything is already up to date.")
        data = api("GET", "/pdfs")

    st.metric("Vectors in FAISS", data["total_vectors"])

    if not data["pdfs"]:
        st.info("No PDFs found yet. Copy some into the folder above.")
    else:
        st.dataframe(
            [
                {"PDF": p["name"], "Size (KB)": p["size_kb"],
                 "Indexed": "✅" if p["indexed"] else "⏳ not yet", "Chunks": p["chunks"]}
                for p in data["pdfs"]
            ],
            use_container_width=True,
            hide_index=True,
        )
        names = [p["name"] for p in data["pdfs"]]
        choice = st.selectbox("Preview a PDF", names)
        if choice:
            url = f"{API_URL}/pdfs/{requests.utils.quote(choice)}"
            st.markdown(f"[Open in new tab]({url})")
            components.iframe(url, height=800)

# ---------- Step 2: Ask - FAISS retrieval + LLM answer ----------
else:
    st.header("Ask your PDFs")
    q = st.text_area("Question", placeholder="e.g. What are the payment terms in the contract?")
    c1, c2 = st.columns([1, 1])
    k = c1.slider("Chunks to retrieve (top-k)", 1, 20, 5)
    retrieval_only = c2.toggle("Retrieval only (skip LLM)", value=False)

    if st.button("Ask", type="primary", disabled=not q.strip()):
        if retrieval_only:
            with st.spinner("Searching vector DB…"):
                res = api("POST", "/query", json={"question": q, "top_k": k})
            sources = res["results"]
        else:
            with st.spinner("Searching vector DB and asking the LLM…"):
                res = api("POST", "/ask", json={"question": q, "top_k": k}, timeout=300)
            st.subheader("Answer")
            st.markdown(res["answer"])
            sources = res["sources"]

        st.subheader("Sources from the vector DB")
        if not sources:
            st.info("No chunks found. Sync some PDFs first (step 1).")
        for i, s in enumerate(sources, 1):
            with st.expander(f"#{i} · {s['source']} · page {s['page']} · score {s['score']}"):
                st.write(s["text"])
