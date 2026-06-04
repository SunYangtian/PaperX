# PaperX Web

This directory stores generated reading notes for analyzed papers.

## Layout

- `../papers/pdfs/`: original PDF files only.
- `index.html`: entry page for analyzed papers.
- `paper.html`: generic two-column workspace for a selected paper.
- `all_papers_classification.html`: dynamic table view generated from the active library's `papers.json`.
- `libraries.json`: available paper libraries.
- `libraries/<library>/papers.json`: lightweight metadata for one library. The default library starts empty.
- `libraries/<library>/papers/<paper-hash>/analysis.md`: stable paper analysis for imported papers.
- `libraries/<library>/papers/<paper-hash>/extracted/`: extracted full text and page-level text.

The published `default` library is intentionally empty except `.gitkeep`; imports populate it locally.

Imported paper hashes are stable IDs derived from arXiv ID when available, otherwise from the normalized PDF URL.
The home page records opened papers in localStorage per library and shows only the six most recently read papers. The full table page always renders the current full list from the active library's `papers.json`.
The paper workspace includes a model selector in the chat composer. The selected model is stored in localStorage and sent with each `/api/chat` request.
The `Analysis` tab renders and edits the current `analysis.md`, can generate a structured paper analysis, and can save assistant exchanges into that file's `QA` section.
The renderer also treats short variable patterns such as `a_t`, `x_1`, and `s_{t+1}` as inline subscripts outside code blocks.
If a model response is marked incomplete by the backend, the assistant message shows a continuation control that appends a follow-up generation to the same message.

## Maintenance

When a new paper is imported from the home page:

1. Paste either a direct PDF URL or an arXiv abstract URL, for example `https://arxiv.org/abs/2604.04913`.
2. The Flask server normalizes arXiv abstract URLs to PDF URLs.
3. The server checks whether the paper is already in the active library's `papers.json`; existing papers are opened without another download.
4. The server downloads the PDF into `../papers/pdfs/`.
5. The server resolves the paper title from arXiv metadata or PDF metadata.
6. The server stores imported paper assets under `libraries/<library>/papers/<paper-hash>/`.
7. The server extracts full text and page-level text into `libraries/<library>/papers/<paper-hash>/extracted/`.
8. The server updates the active library's `papers.json` with the `title` to `hash` mapping and redirects the browser to `paper.html?library=<library>&slug=<paper-hash>`.

When a local PDF is uploaded from the home page:

1. Select a local `.pdf` file in the upload control.
2. The server derives a stable hash from the uploaded file bytes.
3. Duplicate uploads with the same content open the existing paper.
4. New uploads are stored as `../papers/pdfs/<paper-hash>.pdf` and extracted under `libraries/<library>/papers/<paper-hash>/`.

When a paper is deleted from the full table page:

1. The server removes the entry from the active library's `papers.json`.
2. The server removes `libraries/<library>/papers/<paper-id>/`.
3. The server removes the PDF only if no remaining paper references the same file.

When a new paper is maintained manually:

1. Create `web/libraries/<library>/papers/<paper-hash>/` using the same hash convention as imported papers.
2. Add `analysis.md` and optional extracted assets.
3. Add an article `index.html`.
4. Add the paper to `web/libraries/<library>/papers.json` with matching `slug`, `hash`, `library`, and `page`.
5. Reload the home page; cards are rendered dynamically from the active library manifest.
