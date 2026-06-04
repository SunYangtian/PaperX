# PaperX

PaperX is a local paper reading workspace with PDF viewing, paper-aware chat, local notes, and PDF import.

## Quick Start

From a fresh checkout:

```bash
./install.sh
```

The installer will ask for `OPENAI_BASE_URL`, `OPENAI_MODEL`, and `OPENAI_API_KEY` when no local `.env` file exists. Open `http://127.0.0.1:8000` after the server starts.

## Docs

- [Architecture](doc/architecture.md)
- [Deployment](doc/deployment.md)
- [Frontend notes](web/README.md)

## Data

PDF files and extracted assets are local-only and ignored by Git. The default library starts empty; `world-model-library` is available from the library selector.
