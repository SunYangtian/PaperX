from __future__ import annotations

import json
import os
import re
import hashlib
import hmac
import html
import shutil
import socket
import ssl
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from xml.etree import ElementTree

from flask import Flask, jsonify, redirect, render_template_string, request, send_from_directory, session, url_for


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
LIBRARIES_JSON = WEB_DIR / "libraries.json"
LIBRARIES_DIR = WEB_DIR / "libraries"
DEFAULT_LIBRARY = "default"
PDF_DIR = ROOT / "papers" / "pdfs"
CHAT_HISTORY_MESSAGE_LIMIT = 20
CHAT_HISTORY_CHAR_LIMIT = 18000

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5.5"
AVAILABLE_CHAT_MODELS = {
    "qwen3.7-max[1M]",
    "qwen3-vl-plus",
    "qwen3-vl-flash",
    "deepseek-v4-pro[1M]",
    "claude-opus-4-6",
    "gpt-5.5",
    "gemini-3.1-pro-preview",
    "glm-5.1",
    "kimi-k2.6",
    "minimax-m2.7",
}


def strip_env_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        if key not in os.environ:
            os.environ[key] = strip_env_quotes(value)


load_dotenv(ROOT / ".env")

app = Flask(__name__)

LOGIN_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PaperX Login</title>
  <style>
    :root {
      --bg: #f8fbff;
      --panel: #ffffff;
      --ink: #1f2937;
      --muted: #5f6f89;
      --line: #d7e3f4;
      --accent: #4285f4;
      --accent-dark: #1a73e8;
      --warn: #ea4335;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    main {
      width: min(420px, calc(100vw - 32px));
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 28px;
      box-shadow: 0 10px 30px rgba(66, 133, 244, 0.1);
    }
    h1 {
      margin: 0 0 8px;
      font-size: 26px;
      line-height: 1.2;
      letter-spacing: 0;
    }
    p {
      margin: 0 0 22px;
      color: var(--muted);
    }
    label {
      display: block;
      margin-bottom: 8px;
      font-weight: 650;
    }
    input {
      width: 100%;
      min-height: 44px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 12px;
      font: inherit;
      color: var(--ink);
      background: #fff;
    }
    input:focus {
      border-color: var(--accent);
      outline: 3px solid rgba(66, 133, 244, 0.16);
    }
    button {
      width: 100%;
      min-height: 44px;
      margin-top: 16px;
      border: 0;
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }
    button:hover { background: var(--accent-dark); }
    .error {
      margin: 0 0 14px;
      color: var(--warn);
      font-weight: 650;
    }
  </style>
</head>
<body>
  <main>
    <h1>PaperX</h1>
    <p>Enter the access password to continue.</p>
    {% if error %}<div class="error">Invalid password.</div>{% endif %}
    <form method="post" action="{{ url_for('login') }}">
      <input type="hidden" name="next" value="{{ next_url }}">
      <label for="password">Password</label>
      <input id="password" name="password" type="password" autocomplete="current-password" autofocus required>
      <button type="submit">Unlock</button>
    </form>
  </main>
