// PageCite browser UI: upload PDFs (sidebar) and chat with them (main area).
// Talks to the FastAPI backend on the same origin.

const $ = (id) => document.getElementById(id);
const els = {
  sidebar: $("sidebar"), scrim: $("scrim"), menuBtn: $("menuBtn"),
  newChat: $("newChat"), docCount: $("docCount"), docList: $("docList"),
  dropzone: $("dropzone"), fileInput: $("fileInput"), dzTitle: $("dzTitle"), dzSub: $("dzSub"),
  status: $("status"), statusText: $("statusText"),
  chat: $("chat"), welcome: $("welcome"), messages: $("messages"),
  composer: $("composer"), question: $("question"), sendBtn: $("sendBtn"),
  toasts: $("toasts"),
};

const ICONS = {
  spark: '<svg viewBox="0 0 24 24"><path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/></svg>',
  file: '<svg viewBox="0 0 24 24"><path d="M7 4h7l4 4v12H7z"/><path d="M14 4v4h4"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12"/></svg>',
  ok: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16 9.5"/></svg>',
  err: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>',
};

let docs = [];
let asking = false;

// ---------- helpers ----------
async function api(method, path, body) {
  const opts = { method };
  if (body instanceof FormData) opts.body = body;
  else if (body) { opts.body = JSON.stringify(body); opts.headers = { "Content-Type": "application/json" }; }
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new Error("Can't reach the backend. Is `uvicorn backend.main:app` running?");
  }
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON error */ }
  if (!res.ok) {
    const detail = data && data.detail;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${res.status})`);
  }
  return data;
}

function el(tag, cls, html) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
}

function pdfUrl(name, page) {
  return `/pdfs/${encodeURIComponent(name)}${page ? `#page=${page}` : ""}`;
}

function renderMarkdown(text) {
  if (window.marked && window.DOMPurify) {
    return DOMPurify.sanitize(marked.parse(text, { gfm: true, breaks: true }));
  }
  const n = document.createElement("div");
  n.textContent = text;
  return n.innerHTML.replace(/\n/g, "<br>");
}

function plural(n, word) { return `${n} ${word}${n === 1 ? "" : "s"}`; }

function toast(kind, title, body) {
  const t = el("div", `toast ${kind === "err" ? "err" : ""}`);
  t.setAttribute("role", kind === "err" ? "alert" : "status");
  t.innerHTML = `<span class="t-icon">${kind === "err" ? ICONS.err : ICONS.ok}</span><div><div class="t-title"></div><div class="t-body"></div></div>`;
  t.querySelector(".t-title").textContent = title;
  t.querySelector(".t-body").textContent = body;
  els.toasts.appendChild(t);
  setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 300); }, kind === "err" ? 8000 : 5000);
}

// ---------- status + documents ----------
async function refreshStatus() {
  try {
    const h = await api("GET", "/health");
    els.status.className = "status ok";
    els.statusText.textContent = h.vectors ? `Workspace ready · ${plural(h.vectors, "chunk")} indexed` : "Workspace ready";
  } catch {
    els.status.className = "status err";
    els.statusText.textContent = "Backend offline";
  }
}

async function loadDocs(highlight = []) {
  try {
    const data = await api("GET", "/pdfs");
    docs = data.pdfs;
  } catch (e) {
    els.docCount.textContent = "Couldn't load documents";
    return;
  }
  els.docCount.textContent = `${plural(docs.length, "file")} added`;
  els.docList.innerHTML = "";
  for (const d of docs) {
    const li = el("li", `doc${highlight.includes(d.name) ? " fresh" : ""}`);
    li.innerHTML = `
      <span class="doc-badge">PDF</span>
      <div class="doc-main">
        <a class="doc-name" target="_blank" rel="noopener"></a>
        <div class="doc-meta"></div>
      </div>
      <button class="doc-del" type="button">${ICONS.trash}</button>`;
    const a = li.querySelector(".doc-name");
    a.textContent = d.name;
    a.title = `Open ${d.name}`;
    a.href = pdfUrl(d.name);
    li.querySelector(".doc-meta").textContent = d.indexed
      ? `${plural(d.chunks, "chunk")} · ${d.size_kb} KB`
      : "Not indexed (no text?)";
    const del = li.querySelector(".doc-del");
    del.setAttribute("aria-label", `Remove ${d.name}`);
    del.title = "Remove";
    del.addEventListener("click", () => removeDoc(d.name));
    els.docList.appendChild(li);
  }
}

async function removeDoc(name) {
  if (!confirm(`Remove "${name}" from your knowledge base?`)) return;
  try {
    await api("DELETE", `/pdfs/${encodeURIComponent(name)}`);
    toast("ok", "Document removed", `${name} was deleted and removed from search.`);
  } catch (e) {
    toast("err", "Couldn't remove document", e.message);
  }
  loadDocs();
  refreshStatus();
}

// ---------- upload ----------
async function uploadFiles(fileList) {
  const files = [...fileList];
  if (!files.length) return;

  const pdfs = files.filter((f) => f.name.toLowerCase().endsWith(".pdf"));
  for (const f of files.filter((f) => !pdfs.includes(f))) {
    toast("err", "Upload failed", `${f.name}: only PDF files are supported.`);
  }
  if (!pdfs.length) return;

  const form = new FormData();
  pdfs.forEach((f) => form.append("files", f));

  els.dropzone.classList.add("busy");
  els.dzTitle.textContent = "Uploading & indexing…";
  els.dzSub.textContent = pdfs.length === 1 ? pdfs[0].name : `${pdfs.length} files`;

  try {
    const res = await api("POST", "/upload", form);
    const ok = res.results.filter((r) => r.ok);
    for (const r of res.results.filter((r) => !r.ok)) {
      toast("err", "Upload failed", `${r.file}: ${r.reason}`);
    }
    if (ok.length === 1) {
      const r = ok[0];
      toast("ok", r.status === "replaced" ? "Document updated" : "Upload successful",
        `${r.file} · ${plural(r.pages, "page")}, ${plural(r.chunks, "chunk")} indexed. You can now ask questions about it.`);
    } else if (ok.length > 1) {
      toast("ok", "Upload successful",
        `${plural(ok.length, "document")} indexed: ${ok.map((r) => r.file).join(", ")}. You can now ask questions about them.`);
    }
    await loadDocs(ok.map((r) => r.file));
  } catch (e) {
    toast("err", "Upload failed", e.message);
  } finally {
    els.dropzone.classList.remove("busy");
    els.dzTitle.textContent = "Add PDF documents";
    els.dzSub.textContent = "Drop PDFs or browse";
    els.fileInput.value = "";
    refreshStatus();
  }
}

els.fileInput.addEventListener("change", () => uploadFiles(els.fileInput.files));
els.dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); els.fileInput.click(); }
});
["dragenter", "dragover"].forEach((ev) => els.dropzone.addEventListener(ev, (e) => {
  e.preventDefault(); els.dropzone.classList.add("drag");
}));
["dragleave", "drop"].forEach((ev) => els.dropzone.addEventListener(ev, (e) => {
  e.preventDefault(); els.dropzone.classList.remove("drag");
}));
els.dropzone.addEventListener("drop", (e) => uploadFiles(e.dataTransfer.files));
// Dropping a file anywhere else shouldn't navigate away from the app
["dragover", "drop"].forEach((ev) => window.addEventListener(ev, (e) => e.preventDefault()));

// ---------- chat ----------
function showChat() { els.welcome.hidden = true; }

function scrollDown() { els.chat.scrollTop = els.chat.scrollHeight; }

function addUserMessage(text) {
  const m = el("div", "msg user");
  const b = el("div", "bubble-user");
  b.textContent = text;
  m.appendChild(b);
  els.messages.appendChild(m);
}

function addBotMessage() {
  const m = el("div", "msg bot");
  m.innerHTML = `<span class="avatar">${ICONS.spark}</span><div class="bot-body"><div class="typing" aria-label="Thinking"><i></i><i></i><i></i></div></div>`;
  els.messages.appendChild(m);
  return m.querySelector(".bot-body");
}

function renderSources(body, sources) {
  if (!sources || !sources.length) return;
  const wrap = el("div", "sources");
  wrap.appendChild(el("div", "sources-label", "Sources"));
  const chips = el("div", "chips");
  const seen = new Set();
  for (const s of sources) {
    const key = `${s.source}#${s.page}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const a = el("a", "chip");
    a.href = pdfUrl(s.source, s.page);
    a.target = "_blank";
    a.rel = "noopener";
    a.title = `Open ${s.source} at page ${s.page}`;
    a.innerHTML = `${ICONS.file}<span></span><b></b>`;
    a.querySelector("span").textContent = s.source;
    a.querySelector("b").textContent = `p. ${s.page}`;
    chips.appendChild(a);
  }
  wrap.appendChild(chips);

  const det = el("details", "excerpts");
  det.appendChild(el("summary", "", `Show matching excerpts (${sources.length})`));
  sources.forEach((s, i) => {
    const ex = el("div", "excerpt");
    const head = el("div", "excerpt-head");
    head.textContent = `#${i + 1} · ${s.source} · page ${s.page} · score ${s.score}`;
    ex.appendChild(head);
    ex.appendChild(document.createTextNode(s.text));
    det.appendChild(ex);
  });
  wrap.appendChild(det);
  body.appendChild(wrap);
}

