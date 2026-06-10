#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage:
  ./install.sh

Installs PaperX dependencies, creates local configuration, prompts for model settings
when needed, and starts the web server.

Advanced:
  ./scripts/setup.sh --configure-env
  ./scripts/run.sh
EOF
  exit 0
fi

if [[ $# -eq 0 ]]; then
  exec "${ROOT_DIR}/scripts/setup.sh" --run
fi

exec "${ROOT_DIR}/scripts/setup.sh" "$@"