</body>
</html>
"""


@dataclass(frozen=True)
class Chunk:
    label: str
    file: str
    text: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def configured_access_password() -> str:
    return str(os.environ.get("PAPERX_ACCESS_PASSWORD") or "").strip()


def configure_app_security() -> None:
    access_password = configured_access_password()
    secret_key = os.environ.get("PAPERX_SECRET_KEY")
    if not secret_key and access_password:
        secret_key = hashlib.sha256(f"paperx:{access_password}".encode("utf-8")).hexdigest()
    app.secret_key = secret_key or "paperx-local-dev"
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=parse_bool(os.environ.get("PAPERX_COOKIE_SECURE"), default=False),
    )


def auth_enabled() -> bool:
    return bool(configured_access_password())


def safe_next_url(value: str = "") -> str:
    value = str(value or "")
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/") or value.startswith("//"):
        return url_for("index")
    return value


def login_response(error: bool = False, status: int = 200):
    next_url = safe_next_url(request.values.get("next") or "/")
    return (
        render_template_string(LOGIN_TEMPLATE, error=error, next_url=next_url),
        status,
    )


configure_app_security()


@app.before_request
def require_access_password():
    if not auth_enabled():
        return None
    if request.endpoint in {"login", "logout"}:
        return None
    if session.get("paperx_authenticated") is True:
        return None
    if request.path.startswith("/api/"):
        return jsonify({"error": "authentication_required"}), 401
    next_url = request.full_path if request.query_string else request.path
    return redirect(url_for("login", next=next_url))


@app.route("/login", methods=["GET", "POST"])
def login():
    if not auth_enabled():
        return redirect(url_for("index"))
    if request.method == "GET":
        if session.get("paperx_authenticated") is True:
            return redirect(safe_next_url(request.args.get("next") or "/"))
        return login_response()

    password = str(request.form.get("password") or "")
    if hmac.compare_digest(password, configured_access_password()):
        session.clear()
        session["paperx_authenticated"] = True
        return redirect(safe_next_url(request.form.get("next") or "/"))
    return login_response(error=True, status=401)


@app.get("/logout")
def logout():
    session.clear()
    if auth_enabled():
        return redirect(url_for("login"))
    return redirect(url_for("index"))


def model_runtime_config() -> dict[str, Any]:
    provider_name = os.environ.get("PAPER_MODEL_PROVIDER") or "openai"
    base_url = os.environ.get("OPENAI_BASE_URL") or DEFAULT_OPENAI_BASE_URL
    base_url = str(base_url).rstrip("/")
    responses_path = str(os.environ.get("OPENAI_RESPONSES_PATH") or "/responses")
    if not responses_path.startswith("/"):
        responses_path = "/" + responses_path
    api_url = (
        os.environ.get("OPENAI_RESPONSES_URL")
        or f"{base_url}{responses_path}"
    )
    explicit_env_key = os.environ.get("OPENAI_ENV_KEY")
    env_key = explicit_env_key or "OPENAI_API_KEY"
    if explicit_env_key:
        api_key = os.environ.get(str(explicit_env_key)) or os.environ.get("OPENAI_API_KEY")
    else:
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get(str(env_key))
    requires_openai_auth = os.environ.get("REQUIRES_OPENAI_AUTH")

    return {
        "model": os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL,
        "api_url": api_url,
        "api_key": api_key,
        "env_key": env_key,
        "provider": provider_name,
        "requires_openai_auth": parse_bool(requires_openai_auth, default=True),
        "max_output_tokens": int(os.environ.get("MAX_OUTPUT_TOKENS") or 1200),
        "timeout_seconds": int(os.environ.get("OPENAI_TIMEOUT_SECONDS") or 180),
    }


def analysis_runtime_config() -> dict[str, int]:
    return {
        "source_char_limit": int(os.environ.get("ANALYSIS_SOURCE_CHAR_LIMIT") or 70000),
        "max_output_tokens": int(os.environ.get("ANALYSIS_MAX_OUTPUT_TOKENS") or 3000),
        "timeout_seconds": int(os.environ.get("ANALYSIS_TIMEOUT_SECONDS") or 240),
    }


def normalize_library_id(value: str = "") -> str:
    library = str(value or DEFAULT_LIBRARY).strip() or DEFAULT_LIBRARY
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", library):
        return DEFAULT_LIBRARY
    return library


def request_library(payload: Optional[dict[str, Any]] = None) -> str:
    if payload and payload.get("library"):
        return normalize_library_id(str(payload.get("library")))
    return normalize_library_id(request.args.get("library") or DEFAULT_LIBRARY)


def library_dir(library: str = DEFAULT_LIBRARY) -> Path:
    return LIBRARIES_DIR / normalize_library_id(library)


def library_papers_json(library: str = DEFAULT_LIBRARY) -> Path:
    return library_dir(library) / "papers.json"


def library_ids() -> list[str]:
    ids = {DEFAULT_LIBRARY}
    if LIBRARIES_JSON.exists():
        try:
            libraries = json.loads(read_text(LIBRARIES_JSON))
        except json.JSONDecodeError:
            libraries = []
        if isinstance(libraries, list):
            for library in libraries:
                if isinstance(library, dict):
                    ids.add(normalize_library_id(str(library.get("id") or "")))
    if LIBRARIES_DIR.exists():
        ids.update(path.name for path in LIBRARIES_DIR.iterdir() if path.is_dir())
    return sorted(ids)


@lru_cache(maxsize=32)
def load_papers(library: str = DEFAULT_LIBRARY) -> list[dict[str, Any]]:
    path = library_papers_json(library)
    if not path.exists():
        return []
    return json.loads(read_text(path))


def save_papers(papers: list[dict[str, Any]], library: str = DEFAULT_LIBRARY) -> None:
    write_text(library_papers_json(library), json.dumps(papers, ensure_ascii=False, indent=2))
    load_papers.cache_clear()


def existing_paper_slugs(library: str = DEFAULT_LIBRARY) -> set[str]:
    slugs = {str(paper.get("slug")) for paper in load_papers(library) if paper.get("slug")}
    papers_dir = library_dir(library) / "papers"
    if papers_dir.exists():
        slugs.update(path.name for path in papers_dir.iterdir() if path.is_dir())
    return slugs


def paper_hash_for_source(pdf_url: str, arxiv_id: str = "") -> str:
    source = f"arxiv:{arxiv_id}" if arxiv_id else f"pdf:{pdf_url}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def paper_hash_for_bytes(pdf_bytes: bytes) -> str:
    content_hash = hashlib.sha256(pdf_bytes).hexdigest()
    return hashlib.sha256(f"file:{content_hash}".encode("utf-8")).hexdigest()[:16]


def paper_dir_for_slug(slug: str, library: str = DEFAULT_LIBRARY) -> Path:
    return library_dir(library) / "papers" / slug


def paper_assets_exist(paper: dict[str, Any], library: str = DEFAULT_LIBRARY) -> bool:
    slug = str(paper.get("slug") or "")
    return bool(slug) and paper_dir_for_slug(slug, library).exists()


def paper_pdf_filename(paper: dict[str, Any]) -> str:
    pdf = str(paper.get("pdf") or "")
    if not pdf:
        return ""
    return Path(urlparse(pdf).path).name


def paper_matches_source(paper: dict[str, Any], url: str, pdf_url: str, arxiv_id: str) -> bool:
    pdf_name = safe_filename_from_url(pdf_url)
    normalized_candidates = {normalize_pdf_url(url), pdf_url}
    paper_arxiv = str(paper.get("arxiv") or "")
    if arxiv_id and paper_arxiv == arxiv_id:
        return True

    for key in ("pdf_url", "source_url"):
        value = str(paper.get(key) or "").strip()
        if value and normalize_pdf_url(value) in normalized_candidates:
            return True

    return bool(pdf_name and paper_pdf_filename(paper) == pdf_name)


def find_existing_paper(url: str, pdf_url: str, arxiv_id: str, library: str = DEFAULT_LIBRARY) -> dict[str, Any] | None:
    paper_hash = paper_hash_for_source(pdf_url, arxiv_id)
    for paper in load_papers(library):
        if not paper_matches_source(paper, url, pdf_url, arxiv_id):
            continue
        if paper_assets_exist(paper, library) or paper_dir_for_slug(paper_hash, library).exists():
            return paper
    return None


def find_existing_paper_by_hash(paper_hash: str, library: str = DEFAULT_LIBRARY) -> dict[str, Any] | None:
    for paper in load_papers(library):
        if paper.get("hash") == paper_hash or paper.get("slug") == paper_hash:
            if paper_assets_exist(paper, library) or paper_dir_for_slug(paper_hash, library).exists():
                return paper
    return None


def pdf_path_for_paper(paper: dict[str, Any]) -> Path | None:
    filename = paper_pdf_filename(paper)
    if not filename:
        return None
    return PDF_DIR / filename


def pdf_url_for_paper(paper: dict[str, Any]) -> str:
    for key in ("pdf_url", "source_url"):
        value = str(paper.get(key) or "").strip()
        if value:
            return normalize_pdf_url(value)
    arxiv_id = str(paper.get("arxiv") or "").strip()
    if arxiv_id:
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    return ""


def ensure_pdf_text_assets(pdf_path: Path, paper: dict[str, Any], library: str = DEFAULT_LIBRARY) -> None:
    paper_dir = paper_dir_for_slug(str(paper.get("slug") or ""), library)
    extracted = paper_dir / "extracted" / "full_text.txt"
    if paper_dir.exists() and not extracted.exists():
        extract_pdf_assets(pdf_path, paper_dir)


def ensure_paper_pdf(paper: dict[str, Any], library: str = DEFAULT_LIBRARY) -> dict[str, Any]:
    pdf_path = pdf_path_for_paper(paper)
    if pdf_path and pdf_path.exists():
        try:
            ensure_pdf_text_assets(pdf_path, paper, library)
        except Exception:
            pass
        return {"available": True, "downloaded": False}

    pdf_url = pdf_url_for_paper(paper)
    if not pdf_url:
        return {"available": False, "downloaded": False, "error": "no PDF URL is recorded for this paper"}

    pdf_name = paper_pdf_filename(paper) or safe_filename_from_url(pdf_url)
    pdf_path = PDF_DIR / pdf_name
    if not str(paper.get("pdf") or "").strip():
        paper["pdf"] = f"../papers/pdfs/{pdf_name}"

    if pdf_path.exists():
        try:
            ensure_pdf_text_assets(pdf_path, paper, library)
        except Exception:
            pass
        return {"available": True, "downloaded": False}

    try:
        pdf_bytes = download_url(pdf_url)
    except Exception as exc:
        return {"available": False, "downloaded": False, "error": f"failed to download pdf: {exc}"}

    if not pdf_bytes.lstrip().startswith(b"%PDF"):
        return {"available": False, "downloaded": False, "error": "downloaded file is not a PDF"}

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(pdf_bytes)

    try:
        ensure_pdf_text_assets(pdf_path, paper, library)
    except Exception:
        pass

    load_context.cache_clear()
    return {"available": True, "downloaded": True, "url": pdf_url}


def is_pdf_referenced(pdf_path: Path, excluding_slug: str = "", excluding_library: str = DEFAULT_LIBRARY) -> bool:
    for library in library_ids():
        for paper in load_papers(library):
            if library == excluding_library and paper.get("slug") == excluding_slug:
                continue
            if pdf_path_for_paper(paper) == pdf_path:
                return True
    return False


def is_generic_import_title(title: str, arxiv_id: str = "") -> bool:
    normalized = title.strip().lower()
    if not normalized:
        return True
    if arxiv_id:
        arxiv_forms = {
            arxiv_id.lower(),
            arxiv_id.lower().replace(".", "-"),
            "arxiv " + arxiv_id.lower(),
        }
        if normalized in arxiv_forms:
            return True
    return normalized in {"paper", "imported paper"}


def normalize_existing_import(
    matched_paper: dict[str, Any],
    url: str,
    pdf_url: str,
    arxiv_id: str,
    paper_hash: str,
    library: str = DEFAULT_LIBRARY,
) -> dict[str, Any]:
    library = normalize_library_id(library)
    papers = list(load_papers(library))
    paper = next((item for item in papers if item.get("slug") == matched_paper.get("slug")), matched_paper)
    original_slug = str(paper.get("slug") or "")
    target_slug = paper_hash if paper.get("status") == "imported" else original_slug
    pdf_name = safe_filename_from_url(pdf_url)

    if target_slug and target_slug != original_slug:
        old_dir = paper_dir_for_slug(original_slug, library)
        new_dir = paper_dir_for_slug(target_slug, library)
        if old_dir.exists() and not new_dir.exists():
            old_dir.rename(new_dir)
            paper["slug"] = target_slug
        elif new_dir.exists():
            paper["slug"] = target_slug

    paper["hash"] = paper_hash
    paper["library"] = library
    paper["arxiv"] = arxiv_id or paper.get("arxiv", "")
    paper["pdf_url"] = pdf_url
    paper.setdefault("source_url", url)
    paper["page"] = f"libraries/{library}/papers/{paper.get('slug')}/index.html"

    title = str(paper.get("title") or "")
    if arxiv_id and is_generic_import_title(title, arxiv_id):
        arxiv_title = fetch_arxiv_title(arxiv_id)
        if arxiv_title:
            paper["title"] = arxiv_title
        else:
            pdf_path = pdf_path_for_paper(paper)
            if pdf_path and pdf_path.exists():
                pdf_title = infer_title_from_pdf_bytes(pdf_path.read_bytes())
                if pdf_title:
                    paper["title"] = pdf_title

    paper_dir = paper_dir_for_slug(str(paper.get("slug") or ""), library)
    if paper_dir.exists():
        current_title = str(paper.get("title") or paper.get("slug"))
        current_slug = str(paper.get("slug"))
        write_paper_index(paper_dir, current_title, pdf_name, current_slug, library)
        if paper.get("status") == "imported":
            write_import_analysis(paper_dir, current_title, url, pdf_url, paper_hash, current_slug)

    save_papers(papers, library)
    load_context.cache_clear()
    return paper


def slugify_title(title: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
    return slug or "paper"


def infer_title_from_pdf_filename(url: str, pdf_bytes: bytes) -> str:
    parsed = urlparse(url)
    filename = Path(parsed.path).name or "paper.pdf"
    stem = filename.replace(".pdf", "").replace("_", " ").replace("-", " ").strip()
    if stem:
      return stem
    return "Imported Paper"


def safe_filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    filename = Path(parsed.path).name or "paper.pdf"
    if not filename.lower().endswith(".pdf"):
        filename = filename + ".pdf"
    filename = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)
    return filename


def safe_uploaded_filename(filename: str, fallback: str) -> str:
    filename = Path(filename or "").name or fallback
    if not filename.lower().endswith(".pdf"):
        filename = filename + ".pdf"
    filename = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._")
    return filename or fallback


def download_url(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120, context=ssl.create_default_context()) as response:
        return response.read()


def clean_title(title: str) -> str:
    title = html.unescape(title)
    title = re.sub(r"\s+", " ", title).strip()
    return title.strip(" .")


def fetch_arxiv_title(arxiv_id: str) -> str:
    if not arxiv_id:
        return ""

    api_url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
    try:
        payload = download_url(api_url).decode("utf-8", errors="replace")
        root = ElementTree.fromstring(payload)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        title_node = root.find("atom:entry/atom:title", ns)
        if title_node is not None and title_node.text:
            return clean_title(title_node.text)
    except Exception:
        pass

    abs_url = f"https://arxiv.org/abs/{arxiv_id}"
    try:
        payload = download_url(abs_url).decode("utf-8", errors="replace")
        match = re.search(r'<meta\s+name=["\']citation_title["\']\s+content=["\']([^"\']+)["\']', payload)
        if match:
            return clean_title(match.group(1))
        match = re.search(r"<title>\s*\[[^\]]+\]\s*(.*?)\s*</title>", payload, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return clean_title(match.group(1))
    except Exception:
        pass

    return ""


def infer_title_from_pdf_bytes(pdf_bytes: bytes) -> str:
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        metadata_title = clean_title(str(doc.metadata.get("title") or ""))
        if metadata_title and not is_generic_import_title(metadata_title):
            return metadata_title

        if doc.page_count:
            page_text = doc[0].get_text("text")
            for line in page_text.splitlines():
                candidate = clean_title(line)
                if len(candidate) >= 12 and not candidate.lower().startswith(("arxiv:", "abstract")):
                    return candidate
    except Exception:
        return ""
    return ""


def infer_paper_title(url: str, pdf_url: str, arxiv_id: str, pdf_bytes: bytes) -> str:
    arxiv_title = fetch_arxiv_title(arxiv_id)
    if arxiv_title:
        return arxiv_title

    pdf_title = infer_title_from_pdf_bytes(pdf_bytes)
    if pdf_title:
        return pdf_title

    return infer_title_from_pdf_filename(pdf_url or url, pdf_bytes)


def infer_uploaded_paper_title(filename: str, pdf_bytes: bytes) -> str:
    pdf_title = infer_title_from_pdf_bytes(pdf_bytes)
    if pdf_title:
        return pdf_title
    return infer_title_from_pdf_filename(filename, pdf_bytes)


def is_arxiv_host(host: str) -> bool:
    return host == "arxiv.org" or host.endswith(".arxiv.org")


def extract_arxiv_id(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")
    if not is_arxiv_host(host):
        return ""
    if path.startswith("abs/"):
        arxiv_id = path.removeprefix("abs/").strip("/")
    elif path.startswith("pdf/"):
        arxiv_id = path.removeprefix("pdf/").strip("/")
    else:
        return ""
    return arxiv_id.removesuffix(".pdf")


def normalize_pdf_url(url: str) -> str:
    arxiv_id = extract_arxiv_id(url)
    if arxiv_id:
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    return url


def extract_pdf_assets(pdf_path: Path, paper_dir: Path) -> None:
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    extracted = paper_dir / "extracted"
    text_dir = extracted / "text_pages"
    text_dir.mkdir(parents=True, exist_ok=True)

    full_text_parts: list[str] = []
    for index, page in enumerate(doc, start=1):
        page_number = f"{index:02d}"
        page_text = page.get_text("text").strip()
        full_text_parts.append(f"--- page {index} ---\n{page_text}")
        write_text(text_dir / f"page_{page_number}.txt", page_text + "\n")

    write_text(extracted / "full_text.txt", "\n\n".join(full_text_parts).strip() + "\n")


def infer_tags(title: str, full_text: str) -> list[str]:
    text = (title + " " + full_text).lower()
    candidates = [
        ("world model", "world model"),
        ("memory", "memory"),
        ("video", "video"),
        ("interactive", "interactive"),
        ("game", "game"),
        ("dataset", "dataset"),
        ("benchmark", "benchmark"),
        ("diffusion", "diffusion"),
        ("action", "action"),
        ("3d", "3D"),
        ("latent", "latent"),
    ]
    tags = [label for needle, label in candidates if needle in text]
    return tags[:4] or ["imported"]


def write_paper_index(paper_dir: Path, title: str, pdf_name: str, slug: str, library: str = DEFAULT_LIBRARY) -> None:
    escaped_title = html.escape(title)
    escaped_library = html.escape(normalize_library_id(library))
    write_text(
        paper_dir / "index.html",
        f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{escaped_title}</title>
  <link rel=\"icon\" type=\"image/svg+xml\" href=\"/assets/Google_Scholar_logo.svg\">
  <link rel=\"stylesheet\" href=\"/assets/style.css\">
</head>
<body>
  <header>
    <div class=\"wrap\">
      <div class=\"meta\">Imported paper</div>
      <h1>{escaped_title}</h1>
      <nav class=\"nav\">
        <a class=\"button\" href=\"/index.html?library={escaped_library}\">返回索引</a>
        <a class=\"button primary\" href=\"/papers/pdfs/{html.escape(pdf_name)}\">打开 PDF</a>
        <a class=\"button\" href=\"/paper.html?library={escaped_library}&slug={html.escape(slug)}\">打开工作台</a>
      </nav>
    </div>
  </header>
</body>
</html>
""",
    )


