# Code review: src/ideas/IdeaList.tsx

Skill: `code-review` (first version). Reviewed file: `src/ideas/IdeaList.tsx` (31 lines).

### Critical
None.

### Warnings
- Line 20: deleting an idea removes the button that has focus, so focus drops to `<body>`. Keyboard and screen-reader users lose their place in the list. Move focus to the next idea's Delete button, or to the input when the list becomes empty.

### Suggestions
- Line 10: `aria-live="polite"` wraps the whole list, so a change can make a screen reader read out list content, including every "Delete" label. A short, visually hidden status message ("Idea added", "Idea deleted") would be clearer.
- Line 21: the accessible name repeats the full idea text (up to 140 characters) on every button. It is correct, but long. Consider truncating it in the label only.

### Passed
- Typed props: `IdeaListProps` is a named type (lines 3-6) used on line 8.
- Named export: `export function IdeaList` (line 8).
- Error handling: this file has no async calls, `JSON.parse` or storage access. Storage errors are handled in `storage.ts`.
- Semantic HTML: `<ul>`/`<li>` (lines 14, 16) and a real `<button type="button">` (lines 18-19).
- Delete buttons have an accessible name that includes the visible word "Delete" and the idea text (line 21).
- User text is rendered as a text child (line 17), so markup is never interpreted.
- Empty state is shown when the list is empty (line 12).

Summary: Critical 0, Warnings 1, Suggestions 2, Passed 7.
