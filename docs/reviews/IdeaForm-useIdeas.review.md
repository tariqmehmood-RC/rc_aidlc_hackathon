# Code review: IdeaForm.tsx and useIdeas.ts

Skill: `code-review` (first version, before the improvement in Lab 2 step 4).

## src/ideas/IdeaForm.tsx

### Critical
None.

### Warnings
None.

### Suggestions
- src/ideas/IdeaForm.tsx:19 — validation only runs on submit. Showing the remaining character count near 140 would let users see the limit before they hit it.

### Passed
- src/ideas/IdeaForm.tsx:6-8 — props typed with the named type `IdeaFormProps`.
- src/ideas/IdeaForm.tsx:10 — named export.
- src/ideas/IdeaForm.tsx:17-28 — no async calls; invalid input is handled visibly.
- `<form>`, a `<label htmlFor>` tied to the input, a real submit `<button>`, `aria-invalid` and `aria-describedby` on the input, and the error in `role="alert"`.

Summary: Critical 0, Warnings 0, Suggestions 1, Passed 4.

## src/ideas/useIdeas.ts

### Critical
None.

### Warnings
- src/ideas/useIdeas.ts:23 — `crypto.randomUUID()` throws outside a secure context (plain HTTP on a non-localhost host). Nothing catches it, so adding an idea would crash there. Both the proxy URL (HTTPS) and localhost are secure contexts today, so this is not reachable now.

### Suggestions
- src/ideas/useIdeas.ts:24 and :28 — `commit` builds the next list from the `ideas` value captured at render time. Two calls in the same tick would lose one change. The current UI cannot trigger that, but a functional update would remove the risk.

### Passed
- src/ideas/useIdeas.ts:5-10 — return type `UseIdeas` is a named, exported type.
- src/ideas/useIdeas.ts:13 — named export.
- src/ideas/useIdeas.ts:19 — save failures are surfaced through `saveError`, not swallowed.
- Typed props / accessibility: not applicable, because this hook renders nothing. The first version of the skill had no rule for this case.

Summary: Critical 0, Warnings 1, Suggestions 1, Passed 3.