def write_import_analysis(paper_dir: Path, title: str, url: str, pdf_url: str, paper_hash: str, slug: str) -> None:
    write_text(
        paper_dir / "analysis.md",
        f"# {title}\n\n- Imported from: {url}\n- PDF URL: {pdf_url}\n- Hash: {paper_hash}\n- Slug: {slug}\n- Status: imported\n",
    )


def get_paper(slug: str, library: str = DEFAULT_LIBRARY) -> dict[str, Any] | None:
    for paper in load_papers(library):
        if paper.get("slug") == slug:
            return paper
    return None


def split_text(label: str, file_name: str, content: str) -> list[Chunk]:
    blocks = [block.strip() for block in re.split(r"\n{2,}", content) if block.strip()]
    chunks: list[Chunk] = []
    current: list[str] = []
    current_len = 0

    for block in blocks:
        block_len = len(block)
        if current and current_len + block_len > 1600:
            chunks.append(Chunk(label=label, file=file_name, text="\n\n".join(current)))
            current = []
            current_len = 0
        current.append(block)
        current_len += block_len

    if current:
        chunks.append(Chunk(label=label, file=file_name, text="\n\n".join(current)))
    return chunks


@lru_cache(maxsize=128)
def load_context(library: str, slug: str) -> tuple[Chunk, ...]:
    library = normalize_library_id(library)
    paper = get_paper(slug, library)
    if not paper:
        return tuple()

    paper_dir = paper_dir_for_slug(slug, library)
    chunks: list[Chunk] = []

    for name in ("analysis.md",):
        path = paper_dir / name
        if path.exists():
            chunks.extend(split_text(name, name, read_text(path)))

    full_text = paper_dir / "extracted" / "full_text.txt"
    if full_text.exists():
        chunks.extend(split_text("full text", "extracted/full_text.txt", read_text(full_text)))

    pages_dir = paper_dir / "extracted" / "text_pages"
    if pages_dir.exists():
        for page_path in sorted(pages_dir.glob("page_*.txt")):
            page_match = re.search(r"page_(\d+)", page_path.stem)
            page_label = "page " + str(int(page_match.group(1))) if page_match else page_path.stem
            page_text = read_text(page_path).strip()
            if page_text:
                chunks.append(Chunk(label=page_label, file=f"extracted/text_pages/{page_path.name}", text=page_text))

    return tuple(chunks)


