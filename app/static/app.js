"use strict";
const $ = (id) => document.getElementById(id);
let documents = [];
let busy = false;
let uploading = false;
let maxUploadMb = 10;
let historyOffset = 0;
const pageSize = 25;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function showError(message) {
  $("error-text").textContent = message;
  $("error-banner").hidden = false;
}
async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.error?.message || `Request failed (${response.status}).`);
  }
  return response.status === 204 ? null : response.json();
}
function updateBusy() {
  $("send-button").disabled = busy || uploading;
  $("clear-history").disabled = busy;
  $("file-input").disabled = uploading;
  $("sample-button").disabled = uploading;
}
function renderDocuments() {
  const list = $("document-list");
  list.replaceChildren();
  const selection = $("document-scope").value;
  $("document-scope").replaceChildren(new Option("All documents", ""));
  if (!documents.length) list.append(element("p", "empty-library", "A home for your handbooks,\nreports, and bright ideas."));
  for (const doc of documents) {
    const row = element("div", "document-item");
    row.append(element("span", "file-icon", doc.name.toLowerCase().endsWith(".pdf") ? "PDF" : "TXT"));
    const info = element("div", "document-info");
    const name = element("div", "document-name", doc.name);
    name.title = doc.name;
    info.append(name, element("div", "document-meta", `${doc.status === "ready" ? `${doc.chunk_count} chunks` : doc.status} · ${(doc.size_bytes / 1024).toFixed(1)} KB`));
    if (doc.warnings.length) info.title = doc.warnings.join("\n");
    const remove = element("button", "delete-document", "×");
    remove.setAttribute("aria-label", `Delete ${doc.name}`);
    remove.title = "Delete document and its cited answers";
    remove.addEventListener("click", async () => {
      if (!confirm(`Delete ${doc.name}? Its chunks, vectors, and answers citing it will be removed.`)) return;
      remove.disabled = true;
      try {
        await api(`/documents/${doc.id}`, {method: "DELETE"});
        await refreshDocuments();
        await loadHistory(true);
      } catch (error) { showError(error.message); remove.disabled = false; }
    });
    row.append(info, remove);
    list.append(row);
    if (doc.status === "ready") $("document-scope").append(new Option(doc.name, doc.id));
  }
  if (documents.some((doc) => doc.id === selection && doc.status === "ready")) $("document-scope").value = selection;
  $("document-count").textContent = documents.length;
  $("ready-count").textContent = `${documents.filter((doc) => doc.status === "ready").length} ready`;
}
async function refreshDocuments() { documents = await api("/documents"); renderDocuments(); }
async function uploadFiles(files) {
  if (uploading) return;
  uploading = true;
  updateBusy();
  let completed = 0;
  try {
    for (const file of files) {
      if (!/\.(pdf|txt)$/i.test(file.name)) throw new Error("Choose a PDF or UTF-8 TXT file.");
      if (file.size > maxUploadMb * 1024 * 1024) throw new Error(`Files must be at most ${maxUploadMb} MB.`);
      $("upload-status").textContent = `Reading and indexing ${file.name}…`;
      const doc = await api(`/documents?filename=${encodeURIComponent(file.name)}`, {
        method: "POST", headers: {"Content-Type": "application/octet-stream"}, body: file,
      });
      completed++;
      if (doc.warnings.length) showError(doc.warnings.join(" "));
    }
    $("upload-status").textContent = `${completed} document${completed === 1 ? "" : "s"} ready to explore.`;
  } catch (error) { showError(error.message); $("upload-status").textContent = "Upload stopped. You can try again."; }
  finally {
    uploading = false;
    $("file-input").value = "";
    updateBusy();
    await refreshDocuments().catch((error) => showError(error.message));
  }
}
function message(role, text) {
  const article = element("article", `message ${role === "You" ? "user-message" : "assistant-message"}`);
  const header = element("div", "message-header");
  header.append(element("span", "avatar", role === "You" ? "Y" : "✳"), element("span", "", role));
  article.append(header, element("div", "message-text", text));
  return article;
}
function renderAnswer(item) {
  const fragment = document.createDocumentFragment();
  fragment.append(message("You", item.question));
  const reply = message("Document Assistant", item.answer);
  reply.querySelector(".message-header").append(element("span", "answer-label", item.mode === "demo" ? "EXTRACTIVE DEMO" : "AI ANSWER"));
  if (item.citations.length) {
    const sources = element("div", "sources");
    for (const citation of item.citations) {
      const detail = element("details", "source");
      const page = citation.page ? ` · page ${citation.page}` : "";
      detail.append(element("summary", "", `${citation.source_id} · ${citation.document_name}${page}`), element("blockquote", "", citation.quote));
      detail.append(element("small", "", `Chunk ${citation.chunk_id} · Similarity ${citation.similarity.toFixed(2)} · Uploaded ${new Date(citation.uploaded_at).toLocaleDateString()}`));
      sources.append(detail);
    }
    reply.append(sources);
  }
  fragment.append(reply);
  return fragment;
}
async function loadHistory(reset = false) {
  const items = await api(`/history?limit=${pageSize}&offset=${reset ? 0 : historyOffset}`);
  if (reset) {
    $("conversation").querySelectorAll(".message,.history-button").forEach((node) => node.remove());
    historyOffset = 0;
  }
  $("conversation").querySelector(".history-button")?.remove();
  historyOffset += items.length;
  const fragment = document.createDocumentFragment();
  for (const item of items.reverse()) fragment.append(renderAnswer(item));
  $("conversation").prepend(fragment);
  $("welcome").hidden = historyOffset > 0;
  if (items.length === pageSize) {
    const older = element("button", "history-button", "Load older conversations");
    older.addEventListener("click", () => loadHistory().catch((error) => showError(error.message)));
    $("conversation").prepend(older);
  }
  if (reset) scrollToEnd();
}
function scrollToEnd() { $("conversation").scrollTop = $("conversation").scrollHeight; }
$("question-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = $("question").value.trim();
  if (!question || busy || uploading) return;
  if (!documents.some((doc) => doc.status === "ready")) {
    showError("Upload a document or try the samples before asking a question."); return;
  }
  busy = true;
  updateBusy();
  $("welcome").hidden = true;
  const pendingQuestion = message("You", question);
  const pending = message("Document Assistant", "Finding the relevant passages…");
  pending.querySelector(".message-text").classList.add("loading-text");
  $("conversation").append(pendingQuestion, pending);
  scrollToEnd();
  try {
    const scope = $("document-scope").value;
    const body = {question, ...(scope ? {document_ids: [scope]} : {})};
    const answer = await api("/questions", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    pendingQuestion.remove(); pending.remove();
    $("conversation").append(renderAnswer(answer));
    historyOffset++;
    if ($("question").value.trim() === question) $("question").value = "";
  } catch (error) { pendingQuestion.remove(); pending.remove(); showError(error.message); }
  finally { busy = false; updateBusy(); scrollToEnd(); $("question").focus(); }
});
$("question").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); $("question-form").requestSubmit(); }
});
$("file-input").addEventListener("change", (event) => uploadFiles([...event.target.files]));
$("drop-zone").addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") { event.preventDefault(); $("file-input").click(); }
});
for (const name of ["dragenter", "dragover"]) $("drop-zone").addEventListener(name, (event) => { event.preventDefault(); $("drop-zone").classList.add("dragover"); });
for (const name of ["dragleave", "drop"]) $("drop-zone").addEventListener(name, (event) => { event.preventDefault(); $("drop-zone").classList.remove("dragover"); });
$("drop-zone").addEventListener("drop", (event) => uploadFiles([...event.dataTransfer.files]));
$("sample-button").addEventListener("click", async () => {
  if (uploading) return;
  $("sample-button").disabled = true;
  try {
    const files = [];
    for (const name of ["atlas-handbook.txt", "aurora-project.txt"]) {
      if (documents.some((doc) => doc.name === name && doc.status === "ready")) continue;
      const response = await fetch(`/static/examples/${name}`);
      if (!response.ok) throw new Error("Sample documents are unavailable.");
      files.push(new File([await response.blob()], name, {type: "text/plain"}));
    }
    if (files.length) await uploadFiles(files);
    else $("upload-status").textContent = "Sample documents are already in your library.";
  } catch (error) { showError(error.message); }
  finally { updateBusy(); }
});
document.querySelectorAll("[data-question]").forEach((button) => button.addEventListener("click", () => { $("question").value = button.dataset.question; $("question").focus(); }));
$("clear-history").addEventListener("click", async () => {
  if (!confirm("Permanently clear question and answer history? Your documents will remain.")) return;
  try { await api("/history", {method: "DELETE"}); await loadHistory(true); }
  catch (error) { showError(error.message); }
});
$("dismiss-error").addEventListener("click", () => { $("error-banner").hidden = true; });
async function initialize() {
  try {
    const health = await api("/health");
    maxUploadMb = health.max_upload_mb;
    $("upload-limit").textContent = `PDF or TXT · up to ${maxUploadMb} MB`;
    $("mode-badge").textContent = health.mode === "demo" ? "●  Local demo" : "●  AI connected";
    if (health.mode === "llm") {
      $("mode-note").textContent = "AI answers may be inaccurate. Expand the sources to verify each answer.";
      $("privacy-note").textContent = "Questions and retrieved excerpts go to your configured AI provider.";
    }
    await Promise.all([refreshDocuments(), loadHistory(true)]);
  } catch (error) { $("mode-badge").textContent = "Connection unavailable"; showError(error.message); }
}
initialize();