async function ask(question) {
  question = question.trim();
  if (!question || asking) return;
  asking = true;
  updateSend();
  showChat();
  addUserMessage(question);
  const body = addBotMessage();
  scrollDown();

  try {
    if (!docs.length) {
      body.innerHTML = `<div class="answer">You haven't added any documents yet. Upload a PDF using <b>Add PDF documents</b> in the sidebar, then ask again.</div>`;
    } else {
      const res = await api("POST", "/ask", { question });
      body.innerHTML = "";
      body.appendChild(el("div", "answer", renderMarkdown(res.answer)));
      renderSources(body, res.sources);
    }
  } catch (e) {
    body.innerHTML = "";
    const err = el("div", "answer error");
    err.textContent = e.message;
    body.appendChild(err);
  } finally {
    asking = false;
    updateSend();
    scrollDown();
  }
}

function updateSend() {
  els.sendBtn.disabled = asking || !els.question.value.trim();
}

function autoGrow() {
  els.question.style.height = "auto";
  els.question.style.height = `${els.question.scrollHeight}px`;
}

els.composer.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = els.question.value;
  if (asking || !q.trim()) return;
  els.question.value = "";
  autoGrow();
  ask(q);
});
els.question.addEventListener("input", () => { autoGrow(); updateSend(); });
els.question.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    els.composer.requestSubmit();
  }
});

document.querySelectorAll(".suggestions button").forEach((b) =>
  b.addEventListener("click", () => ask(b.dataset.prompt)));

els.newChat.addEventListener("click", () => {
  if (asking) return;
  els.messages.innerHTML = "";
  els.welcome.hidden = false;
  els.question.value = "";
  autoGrow();
  updateSend();
  closeSidebar();
  els.question.focus();
});

// ---------- mobile sidebar ----------
function closeSidebar() { els.sidebar.classList.remove("open"); els.scrim.hidden = true; }
els.menuBtn.addEventListener("click", () => { els.sidebar.classList.add("open"); els.scrim.hidden = false; });
els.scrim.addEventListener("click", closeSidebar);

// ---------- start ----------
loadDocs();
refreshStatus();
els.question.focus();