def tokenize(text: str) -> set[str]:
    terms = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_.+-]*|[\u4e00-\u9fff]{2,}", text.lower())
    return {term for term in terms if len(term) > 1}


def retrieve(library: str, slug: str, query: str, limit: int = 6) -> list[Chunk]:
    query_terms = tokenize(query)
    if not query_terms:
        return list(load_context(library, slug)[:limit])

    scored: list[tuple[float, Chunk]] = []
    for chunk in load_context(library, slug):
        text_lower = chunk.text.lower()
        chunk_terms = tokenize(chunk.text)
        overlap = len(query_terms & chunk_terms)
        phrase_bonus = 2.5 if query.lower() in text_lower else 0
        score = overlap + phrase_bonus
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return list(load_context(library, slug)[:limit])
    return [chunk for _, chunk in scored[:limit]]


def format_conversation(messages: list[dict[str, Any]]) -> str:
    selected: list[str] = []
    used_chars = 0
    for message in reversed(messages[-CHAT_HISTORY_MESSAGE_LIMIT:]):
        role = str(message.get("role") or "user")
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        line = f"{role}: {content}"
        line_len = len(line)
        if selected and used_chars + line_len > CHAT_HISTORY_CHAR_LIMIT:
            break
        selected.append(line)
        used_chars += line_len
    return "\n".join(reversed(selected))


def build_prompt(paper: dict[str, Any], messages: list[dict[str, Any]], chunks: list[Chunk]) -> str:
    conversation = format_conversation(messages)
    context = "\n\n".join(
        f"[{idx + 1}] {chunk.label} ({chunk.file})\n{chunk.text}"
        for idx, chunk in enumerate(chunks)
    )
    return f"""你是一个严谨的论文阅读助手。请围绕当前论文回答用户问题。

论文标题：{paper.get("title", "")}
论文 slug：{paper.get("slug", "")}

回答要求：
- 优先依据给定材料回答；材料不足时明确说明。
- 用中文回答，保留必要英文术语。
- 分析方法、实验、贡献或局限时给出结构化结论。
- 数学变量和公式必须使用 LaTeX math delimiter：行内公式用 `$...$`，独立公式用 `$$...$$`。
- 不要把数学变量或公式放进反引号、代码块、```text```、```math``` 或 ```latex``` 中。

最近对话：
{conversation}

本地材料：
{context}
"""


def parse_openai_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"].strip()

    texts: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if isinstance(content.get("text"), str):
                texts.append(content["text"])
    return "\n".join(texts).strip()


def parse_openai_response_info(payload: dict[str, Any]) -> dict[str, Any]:
    incomplete_details = payload.get("incomplete_details") or {}
    incomplete_reason = str(incomplete_details.get("reason") or "")
    status = str(payload.get("status") or "")

    if not incomplete_reason:
        for choice in payload.get("choices", []):
            finish_reason = str(choice.get("finish_reason") or "")
            if finish_reason in {"length", "max_tokens"}:
                incomplete_reason = finish_reason
                break

    return {
        "incomplete": status == "incomplete" or bool(incomplete_reason),
        "incomplete_reason": incomplete_reason,
        "response_id": payload.get("id") or "",
        "usage": payload.get("usage") or {},
    }


def call_openai(
    prompt: str,
    model_override: str = "",
    *,
    max_output_tokens: Optional[int] = None,
    timeout_seconds: Optional[int] = None,
) -> dict[str, Any]:
    runtime = model_runtime_config()
    api_key = runtime["api_key"]
    if not api_key and runtime["requires_openai_auth"]:
        raise RuntimeError(f"{runtime['env_key']} is not configured")

    body = {
        "model": model_override or runtime["model"],
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
                    }
                ],
            }
        ],
        "max_output_tokens": max_output_tokens or runtime["max_output_tokens"],
    }
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        runtime["api_url"],
        data=data,
        headers=headers,
        method="POST",
    )
    context = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout_seconds or runtime["timeout_seconds"], context=context) as response:
        payload = json.loads(response.read().decode("utf-8"))
    answer = parse_openai_text(payload)
    if not answer:
        raise RuntimeError("OpenAI response did not contain text")
    result = parse_openai_response_info(payload)
    result["answer"] = answer
    return result


