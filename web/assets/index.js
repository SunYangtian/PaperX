(function () {
  const RECENT_PAPERS_KEY = "paper-recent-slugs";
  const ACTIVE_LIBRARY_KEY = "paper-active-library";
  const params = new URLSearchParams(window.location.search);
  const state = {
    libraries: [],
    activeLibrary: params.get("library") || window.localStorage.getItem(ACTIVE_LIBRARY_KEY) || "default"
  };
  const els = {
    form: document.getElementById("importPaperForm"),
    input: document.getElementById("paperUrlInput"),
    fileInput: document.getElementById("paperFileInput"),
    fileLabel: document.getElementById("paperFileLabel"),
    button: document.getElementById("importPaperButton"),
    status: document.getElementById("importStatus"),
    grid: document.getElementById("paperGrid"),
    library: document.getElementById("librarySelect"),
    allPapers: document.getElementById("allPapersLink")
  };

  function setStatus(message, isError) {
    els.status.textContent = message || "";
    els.status.classList.toggle("error", Boolean(isError));
  }

  function getRecentKey() {
    return RECENT_PAPERS_KEY + ":" + state.activeLibrary;
  }

  function updateLibraryLinks() {
    if (els.allPapers) {
      els.allPapers.href = "all_papers_classification.html?library=" + encodeURIComponent(state.activeLibrary);
    }
  }

  function setActiveLibrary(library) {
    state.activeLibrary = library || "default";
    window.localStorage.setItem(ACTIVE_LIBRARY_KEY, state.activeLibrary);
    const url = new URL(window.location.href);
    url.searchParams.set("library", state.activeLibrary);
    window.history.replaceState({}, "", url);
    updateLibraryLinks();
  }

  async function loadLibraries() {
    const response = await fetch("/api/libraries", { cache: "no-cache" });
    if (!response.ok) {
      throw new Error("无法加载 library 列表");
    }
    const data = await response.json();
    state.libraries = Array.isArray(data.libraries) ? data.libraries : [{ id: "default", name: "Default" }];
    if (!state.libraries.some((library) => library.id === state.activeLibrary)) {
      state.activeLibrary = data.default || "default";
    }
    els.library.textContent = "";
    state.libraries.forEach((library) => {
      const option = document.createElement("option");
      option.value = library.id;
      option.textContent = library.name || library.id;
      els.library.appendChild(option);
    });
    els.library.value = state.activeLibrary;
    setActiveLibrary(state.activeLibrary);
  }

  function loadRecentSlugs() {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(getRecentKey()) || "[]");
      return Array.isArray(parsed) ? parsed.filter(Boolean) : [];
    } catch (error) {
      return [];
    }
  }

  function recentPapers(papers) {
    const bySlug = new Map(papers.map((paper) => [paper.slug, paper]));
    return loadRecentSlugs()
      .map((slug) => bySlug.get(slug))
      .filter(Boolean)
      .slice(0, 6);
  }

  async function loadPapers() {
    const response = await fetch("libraries/" + encodeURIComponent(state.activeLibrary) + "/papers.json", { cache: "no-cache" });
    if (!response.ok) {
      throw new Error("无法加载当前 library 的 papers.json");
    }
    const papers = await response.json();
    renderPapers(recentPapers(papers));
  }

  function renderPapers(papers) {
    els.grid.textContent = "";
    if (!papers.length) {
      const empty = document.createElement("p");
      empty.className = "note";
      empty.textContent = "还没有最近阅读记录。";
      els.grid.appendChild(empty);
      return;
    }
    papers.forEach((paper) => {
      const card = document.createElement("article");
      card.className = "card";

      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = [paper.arxiv ? "arXiv " + paper.arxiv : "", paper.status || "", paper.updated || ""]
        .filter(Boolean)
        .join(" · ");
      card.appendChild(meta);

      const title = document.createElement("h2");
      const titleLink = document.createElement("a");
      titleLink.href = "paper.html?library=" + encodeURIComponent(state.activeLibrary) + "&slug=" + encodeURIComponent(paper.slug);
      titleLink.textContent = paper.title || paper.slug;
      title.appendChild(titleLink);
      card.appendChild(title);

      const desc = document.createElement("p");
      desc.textContent = paper.summary || "已加入本地论文库，可在工作台中阅读 PDF 并对话分析。";
      card.appendChild(desc);

      const chips = document.createElement("div");
      chips.className = "chips";
      (paper.tags || ["imported"]).slice(0, 4).forEach((tag, idx) => {
        const chip = document.createElement("span");
        chip.className = "chip" + (idx === 3 ? " blue" : "");
        chip.textContent = tag;
        chips.appendChild(chip);
      });
      card.appendChild(chips);

      const actions = document.createElement("div");
      actions.className = "card-actions";

      const open = document.createElement("a");
      open.className = "button";
      open.href = "paper.html?library=" + encodeURIComponent(state.activeLibrary) + "&slug=" + encodeURIComponent(paper.slug);
      open.textContent = "打开工作台";
      actions.appendChild(open);

      const pdf = document.createElement("a");
      pdf.className = "button";
      pdf.href = paper.pdf;
      pdf.textContent = "打开 PDF";
      actions.appendChild(pdf);

      card.appendChild(actions);

      els.grid.appendChild(card);
    });
  }

  async function importPaper(url) {
    els.button.disabled = true;
    setStatus("正在下载并整理 PDF...", false);
    try {
      const response = await fetch("/api/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, library: state.activeLibrary })
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.error || "导入失败");
      }
      setStatus((data.existing ? "已存在：" : "已导入：") + data.paper.title, false);
      els.input.value = "";
      await loadPapers();
      window.location.href = "paper.html?library=" + encodeURIComponent(state.activeLibrary) + "&slug=" + encodeURIComponent(data.paper.slug);
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      els.button.disabled = false;
    }
  }

  async function uploadPaper(file) {
    els.button.disabled = true;
    setStatus("正在上传并整理 PDF...", false);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("library", state.activeLibrary);
      const response = await fetch("/api/import-file", {
        method: "POST",
        body: formData
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.error || "上传失败");
      }
      setStatus((data.existing ? "已存在：" : "已上传：") + data.paper.title, false);
      els.fileInput.value = "";
      els.fileLabel.textContent = "选择文件";
      await loadPapers();
      window.location.href = "paper.html?library=" + encodeURIComponent(state.activeLibrary) + "&slug=" + encodeURIComponent(data.paper.slug);
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      els.button.disabled = false;
    }
  }

  els.form.addEventListener("submit", (event) => {
    event.preventDefault();
    const file = els.fileInput.files && els.fileInput.files[0];
    if (file) {
      uploadPaper(file);
      return;
    }
    const url = els.input.value.trim();
    if (!url) {
      setStatus("请输入 PDF 链接或选择本地 PDF 文件", true);
      return;
    }
    importPaper(url);
  });

  els.fileInput.addEventListener("change", () => {
    const file = els.fileInput.files && els.fileInput.files[0];
    if (!file) {
      els.fileLabel.textContent = "选择文件";
      return;
    }
    els.input.value = file.name;
    els.fileLabel.textContent = "已选择";
    setStatus("已选择本地 PDF：" + file.name, false);
  });

  els.input.addEventListener("input", () => {
    if (!els.input.value.trim()) {
      return;
    }
    if (els.fileInput.value) {
      els.fileInput.value = "";
      els.fileLabel.textContent = "选择文件";
    }
  });

  els.library.addEventListener("change", async () => {
    setActiveLibrary(els.library.value);
    await loadPapers().catch((error) => setStatus(error.message, true));
  });

  loadLibraries()
    .then(loadPapers)
    .catch((error) => setStatus(error.message, true));
})();
