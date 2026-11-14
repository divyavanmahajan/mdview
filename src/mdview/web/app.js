/* mdview graphical UI. Rendering is done by the Python backend so that the
   terminal and graphical UIs agree; this file handles interaction. */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const TOKEN = document.querySelector('meta[name="mdview-token"]').content;
  const editor = $("editor");
  const preview = $("preview");
  const previewPane = $("preview-pane");
  const main = $("main");

  const state = {
    path: null,        // absolute path of the current document, null if untitled
    saved: "",         // text as last loaded or saved
    mtime: null,       // modification time when loaded or saved
    native: false,     // native file dialogs available
    cwd: "",
    sep: "/",
    history: [],       // [{path, scroll}]
    index: -1,
    renderSeq: 0,
    lastDir: null,
  };

  // ---- backend ---------------------------------------------------------
  async function api(name, body = {}) {
    const response = await fetch(`/api/${name}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-MDView-Token": TOKEN },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(data.error || response.statusText);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  // ---- small UI helpers ------------------------------------------------
  let toastTimer = 0;
  function toast(message) {
    $("toast").textContent = message;
    $("toast").hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { $("toast").hidden = true; }, 3500);
  }

  function showBanner(text, actionLabel, action) {
    $("banner-text").textContent = text;
    $("banner-action").textContent = actionLabel;
    $("banner-action").onclick = () => { hideBanner(); action(); };
    $("banner").hidden = false;
  }
  function hideBanner() { $("banner").hidden = true; }
  $("banner-dismiss").onclick = hideBanner;

  const isDirty = () => editor.value !== state.saved;
  const baseName = (path) => path.split(/[\\/]/).pop();
  const dirName = (path) => path.replace(/[\\/][^\\/]*$/, "") || state.sep;
  const isAbsolute = (path) => /^([\\/]|[A-Za-z]:[\\/]|~)/.test(path);
  const joinPath = (dir, name) => (/[\\/]$/.test(dir) ? dir + name : dir + state.sep + name);

  let lastSession = "";
  function refreshChrome() {
    const dirty = isDirty();
    const name = state.path ? baseName(state.path) : "Untitled";
    const title = `${dirty ? "● " : ""}${name} — mdview`;
    document.title = title;
    $("doc-path").textContent = state.path ? `‎${state.path}` : "Untitled";
    $("doc-path").title = state.path || "";
    $("doc-path").classList.toggle("dirty", dirty);
    $("btn-back").disabled = state.index <= 0;
    $("btn-forward").disabled = state.index >= state.history.length - 1;
    const session = JSON.stringify({ dirty, title });
    if (session !== lastSession) {
      lastSession = session;
      api("session", { dirty, title }).catch(() => {});
    }
  }

  // ---- modal dialogs ---------------------------------------------------
  let modalClose = null;
  function openModal(title, buttons, { input = null, list = false } = {}) {
    return new Promise((resolve) => {
      $("modal-title").textContent = title;
      $("modal-input").hidden = input === null;
      $("modal-input").value = input || "";
      $("modal-list").hidden = !list;
      $("modal-dir").hidden = !list;
      const row = $("modal-buttons");
      row.replaceChildren();
      const previousFocus = document.activeElement;
      modalClose = (value) => {
        modalClose = null;
        $("modal").hidden = true;
        if (previousFocus && previousFocus.focus) previousFocus.focus();
        resolve(value);
      };
      for (const [id, label, primary] of buttons) {
        const button = document.createElement("button");
        button.textContent = label;
        button.dataset.id = id;
        if (primary) button.className = "primary";
        button.onclick = () => modalClose && modalClose(id);
        row.append(button);
      }
      $("modal").hidden = false;
      (input !== null ? $("modal-input") : row.querySelector(".primary") || row.lastChild).focus();
    });
  }
  $("modal").addEventListener("keydown", (event) => {
    if (event.key === "Escape" && modalClose) { event.preventDefault(); modalClose(null); }
  });

  /** In-page file chooser, used when no native dialog is available. */
  async function pickPath(kind) {
    let dir = state.lastDir || (state.path ? dirName(state.path) : state.cwd);
    const input = $("modal-input");
    const list = $("modal-list");
    const show = async (target) => {
      let listing;
      try { listing = await api("list", { dir: target }); } catch (error) { toast(error.message); return; }
      dir = listing.dir;
      $("modal-dir").textContent = dir;
      list.replaceChildren();
      const add = (label, className, onClick) => {
        const item = document.createElement("li");
        item.textContent = label;
        item.className = className;
        item.onclick = onClick;
        list.append(item);
      };
      if (listing.parent) add("..", "dir", () => show(listing.parent));
      for (const entry of listing.entries) {
        const full = joinPath(dir, entry.name);
        if (entry.dir) add(entry.name + state.sep, "dir", () => show(full));
        else if (kind === "open") add(entry.name, "file", () => modalClose && modalClose(full));
        else add(entry.name, "file", () => { input.value = entry.name; input.focus(); });
      }
    };
    const initial = kind === "save" ? (state.path ? baseName(state.path) : "untitled.md") : "";
    const title = kind === "save" ? "Save as" : "Open a Markdown file";
    const onKey = async (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      const typed = input.value.trim();
      if (!typed) return;
      const full = isAbsolute(typed) ? typed : joinPath(dir, typed);
      const listing = await api("list", { dir: full }).catch(() => null);
      if (listing && listing.dir.replace(/[\\/]$/, "") === full.replace(/[\\/]$/, "")) {
        input.value = "";
        await show(full);  // typed a folder: browse into it
      } else if (modalClose) {
        modalClose(full);
      }
    };
    input.addEventListener("keydown", onKey);
    const pending = openModal(title, [["cancel", "Cancel"], ["ok", kind === "save" ? "Save" : "Open", true]],
      { input: initial, list: true });
    input.placeholder = kind === "save" ? "File name" : "File name or path";
    await show(dir);
    let result = await pending;
    input.removeEventListener("keydown", onKey);
    if (result === "ok") {
      const typed = input.value.trim();
      result = typed ? (isAbsolute(typed) ? typed : joinPath(dir, typed)) : null;
    }
    if (!result || result === "cancel") return null;
    state.lastDir = dir;
    return result;
  }

  /** Returns {path, confirmed}; confirmed means the OS dialog already asked about overwriting. */
  async function choosePath(kind) {
    if (state.native) {
      const dir = state.path ? dirName(state.path) : state.cwd;
      const name = state.path ? baseName(state.path) : "untitled.md";
      const result = await api("dialog", { kind, dir, name });
      if (result.native) return { path: result.path, confirmed: true };
    }
    return { path: await pickPath(kind), confirmed: false };
  }

  // ---- rendering -------------------------------------------------------
  const mermaidCache = new Map();
  let mermaidCounter = 0;
  const theme = () => document.documentElement.dataset.theme;

  function initMermaid() {
    if (!window.mermaid) return;
    window.mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: theme() === "dark" ? "dark" : "default",
      suppressErrorRendering: true,
    });
  }

  function mediaUrl(src) {
    if (!src || /^([a-z][a-z0-9+.-]+:|\/\/|#)/i.test(src)) return null;
    let rel = src.split(/[?#]/)[0];
    try { rel = decodeURIComponent(rel); } catch (_) { /* keep as written */ }
    const base = state.path ? dirName(state.path) : state.cwd;
    const full = isAbsolute(rel) ? rel : joinPath(base, rel);
    return `/media/${TOKEN}?path=${encodeURIComponent(full)}`;
  }

  function showRenderError(node, source, error) {
    node.textContent = source;
    const note = document.createElement("div");
    note.className = "render-error";
    note.textContent = String((error && error.message) || error);
    node.append(note);
  }

  async function decorate(seq) {
    for (const node of preview.querySelectorAll("img[src], video[src], audio[src], source[src]")) {
      const url = mediaUrl(node.getAttribute("src"));
      if (url) node.setAttribute("src", url);
    }
    if (window.katex) {
      for (const node of preview.querySelectorAll(".math")) {
        const source = node.textContent;
        const display = node.classList.contains("block");
        let target = node;
        if (node.tagName === "PRE") {  // ```math fence
          target = document.createElement("div");
          target.className = "math block";
          node.replaceWith(target);
        }
        try {
          window.katex.render(source, target, { displayMode: display, throwOnError: false });
        } catch (error) { showRenderError(target, source, error); }
      }
    }
    buildOutline();
    if (!window.mermaid) return;
    for (const node of preview.querySelectorAll("pre.mermaid")) {
      const source = node.textContent;
      const key = `${theme()}\n${source}`;
      let svg = mermaidCache.get(key);
      if (svg === undefined) {
        try {
          svg = (await window.mermaid.render(`mermaid-${++mermaidCounter}`, source)).svg;
          mermaidCache.set(key, svg);
        } catch (error) {
          if (seq === state.renderSeq) showRenderError(node, source, error);
          continue;
        }
      }
      if (seq !== state.renderSeq) return;  // a newer render replaced the DOM
      node.innerHTML = svg;
    }
  }

  function setPreview(html) {
    const seq = ++state.renderSeq;
    if (html.trim()) preview.innerHTML = html;
    else preview.innerHTML = '<p class="hint">Nothing to preview yet.<br>Open a file or start typing in the editor.</p>';
    return decorate(seq);
  }

  let renderTimer = 0;
  function scheduleRender() {
    clearTimeout(renderTimer);
    renderTimer = setTimeout(renderNow, 120);
  }
  async function renderNow() {
    clearTimeout(renderTimer);
    const seq = state.renderSeq + 1;
    try {
      const { html } = await api("render", { text: editor.value });
      if (seq === state.renderSeq + 1) await setPreview(html);
    } catch (error) { toast(`Render failed: ${error.message}`); }
  }

  function buildOutline() {
    const outline = $("outline");
    outline.replaceChildren();
    const headings = preview.querySelectorAll("h1[id], h2[id], h3[id], h4[id], h5[id], h6[id]");
    for (const heading of headings) {
      const link = document.createElement("a");
      link.textContent = heading.textContent;
      link.href = `#${heading.id}`;
      link.style.paddingLeft = `${8 + (Number(heading.tagName[1]) - 1) * 12}px`;
      link.onclick = (event) => { event.preventDefault(); scrollToAnchor(heading.id); };
      outline.append(link);
    }
    if (!headings.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "No headings";
      outline.append(empty);
    }
  }

  function scrollToAnchor(anchor) {
    if (!anchor) return false;
    const candidates = [anchor, anchor.toLowerCase()];
    for (const id of candidates) {
      const target = preview.querySelector(`[id="${CSS.escape(id)}"], a[name="${CSS.escape(id)}"]`);
      if (target) {
        if (main.dataset.mode === "edit") setMode("split");
        target.scrollIntoView({ block: "start" });
        return true;
      }
    }
    toast(`No section "#${anchor}" in this document`);
    return false;
  }

  // ---- documents -------------------------------------------------------
  /** Resolve unsaved changes before replacing the document. False means "stay". */
  async function confirmLeave() {
    if (!isDirty()) return true;
    const name = state.path ? baseName(state.path) : "Untitled";
    const answer = await openModal(`Save changes to ${name}?`,
      [["cancel", "Cancel"], ["discard", "Discard"], ["save", "Save", true]]);
    if (answer === "discard") return true;
    if (answer === "save") return save();
    return false;
  }

  async function setDocument(doc, { anchor = "", scroll = 0 } = {}) {
    state.path = doc.path;
    state.saved = doc.text;
    state.mtime = doc.mtime;
    editor.value = doc.text;
    editor.scrollTop = 0;
    editor.setSelectionRange(0, 0);
    hideBanner();
    refreshChrome();
    await setPreview(doc.html);
    if (anchor) scrollToAnchor(anchor);
    else previewPane.scrollTop = scroll;
  }

  /** Open a document. `record` adds it to the back/forward history. */
  async function openPath(path, { anchor = "", record = true, scroll = 0 } = {}) {
    if (!(await confirmLeave())) return false;
    let doc;
    try { doc = await api("open", { path }); } catch (error) { toast(error.message); return false; }
    if (record) {
      if (state.index >= 0) state.history[state.index].scroll = previewPane.scrollTop;
      state.history.splice(state.index + 1);
      state.history.push({ path: doc.path, scroll: 0 });
      state.index = state.history.length - 1;
    }
    await setDocument(doc, { anchor, scroll });
    if (!doc.exists) {
      if (main.dataset.mode === "view") setMode("split");
      toast(`${baseName(doc.path)} does not exist yet. It will be created when you save.`);
      editor.focus();
    }
    return true;
  }

  async function go(delta) {
    const index = state.index + delta;
    if (index < 0 || index >= state.history.length) return;
    const from = state.history[state.index];
    const leaving = previewPane.scrollTop;
    const entry = state.history[index];
    const ok = entry.path
      ? await openPath(entry.path, { record: false, scroll: entry.scroll })
      : await newDocument({ record: false });
    if (ok) { from.scroll = leaving; state.index = index; refreshChrome(); }
  }

  async function newDocument({ record = true } = {}) {
    if (!(await confirmLeave())) return false;
    if (record) {
      if (state.index >= 0) state.history[state.index].scroll = previewPane.scrollTop;
      state.history.splice(state.index + 1);
      state.history.push({ path: null, scroll: 0 });
      state.index = state.history.length - 1;
    }
    await setDocument({ path: null, text: "", html: "", mtime: null });
    if (main.dataset.mode === "view") setMode("split");
    editor.focus();
    return true;
  }

  async function openDialog() {
    const { path } = await choosePath("open");
    if (path) await openPath(path);
  }

  async function writeTo(path, mtime, force) {
    const text = editor.value;
    try {
      const result = await api("save", { path, text, mtime, force });
      state.path = result.path;
      state.saved = text;
      state.mtime = result.mtime;
      if (state.index >= 0) state.history[state.index].path = result.path;
      else { state.history.push({ path: result.path, scroll: 0 }); state.index = 0; }
      hideBanner();
      refreshChrome();
      toast(`Saved ${baseName(result.path)}`);
      return true;
    } catch (error) {
      if (error.status !== 409) { toast(`Could not save: ${error.message}`); return false; }
      const question = path === state.path
        ? `${baseName(path)} was changed on disk by another program. Overwrite it with your version?`
        : `${baseName(path)} already exists. Replace it?`;
      const answer = await openModal(question, [["cancel", "Cancel"], ["overwrite", "Overwrite", true]]);
      return answer === "overwrite" ? writeTo(path, mtime, true) : false;
    }
  }

  async function save() {
    if (!state.path) return saveAs();
    return writeTo(state.path, state.mtime, false);
  }

  async function saveAs() {
    const { path, confirmed } = await choosePath("save");
    if (!path) return false;
    const target = /\.[^\\/.]+$/.test(path) ? path : `${path}.md`;
    const same = target === state.path;
    const ok = await writeTo(target, same ? state.mtime : null, confirmed && target === path);
    if (ok) scheduleRender();  // relative images now resolve against the new folder
    return ok;
  }

  async function reloadFromDisk() {
    if (!state.path) return;
    const scroll = previewPane.scrollTop;
    try {
      const doc = await api("open", { path: state.path });
      if (doc.exists) await setDocument(doc, { scroll });
    } catch (error) { toast(error.message); }
  }

  // Follow changes made by other programs.
  let noticedMtime = null;
  setInterval(async () => {
    if (!state.path || state.mtime === null || document.hidden || modalClose) return;
    const path = state.path;
    let mtime;
    try { mtime = (await api("stat", { path })).mtime; } catch (_) { return; }
    if (path !== state.path || mtime === null || mtime === state.mtime) return;
    if (!isDirty()) { await reloadFromDisk(); return; }
    if (mtime !== noticedMtime) {
      noticedMtime = mtime;
      showBanner("This file was changed on disk by another program.", "Reload and lose my changes", reloadFromDisk);
    }
  }, 2000);

  // ---- links -----------------------------------------------------------
  preview.addEventListener("click", async (event) => {
    const link = event.target.closest("a[href]");
    if (!link || !preview.contains(link)) return;
    event.preventDefault();
    const href = link.getAttribute("href");
    if (href.startsWith("#")) {
      let anchor = href.slice(1);
      try { anchor = decodeURIComponent(anchor); } catch (_) { /* keep */ }
      scrollToAnchor(anchor);
      return;
    }
    try {
      const target = await api("resolve", { href, base: state.path });
      if (target.kind === "anchor") scrollToAnchor(target.anchor);
      else if (target.kind === "document") {
        if (target.path === state.path) scrollToAnchor(target.anchor) || (previewPane.scrollTop = 0);
        else await openPath(target.path, { anchor: target.anchor });
      } else if (target.kind === "file") {
        if (target.exists) await api("open-external", { path: target.path });
        else toast(`${target.path} does not exist`);
      } else await api("open-external", { url: target.url });
    } catch (error) { toast(error.message); }
  });

  // ---- layout ----------------------------------------------------------
  function setMode(mode) {
    main.dataset.mode = mode;
    for (const button of document.querySelectorAll(".segmented button")) {
      button.classList.toggle("active", button.dataset.mode === mode);
    }
    if (mode === "view") previewPane.focus(); else editor.focus();
  }
  for (const button of document.querySelectorAll(".segmented button")) {
    button.onclick = () => setMode(button.dataset.mode);
  }
  const cycleMode = () => setMode({ view: "split", split: "edit", edit: "view" }[main.dataset.mode]);

  $("divider").addEventListener("pointerdown", (event) => {
    const divider = $("divider");
    divider.setPointerCapture(event.pointerId);
    divider.classList.add("dragging");
    const move = (e) => {
      const left = $("editor-pane").getBoundingClientRect().left;
      const total = main.getBoundingClientRect().right - left;
      const share = Math.min(85, Math.max(15, ((e.clientX - left) / total) * 100));
      $("editor-pane").style.flexBasis = `${share}%`;
      previewPane.style.flexBasis = `${100 - share}%`;
    };
    const up = () => {
      divider.classList.remove("dragging");
      divider.removeEventListener("pointermove", move);
      divider.removeEventListener("pointerup", up);
    };
    divider.addEventListener("pointermove", move);
    divider.addEventListener("pointerup", up);
  });

  // Keep the two panes roughly aligned while scrolling either of them.
  let syncSource = null;
  let syncTimer = 0;
  function syncScroll(from, to) {
    if (main.dataset.mode !== "split" || (syncSource && syncSource !== from)) return;
    syncSource = from;
    clearTimeout(syncTimer);
    syncTimer = setTimeout(() => { syncSource = null; }, 150);
    const range = from.scrollHeight - from.clientHeight;
    if (range > 0) to.scrollTop = (from.scrollTop / range) * (to.scrollHeight - to.clientHeight);
  }
  editor.addEventListener("scroll", () => syncScroll(editor, previewPane));
  previewPane.addEventListener("scroll", () => syncScroll(previewPane, editor));

  function setTheme(name) {
    document.documentElement.dataset.theme = name;
    initMermaid();
  }
  $("btn-theme").onclick = () => {
    setTheme(theme() === "dark" ? "light" : "dark");
    renderNow();
  };

  // ---- editing helpers -------------------------------------------------
  function insertText(text) {
    editor.focus();
    if (!document.execCommand("insertText", false, text)) {  // keeps the undo stack
      editor.setRangeText(text, editor.selectionStart, editor.selectionEnd, "end");
      editor.dispatchEvent(new Event("input"));
    }
  }
  function wrapSelection(before, after, placeholder) {
    const { selectionStart: start, selectionEnd: end, value } = editor;
    const selected = value.slice(start, end) || placeholder;
    insertText(before + selected + after);
    editor.setSelectionRange(start + before.length, start + before.length + selected.length);
  }

  editor.addEventListener("input", () => { refreshChrome(); scheduleRender(); });
  editor.addEventListener("keydown", (event) => {
    if (event.isComposing) return;
    const mod = event.ctrlKey || event.metaKey;
    if (event.key === "Tab" && !mod && !event.altKey) {
      event.preventDefault();
      insertText("    ");
    } else if (event.key === "Enter" && !mod && !event.shiftKey && !event.altKey) {
      // Continue lists, task lists and quotes on the next line.
      const { selectionStart: start, selectionEnd: end, value } = editor;
      if (start !== end) return;
      const lineStart = value.lastIndexOf("\n", start - 1) + 1;
      const line = value.slice(lineStart, start);
      const match = line.match(/^(\s*)(?:([-*+])|(\d+)([.)])|(>))(\s+)(\[[ xX]\]\s+)?/);
      if (!match) return;
      event.preventDefault();
      if (line.length === match[0].length) {  // empty item: end the list
        editor.setSelectionRange(lineStart, start);
        insertText("");
        return;
      }
      const marker = match[2] || match[5] || `${Number(match[3]) + 1}${match[4]}`;
      insertText(`\n${match[1]}${marker}${match[6]}${match[7] ? "[ ] " : ""}`);
    } else if (mod && !event.shiftKey && !event.altKey) {
      const key = event.key.toLowerCase();
      if (key === "b") { event.preventDefault(); wrapSelection("**", "**", "bold"); }
      else if (key === "i") { event.preventDefault(); wrapSelection("*", "*", "italic"); }
      else if (key === "k") { event.preventDefault(); wrapSelection("[", "](url)", "text"); }
    }
  });

  // ---- commands --------------------------------------------------------
  $("btn-back").onclick = () => go(-1);
  $("btn-forward").onclick = () => go(1);
  $("btn-new").onclick = () => newDocument();
  $("btn-open").onclick = openDialog;
  $("btn-save").onclick = save;
  $("btn-outline").onclick = () => { $("outline").hidden = !$("outline").hidden; };

  window.addEventListener("keydown", (event) => {
    if (modalClose) return;
    const mod = event.ctrlKey || event.metaKey;
    const key = event.key.toLowerCase();
    let handled = true;
    if (mod && key === "s") event.shiftKey ? saveAs() : save();
    else if (mod && key === "o") openDialog();
    else if (mod && key === "n") newDocument();
    else if (mod && key === "e") cycleMode();
    else if ((event.altKey && key === "arrowleft") || (mod && key === "[")) go(-1);
    else if ((event.altKey && key === "arrowright") || (mod && key === "]")) go(1);
    else handled = false;
    if (handled) event.preventDefault();
  });

  window.addEventListener("beforeunload", (event) => {
    if (!state.native && isDirty()) { event.preventDefault(); event.returnValue = ""; }
  });

  // Called by the native window host when the user closes a window with unsaved changes.
  window.mdviewRequestClose = async () => {
    if (modalClose) return;
    if (await confirmLeave()) {
      state.saved = editor.value;
      await api("close").catch(() => {});
    }
  };

  // ---- start -----------------------------------------------------------
  (async () => {
    const dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    setTheme(dark ? "dark" : "light");
    let info;
    try { info = await api("state"); } catch (error) { toast(`Backend unavailable: ${error.message}`); return; }
    state.native = info.native;
    state.cwd = info.cwd;
    state.sep = info.sep;
    if (info.initial) {
      setMode(info.mode || "view");
      await openPath(info.initial);
    } else {
      setMode(info.mode || "split");
      await setPreview("");
      state.history.push({ path: null, scroll: 0 });
      state.index = 0;
      refreshChrome();
    }
    document.body.dataset.ready = "1";
  })();
})();