def fallback_answer(question: str, chunks: list[Chunk], reason: str) -> str:
    excerpts = []
    for idx, chunk in enumerate(chunks[:4], start=1):
        compact = re.sub(r"\s+", " ", chunk.text).strip()
        excerpts.append(f"{idx}. {chunk.label}：{compact[:420]}")
    joined = "\n".join(excerpts) if excerpts else "没有找到可用的本地材料。"
    return (
        "当前使用本地检索模式，未调用远程模型。"
        f"\n原因：{reason}"
        f"\n\n和你的问题最相关的材料如下：\n{joined}"
        "\n\n配置 `OPENAI_API_KEY` 后，同一个聊天框会返回生成式分析。"
    )


def source_payload(chunks: list[Chunk]) -> list[dict[str, str]]:
    return [{"label": chunk.label, "file": chunk.file} for chunk in chunks]


def conversation_path_for_slug(slug: str, library: str = DEFAULT_LIBRARY) -> Path:
    return paper_dir_for_slug(slug, library) / "conversation.json"


def normalize_chat_message(message: Any) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return None
    role = str(message.get("role") or "").strip()
    if role not in {"user", "assistant"}:
        return None
    content = str(message.get("content") or "").strip()
    if not content:
        return None

    normalized: dict[str, Any] = {
        "role": role,
        "content": content[:50000],
    }
    if isinstance(message.get("sources"), list):
        sources = []
        for source in message.get("sources", [])[:12]:
            if isinstance(source, dict):
                sources.append(
                    {
                        "label": str(source.get("label") or "")[:200],
                        "file": str(source.get("file") or "")[:300],
                    }
                )
        normalized["sources"] = sources
    if message.get("created_at"):
        normalized["created_at"] = str(message.get("created_at"))[:40]
    if message.get("model"):
        normalized["model"] = str(message.get("model"))[:100]
    if message.get("incomplete") is not None:
        normalized["incomplete"] = bool(message.get("incomplete"))
    if message.get("incomplete_reason"):
        normalized["incomplete_reason"] = str(message.get("incomplete_reason"))[:300]
    if message.get("saved_to_qa") or message.get("saved_to_analysis"):
        normalized["saved_to_qa"] = True
    if message.get("analysis_anchor"):
        normalized["analysis_anchor"] = str(message.get("analysis_anchor"))[:120]
    return normalized


def load_conversation(slug: str, library: str = DEFAULT_LIBRARY) -> dict[str, Any]:
    path = conversation_path_for_slug(slug, library)
    if not path.exists():
        return {"version": 1, "messages": []}
    try:
        payload = json.loads(read_text(path))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "messages": []}
    raw_messages = payload.get("messages") if isinstance(payload, dict) else []
    messages = [
        normalized
        for normalized in (normalize_chat_message(message) for message in raw_messages or [])
        if normalized
    ]
    return {"version": 1, "messages": messages}


def save_conversation(slug: str, messages: list[dict[str, Any]], library: str = DEFAULT_LIBRARY) -> None:
    normalized_messages = [
        normalized
        for normalized in (normalize_chat_message(message) for message in messages)
        if normalized
    ]
    payload = {
        "version": 1,
        "updated": datetime.now().isoformat(timespec="seconds"),
        "messages": normalized_messages,
    }
    write_text(conversation_path_for_slug(slug, library), json.dumps(payload, ensure_ascii=False, indent=2))


