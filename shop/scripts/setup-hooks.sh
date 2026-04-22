#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_DIR="${ROOT_DIR}/.githooks"

if [[ ! -d "${HOOKS_DIR}" ]]; then
  echo "Missing hooks directory: ${HOOKS_DIR}" >&2
  exit 1
fi

git -C "${ROOT_DIR}" config core.hooksPath .githooks
echo "Git hooks path set to .githooks"
