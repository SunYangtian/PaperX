# PaperX Architecture

## Goal

The web system provides an interactive paper reading workspace. When a user opens a paper from the web index, the browser shows a two-column layout: the PDF on the left and a paper-aware chat panel on the right.
The right side now follows an alphaXiv-style tool strip with three tabs: `Assistant`, `Analysis`, and `Similar`.

## Components

### Static Web Assets

- `web/index.html`: entry page for analyzed papers.
- `web/all_papers_classification.html`: dynamic full-library table generated from the active library's `papers.json`.
- `web/paper.html`: generic paper workspace page, loaded with `?slug=<paper-id>`.
- `web/assets/style.css`: shared styles, including the workspace split layout and chat UI.
- `web/assets/paper_chat.js`: client controller for loading paper metadata, rendering the PDF, sending chat messages, and displaying answers.
- `web/libraries.json`: available paper libraries. The default library is `default`; `world-model-library` contains the built-in World Model reading library.
- `web/libraries/<library>/papers.json`: canonical paper metadata for one library. The workspace uses `slug`, `hash`, `library`, `title`, `arxiv`, `pdf`, `status`, `tags`, and `updated`. For imported papers, `slug` is the stable hash and `title` is the display name.

### Paper Materials

Each paper keeps local analysis assets under `web/libraries/<library>/papers/<paper-hash>/`:

- `analysis.md`: stable reading notes.
- `extracted/full_text.txt`: extracted full paper text.
- `extracted/text_pages/page_*.txt`: page-level extracted text used for source labels and retrieval.

For imported papers, the hash is `sha256("arxiv:<id>")[:16]` when an arXiv ID is available, otherwise `sha256("pdf:<normalized-pdf-url>")[:16]`.

The home page starts in the `default` library, lets the user switch libraries, and keeps the visible list small by reading a browser-local recent-read list per library. Opening a paper workspace updates that library-specific recent-read list. The full table page reads the active library manifest and always reflects the current library.

### Flask Server

`server/app.py` serves both static files and chat APIs:

- `GET /`: serves `web/index.html`.
- `GET /paper.html?library=<library>&slug=<paper-id>`: serves the generic workspace.
- `GET /api/papers/<paper-id>?library=<library>`: returns metadata about available local context.
- `GET /api/papers/<paper-id>/analysis?library=<library>`: returns the current `analysis.md` content.
- `POST /api/papers/<paper-id>/analysis`: appends a raw note to `analysis.md`; request JSON includes `library`.
- `PUT /api/papers/<paper-id>/analysis?library=<library>`: replaces `analysis.md` with edited content from the Analysis tab.
- `POST /api/papers/<paper-id>/analysis/generate`: generates or replaces the `Structured Analysis` section; request JSON includes `library`.
- `POST /api/papers/<paper-id>/analysis/qa`: appends a selected assistant exchange to the `QA` section; request JSON includes `library`.
- `GET /api/libraries`: returns available paper libraries.
- `POST /api/import`: receives `{ url, library }`, downloads a PDF, extracts local assets, creates a new paper workspace, and updates the active library's `papers.json`.
- `POST /api/import-file`: receives multipart PDF upload plus `library`, imports it into the same local paper workspace format, and updates the active library's `papers.json`.
- `DELETE /api/papers/<paper-id>?library=<library>`: removes a paper entry, its `web/libraries/<library>/papers/<paper-id>/` directory, and its PDF when no other paper in that library references the same PDF file.
- `POST /api/chat`: receives `{ paper_slug, messages }`, retrieves relevant local context, and returns `{ answer, mode, sources }`.
  The payload may include `model` to override the runtime default for that request. Supported UI choices are `qwen3.7-max[1M]`, `deepseek-v4-pro[1M]`, `claude-opus-4-6`, `gpt-5.5`, `gemini-3.1-pro-preview`, `glm-5.1`, `kimi-k2.6`, `minimax-m2.7`, `qwen3-vl-plus`, and `qwen3-vl-flash`.
  The response includes `incomplete`, `incomplete_reason`, and `usage` when available, so the frontend can expose continuation controls for truncated model outputs.

The server also maps:

- `/assets/*` to `web/assets/*`.
- `/papers/pdfs/*` to `papers/pdfs/*`.
- `/libraries/<library>/papers/*` to `web/libraries/<library>/papers/*`.
- `/papers/*` to the `default` library's paper directory for backwards compatibility.

## Chat Flow

1. The user opens `paper.html?library=<library>&slug=<paper-id>`.
2. `paper_chat.js` loads `web/libraries/<library>/papers.json`, finds the selected paper, and assigns the PDF URL to the left iframe.
3. The frontend calls `GET /api/papers/<paper-id>?library=<library>` to report how many context files and chunks are available.
4. When the user sends a message, the frontend posts the recent conversation and current library to `POST /api/chat`.
5. The backend retrieves relevant chunks from the current paper's local materials.
6. If `OPENAI_API_KEY` is configured, the backend calls the OpenAI Responses API.
7. If no API key is configured or the remote call fails, the backend returns a local retrieval answer with the most relevant excerpts.
8. The frontend renders the answer and source chips.
9. Each assistant answer exposes a control that can append the user question and assistant answer to the `QA` section in `analysis.md`.
10. The `Analysis` tab renders the current `analysis.md` from the backend and can edit/save it.
11. The `Analysis` tab can generate a structured paper analysis from local paper materials.
12. `Similar` ranks other papers by shared tags.

