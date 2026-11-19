---
name: code-review
description: Reviews a .ts or .tsx file in this project (React 19 + TypeScript) for typed props, named exports, error handling on async calls and storage, and accessibility, and reports findings with file and line. Use when the user asks to review, audit or check a .ts/.tsx file, component or hook in this repository. Do not use for CSS, config, JSON or Markdown files, or for writing or fixing code.
---

# Code review

Review the `.ts` or `.tsx` file the user names in this project. If they name a component, find its file first.

## Before you review
- Read the whole file. Do not review code you have not read.
- If the file is not `.ts` or `.tsx`, say this skill does not apply and stop.
- Number the lines (for example with `nl -ba <file>`) so every finding can cite a real line.
- Read another file only to confirm a finding (for example where a prop comes from). Do not review that other file.

## What to check

1. **Typed props.** Every component declares a named `type` or `interface` for its props. Flag `any`, missing prop types, and inline anonymous prop types on exported components. For hooks and helpers, check that exported functions have typed parameters and return values instead.
2. **Named exports.** Components, hooks and helpers use named exports. Flag `export default`, except `App` in `src/App.tsx`, which `main.tsx` imports as a default.
3. **Error handling.** Every `await`, `fetch`, `JSON.parse`, `localStorage` access and call that can throw (for example `crypto.randomUUID()` outside a secure context) is inside `try/catch` or has a `.catch`, and the failure is handled visibly or with a safe fallback. Flag errors that are swallowed silently.
4. **Accessibility** (files that render JSX only).
   - Semantic HTML: `<form>`, `<label>`, `<button>`, `<ul>/<li>`, `<main>`. Flag a `<div>` or `<span>` with `onClick` standing in for a button.
   - Every input has a label. Every icon-only or ambiguous button has an `aria-label`.
   - Errors use `role="alert"`. Live list changes use `aria-live`.
   - Focus is not lost when the focused element is removed.

If a check does not apply to the file (for example accessibility in a hook that renders nothing), list it under Passed as "not applicable" with the reason.

## Rules for findings
- Every finding MUST start with `path:line` (or `path:start-end`), using the path from the project root, for example `src/ideas/IdeaList.tsx:20`.
- One finding per bullet. Say what is wrong, why it matters, and what to change.
- Only report what you can point to in the code. If you are unsure, put it under Suggestions and say what you could not confirm.
- Do not edit the file. This skill reports; the user decides what to change.

## Output format

Reply with exactly these four sections, in this order. Write "None." under a section with no entries.

### Critical
Problems that break behaviour, lose data, or block users of assistive technology.

### Warnings
Problems that break a rule above but do not break behaviour today.

### Suggestions
Optional improvements.

### Passed
Each check the code satisfies, with `path:line` where it applies.

End with one line: `Summary: Critical N, Warnings N, Suggestions N, Passed N.`
