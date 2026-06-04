#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PAPERX_VENV:-${ROOT_DIR}/.venv}"

cd "${ROOT_DIR}"

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "Virtual environment not found. Running setup first."
  "${ROOT_DIR}/scripts/setup.sh"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

if [[ -f .env ]]; then
  while IFS= read -r line || [[ -n "${line}" ]]; do
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
    if [[ "${key}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ && -z "${!key+x}" ]]; then
      export "${key}=${value}"
    fi
  done < .env
fi

export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-8000}"

echo "Starting PaperX at http://${HOST}:${PORT}"
exec python server/app.py
