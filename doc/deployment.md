# Deployment

This project is designed to run as a local Flask app with a static frontend.

## One-command Local Setup

```bash
git clone <repo-url>
cd <repo>
./install.sh
```

Open `http://127.0.0.1:8000`.

`install.sh` creates `.venv`, installs Python dependencies, creates local paper storage directories, asks for model credentials when no local `.env` file exists, and starts the server.

To reconfigure `.env` later:

```bash
./install.sh --configure-env
```

## Configuration

Runtime configuration is stored in `.env` or passed as shell environment variables:

```bash
export OPENAI_API_KEY=...
export OPENAI_MODEL=gpt-5.5
export OPENAI_BASE_URL=https://api.openai.com/v1
./scripts/run.sh
```

`./scripts/run.sh` automatically loads `.env` if present. Shell variables passed directly to the command take precedence over `.env` values:

```bash
HOST=0.0.0.0 PORT=12457 ./scripts/run.sh
```

For OpenAI-compatible gateways, edit `.env` and set `OPENAI_BASE_URL`, `OPENAI_MODEL`, and `OPENAI_API_KEY`. Advanced runtime variables such as `OPENAI_RESPONSES_PATH`, `MAX_OUTPUT_TOKENS`, `OPENAI_TIMEOUT_SECONDS`, and the analysis limits are also documented in `.env.example`.

### `.env` Variables

| Variable | Meaning |
| --- | --- |
| `OPENAI_BASE_URL` | Base URL for an OpenAI-compatible API, without the final endpoint path. |
| `OPENAI_MODEL` | Default model used by chat and analysis generation. The chat UI can override this per request. |
| `OPENAI_API_KEY` | API credential for model-backed chat and analysis. Leave empty only when using local retrieval mode or a gateway that does not require auth. |
| `OPENAI_RESPONSES_PATH` | Endpoint path appended to `OPENAI_BASE_URL`. Defaults to `/responses`. |
| `PAPER_MODEL_PROVIDER` | Informational provider label returned in backend runtime config. It does not load external provider config. |
| `REQUIRES_OPENAI_AUTH` | When `true`, missing API credentials make model-backed calls fail fast. When `false`, the app can call gateways that do not require auth. |
| `MAX_OUTPUT_TOKENS` | Default output budget for chat responses. |
| `OPENAI_TIMEOUT_SECONDS` | Timeout for remote chat/model calls. |
| `ANALYSIS_SOURCE_CHAR_LIMIT` | Maximum extracted paper text characters sent to structured analysis generation. |
| `ANALYSIS_MAX_OUTPUT_TOKENS` | Output budget for generated structured analysis. |
| `ANALYSIS_TIMEOUT_SECONDS` | Timeout for structured analysis generation. |
| `HOST` | Host/interface used by `scripts/run.sh`. Use `127.0.0.1` for local-only access or `0.0.0.0` for server access. |
| `PORT` | Port used by `scripts/run.sh`. |

Optional advanced variable:

| Variable | Meaning |
| --- | --- |
| `OPENAI_ENV_KEY` | Name of another environment variable that stores the API key, for example `CODEX_API_KEY`. This is not needed for normal `.env` usage. |

## Running on a Server

Bind to a public interface and custom port:

```bash
HOST=0.0.0.0 PORT=12457 ./scripts/run.sh
```

Then open `http://<server-ip>:12457` after allowing the port in the firewall or cloud security group.

For long-running service management, run `./scripts/run.sh` under `systemd`, `supervisord`, `tmux`, or another process manager.

## GitHub Publishing Notes

Do not commit local credentials, private gateway URLs, downloaded PDFs, or generated extraction artifacts.

The repository should track:

- source code in `server/` and `web/`
- library metadata such as `web/libraries/<library>/papers.json`
- curated notes such as `web/libraries/<library>/papers/<paper-id>/analysis.md`
- templates such as `.env.example`

The repository should not track:

- `.env`
- `papers/pdfs/*.pdf`
- `web/libraries/**/papers/**/extracted/`

The `default` library should stay usable as a clean starter library. Domain-specific paper lists and curated notes can live in their own library, such as `world-model-library`, instead of being loaded as the default.