def chat_message(role: str, content: str, **extra: Any) -> dict[str, Any]:
    message: dict[str, Any] = {
        "role": role,
        "content": content,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    message.update(extra)
    normalized = normalize_chat_message(message)
    return normalized or {"role": role, "content": content}


def last_user_question(messages: list[dict[str, Any]], before_index: int | None = None) -> str:
    search = messages[:before_index] if before_index is not None else messages
    for message in reversed(search):
        if message.get("role") == "user":
            return str(message.get("content") or "").strip()
    return ""


def trim_incomplete_tail(content: str) -> str:
    trimmed = str(content or "").rstrip()

    fence_matches = list(re.finditer(r"(?m)^```", trimmed))
    if len(fence_matches) % 2 == 1:
        return trimmed[: fence_matches[-1].start()].rstrip()

    display_matches = list(re.finditer(r"(?m)^\s*\$\$\s*$", trimmed))
    if len(display_matches) % 2 == 1:
        return trimmed[: display_matches[-1].start()].rstrip()

    return trimmed


def analysis_path_for_slug(slug: str, library: str = DEFAULT_LIBRARY) -> Path:
    return paper_dir_for_slug(slug, library) / "analysis.md"


def ensure_analysis_file(paper: dict[str, Any], library: str = DEFAULT_LIBRARY) -> Path:
    slug = str(paper.get("slug") or "")
    path = analysis_path_for_slug(slug, library)
    if not path.exists():
        write_text(path, f"# {paper.get('title') or slug}\n")
    return path


def replace_markdown_section(content: str, heading: str, body: str) -> str:
    normalized = content.rstrip()
    block = f"## {heading}\n\n{body.strip()}\n"
    pattern = re.compile(rf"(?ms)^## {re.escape(heading)}\s*\n.*?(?=^## |\Z)")
    if pattern.search(normalized):
        return pattern.sub(block.rstrip(), normalized).rstrip() + "\n"
    return f"{normalized}\n\n{block}".lstrip()


def append_markdown_section(content: str, heading: str, addition: str) -> str:
    normalized = content.rstrip()
    section_match = re.search(rf"(?m)^## {re.escape(heading)}\s*$", normalized)
    if not section_match:
        return f"{normalized}\n\n## {heading}\n\n{addition.strip()}\n".lstrip()

    next_match = re.search(r"(?m)^## ", normalized[section_match.end() :])
    if not next_match:
        return f"{normalized}\n\n{addition.strip()}\n"

    insert_at = section_match.end() + next_match.start()
    before = normalized[:insert_at].rstrip()
    after = normalized[insert_at:].lstrip()
    return f"{before}\n\n{addition.strip()}\n\n{after}\n"


def trim_references_section(content: str) -> str:
    match = re.search(r"(?im)^\s*(references|bibliography)\s*$", content)
    if match and match.start() > 8000:
        return content[: match.start()].rstrip()
    return content


def analysis_source_text(slug: str, library: str = DEFAULT_LIBRARY, limit: int = 70000) -> str:
    paper_dir = paper_dir_for_slug(slug, library)
    full_text = paper_dir / "extracted" / "full_text.txt"
    if full_text.exists():
        return trim_references_section(read_text(full_text))[:limit]

    pages_dir = paper_dir / "extracted" / "text_pages"
    if pages_dir.exists():
        pages = []
        for page_path in sorted(pages_dir.glob("page_*.txt")):
            page_match = re.search(r"page_(\d+)", page_path.stem)
            page_label = str(int(page_match.group(1))) if page_match else page_path.stem
            pages.append(f"\n\n--- page {page_label} ---\n{read_text(page_path)}")
        joined = "".join(pages)
        if joined.strip():
            return trim_references_section(joined)[:limit]

    analysis_path = analysis_path_for_slug(slug, library)
    if analysis_path.exists():
        return read_text(analysis_path)[:limit]
    return ""


def build_analysis_prompt(paper: dict[str, Any], source_text: str) -> str:
    return f"""你是一个严谨的论文阅读助手。请基于给定材料，为当前论文生成一份紧凑、稳定的中文结构化解析。

论文标题：{paper.get("title", "")}
论文 slug：{paper.get("slug", "")}

材料说明：
- 论文材料按页组织，页边界以 `--- page N ---` 标记。
- 原文中的 section 标题、Fig./Figure caption、Table caption 会尽量保留，但它们来自 PDF 文本抽取，阅读顺序和表格结构可能不完全可靠。

输出要求：
- 只输出 `## Structured Analysis` 之下应该出现的正文，不要输出一级标题，不要输出 `## QA`。
- 用中文组织，保留必要英文术语。
- 如果材料不足以判断某一点，明确写“材料不足，无法确定”，不要编造。
- 总长度控制在约 1800-2500 个中文字；不要为了覆盖所有细节而写成长综述。
- 重点解释 motivation、problem setting、core idea、method、核心贡献和最关键证据。
- 实验部分少写，只保留最能支撑论文贡献的 2-3 条证据或结论。
- Conclusion、limitation 和 relation to other work 合并为一个部分。
- 尽量写成稳定笔记，而不是对话口吻。
- 每个小节最多 3-5 条 bullet 或短段落，避免展开背景常识。
- 数学变量和公式必须使用 LaTeX math delimiter：行内公式用 `$...$`，独立公式用 `$$...$$`。
- 不要把数学变量或公式放进反引号、代码块、```text```、```math``` 或 ```latex``` 中。
- 对关键判断、方法细节、实验结论和数字结果，尽量在句末标注来源位置，格式如 `（Section 3, p.4）`、`（Fig. 2, p.3）`、`（Table 1, p.6）`。
- 来源引用不需要逐句标注；每个小节给出 1-2 个最关键来源即可。
- 如果依据来自图或表，优先引用 Fig./Table 编号；如果只能定位到页，则引用页码；如果材料中没有明确来源，不要伪造 Section/Fig/Table 编号。

建议结构：
### Motivation
### Problem Setting
### Core Idea
### Method
### Key Contributions
### Experiments / Evidence
### Conclusions, Limitations, and Relation to Other Work

论文材料：
{source_text}
"""


def import_pdf_bytes(
    *,
    pdf_bytes: bytes,
    title: str,
    paper_hash: str,
    pdf_name: str,
    source_url: str,
    pdf_url: str,
    arxiv_id: str = "",
    summary: str = "Imported from a user-provided PDF.",
    library: str = DEFAULT_LIBRARY,
) -> dict[str, Any]:
    library = normalize_library_id(library)
    papers = [
        paper
        for paper in load_papers(library)
        if paper_assets_exist(paper, library)
        or (
            paper.get("hash") != paper_hash
            and not (pdf_url and paper_matches_source(paper, source_url, pdf_url, arxiv_id))
        )
    ]
    existing_slugs = {str(paper.get("slug")) for paper in papers if paper.get("slug")}
    papers_dir = library_dir(library) / "papers"
    if papers_dir.exists():
        existing_slugs.update(path.name for path in papers_dir.iterdir() if path.is_dir())

    unique_slug = paper_hash
    suffix = 2
    while unique_slug in existing_slugs:
        unique_slug = f"{paper_hash}-{suffix}"
        suffix += 1

    pdf_path = PDF_DIR / pdf_name
    paper_dir = paper_dir_for_slug(unique_slug, library)
    pdf_existed = pdf_path.exists()

    try:
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(pdf_bytes)

        paper_dir.mkdir(parents=True, exist_ok=False)

        extract_pdf_assets(pdf_path, paper_dir)
        full_text = read_text(paper_dir / "extracted" / "full_text.txt")
        inferred_tags = infer_tags(title, full_text)

        write_import_analysis(paper_dir, title, source_url, pdf_url, paper_hash, unique_slug)
        write_paper_index(paper_dir, title, pdf_name, unique_slug, library)

        new_paper = {
            "slug": unique_slug,
            "hash": paper_hash,
            "library": library,
            "title": title,
            "arxiv": arxiv_id,
            "pdf": f"../papers/pdfs/{pdf_name}",
            "page": f"libraries/{library}/papers/{unique_slug}/index.html",
            "status": "imported",
            "tags": inferred_tags,
            "updated": date.today().isoformat(),
            "summary": summary,
            "source_url": source_url,
            "pdf_url": pdf_url,
        }
        papers.insert(0, new_paper)
        save_papers(papers, library)
    except Exception:
        if paper_dir.exists():
            shutil.rmtree(paper_dir, ignore_errors=True)
        if not pdf_existed and pdf_path.exists():
            pdf_path.unlink(missing_ok=True)
        raise

    return new_paper


@app.post("/api/import")
def import_paper():
    payload = request.get_json(silent=True) or {}
    library = request_library(payload)
    url = str(payload.get("url", "")).strip()
    if not url:
        return jsonify({"error": "url is required"}), 400
    pdf_url = normalize_pdf_url(url)
    arxiv_id = extract_arxiv_id(url) or extract_arxiv_id(pdf_url)
    paper_hash = paper_hash_for_source(pdf_url, arxiv_id)
    existing_paper = find_existing_paper(url, pdf_url, arxiv_id, library)
    if existing_paper:
        existing_paper = normalize_existing_import(existing_paper, url, pdf_url, arxiv_id, paper_hash, library)
        return jsonify({"paper": existing_paper, "existing": True})

    try:
        pdf_bytes = download_url(pdf_url)
    except Exception as exc:
        return jsonify({"error": f"failed to download pdf: {exc}"}), 400

    title = infer_paper_title(url, pdf_url, arxiv_id, pdf_bytes)
    pdf_name = safe_filename_from_url(pdf_url)
    try:
        new_paper = import_pdf_bytes(
            pdf_bytes=pdf_bytes,
            title=title,
            paper_hash=paper_hash,
            pdf_name=pdf_name,
            source_url=url,
            pdf_url=pdf_url,
            arxiv_id=arxiv_id,
            summary="Imported from a user-provided PDF or arXiv URL.",
            library=library,
        )
    except Exception as exc:
        return jsonify({"error": f"failed to import pdf: {exc}"}), 500

    return jsonify({"paper": new_paper})


@app.post("/api/import-file")
def import_paper_file():
    library = request_library(request.form.to_dict())
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "file is required"}), 400

    original_name = safe_uploaded_filename(uploaded.filename, "uploaded.pdf")
    pdf_bytes = uploaded.read()
    if not pdf_bytes:
        return jsonify({"error": "uploaded file is empty"}), 400
    if not pdf_bytes.lstrip().startswith(b"%PDF"):
        return jsonify({"error": "uploaded file must be a PDF"}), 400

    paper_hash = paper_hash_for_bytes(pdf_bytes)
    existing_paper = find_existing_paper_by_hash(paper_hash, library)
    if existing_paper:
        return jsonify({"paper": existing_paper, "existing": True})

    title = infer_uploaded_paper_title(original_name, pdf_bytes)
    pdf_name = f"{paper_hash}.pdf"
    source_url = f"upload:{original_name}"
    try:
        new_paper = import_pdf_bytes(
            pdf_bytes=pdf_bytes,
            title=title,
            paper_hash=paper_hash,
            pdf_name=pdf_name,
            source_url=source_url,
            pdf_url="",
            summary="Imported from a local PDF upload.",
            library=library,
        )
    except Exception as exc:
        return jsonify({"error": f"failed to import pdf: {exc}"}), 500

    return jsonify({"paper": new_paper})


