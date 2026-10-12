(() => {
  const $ = (id) => document.getElementById(id);
  const fileInput = $("file-input");
  const dropzone = $("dropzone");
  const fileLabel = $("file-label");
  const fileSub = $("file-sub");
  const selectedFilesEl = $("selected-files");
  const modeSummarize = $("mode-summarize");
  const modeMerge = $("mode-merge");
  const mergeNote = $("merge-note");
  const actionBtn = $("action-btn");
  const errorBox = $("error");
  const loading = $("loading");
  const loadingText = $("loading-text");
  const result = $("result");
  const summaryEl = $("summary");
  const metaEl = $("meta");
  const resultTitle = $("result-title");
  const resultActions = $("result-actions");

  let mode = "summarize";
  let files = [];
  let lastResult = null;

  const MODE_LABELS = { quick: "Quick summary", bullets: "Key points", detailed: "In-depth analysis" };

  function showError(message) {
    errorBox.textContent = message;
    errorBox.classList.toggle("hidden", !message);
  }

  function renderFiles() {
    if (files.length === 0) {
      selectedFilesEl.classList.add("hidden");
      fileLabel.textContent = mode === "summarize" ? "Tap to choose a PDF, or drop it here" : "Tap to choose PDFs to merge, or drop them here";
      fileSub.textContent = mode === "summarize" ? "Max 100 MB | Up to 200+ pages" : "Max 100 MB total | 2+ PDFs required";
      return;
    }

    selectedFilesEl.classList.remove("hidden");
    const max = mode === "summarize" ? 1 : undefined;
    fileInput.multiple = mode === "merge";

    let html = "";
    files.slice(0, max).forEach((file, idx) => {
      const mb = (file.size / (1024 * 1024)).toFixed(2);
      html += `
        <div class="file-item">
          <span class="name">${file.name}</span>
          <span class="meta">${file.size} bytes</span>
          <button type="button" class="remove" data-idx="${idx}" title="Remove">x</button>
        </div>`;
    });
    selectedFilesEl.innerHTML = html;
    selectedFilesEl.querySelectorAll(".remove").forEach((btn) =>
      btn.addEventListener("click", () => removeFile(parseInt(btn.dataset.idx, 10)))
    );
    fileLabel.textContent = `${files.length} file${files.length > 1 ? "s" : ""}`;
    fileSub.textContent = mode === "summarize"
      ? `Max 100 MB | Up to 200+ pages`
      : `${totalSizeMb().toFixed(2)} MB total | Max 100 MB`;
  }

  function removeFile(idx) {
    files.splice(idx, 1);
    renderFiles();
    actionBtn.disabled = files.length === 0 || (mode === "merge" && files.length < 2);
  }

  function addFiles(newFiles) {
    for (const file of newFiles) {
      if (!file.name.toLowerCase().endsWith(".pdf") && file.type !== "application/pdf") {
        showError(`"${file.name}" is not a PDF file.`);
        return;
      }
      const exists = files.some((f) => f.name === file.name && f.size === file.size);
      if (!exists) files.push(file);
    }
    renderFiles();
    const ok = mode === "summarize" ? files.length >= 1 : files.length >= 2;
    actionBtn.disabled = !ok;
    if (mode === "merge") showError("");
  }

  fileInput.addEventListener("change", () => addFiles(Array.from(fileInput.files)));

  function bindDragAndDrop() {
    ["dragenter", "dragover"].forEach((evt) =>
      dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        dropzone.classList.add("dragover");
      })
    );
    ["dragleave", "drop"].forEach((evt) =>
      dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        dropzone.classList.remove("dragover");
      })
    );
    dropzone.addEventListener("drop", (e) => addFiles(Array.from(e.dataTransfer.files)));
  }
  bindDragAndDrop();

  modeSummarize.addEventListener("click", () => {
    if (mode === "summarize") return;
    mode = "summarize";
    modeSummarize.classList.add("active");
    modeMerge.classList.remove("active");
    mergeNote.classList.add("hidden");
    actionBtn.textContent = "Summarize";
    renderFiles();
  });

  modeMerge.addEventListener("click", () => {
    if (mode === "merge") return;
    mode = "merge";
    modeMerge.classList.add("active");
    modeSummarize.classList.remove("active");
    mergeNote.classList.remove("hidden");
    actionBtn.textContent = "Merge";
    renderFiles();
  });

  async function handleAction() {
    if (files.length === 0) return;
    showError("");
    result.classList.add("hidden");

    if (mode === "summarize") {
      const file = files[0];
      actionBtn.disabled = true;
      loading.classList.remove("hidden");
      loadingText.textContent = "Extracting text and summarizing. Long documents can take a few minutes...";

      const form = new FormData();
      form.append("file", file);
      form.append("mode", "detailed");

      try {
        const response = await fetch("/api/summarize", { method: "POST", body: form });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || `Request failed (${response.status}).`);

        lastResult = data;
        summaryEl.textContent = data.summary;
        const pages = data.pages ? `${data.pages} pages | ` : "";
        metaEl.textContent =
          `${data.filename} | ${pages}${MODE_LABELS[data.mode]} | ${data.model} | ${data.strategy}` +
          (data.chunks > 1 ? ` (${data.chunks} sections)` : "");
        resultTitle.textContent = "Summary";
        resultActions.innerHTML = `
          <button id="copy-btn" class="action-btn">Copy</button>
          <button id="download-btn" class="action-btn">Download</button>`;
        setupResultActions();
        result.classList.remove("hidden");
        result.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (err) {
        showError(err.message || "Something went wrong.");
      } finally {
        loading.classList.add("hidden");
        actionBtn.disabled = false;
      }
    } else {
      actionBtn.disabled = true;
      loading.classList.remove("hidden");
      loadingText.textContent = `Merging ${files.length} PDF(s)...`;

      const form = new FormData();
      files.forEach((file) => form.append("files", file));

      try {
        const response = await fetch("/api/merge", { method: "POST", body: form });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || `Request failed (${response.status}).`);

        lastResult = data;
        summaryEl.textContent = `Merged successfully: ${data.pages} pages, ${Math.round(data.size / 1024)} KB.`;
        metaEl.textContent = `${data.filename} | ${data.pages} pages`;
        resultTitle.textContent = "Merged PDF";
        resultActions.innerHTML = `
          <button id="summarize-merged" class="action-btn">Summarize</button>
          <button id="download-btn" class="action-btn">Download</button>`;
        setupResultActions();
        result.classList.remove("hidden");
        result.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (err) {
        showError(err.message || "Something went wrong.");
      } finally {
        loading.classList.add("hidden");
        actionBtn.disabled = false;
      }
    }
  }

  actionBtn.addEventListener("click", handleAction);

  function b64ToBlob(b64, type) {
    const bin = atob(b64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    return new Blob([arr], { type });
  }

  function setupResultActions() {
    const copyBtn = $("copy-btn");
    const downloadBtn = $("download-btn");
    const summarizeMergedBtn = $("summarize-merged");

    if (copyBtn) {
      copyBtn.addEventListener("click", async (e) => {
        if (!lastResult) return;
        const btn = e.currentTarget;
        try {
          await navigator.clipboard.writeText(lastResult.summary);
          btn.textContent = "Copied";
        } catch {
          const range = document.createRange();
          range.selectNodeContents(summaryEl);
          const sel = window.getSelection();
          sel.removeAllRanges();
          sel.addRange(range);
          btn.textContent = "Selected";
        }
        setTimeout(() => (btn.textContent = "Copy"), 1500);
      });
    }

    if (downloadBtn) {
      downloadBtn.addEventListener("click", () => {
        if (!lastResult) return;
        if (lastResult.file) {
          const blob = b64ToBlob(lastResult.file, "application/pdf");
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = lastResult.filename;
          a.click();
          URL.revokeObjectURL(a.href);
        } else {
          const base = lastResult.filename.replace(/\.pdf$/i, "");
          const blob = new Blob([lastResult.summary], { type: "text/markdown" });
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = `${base}-summary.md`;
          a.click();
          URL.revokeObjectURL(a.href);
        }
      });
    }

    if (summarizeMergedBtn) summarizeMergedBtn.addEventListener("click", async () => {
      if (!lastResult || !lastResult.file) return;
      actionBtn.disabled = true;
      loading.classList.remove("hidden");
      loadingText.textContent = "Summarizing merged PDF...";

      const blob = b64ToBlob(lastResult.file, "application/pdf");
      const file = new File([blob], lastResult.filename);
      const form = new FormData();
      form.append("file", file);
      form.append("mode", "detailed");

      try {
        const response = await fetch("/api/summarize", { method: "POST", body: form });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || `Request failed (${response.status}).`);
        lastResult = data;
        summaryEl.textContent = data.summary;
        const pages = data.pages ? `${data.pages} pages | ` : "";
        metaEl.textContent =
          `${data.filename} | ${pages}${MODE_LABELS[data.mode]} | ${data.model} | ${data.strategy}` +
          (data.chunks > 1 ? ` (${data.chunks} sections)` : "");
        resultTitle.textContent = "Summary";
        resultActions.innerHTML = `
          <button id="copy-btn" class="action-btn">Copy</button>
          <button id="download-btn" class="action-btn">Download</button>`;
        setupResultActions();
      } catch (err) {
        showError(err.message || "Something went wrong.");
      } finally {
        loading.classList.add("hidden");
        actionBtn.disabled = false;
      }
    });
  }

  function totalSizeMb() {
    return files.reduce((sum, file) => sum + file.size, 0) / (1024 * 1024);
  }

  async function checkHealth() {
    const dot = $("status-dot");
    const text = $("status-text");
    try {
      const response = await fetch("/api/health");
      const health = await response.json();
      if (health.ollama && health.model_ready) {
        dot.className = "h-2 w-2 rounded-full bg-emerald-400";
        text.textContent = `Ready | ${health.default_model}`;
      } else if (health.ollama) {
        dot.className = "h-2 w-2 rounded-full bg-amber-400";
        text.textContent = `Model missing | ollama pull ${health.default_model}`;
      } else {
        dot.className = "h-2 w-2 rounded-full bg-red-400";
        text.textContent = "Ollama is not running";
      }
    } catch {
      dot.className = "h-2 w-2 rounded-full bg-red-400";
      text.textContent = "Health check unavailable";
    }
  }

  checkHealth();
})();
