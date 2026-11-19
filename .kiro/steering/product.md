# Product

## Overview
`idea-board` is a single-page, client-side web app for capturing short ideas. The first feature (specified in `docs/brd-idea-board.md` and `.kiro/specs/idea-board/`) is a minimal idea board: add a short idea, see the list, delete one, and keep the list in the browser's local storage.

## What I am building now
The idea board described above, and nothing more. Out of scope for this feature: editing ideas, tags, search, sorting, accounts, syncing, and any backend.

## Current state
- Single feature in progress: the idea board.
- No backend, routing, authentication or database. Data lives only in `localStorage`.
- Tests are required for new behaviour (see `testing.md`).

## Guidance for the agent
- Do not assume features beyond what the user asks for. When a request depends on product intent, ask or state the assumption.
- Treat `docs/brd-idea-board.md` as the source of truth for scope. If it is ambiguous or incomplete, say so instead of guessing.
- Keep the app client-side only unless the user asks for a backend.
- Do not add unrequested extras (for example undo, export, drag and drop). Propose them and wait.

## Update this file
When the product direction grows, record here: target users, core entities, main user flows, and out-of-scope items.
