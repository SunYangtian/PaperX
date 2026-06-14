#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PAPERX_VENV:-${ROOT_DIR}/.venv}"
PYTHON_BIN="${PYTHON:-python3}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple/}"
RUN_AFTER_SETUP=0
CONFIGURE_ENV="auto"

usage() {
  cat <<'EOF'
Usage: ./install.sh [--run] [--configure-env] [--no-env-prompt]

Options:
  --run             Start the Flask server after installing dependencies.
  --configure-env   Prompt for model credentials and write or replace a local .env file.
  --no-env-prompt   Skip the interactive .env prompt.

Environment:
  PYTHON              Python executable to use. Default: python3
  PAPERX_VENV          Virtualenv path. Default: .venv
  PIP_INDEX_URL        Python package index. Default: https://mirrors.aliyun.com/pypi/simple/
  HOST                Server bind host when --run is used. Default: 127.0.0.1
  PORT                Server port when --run is used. Default: 8000
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run)
      RUN_AFTER_SETUP=1
      shift
      ;;
    --configure-env)
      CONFIGURE_ENV="yes"
      shift
      ;;
    --no-env-prompt)
      CONFIGURE_ENV="no"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

configure_env_file() {
  local default_model default_base_url default_host default_port default_proxy
  local api_key model base_url host port access_password access_secret proxy_url

  default_model="gpt-5.5"
  default_base_url="https://api.openai.com/v1"
  default_host="127.0.0.1"
  default_port="8000"
  default_proxy="http://192.168.48.17:18000"

  read -r -p "OPENAI_BASE_URL [${default_base_url}]: " base_url
  read -r -p "OPENAI_MODEL [${default_model}]: " model
  read -r -s -p "OPENAI_API_KEY (leave blank for local retrieval mode): " api_key
  echo
  read -r -s -p "PAPERX_ACCESS_PASSWORD (leave blank to disable page login): " access_password
  echo
  read -r -p "HTTP/HTTPS proxy for paper downloads [${default_proxy}, enter none to disable]: " proxy_url
  read -r -p "HOST [${default_host}]: " host
  read -r -p "PORT [${default_port}]: " port

  base_url="${base_url:-${default_base_url}}"
  model="${model:-${default_model}}"
  host="${host:-${default_host}}"
  port="${port:-${default_port}}"
  proxy_url="${proxy_url:-${default_proxy}}"
  if [[ "${proxy_url}" == "none" || "${proxy_url}" == "NONE" ]]; then
    proxy_url=""
  fi
  access_secret=""
  if [[ -n "${access_password}" ]]; then
    access_secret="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
  fi

  {
    printf '%s\n' "# Local runtime secrets. This file is ignored by Git."
    printf 'OPENAI_BASE_URL=%s\n' "${base_url}"
    printf 'OPENAI_MODEL=%s\n' "${model}"
    printf 'OPENAI_API_KEY=%s\n' "${api_key}"
    printf 'OPENAI_RESPONSES_PATH=/responses\n'
    printf 'PAPER_MODEL_PROVIDER=openai\n'
    printf 'REQUIRES_OPENAI_AUTH=true\n'
    printf 'MAX_OUTPUT_TOKENS=1200\n'
    printf 'OPENAI_TIMEOUT_SECONDS=180\n'
    printf 'ANALYSIS_SOURCE_CHAR_LIMIT=70000\n'
    printf 'ANALYSIS_MAX_OUTPUT_TOKENS=3000\n'
    printf 'ANALYSIS_TIMEOUT_SECONDS=240\n'
    printf 'HOST=%s\n' "${host}"
    printf 'PORT=%s\n' "${port}"
    printf 'PAPERX_ACCESS_PASSWORD=%s\n' "${access_password}"
    printf 'PAPERX_SECRET_KEY=%s\n' "${access_secret}"
    printf 'http_proxy=%s\n' "${proxy_url}"
    printf 'https_proxy=%s\n' "${proxy_url}"
  } > .env
  chmod 600 .env
  echo "Created local .env"
}

cd "${ROOT_DIR}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "Creating virtual environment at ${VENV_DIR}"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

python -m pip install --index-url "${PIP_INDEX_URL}" --upgrade pip
python -m pip install --index-url "${PIP_INDEX_URL}" -r requirements.txt

mkdir -p papers/pdfs web/libraries/default/papers
touch papers/pdfs/.gitkeep
touch web/libraries/default/papers/.gitkeep
if [[ ! -f web/libraries/default/papers.json ]]; then
  printf '[]\n' > web/libraries/default/papers.json
fi

if [[ "${CONFIGURE_ENV}" == "yes" ]]; then
  configure_env_file
elif [[ ! -f .env && "${CONFIGURE_ENV}" == "auto" && -t 0 ]]; then
  configure_env_file
elif [[ -f .env ]]; then
  echo "Using existing local .env"
fi

display_host="${HOST:-127.0.0.1}"
display_port="${PORT:-8000}"
if [[ -f .env ]]; then
  while IFS= read -r line || [[ -n "${line}" ]]; do
    if [[ "${line}" == export" "* ]]; then
      line="${line#export }"
      line="${line#"${line%%[![:space:]]*}"}"
    fi
    [[ -z "${line}" || "${line}" == \#* || "${line}" != *=* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    if [[ ${#value} -ge 2 ]]; then
      first="${value:0:1}"
      last="${value: -1}"
      if [[ "${first}" == "${last}" && ( "${first}" == "'" || "${first}" == '"' ) ]]; then
        value="${value:1:${#value}-2}"
      fi
    fi
    if [[ "${key}" == "HOST" && -z "${HOST+x}" ]]; then
      display_host="${value}"
    elif [[ "${key}" == "PORT" && -z "${PORT+x}" ]]; then
      display_port="${value}"
    fi
  done < .env
fi

cat <<EOF

PaperX is ready.

Next steps:
  1. Edit .env if you need to change model settings.
  2. Start the server:
       ./scripts/run.sh
  3. Open:
       http://${display_host}:${display_port}

EOF

if [[ "${RUN_AFTER_SETUP}" == "1" ]]; then
  exec "${ROOT_DIR}/scripts/run.sh"
fi