## Import Flow

1. The home page import bar accepts either a direct PDF URL or an arXiv abstract URL such as `https://arxiv.org/abs/2604.04913`.
2. `POST /api/import` normalizes arXiv abstract URLs to the corresponding PDF URL, for example `https://arxiv.org/pdf/2604.04913.pdf`.
3. Before downloading, the backend checks existing papers by arXiv ID, normalized `source_url` / `pdf_url`, and local PDF filename. If a match exists, it returns the existing paper with `existing: true`.
4. The backend downloads the PDF bytes only when no existing paper matches in the active library. If download fails, it returns an error without creating a `web/libraries/<library>/papers/<paper-hash>/` directory.
5. After a successful download, the backend writes the PDF into `papers/pdfs/`.
6. The backend resolves a display title. For arXiv URLs it first tries arXiv metadata, then falls back to PDF metadata or first-page text.
7. PyMuPDF extracts full text and page-level text into `web/libraries/<library>/papers/<paper-hash>/extracted/`.
8. The backend creates starter `analysis.md` and `index.html` files.
9. The backend prepends the new entry to the active library's `papers.json`, including `title`, `hash`, `library`, `source_url`, normalized `pdf_url`, and `arxiv` when available.
10. If extraction or metadata writing fails, the backend removes the paper directory and any PDF file created by this import.
11. The frontend reloads the paper list and navigates to `paper.html?library=<library>&slug=<paper-hash>`.

Local PDF uploads follow the same extraction and metadata-writing path through `POST /api/import-file`. Uploaded papers use a content-derived hash, save the PDF as `<hash>.pdf`, and resolve the display title from PDF metadata or first-page text before falling back to the uploaded filename.

## Delete Flow

1. Each row in `all_papers_classification.html` has a delete action.
2. The full table page calls `DELETE /api/papers/<paper-id>?library=<library>` after confirmation.
3. The backend removes the matching entry from the active library's `papers.json`.
4. The backend removes `web/libraries/<library>/papers/<paper-id>/`.
5. The backend removes the PDF file only if no remaining paper entry references the same file.

## Retrieval Strategy

The current implementation uses lightweight local lexical retrieval:

- Markdown files are split into paragraph chunks.
- Page text files are kept as page-labeled chunks.
- User questions are tokenized into English and Chinese terms.
- Chunks are ranked by query-term overlap and simple phrase matching.

This keeps the system dependency-light and makes it usable without an embedding database. A future upgrade can replace `retrieve()` in `server/app.py` with embeddings or a vector store without changing the frontend contract.

## Runtime Configuration

Environment variables:

- `OPENAI_API_KEY`: enables model-backed chat.
- `OPENAI_MODEL`: default chat and analysis model.
- `OPENAI_BASE_URL`: OpenAI-compatible API base URL.
- `OPENAI_RESPONSES_PATH`: Responses API path appended to `OPENAI_BASE_URL`.
- `PAPER_MODEL_PROVIDER`: informational provider label returned in backend runtime config.
- `REQUIRES_OPENAI_AUTH`: whether missing credentials should block model-backed chat.
- `MAX_OUTPUT_TOKENS`: default chat response output budget.
- `OPENAI_TIMEOUT_SECONDS`: remote model call timeout.
- `ANALYSIS_SOURCE_CHAR_LIMIT`: maximum paper text characters sent to analysis generation.
- `ANALYSIS_MAX_OUTPUT_TOKENS`: analysis generation output budget.
- `ANALYSIS_TIMEOUT_SECONDS`: analysis generation timeout.
- `HOST`: optional server bind host. Defaults to `127.0.0.1`.
- `PORT`: optional server port. Defaults to `8000`.
- `OPENAI_ENV_KEY`: optional advanced indirection for using another environment variable as the API key source.

- Project runtime settings are stored in `.env` or passed directly as shell environment variables.
- `.env.example` lists the supported variables, including model, base URL, response path, output limits, timeout settings, and analysis generation limits.
- The server does not read `~/.codex/config.toml`; `.env` and shell environment variables are the only runtime configuration sources.
- Paper content, retrieval sources, and prompt policy still come from the local workspace.

Run locally:

```bash
pip install -r requirements.txt
OPENAI_API_KEY=... python3 server/app.py
```

Without `OPENAI_API_KEY`, the UI still works in local retrieval mode.

## Extension Points

- Add page jump links by returning page numbers in `sources` and appending `#page=<n>` to the PDF URL.
- Add cross-paper comparison by allowing `/api/chat` to retrieve from multiple slugs.
- Upgrade retrieval to embeddings while preserving the `POST /api/chat` response shape.