@app.delete("/api/papers/<slug>")
def delete_paper(slug: str):
    library = request_library()
    slug = slug.strip()
    papers = list(load_papers(library))
    paper = next((item for item in papers if item.get("slug") == slug), None)
    if not paper:
        return jsonify({"error": "paper not found"}), 404

    pdf_path = pdf_path_for_paper(paper)
    remaining_papers = [item for item in papers if item.get("slug") != slug]

    paper_dir = paper_dir_for_slug(slug, library)
    if paper_dir.exists():
        shutil.rmtree(paper_dir, ignore_errors=True)

    if pdf_path and pdf_path.exists():
        if not is_pdf_referenced(pdf_path, excluding_slug=slug, excluding_library=library):
            pdf_path.unlink(missing_ok=True)

    save_papers(remaining_papers, library)
    load_context.cache_clear()
    return jsonify({"deleted": True, "slug": slug, "library": library})


@app.get("/api/papers/<slug>")
def paper_api(slug: str):
    library = request_library()
    paper = get_paper(slug, library)
    if not paper:
        return jsonify({"error": "paper not found"}), 404
    original_paper = dict(paper)
    pdf_status = ensure_paper_pdf(paper, library)
    if pdf_status.get("downloaded") or paper != original_paper:
        papers = list(load_papers(library))
        for index, item in enumerate(papers):
            if item.get("slug") == slug:
                papers[index] = paper
                save_papers(papers, library)
                break
    chunks = load_context(library, slug)
    files = {chunk.file for chunk in chunks}
    return jsonify(
        {
            "paper": paper,
            "pdf_status": pdf_status,
            "context_files": len(files),
            "chunk_count": len(chunks),
        }
    )


@app.get("/api/papers/<slug>/analysis")
def paper_analysis_api(slug: str):
    library = request_library()
    paper = get_paper(slug, library)
    if not paper:
        return jsonify({"error": "paper not found"}), 404

    path = ensure_analysis_file(paper, library)
    return jsonify({"content": read_text(path)})


@app.get("/api/papers/<slug>/conversation")
def paper_conversation_api(slug: str):
    library = request_library()
    paper = get_paper(slug, library)
    if not paper:
        return jsonify({"error": "paper not found"}), 404
    return jsonify(load_conversation(slug, library))


@app.put("/api/papers/<slug>/conversation")
def update_paper_conversation_api(slug: str):
    payload = request.get_json(silent=True) or {}
    library = request_library(payload)
    paper = get_paper(slug, library)
    if not paper:
        return jsonify({"error": "paper not found"}), 404
    raw_messages = payload.get("messages") or []
    if not isinstance(raw_messages, list):
        return jsonify({"error": "messages must be a list"}), 400
    messages = [
        normalized
        for normalized in (normalize_chat_message(message) for message in raw_messages)
        if normalized
    ]
    save_conversation(slug, messages, library)
    return jsonify(load_conversation(slug, library))


@app.post("/api/papers/<slug>/analysis")
def append_paper_analysis(slug: str):
    library = request_library()
    paper = get_paper(slug, library)
    if not paper:
        return jsonify({"error": "paper not found"}), 404

    payload = request.get_json(silent=True) or {}
    content = str(payload.get("content") or "").strip()
    if not content:
        return jsonify({"error": "content is required"}), 400
    if len(content) > 50000:
        return jsonify({"error": "content is too long"}), 400

    path = ensure_analysis_file(paper, library)
    existing = read_text(path).rstrip()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"{existing}\n\n## Assistant Note ({timestamp})\n\n{content}\n"
    write_text(path, entry)
    load_context.cache_clear()

    return jsonify({"saved": True, "content": entry})


@app.put("/api/papers/<slug>/analysis")
def replace_paper_analysis(slug: str):
    library = request_library()
    paper = get_paper(slug, library)
    if not paper:
        return jsonify({"error": "paper not found"}), 404

    payload = request.get_json(silent=True) or {}
    content = str(payload.get("content") or "")
    if not content.strip():
        return jsonify({"error": "content is empty; refusing to overwrite analysis.md"}), 400
    if len(content) > 300000:
        return jsonify({"error": "content is too long"}), 400

    path = ensure_analysis_file(paper, library)
    normalized = content.rstrip() + "\n"
    write_text(path, normalized)
    load_context.cache_clear()

    return jsonify({"saved": True, "content": normalized})


@app.post("/api/papers/<slug>/analysis/generate")
def generate_paper_analysis(slug: str):
    payload = request.get_json(silent=True) or {}
    library = request_library(payload)
    paper = get_paper(slug, library)
    if not paper:
        return jsonify({"error": "paper not found"}), 404

    selected_model = str(payload.get("model", "")).strip()
    if selected_model and selected_model not in AVAILABLE_CHAT_MODELS:
        return jsonify({"error": "unsupported model"}), 400

    analysis_runtime = analysis_runtime_config()
    source_text = analysis_source_text(slug, library, limit=analysis_runtime["source_char_limit"])
    if not source_text.strip():
        return jsonify({"error": "no paper materials available"}), 400

    try:
        result = call_openai(
            build_analysis_prompt(paper, source_text),
            selected_model,
            max_output_tokens=analysis_runtime["max_output_tokens"],
            timeout_seconds=analysis_runtime["timeout_seconds"],
        )
    except (RuntimeError, TimeoutError, socket.timeout, urllib.error.URLError, urllib.error.HTTPError) as exc:
        return jsonify({"error": f"failed to generate analysis: {exc}"}), 502

    path = ensure_analysis_file(paper, library)
    updated = replace_markdown_section(read_text(path), "Structured Analysis", result["answer"])
    write_text(path, updated)
    load_context.cache_clear()

    return jsonify(
        {
            "saved": True,
            "content": updated,
            "model": selected_model or model_runtime_config()["model"],
            "usage": result.get("usage") or {},
            "analysis_runtime": analysis_runtime,
        }
    )


@app.post("/api/papers/<slug>/analysis/qa")
def append_paper_analysis_qa(slug: str):
    payload = request.get_json(silent=True) or {}
    library = request_library(payload)
    paper = get_paper(slug, library)
    if not paper:
        return jsonify({"error": "paper not found"}), 404

    question = str(payload.get("question") or "").strip()
    answer = str(payload.get("answer") or payload.get("content") or "").strip()
    if not answer:
        return jsonify({"error": "answer is required"}), 400
    if len(question) > 20000 or len(answer) > 50000:
        return jsonify({"error": "content is too long"}), 400

    anchor = "qa-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    entry = f"### QA {anchor}\n\n"
    if question:
        entry += f"**Q:** {question}\n\n"
    entry += f"**A:**\n\n{answer}\n"

    path = ensure_analysis_file(paper, library)
    updated = append_markdown_section(read_text(path), "QA", entry)
    write_text(path, updated)
    load_context.cache_clear()

    return jsonify({"saved": True, "content": updated, "anchor": anchor})


