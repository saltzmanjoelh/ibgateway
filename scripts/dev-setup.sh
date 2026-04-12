#!/usr/bin/env bash
# Local development environment for the ibgateway Python package (not the full IB Gateway stack).
# For Docker + IB Gateway + noVNC, see README.md.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export PATH="${HOME}/.local/bin:${PATH}"

if ! command -v poetry >/dev/null 2>&1; then
  echo "Installing Poetry..."
  python3 -m pip install --user --upgrade pip
  python3 -m pip install --user poetry
  export PATH="${HOME}/.local/bin:${PATH}"
fi

# In-project venv avoids PEP 660 install issues when the system site-packages dir is not writable.
poetry config virtualenvs.create true
poetry config virtualenvs.in-project true

poetry install --no-interaction --no-ansi

echo ""
echo "Done. Activate the environment:"
echo "  source ${REPO_ROOT}/.venv/bin/activate"
echo ""
echo "Run tests:"
echo "  poetry run python -m unittest discover -s tests -p 'test*.py' -v"
echo ""
echo "Optional: copy .env.example to .env and set IBGATEWAY_USERNAME / IBGATEWAY_PASSWORD for automation."
