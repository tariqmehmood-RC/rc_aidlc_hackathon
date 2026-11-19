---
inclusion: fileMatch
fileMatchPattern: "**/*.{ts,tsx}"
---

# Code style (TypeScript and TSX only)

Rules for the agent. `code-review` skill checks these same rules.

## Types
- MUST type every component's props with a named `type` or `interface` declared above the component.
- NEVER use `any`. Use `unknown` and narrow it. NEVER use `enum`, `namespace` or constructor parameter properties (`erasableSyntaxOnly` is on).
- MUST use `import type { ... }` for type-only imports (`verbatimModuleSyntax` is on).

## Exports and structure
- MUST use named exports. NEVER use `export default` except where a tool requires it (for example `App` in `main.tsx`).
- One component per file, file named after the component in PascalCase.
- Function components and hooks only. Hooks start with `use`.

## Error handling
- MUST wrap every `await`, `JSON.parse` and `localStorage` access in `try/catch` and handle the failure visibly or with a safe fallback. NEVER swallow an error silently.
- NEVER trust data from `localStorage`: validate its shape before use.

## Accessibility
- MUST use semantic HTML: `<form>`, `<label>`, `<button>`, `<ul>/<li>`. NEVER use a `<div>` with `onClick` as a button.
- Every input MUST have a visible or `aria-label` label. Every icon-only or ambiguous button MUST have an `aria-label` naming its target.
- Status and error messages MUST be announced: use `role="alert"` for errors and `aria-live="polite"` for list changes.
