# Development setup

Python **3.8+** (CI uses 3.11). This repo uses [Poetry](https://python-poetry.org/) for dependencies.

## Quick start

```bash
chmod +x scripts/dev-setup.sh
./scripts/dev-setup.sh
source .venv/bin/activate
```

Or manually:

```bash
export PATH="$HOME/.local/bin:$PATH"
pip install poetry   # or: python3 -m pip install --user poetry
poetry config virtualenvs.in-project true
poetry install
```

Use **`poetry config virtualenvs.in-project true`** so the virtualenv lives at `.venv/`. That avoids install failures when Poetry cannot write the editable package into system `site-packages`.

## Run tests

```bash
poetry run python -m unittest discover -s tests -p 'test*.py' -v
```

Same as CI’s `python-tests` workflow (with `SKIP_SYSTEM_DEPS=1` only the lockfile dependencies are installed; no IB Gateway binary).

## Optional: full stack on Linux (IB Gateway GUI)

For Xvfb, VNC, screenshots, and the IB installer, use `scripts/setup.sh` (see `README.md`). That path downloads IB Gateway and system packages; it is heavier than `dev-setup.sh`.

## Configuration

Copy `.env.example` to `.env` for local CLI runs. `ibgateway_manager` loads the first existing file among the repository root `.env` and the current working directory `.env`.

## Editor / IDE

Point the Python interpreter at `.venv/bin/python` so imports resolve to the editable `ibgateway_manager` package.
