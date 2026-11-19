# Design: Idea board

Implements `requirements.md`. Stack and rules: see `.kiro/steering/`.

## Files to add or change
| File | Purpose |
|---|---|
| `src/ideas/types.ts` | `Idea` type and the `MAX_IDEA_LENGTH` constant (140) |
| `src/ideas/validate.ts` | `validateIdea(raw)`: returns `{ ok: true, text }` or `{ ok: false, message }` |
| `src/ideas/storage.ts` | `loadIdeas()` and `saveIdeas(ideas)`; storage key `idea-board:ideas` |
| `src/ideas/useIdeas.ts` | Hook holding the list, `addIdea`, `deleteIdea`, and a `saveError` flag |
| `src/ideas/IdeaForm.tsx` | Labelled input, Add button, error message |
| `src/ideas/IdeaList.tsx` | The list, empty state, Delete buttons |
| `src/ideas/IdeaBoard.tsx` | Composes the form and list |
| `src/App.tsx` | Renders `IdeaBoard` (replaces the Vite starter page) |
| `src/App.css`, `src/index.css` | Replaced with small styles for the board |
| `src/ideas/*.test.ts(x)` | Tests, one per behaviour group |
| `src/test/setup.ts` | Testing Library matchers and `localStorage` reset |
| `vite.config.ts`, `package.json` | Vitest config (`test` block) and `test` script |

Removed: the Vite starter content in `src/assets/` (hero.png, react.svg, vite.svg) and `public/icons.svg`, which nothing references once `App.tsx` is replaced.

## Data shape
```ts
export type Idea = { id: string; text: string; createdAt: number }
```
- `id`: `crypto.randomUUID()`. Needs a secure context. localhost and HTTPS both qualify, which covers the IDE proxy URL.
- Stored as a JSON array in `localStorage["idea-board:ideas"]`, newest first.

## Behaviour
- `validateIdea` trims, rejects empty with "Enter an idea before adding it.", rejects more than 140 trimmed characters with "Ideas can be at most 140 characters." (Req 2).
- `loadIdeas` wraps `getItem` and `JSON.parse` in `try/catch`, checks the value is an array whose items have string `id`, string `text` and numeric `createdAt`, and returns `[]` otherwise (Req 5.3, 5.4).
- `saveIdeas` wraps `setItem` in `try/catch` and returns a boolean (Req 5.5).
- `useIdeas` initialises state lazily from `loadIdeas`, prepends on add, filters by `id` on delete, and calls `saveIdeas` after each change (Req 1, 4, 5).
- `IdeaForm` is a `<form>`; Enter submit comes free from the form. Errors render in an element with `role="alert"`. After a successful add it clears the input and refocuses it (Req 1.3).
- `IdeaList` renders `<ul>` with `<li>` per idea. Text is rendered as a React text child, so markup is never interpreted (Req 3.4). Long text wraps with CSS `overflow-wrap: anywhere` (Req 3.5).
- The list container has `aria-live="polite"` so changes are announced.

## Error handling
All `localStorage` and `JSON.parse` calls are in `try/catch` (see `code-style.md`). A save failure surfaces as a visible, non-blocking message; the in-memory list stays correct.

## Testing approach
Vitest + React Testing Library + jsdom. Pure functions get unit tests; each acceptance criterion group gets a component test driven through the real UI (typing, clicking). `localStorage` is cleared before each test. No network.

## Decisions
- No extra dependencies at runtime. Dev-only additions: `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom`.
- No undo, no confirmation on delete: both are out of scope in the brief.
