(function () {
  const RECENT_PAPERS_KEY = "paper-recent-slugs";
  const CHAT_MODEL_KEY = "paper-chat-model";
  const CHAT_MODEL_DEFAULT_VERSION_KEY = "paper-chat-model-default-version";
  const DEFAULT_CHAT_MODEL = "gpt-5.5";
  const CHAT_MODEL_DEFAULT_VERSION = "20260612-gpt-5.5";
  const ACTIVE_LIBRARY_KEY = "paper-active-library";
  const params = new URLSearchParams(window.location.search);
  const slug = params.get("slug");
  const library = params.get("library") || window.localStorage.getItem(ACTIVE_LIBRARY_KEY) || "default";
  window.localStorage.setItem(ACTIVE_LIBRARY_KEY, library);
  const state = {
    paper: null,
    papers: [],
    messages: [],
    analysisRaw: "",
    analysisEditing: false,
    sidePanelWidth: 430,
    resizing: false
  };

  const md = window.markdownit
    ? window.markdownit({
        html: false,
        linkify: true,
        breaks: true
      })
    : null;

  const els = {
    title: document.getElementById("paperTitle"),
    meta: document.getElementById("paperMeta"),
    openPdf: document.getElementById("openPdfLink"),
    openPdfInline: document.getElementById("openPdfInlineLink"),
    pdfFrame: document.getElementById("pdfFrame"),
    pdfStatus: document.getElementById("pdfStatus"),
    contextStatus: document.getElementById("contextStatus"),
    thread: document.getElementById("chatThread"),
    form: document.getElementById("chatForm"),
    input: document.getElementById("chatInput"),
    model: document.getElementById("modelSelect"),
    send: document.getElementById("sendButton"),
    similarList: document.getElementById("similarList"),
    analysisContent: document.getElementById("analysisContent"),
    analysisStatus: document.getElementById("analysisStatus"),
    analysisEditor: document.getElementById("analysisEditor"),
    analysisGenerate: document.getElementById("analysisGenerateButton"),
    analysisEdit: document.getElementById("analysisEditButton"),
    analysisSave: document.getElementById("analysisSaveButton"),
    analysisCancel: document.getElementById("analysisCancelButton"),
    splitter: document.getElementById("paneSplitter")
  };

  function text(value) {
    return value == null ? "" : String(value);
  }

  function addMessage(role, content, sources, meta) {
    const message = Object.assign(
      { role, content: text(content), sources: sources || [] },
      meta || {}
    );
    state.messages.push(message);
    renderMessage(message);
    els.thread.scrollTop = els.thread.scrollHeight;
  }

  function getConversationKey() {
    return slug ? "paper-conversation:" + library + ":" + slug : "paper-conversation:" + library;
  }

  function setupModelSelect() {
    const savedModel = window.localStorage.getItem(CHAT_MODEL_KEY);
    const options = Array.from(els.model.options);
    const hasOption = (value) => options.some((option) => option.value === value);
    const defaultVersion = window.localStorage.getItem(CHAT_MODEL_DEFAULT_VERSION_KEY);
    if (defaultVersion !== CHAT_MODEL_DEFAULT_VERSION && hasOption(DEFAULT_CHAT_MODEL)) {
      els.model.value = DEFAULT_CHAT_MODEL;
      window.localStorage.setItem(CHAT_MODEL_KEY, DEFAULT_CHAT_MODEL);
      window.localStorage.setItem(CHAT_MODEL_DEFAULT_VERSION_KEY, CHAT_MODEL_DEFAULT_VERSION);
    } else if (savedModel && hasOption(savedModel)) {
      els.model.value = savedModel;
    } else if (hasOption(DEFAULT_CHAT_MODEL)) {
      els.model.value = DEFAULT_CHAT_MODEL;
    }
    els.model.addEventListener("change", () => {
      window.localStorage.setItem(CHAT_MODEL_KEY, els.model.value);
      window.localStorage.setItem(CHAT_MODEL_DEFAULT_VERSION_KEY, CHAT_MODEL_DEFAULT_VERSION);
    });
  }

  function recordRecentPaper(paperSlug) {
    if (!paperSlug) {
      return;
    }
    let slugs = [];
    try {
      const parsed = JSON.parse(window.localStorage.getItem(RECENT_PAPERS_KEY + ":" + library) || "[]");
      slugs = Array.isArray(parsed) ? parsed : [];
    } catch (error) {
      slugs = [];
    }
    slugs = [paperSlug].concat(slugs.filter((item) => item && item !== paperSlug)).slice(0, 24);
    window.localStorage.setItem(RECENT_PAPERS_KEY + ":" + library, JSON.stringify(slugs));
  }

  async function saveConversationToServer(messages) {
    if (!slug) {
      return null;
    }
    const response = await fetch("/api/papers/" + encodeURIComponent(slug) + "/conversation", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ library, messages })
    });
    if (!response.ok) {
      throw await responseError(response, "conversation save failed");
    }
    return response.json();
  }

  async function loadConversationFromServer() {
    if (!slug) {
      return [];
    }
    const response = await fetch("/api/papers/" + encodeURIComponent(slug) + "/conversation?library=" + encodeURIComponent(library), { cache: "no-cache" });
    if (!response.ok) {
      throw await responseError(response, "conversation unavailable");
    }
    const data = await response.json();
    return Array.isArray(data.messages) ? data.messages : [];
  }

  function loadLocalConversation() {
    if (!slug) {
      return [];
    }
    try {
      const raw = window.localStorage.getItem(getConversationKey());
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (error) {
      return [];
    }
  }

  async function loadConversation() {
    const localMessages = loadLocalConversation()
      .filter((message) => message && (message.role === "user" || message.role === "assistant") && message.content);
    let serverMessages = [];
    try {
      serverMessages = await loadConversationFromServer();
    } catch (error) {
      return localMessages;
    }
    if (serverMessages.length) {
      return serverMessages;
    }

    if (!localMessages.length) {
      return [];
    }

    const saved = await saveConversationToServer(localMessages);
    return saved && Array.isArray(saved.messages) ? saved.messages : localMessages;
  }

  function renderConversation(messages) {
    els.thread.textContent = "";
    state.messages = [];
    messages.forEach((message) => {
      if (!message || !message.role || !message.content) {
        return;
      }
      const normalized = {
        role: message.role,
        content: text(message.content),
        sources: Array.isArray(message.sources) ? message.sources : [],
        incomplete: Boolean(message.incomplete),
        incomplete_reason: text(message.incomplete_reason),
        model: text(message.model),
        saved_to_qa: Boolean(message.saved_to_qa || message.saved_to_analysis),
        analysis_anchor: text(message.analysis_anchor)
      };
      state.messages.push(normalized);
      renderMessage(normalized);
    });
    els.thread.scrollTop = els.thread.scrollHeight;
  }

  function renderMessage(message) {
    const item = document.createElement("article");
    item.className = "chat-message " + (message.role === "user" ? "user" : "assistant");

    const label = document.createElement("div");
    label.className = "message-role";
    label.textContent = message.role === "user" ? "You" : "Assistant";
    item.appendChild(label);

    const body = document.createElement("div");
    body.className = "message-body";
    body.innerHTML = renderRichText(message.content);
    item.appendChild(body);

    if (message.role === "assistant") {
      const controls = document.createElement("div");
      controls.className = "message-actions";

      const saveButton = document.createElement("button");
      saveButton.type = "button";
      saveButton.className = "button slim save-analysis-button";
      if (message.saved_to_qa) {
        saveButton.textContent = message.analysis_anchor ? "打开 QA" : "已保存到 QA";
        saveButton.disabled = !message.analysis_anchor;
        if (message.analysis_anchor) {
          saveButton.addEventListener("click", () => scrollToAnalysisAnchor(message.analysis_anchor));
        }
      } else {
        saveButton.textContent = "保存到 QA";
        saveButton.addEventListener("click", () => saveMessageToQa(message, saveButton));
      }
      controls.appendChild(saveButton);

      const regenerateButton = document.createElement("button");
      regenerateButton.type = "button";
      regenerateButton.className = "button slim regenerate-button";
      regenerateButton.textContent = "重新生成";
      regenerateButton.addEventListener("click", () => regenerateMessage(message));
      controls.appendChild(regenerateButton);

      if (message.incomplete) {
        const note = document.createElement("span");
        note.className = "incomplete-note";
        note.textContent = message.incomplete_reason
          ? "回答可能被截断：" + message.incomplete_reason
          : "回答可能被截断";
        controls.appendChild(note);
      }

      const button = document.createElement("button");
      button.type = "button";
      button.className = "button slim continue-button";
      button.textContent = "继续生成";
      button.addEventListener("click", () => continueMessage(message));
      if (message.incomplete) {
        controls.appendChild(button);
      }
      item.appendChild(controls);
    }

    els.thread.appendChild(item);
    return item;
  }

  function formatElapsed(milliseconds) {
    const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
    if (totalSeconds < 60) {
      return totalSeconds + "s";
    }
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return minutes + "m " + String(seconds).padStart(2, "0") + "s";
  }

  function createPendingMessage() {
    const item = document.createElement("article");
    item.className = "chat-message assistant pending-message";

    const label = document.createElement("div");
    label.className = "message-role";
    label.textContent = "Assistant";
    item.appendChild(label);

    const body = document.createElement("div");
    body.className = "message-body pending-body";

    const dots = document.createElement("span");
    dots.className = "pending-dots";
    dots.setAttribute("aria-hidden", "true");
    dots.appendChild(document.createElement("i"));
    dots.appendChild(document.createElement("i"));
    dots.appendChild(document.createElement("i"));
    body.appendChild(dots);

    const status = document.createElement("span");
    status.className = "pending-text";
    body.appendChild(status);

    item.appendChild(body);
    els.thread.appendChild(item);

    const startedAt = Date.now();
    const update = () => {
      status.textContent = "正在分析论文内容 · 已等待 " + formatElapsed(Date.now() - startedAt);
    };
    update();
    const timer = window.setInterval(update, 1000);
    els.thread.scrollTop = els.thread.scrollHeight;

    return {
      remove() {
        window.clearInterval(timer);
        item.remove();
      }
    };
  }

  function renderRichText(text) {
    const extracted = extractMath(text);
    const rendered = md ? md.render(extracted.text) : escapeHtml(extracted.text).replace(/\n/g, "<br>");
    const container = document.createElement("div");
    container.innerHTML = rendered;
    restoreMath(container, extracted.math);
    applyInlineSubscripts(container);
    return container.innerHTML;
  }

  function escapeHtml(value) {
    return text(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  async function responseError(response, fallback) {
    const payload = await response.json().catch(() => ({}));
    const message = payload.error || fallback || "request failed";
    return new Error(message + " (HTTP " + response.status + ")");
  }

  function applyInlineSubscripts(root) {
    const pattern = /\b([a-z]{1,3}|[A-Z])_(?:\{([^{}]+)\}|([A-Za-z0-9+\-]+))/g;
    const nodes = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent || parent.closest("code, pre, a, .katex, .math-inline, .math-block")) {
          return NodeFilter.FILTER_REJECT;
        }
        pattern.lastIndex = 0;
        return pattern.test(node.nodeValue || "")
          ? NodeFilter.FILTER_ACCEPT
          : NodeFilter.FILTER_REJECT;
      }
    });

    while (walker.nextNode()) {
      nodes.push(walker.currentNode);
    }

    nodes.forEach((node) => {
      pattern.lastIndex = 0;
      const value = node.nodeValue || "";
      const fragment = document.createDocumentFragment();
      let cursor = 0;
      let match;
      while ((match = pattern.exec(value))) {
        fragment.appendChild(document.createTextNode(value.slice(cursor, match.index)));
        fragment.appendChild(document.createTextNode(match[1]));
        const sub = document.createElement("sub");
        sub.textContent = match[2] || match[3] || "";
        fragment.appendChild(sub);
        cursor = match.index + match[0].length;
      }
      fragment.appendChild(document.createTextNode(value.slice(cursor)));
      node.replaceWith(fragment);
    });
  }

  function extractMath(value) {
    const math = [];
    const source = text(value);
    const replaced = source.replace(/\\\[([\s\S]+?)\\\]|\$\$([\s\S]+?)\$\$|\\\(([\s\S]+?)\\\)|\$([^$\n]+?)\$/g, (match, bracketBlock, dollarBlock, parenInline, dollarInline) => {
      const raw = bracketBlock || dollarBlock || parenInline || dollarInline || "";
      const display = Boolean(bracketBlock || dollarBlock);
      const token = "MATHPLACEHOLDER" + math.length + "END";
      math.push({ token, raw: raw.trim(), display });
      return token;
    });
    return { text: replaced, math };
  }

  function restoreMath(root, mathItems) {
    if (!mathItems.length) {
      return;
    }
    const byToken = new Map(mathItems.map((item) => [item.token, item]));
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) {
      nodes.push(walker.currentNode);
    }

    nodes.forEach((node) => {
      const nodeText = node.nodeValue;
      if (!nodeText || !nodeText.includes("MATHPLACEHOLDER")) {
        return;
      }

      const wholeToken = nodeText.trim();
      const wholeItem = byToken.get(wholeToken);
      const parent = node.parentElement;
      if (wholeItem && wholeItem.display && parent && parent.tagName === "P" && parent.textContent.trim() === wholeToken) {
        parent.replaceWith(renderMathElement(wholeItem));
        return;
      }

      const parts = [];
      let index = 0;
      const pattern = /MATHPLACEHOLDER\d+END/g;
      let match;
      while ((match = pattern.exec(nodeText))) {
        if (match.index > index) {
          parts.push({ type: "text", value: nodeText.slice(index, match.index) });
        }
        parts.push({ type: "math", value: match[0] });
        index = match.index + match[0].length;
      }
      if (index < nodeText.length) {
        parts.push({ type: "text", value: nodeText.slice(index) });
      }

      const fragment = document.createDocumentFragment();
      parts.forEach((part) => {
        if (part.type === "text") {
          fragment.appendChild(document.createTextNode(part.value));
          return;
        }
        const item = byToken.get(part.value);
        if (!item) {
          fragment.appendChild(document.createTextNode(part.value));
          return;
        }
        fragment.appendChild(renderMathElement(item));
      });
      if (node.parentNode) {
        node.parentNode.replaceChild(fragment, node);
      }
    });
  }

  function renderMathElement(item) {
    const element = document.createElement(item.display ? "div" : "span");
    element.className = item.display ? "math-block" : "math-inline";
    try {
      if (!window.katex) {
        throw new Error("KaTeX unavailable");
      }
      element.innerHTML = window.katex.renderToString(item.raw, {
        displayMode: item.display,
        throwOnError: false
      });
    } catch (error) {
      element.textContent = item.raw;
    }
    return element;
  }

  function setBusy(isBusy) {
    els.send.disabled = isBusy;
    els.input.disabled = isBusy;
    els.model.disabled = isBusy;
    els.send.textContent = isBusy ? "Thinking" : "Send";
  }

  function stopWheelPropagation(element) {
    if (!element) {
      return;
    }
    element.addEventListener("wheel", (event) => {
      event.stopPropagation();
    }, { passive: false });
  }

  function getStoredPanelWidth() {
    const raw = window.localStorage.getItem("paper-side-panel-width");
    const value = Number(raw);
    if (!Number.isFinite(value)) {
      return 430;
    }
    return Math.min(700, Math.max(320, value));
  }

  function applyPanelWidth(width) {
    state.sidePanelWidth = Math.min(700, Math.max(320, width));
    document.documentElement.style.setProperty("--side-panel-width", state.sidePanelWidth + "px");
    window.localStorage.setItem("paper-side-panel-width", String(state.sidePanelWidth));
  }

  function setupSplitter() {
    if (!els.splitter) {
      return;
    }
    applyPanelWidth(getStoredPanelWidth());

    const startDrag = (event) => {
      state.resizing = true;
      document.body.classList.add("resizing-panes");
      els.splitter.classList.add("dragging");
      const startX = event.clientX;
      const startWidth = state.sidePanelWidth;

      const onMove = (moveEvent) => {
        const delta = startX - moveEvent.clientX;
        applyPanelWidth(startWidth + delta);
      };

      const onUp = () => {
        state.resizing = false;
        document.body.classList.remove("resizing-panes");
        els.splitter.classList.remove("dragging");
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };

      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    };

    els.splitter.addEventListener("mousedown", startDrag);
    els.splitter.addEventListener("touchstart", (event) => {
      if (!event.touches || !event.touches[0]) {
        return;
      }
      const touch = event.touches[0];
      state.resizing = true;
      document.body.classList.add("resizing-panes");
      els.splitter.classList.add("dragging");
      const startX = touch.clientX;
      const startWidth = state.sidePanelWidth;

      const onMove = (moveEvent) => {
        moveEvent.preventDefault();
        const point = moveEvent.touches && moveEvent.touches[0];
        if (!point) {
          return;
        }
        const delta = startX - point.clientX;
        applyPanelWidth(startWidth + delta);
      };

      const onEnd = () => {
        state.resizing = false;
        document.body.classList.remove("resizing-panes");
        els.splitter.classList.remove("dragging");
        window.removeEventListener("touchmove", onMove);
        window.removeEventListener("touchend", onEnd);
      };

      window.addEventListener("touchmove", onMove, { passive: false });
      window.addEventListener("touchend", onEnd);
    }, { passive: false });
  }

  function setActiveTab(tabName) {
    document.querySelectorAll(".tab-button").forEach((button) => {
      button.classList.toggle("active", button.dataset.tab === tabName);
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => {
      panel.classList.toggle("active", panel.dataset.panel === tabName);
    });
  }

  function setupTabs() {
    document.querySelectorAll(".tab-button").forEach((button) => {
      button.addEventListener("click", () => setActiveTab(button.dataset.tab));
    });
  }

  async function loadPaper() {
    if (!slug) {
      throw new Error("URL 缺少 slug 参数");
    }

    const response = await fetch("libraries/" + encodeURIComponent(library) + "/papers.json", { cache: "no-cache" });
    if (!response.ok) {
      throw new Error("无法加载当前 library 的 papers.json");
    }
    state.papers = await response.json();
    const paper = state.papers.find((item) => item.slug === slug);
    if (!paper) {
      throw new Error("未找到论文: " + slug);
    }

    state.paper = paper;
    document.querySelectorAll('a[href="index.html"]').forEach((link) => {
      link.href = "index.html?library=" + encodeURIComponent(library);
    });
    recordRecentPaper(paper.slug);
    document.title = paper.title;
    els.title.textContent = paper.title;
    els.meta.textContent = [paper.arxiv ? "arXiv " + paper.arxiv : "", paper.status || "", paper.updated || ""]
      .filter(Boolean)
      .join(" · ");
    setPaperPdf(paper, { available: Boolean(paper.pdf), downloaded: false, checking: true });

    renderSimilarPapers(paper);
    stopWheelPropagation(els.thread);
    stopWheelPropagation(els.analysisContent);
    stopWheelPropagation(els.analysisEditor);
    renderConversation(await loadConversation());
    const [paperStatus] = await Promise.all([loadContextStatus(slug), loadAnalysis(slug)]);
    if (paperStatus && paperStatus.paper) {
      state.paper = paperStatus.paper;
      setPaperPdf(paperStatus.paper, paperStatus.pdf_status || {});
    }
    if (!state.messages.length) {
      addMessage("assistant", "I have loaded the local materials for this paper. Ask about contributions, method details, experiments, limitations, or comparisons.");
    }
  }

  function setPaperPdf(paper, pdfStatus) {
    const status = pdfStatus || {};
    const pdf = paper && paper.pdf ? paper.pdf : "";
    els.openPdf.href = pdf || "#";
    els.openPdfInline.href = pdf || "#";
    els.openPdf.classList.toggle("disabled", !pdf);
    els.openPdfInline.classList.toggle("disabled", !pdf);
    if (pdf && status.available !== false && !status.checking) {
      els.pdfFrame.src = pdf;
    } else {
      els.pdfFrame.removeAttribute("src");
    }
    if (status.checking) {
      els.pdfStatus.textContent = "Checking PDF";
    } else if (status.downloaded) {
      els.pdfStatus.textContent = "PDF downloaded";
    } else if (status.available) {
      els.pdfStatus.textContent = "Loaded";
    } else {
      els.pdfStatus.textContent = status.error || "PDF unavailable";
    }
  }

  async function loadContextStatus(paperSlug) {
    try {
      els.contextStatus.textContent = "正在检查 PDF 和材料";
      const response = await fetch("/api/papers/" + encodeURIComponent(paperSlug) + "?library=" + encodeURIComponent(library));
      if (!response.ok) {
        throw new Error("API unavailable");
      }
      const data = await response.json();
      els.contextStatus.textContent = data.context_files + " files · " + data.chunk_count + " chunks";
      return data;
    } catch (error) {
      els.contextStatus.textContent = "Backend disconnected";
      return null;
    }
  }

  function renderSimilarPapers(paper) {
    const currentTags = new Set((paper.tags || []).map((tag) => tag.toLowerCase()));
    const scored = state.papers
      .filter((item) => item.slug !== paper.slug)
      .map((item) => {
        const overlap = (item.tags || []).filter((tag) => currentTags.has(tag.toLowerCase())).length;
        return { paper: item, score: overlap };
      })
      .sort((a, b) => b.score - a.score || a.paper.title.localeCompare(b.paper.title))
      .slice(0, 6);

    els.similarList.textContent = "";
    scored.forEach(({ paper: item, score }) => {
      const card = document.createElement("article");
      card.className = "tool-card";
      const title = document.createElement("a");
      title.href = "paper.html?library=" + encodeURIComponent(library) + "&slug=" + encodeURIComponent(item.slug);
      title.textContent = item.title;
      card.appendChild(title);
      const meta = document.createElement("div");
      meta.className = "note";
      meta.textContent = [item.arxiv ? "arXiv " + item.arxiv : "", score ? score + " shared tag" + (score > 1 ? "s" : "") : "related reading"]
        .filter(Boolean)
        .join(" · ");
      card.appendChild(meta);
      const chips = document.createElement("div");
      chips.className = "chips compact-chips";
      (item.tags || []).slice(0, 4).forEach((tag) => {
        const chip = document.createElement("span");
        chip.className = "chip";
        chip.textContent = tag;
        chips.appendChild(chip);
      });
      card.appendChild(chips);
      els.similarList.appendChild(card);
    });
  }

  async function loadAnalysis(paperSlug) {
    els.analysisStatus.textContent = "Loading analysis.md";
    try {
      const response = await fetch("/api/papers/" + encodeURIComponent(paperSlug) + "/analysis?library=" + encodeURIComponent(library), { cache: "no-cache" });
      if (!response.ok) {
        throw await responseError(response, "analysis unavailable");
      }
      const data = await response.json();
      setAnalysisContent(data.content || "", { render: true, syncEditor: true });
      els.analysisStatus.textContent = "analysis.md";
    } catch (error) {
      els.analysisContent.textContent = "Analysis is unavailable: " + error.message;
      els.analysisStatus.textContent = "analysis.md unavailable";
    }
  }

  function currentAnalysisContent() {
    return state.analysisEditing ? els.analysisEditor.value : state.analysisRaw;
  }

  function setAnalysisContent(content, options) {
    const nextContent = text(content);
    const settings = Object.assign({ render: false, syncEditor: false }, options || {});
    state.analysisRaw = nextContent;
    if (settings.syncEditor || state.analysisEditing) {
      els.analysisEditor.value = nextContent;
    }
    if (settings.render || !state.analysisEditing) {
      renderAnalysis(nextContent);
    }
  }

  function renderAnalysis(content) {
    const value = text(content).trim();
    els.analysisContent.textContent = "";
    if (!value) {
      els.analysisContent.textContent = "No analysis yet.";
      return;
    }
    const body = document.createElement("div");
    body.className = "message-body analysis-rich-text";
    body.innerHTML = renderRichText(value);
    els.analysisContent.appendChild(body);
    applyAnalysisAnchors();
  }

  function applyAnalysisAnchors() {
    els.analysisContent.querySelectorAll("h2, h3, h4").forEach((heading) => {
      const match = heading.textContent.match(/\b(qa-\d{8}-\d{6})\b/);
      if (match) {
        heading.id = match[1];
      }
    });
  }

  function scrollToAnalysisAnchor(anchor) {
    setActiveTab("analysis");
    window.scrollTo(0, 0);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    window.requestAnimationFrame(() => {
      const target = document.getElementById(anchor);
      const container = els.analysisContent;
      if (target && container) {
        const targetTop = target.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop;
        container.scrollTo({
          top: Math.max(0, targetTop - 10),
          behavior: "smooth"
        });
      }
    });
  }

  function questionForAssistantMessage(message) {
    const index = state.messages.indexOf(message);
    for (let idx = index - 1; idx >= 0; idx -= 1) {
      if (state.messages[idx].role === "user") {
        return state.messages[idx].content;
      }
    }
    return "";
  }

  function setAnalysisEditing(isEditing) {
    state.analysisEditing = isEditing;
    els.analysisContent.hidden = isEditing;
    els.analysisEditor.hidden = !isEditing;
    els.analysisGenerate.hidden = isEditing;
    els.analysisEdit.hidden = isEditing;
    els.analysisSave.hidden = !isEditing;
    els.analysisCancel.hidden = !isEditing;
    if (isEditing) {
      els.analysisEditor.value = currentAnalysisContent();
      window.requestAnimationFrame(() => els.analysisEditor.focus());
    } else {
      renderAnalysis(state.analysisRaw);
    }
  }

  async function saveAnalysisEdit() {
    const content = currentAnalysisContent();
    if (!content.trim()) {
      window.alert("analysis.md 内容为空，已取消保存，避免覆盖已有解析。");
      return;
    }
    els.analysisSave.disabled = true;
    els.analysisStatus.textContent = "Saving analysis.md";
    try {
      const response = await fetch("/api/papers/" + encodeURIComponent(slug) + "/analysis?library=" + encodeURIComponent(library), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, library })
      });
      if (!response.ok) {
        throw await responseError(response, "save failed");
      }
      const data = await response.json();
      setAnalysisContent(data.content || content, { syncEditor: true });
      setAnalysisEditing(false);
      await loadContextStatus(slug);
      els.analysisStatus.textContent = "analysis.md";
    } catch (error) {
      window.alert("保存 analysis.md 失败：" + error.message);
      els.analysisStatus.textContent = "analysis.md";
    } finally {
      els.analysisSave.disabled = false;
    }
  }

  async function generateAnalysis() {
    if (state.analysisEditing) {
      return;
    }
    const originalText = els.analysisGenerate.textContent;
    els.analysisGenerate.disabled = true;
    els.analysisEdit.disabled = true;
    els.analysisStatus.textContent = "Generating analysis...";
    try {
      const response = await fetch("/api/papers/" + encodeURIComponent(slug) + "/analysis/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: els.model.value, library })
      });
      if (!response.ok) {
        throw await responseError(response, "generation failed");
      }
      const data = await response.json();
      setAnalysisContent(data.content || "", { render: true, syncEditor: true });
      await loadContextStatus(slug);
      setActiveTab("analysis");
      els.analysisStatus.textContent = "analysis.md";
    } catch (error) {
      window.alert("生成 analysis.md 失败：" + error.message);
      els.analysisStatus.textContent = "analysis.md";
    } finally {
      els.analysisGenerate.disabled = false;
      els.analysisEdit.disabled = false;
      els.analysisGenerate.textContent = originalText;
    }
  }

  function setupAnalysisEditor() {
    els.analysisGenerate.addEventListener("click", () => generateAnalysis());
    els.analysisEdit.addEventListener("click", () => setAnalysisEditing(true));
    els.analysisCancel.addEventListener("click", () => setAnalysisEditing(false));
    els.analysisSave.addEventListener("click", () => saveAnalysisEdit());
  }

  async function saveMessageToQa(message, button) {
    if (!slug || !message || !message.content) {
      return;
    }
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = "正在整理...";
    try {
      const response = await fetch("/api/papers/" + encodeURIComponent(slug) + "/analysis/qa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          library,
          question: questionForAssistantMessage(message),
          answer: message.content
        })
      });
      if (!response.ok) {
        throw await responseError(response, "save failed");
      }
      const data = await response.json();
      message.saved_to_qa = true;
      message.analysis_anchor = data.anchor || "";
      await saveConversationToServer(state.messages);
      setAnalysisContent(data.content || "", { render: !state.analysisEditing, syncEditor: true });
      await loadContextStatus(slug);
      renderConversation(state.messages);
      if (message.analysis_anchor) {
        scrollToAnalysisAnchor(message.analysis_anchor);
      }
    } catch (error) {
      button.disabled = false;
      button.textContent = originalText;
      window.alert("保存到 QA 失败：" + error.message);
    }
  }

  async function sendMessage(content) {
    addMessage("user", content);
    setBusy(true);
    const pending = createPendingMessage();
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          library,
          paper_slug: slug,
          model: els.model.value,
          message: content
        })
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || "请求失败");
      }

      const data = await response.json();
      pending.remove();
      if (Array.isArray(data.messages)) {
        renderConversation(data.messages);
      } else {
        addMessage("assistant", data.answer, data.sources || [], {
          incomplete: Boolean(data.incomplete),
          incomplete_reason: data.incomplete_reason || "",
          model: data.model || els.model.value
        });
      }
    } catch (error) {
      pending.remove();
      addMessage("assistant", "Chat service is unavailable: " + error.message);
    } finally {
      setBusy(false);
      els.input.focus();
    }
  }

  async function continueMessage(message) {
    setBusy(true);
    const pending = createPendingMessage();
    const messageIndex = state.messages.indexOf(message);
    const continuePrompt = "请从上一条 assistant 回答被截断的位置继续生成，不要重复已经写过的内容。请确保续写内容中的 Markdown 和 LaTeX 分隔符成对闭合。";

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          library,
          paper_slug: slug,
          model: els.model.value,
          message: continuePrompt,
          continue_message_index: messageIndex
        })
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || "请求失败");
      }

      const data = await response.json();
      pending.remove();
      if (Array.isArray(data.messages)) {
        renderConversation(data.messages);
      } else {
        message.content = message.content + "\n\n" + data.answer;
        message.sources = Array.isArray(data.sources)
          ? (message.sources || []).concat(data.sources)
          : message.sources || [];
        message.incomplete = Boolean(data.incomplete);
        message.incomplete_reason = data.incomplete_reason || "";
        message.model = data.model || els.model.value;
        message.saved_to_qa = false;
        message.analysis_anchor = "";
        await saveConversationToServer(state.messages);
        renderConversation(state.messages);
      }
    } catch (error) {
      pending.remove();
      addMessage("assistant", "Continue generation failed: " + error.message);
    } finally {
      setBusy(false);
      els.input.focus();
    }
  }

  async function regenerateMessage(message) {
    const messageIndex = state.messages.indexOf(message);
    if (messageIndex < 0) {
      return;
    }
    setBusy(true);
    const pending = createPendingMessage();
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          library,
          paper_slug: slug,
          model: els.model.value,
          regenerate_message_index: messageIndex
        })
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || "请求失败");
      }

      const data = await response.json();
      pending.remove();
      if (Array.isArray(data.messages)) {
        renderConversation(data.messages);
      } else {
        message.content = data.answer || message.content;
        message.sources = Array.isArray(data.sources) ? data.sources : [];
        message.incomplete = Boolean(data.incomplete);
        message.incomplete_reason = data.incomplete_reason || "";
        message.model = data.model || els.model.value;
        message.saved_to_qa = false;
        message.analysis_anchor = "";
        await saveConversationToServer(state.messages);
        renderConversation(state.messages);
      }
    } catch (error) {
      pending.remove();
      window.alert("重新生成失败：" + error.message);
    } finally {
      setBusy(false);
      els.input.focus();
    }
  }

  els.form.addEventListener("submit", function (event) {
    event.preventDefault();
    const content = els.input.value.trim();
    if (!content) {
      return;
    }
    els.input.value = "";
    sendMessage(content);
  });

  els.input.addEventListener("keydown", function (event) {
    if (event.key !== "Enter") {
      return;
    }
    if (event.ctrlKey || event.metaKey) {
      const start = els.input.selectionStart;
      const end = els.input.selectionEnd;
      const value = els.input.value;
      els.input.value = value.slice(0, start) + "\n" + value.slice(end);
      els.input.selectionStart = start + 1;
      els.input.selectionEnd = start + 1;
      event.preventDefault();
      return;
    }
    event.preventDefault();
    els.form.requestSubmit();
  });

  setupTabs();
  setupModelSelect();
  setupAnalysisEditor();
  setupSplitter();
  loadPaper().catch((error) => {
    els.title.textContent = "无法打开文章";
    els.contextStatus.textContent = error.message;
    addMessage("assistant", error.message);
  });
})();
