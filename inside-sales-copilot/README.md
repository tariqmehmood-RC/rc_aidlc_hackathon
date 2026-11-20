# Inside Sales Copilot

Team 5, AWS AI-DLC Hackathon, November 20, 2026. Turns a pasted meeting invite into a cited discovery brief. See `docs/brd-inside-sales-copilot.md` and `.kiro/specs/inside-sales-copilot/`.

This README is a stub. The full version (architecture, deploy steps, demo script) is written in Wave 6.

## Setup

Region is `us-east-1` only:

```bash
export AWS_REGION=us-east-1
export AWS_DEFAULT_REGION=us-east-1
```

### Python 3.12 for the backend

The Lambda runtime is Python 3.12. Do not use the system `python3`.

```bash
pip install uv
uv python install 3.12
uv venv --python 3.12 backend/.venv
backend/.venv/bin/python --version   # Python 3.12.x
```

Run all backend commands and tests inside this venv, for example `backend/.venv/bin/python -m pytest`. `backend/.venv` is not committed.

### Git

Local repository only. No remote, no push. See `.kiro/steering/git-workflow.md`.