@app.post("/api/chat")
def chat_api():
    payload = request.get_json(silent=True) or {}
    library = request_library(payload)
    slug = str(payload.get("paper_slug", "")).strip()
    selected_model = str(payload.get("model", "")).strip()
    new_message = str(payload.get("message") or "").strip()
    raw_messages = payload.get("messages") or []
    if not slug:
        return jsonify({"error": "paper_slug is required"}), 400
    if selected_model and selected_model not in AVAILABLE_CHAT_MODELS:
        return jsonify({"error": "unsupported model"}), 400

    paper = get_paper(slug, library)
    if not paper:
        return jsonify({"error": "paper not found"}), 404

    saved_messages = load_conversation(slug, library)["messages"]
    continue_index_raw = payload.get("continue_message_index")
    regenerate_index_raw = payload.get("regenerate_message_index")

    if regenerate_index_raw is not None:
        try:
            regenerate_index = int(regenerate_index_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "regenerate_message_index must be an integer"}), 400
        if regenerate_index < 0 or regenerate_index >= len(saved_messages):
            return jsonify({"error": "regenerate_message_index is out of range"}), 400
        target = saved_messages[regenerate_index]
        if target.get("role") != "assistant":
            return jsonify({"error": "regenerate_message_index must point to an assistant message"}), 400

        question = last_user_question(saved_messages, regenerate_index)
        if not question:
            return jsonify({"error": "no user question found before this assistant message"}), 400

        prompt_messages = saved_messages[:regenerate_index]
        chunks = retrieve(library, slug, question)
        prompt = build_prompt(paper, prompt_messages, chunks)
        incomplete = False
        incomplete_reason = ""
        usage: dict[str, Any] = {}
        try:
            result = call_openai(prompt, selected_model)
            answer = result["answer"]
            incomplete = bool(result.get("incomplete"))
            incomplete_reason = str(result.get("incomplete_reason") or "")
            usage = result.get("usage") or {}
            mode = "openai"
        except (RuntimeError, TimeoutError, socket.timeout, urllib.error.URLError, urllib.error.HTTPError) as exc:
            answer = fallback_answer(question, chunks, str(exc))
            mode = "local"

        saved_messages[regenerate_index] = chat_message(
            "assistant",
            answer,
            sources=source_payload(chunks),
            incomplete=incomplete,
            incomplete_reason=incomplete_reason,
            model=selected_model or model_runtime_config()["model"],
        )
        save_conversation(slug, saved_messages, library)
        return jsonify(
            {
                "answer": answer,
                "mode": mode,
                "model": selected_model or model_runtime_config()["model"],
                "library": library,
                "incomplete": incomplete,
                "incomplete_reason": incomplete_reason,
                "usage": usage,
                "sources": source_payload(chunks),
                "messages": load_conversation(slug, library)["messages"],
            }
        )

    if continue_index_raw is not None:
        try:
            continue_index = int(continue_index_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "continue_message_index must be an integer"}), 400
        if continue_index < 0 or continue_index >= len(saved_messages):
            return jsonify({"error": "continue_message_index is out of range"}), 400
        target = saved_messages[continue_index]
        if target.get("role") != "assistant":
            return jsonify({"error": "continue_message_index must point to an assistant message"}), 400

        question = last_user_question(saved_messages, continue_index) or "继续生成"
        existing_content = str(target.get("content") or "")
        clean_content = trim_incomplete_tail(existing_content)
        target["content"] = clean_content
        continue_prompt = new_message or (
            "请从上一条 assistant 回答被截断的位置继续生成，不要重复已经写过的内容。"
            "请确保续写内容中的 Markdown 和 LaTeX 分隔符成对闭合。"
        )
        prompt_messages = saved_messages + [chat_message("user", continue_prompt)]
        chunks = retrieve(library, slug, question)
        prompt = build_prompt(paper, prompt_messages, chunks)
        incomplete = False
        incomplete_reason = ""
        usage: dict[str, Any] = {}
        try:
            result = call_openai(prompt, selected_model)
            answer = result["answer"]
            incomplete = bool(result.get("incomplete"))
            incomplete_reason = str(result.get("incomplete_reason") or "")
            usage = result.get("usage") or {}
            mode = "openai"
        except (RuntimeError, TimeoutError, socket.timeout, urllib.error.URLError, urllib.error.HTTPError) as exc:
            answer = fallback_answer(question, chunks, str(exc))
            mode = "local"

        target["content"] = f"{clean_content}\n\n{answer}".strip()
        target["sources"] = (target.get("sources") or []) + source_payload(chunks)
        target["incomplete"] = incomplete
        target["incomplete_reason"] = incomplete_reason
        target["model"] = selected_model or model_runtime_config()["model"]
        target["saved_to_qa"] = False
        target["analysis_anchor"] = ""
        save_conversation(slug, saved_messages, library)
        return jsonify(
            {
                "answer": answer,
                "mode": mode,
                "model": selected_model or model_runtime_config()["model"],
                "library": library,
                "incomplete": incomplete,
                "incomplete_reason": incomplete_reason,
                "usage": usage,
                "sources": source_payload(chunks),
                "messages": load_conversation(slug, library)["messages"],
            }
        )

    if new_message:
        user_message = chat_message("user", new_message)
        messages = saved_messages + [user_message]
        question = new_message
    else:
        if not isinstance(raw_messages, list):
            return jsonify({"error": "messages must be a list"}), 400
        messages = [
            normalized
            for normalized in (normalize_chat_message(message) for message in raw_messages)
            if normalized
        ]
        question = last_user_question(messages)

    if not question:
        return jsonify({"error": "a user question is required"}), 400

    chunks = retrieve(library, slug, question)
    prompt = build_prompt(paper, messages, chunks)
    incomplete = False
    incomplete_reason = ""
    usage: dict[str, Any] = {}
    try:
        result = call_openai(prompt, selected_model)
        answer = result["answer"]
        incomplete = bool(result.get("incomplete"))
        incomplete_reason = str(result.get("incomplete_reason") or "")
        usage = result.get("usage") or {}
        mode = "openai"
    except (RuntimeError, TimeoutError, socket.timeout, urllib.error.URLError, urllib.error.HTTPError) as exc:
        answer = fallback_answer(question, chunks, str(exc))
        mode = "local"

    assistant_message = chat_message(
        "assistant",
        answer,
        sources=source_payload(chunks),
        incomplete=incomplete,
        incomplete_reason=incomplete_reason,
        model=selected_model or model_runtime_config()["model"],
    )
    save_conversation(slug, messages + [assistant_message], library)

    return jsonify(
        {
            "answer": answer,
            "mode": mode,
            "model": selected_model or model_runtime_config()["model"],
            "library": library,
            "incomplete": incomplete,
            "incomplete_reason": incomplete_reason,
            "usage": usage,
            "sources": source_payload(chunks),
            "messages": load_conversation(slug, library)["messages"],
        }
    )


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/paper.html")
def paper_workspace():
    return send_from_directory(WEB_DIR, "paper.html")


@app.get("/api/libraries")
def libraries_api():
    if LIBRARIES_JSON.exists():
        libraries = json.loads(read_text(LIBRARIES_JSON))
    else:
        libraries = [{"id": DEFAULT_LIBRARY, "name": "Default"}]
    return jsonify({"libraries": libraries, "default": DEFAULT_LIBRARY})


@app.get("/assets/<path:filename>")
def assets(filename: str):
    return send_from_directory(WEB_DIR / "assets", filename)


@app.get("/papers/pdfs/<path:filename>")
def pdfs(filename: str):
    return send_from_directory(PDF_DIR, filename)


@app.get("/papers/<path:filename>")
def paper_files(filename: str):
    return send_from_directory(library_dir(DEFAULT_LIBRARY) / "papers", filename)


@app.get("/libraries/<library>/papers/<path:filename>")
def library_paper_files(library: str, filename: str):
    return send_from_directory(library_dir(library) / "papers", filename)


@app.get("/<path:filename>")
def web_files(filename: str):
    return send_from_directory(WEB_DIR, filename)


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    app.run(host=host, port=port, debug=debug, use_reloader=False)
