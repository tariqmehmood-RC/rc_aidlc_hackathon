# Implementation Plan: Edit Idea

## Overview

The plan adds in-place editing in seven small tasks, bottom up: validator, hook operation, edit row component, list integration, board-level tests, CSS, final verification. Each task writes its code and its Vitest tests together, then ends with one commit. Language is TypeScript (React 19.3.1, Vitest 5.1.1, Testing Library), as in the design. There is no install task and no new dependency. `package.json` scripts checked: `test` (`vitest run`), `lint`, `build`, `scan:secrets`, `scan:sast`, `check`.

### Rules that apply to every task

- Work on branch `feat/edit-idea`, never `main`. Before the first task run `git status`. If the tree is dirty, stop and ask the user. Then create the branch.
- Each task's final sub-task runs `npm test`, `npm run lint` and `npm run build` and shows the output. If any fails, fix the cause and rerun. Never delete or weaken a failing test.
- Then make exactly one commit for the task. Stage files by name (no `git add -A` or `git add .`). Message format `<type>: <imperative summary>`, at most 72 characters, no trailing period. No `--no-verify`, no `--amend`, no push, merge, rebase or reset.
- Tests live beside the code as `<name>.test.ts(x)`. `src/test/setup.ts` already clears `localStorage` in `beforeEach` and calls `cleanup()` in `afterEach`. Tests that spy on `Storage.prototype.setItem` restore the spy in `afterEach`.
- Do not start the dev server or any watch mode.
- Read the installed type declarations or existing tests before using a library API not already used in the repo, and state the versions checked when reporting.

## Tasks

- [ ] 1. Add the edit validator
  - [ ] 1.1 Add `EDIT_EMPTY_MESSAGE` and `validateEdit` to `src/ideas/validate.ts`, with tests in `src/ideas/validate.test.ts`
    - Create branch `feat/edit-idea` first (after the clean `git status` check described above).
    - Export `EDIT_EMPTY_MESSAGE = 'Enter some text before saving.'`.
    - Export `validateEdit(raw: string): ValidationResult`. It calls `validateIdea`. When the failure message is `EMPTY_MESSAGE` it returns `EDIT_EMPTY_MESSAGE`. Over-length keeps `TOO_LONG_MESSAGE`. Success passes through. Leave `validateIdea` and `EMPTY_MESSAGE` unchanged.
    - Tests to add to `src/ideas/validate.test.ts`:
      - `validateEdit('')` returns `EDIT_EMPTY_MESSAGE` (R3.1).
      - `validateEdit` on whitespace-only text, via `it.each` over spaces, a tab, a newline and a mixed string, returns `EDIT_EMPTY_MESSAGE` (R3.4).
      - `validateEdit` on 141 characters returns `TOO_LONG_MESSAGE`, which reads "Ideas can be at most 140 characters." (R3.2).
      - `validateEdit` on exactly 140 characters, and on 140 characters padded with surrounding spaces, returns ok with the trimmed text (R3.3).
      - `validateEdit('  hi  ')` returns ok with `'hi'` (R2.1 trimming).
      - Regression: `validateIdea('')` still returns `EMPTY_MESSAGE`, "Enter an idea before adding it." (R3.10 at validator level).
    - _Requirements: 2.1, 3.1, 3.2, 3.3, 3.4, 3.10_
  - [ ] 1.2 Run `npm test`, `npm run lint`, `npm run build`, then commit
    - Stage `src/ideas/validate.ts` and `src/ideas/validate.test.ts`.
    - Commit message: `feat: add edit-specific validation message`

- [ ] 2. Add `updateIdea` to the ideas hook
  - [ ] 2.1 Implement `updateIdea` and `UpdateResult` in `src/ideas/useIdeas.ts`, with tests in `src/ideas/useIdeas.test.tsx`
    - Export `type UpdateResult = 'saved' | 'unchanged' | 'invalid' | 'not-found'` and add `updateIdea(id, text): UpdateResult` to the hook's return value, as in the design's contract: look up the idea, validate with `validateIdea`, return `'unchanged'` when the trimmed text equals the current text, otherwise `commit` the mapped list and return `'saved'`. Reuse the existing `commit` so `saveError` behaves as in add and delete. Do not change `storage.ts` or `types.ts`.
    - Tests to add to `src/ideas/useIdeas.test.tsx` (use `renderHook` and `act` as the file already does; count writes with `vi.spyOn(Storage.prototype, 'setItem')`):
      - Valid update replaces only `text` with the trimmed text and keeps `id` and `createdAt` (R9.1, R2.4, R2.1).
      - Other ideas are deep-equal before and after (R9.2, R2.8).
      - Exactly one `setItem` call, and the stored list equals the new in-memory list (R9.3, R2.5).
      - Unknown id returns `'not-found'`, list unchanged, zero `setItem` calls (R9.4).
      - Invalid text, via `it.each` over empty, whitespace-only and 141 characters, returns `'invalid'`, list unchanged, zero `setItem` calls (R9.5).
      - With `setItem` mocked to throw, the list holds the new text and `saveError` is true (R9.6, R2.10).
      - Same trimmed text (including extra surrounding spaces) returns `'unchanged'`, zero writes, and `saveError` stays as it was (R2.7).
      - After a failed write, a later successful `updateIdea` clears `saveError` (R7.4, save case).
      - Table test for Property 1 (R9.7): nested loops build 18 cases (sizes 1, 2, 5; positions first, middle, last where they exist; new text of 1, 70 and 140 `'x'` characters, different from the old text). Each case asserts the result is `'saved'` and that length and id order are unchanged. Use `it.each`. No random values.
      - Table test for Property 2 (R9.8): same 18 cases; after `'saved'`, `loadIdeas()` deep-equals the hook's `ideas`.
    - _Requirements: 2.1, 2.4, 2.5, 2.7, 2.8, 2.10, 7.4, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8_
  - [ ] 2.2 Run `npm test`, `npm run lint`, `npm run build`, then commit
    - Stage `src/ideas/useIdeas.ts` and `src/ideas/useIdeas.test.tsx`.
    - Commit message: `feat: add updateIdea to the ideas hook`

- [ ] 3. Build the `IdeaEditRow` component
  - [ ] 3.1 Create `src/ideas/IdeaEditRow.tsx` with tests in `src/ideas/IdeaEditRow.test.tsx`
    - Props `{ idea: Idea; onSave: (id: string, text: string) => void; onCancel: (id: string) => void }`. Markup and behaviour as in the design: a `noValidate` form with a visually hidden label "Edit idea", a single-line `type="text"` input with no `maxLength`, Save (`type="submit"`, `aria-label` "Save idea: <text>"), Cancel (`type="button"`, `aria-label` "Cancel editing idea: <text>"), and an error `<p role="alert">`. Use `useId` for ids. Draft starts as the exact saved text. On mount, focus and select the field. Submit runs `validateEdit`: on failure set the error and refocus the field, on success call `onSave(idea.id, trimmed)`. `onChange` clears the error. Escape on the form calls `onCancel`. No blur handler. Text is only used as `value` and in attribute strings. Named export, typed props, no `any`.
    - Tests in `src/ideas/IdeaEditRow.test.tsx` (render the row alone with `vi.fn()` callbacks and `userEvent.setup()`):
      - Field has focus on mount (R1.3, R5.5 row part).
      - Field value equals the saved text exactly, including leading and trailing spaces (R1.2 value).
      - Field is found by label "Edit idea" (R1.6).
      - Field has `type="text"` and no `maxLength` attribute (R1.7).
      - `selectionStart` is 0 and `selectionEnd` equals the value length (R1.8).
      - Exactly one button named "Save idea: <text>" (R1.4) and one named "Cancel editing idea: <text>" (R1.9).
      - Click Save with valid text calls `onSave(id, trimmed)` once (R2.1).
      - Enter in the field gives the same single `onSave` call (R2.2).
      - Invalid text: `onSave` not called, error shown, field still present (R2.9).
      - Empty draft shows "Enter some text before saving." (R3.1). 141 characters shows "Ideas can be at most 140 characters." (R3.2). Exactly 140 characters calls `onSave` and shows no error (R3.3). Whitespace-only drafts, via `it.each` over spaces, tab and newline, show the edit message and the field remains (R3.4).
      - Error element has `role="alert"` (R3.6). Field has `aria-invalid="true"` and `aria-describedby` equal to the error element's id (R3.7).
      - After a rejected save by button click, the field has focus (R3.8).
      - Typing after an error removes the alert and `aria-invalid` is not `"true"` (R3.9).
      - Click Cancel calls `onCancel(id)` and not `onSave` (R4.1).
      - Escape in the field calls `onCancel` (R4.2). Escape while the Save button is focused, and while the Cancel button is focused, via `it.each`, calls `onCancel` (R4.3).
      - Blur: tab away from the field; field, draft text and any error are unchanged and neither callback was called (R4.8).
      - Focused Save and Cancel activated with Enter and with Space behave like a click, via `it.each` (R8.5, Save and Cancel part).
      - Idea text `<b>x</b>` appears verbatim as the field value and `document.querySelector('b')` is null (R8.6, R8.3 row part).
    - _Requirements: 1.2, 1.3, 1.4, 1.6, 1.7, 1.8, 1.9, 2.1, 2.2, 2.9, 3.1, 3.2, 3.3, 3.4, 3.6, 3.7, 3.8, 3.9, 4.1, 4.2, 4.3, 4.8, 5.5, 8.3, 8.5, 8.6_
  - [ ] 3.2 Run `npm test`, `npm run lint`, `npm run build`, then commit
    - Stage `src/ideas/IdeaEditRow.tsx` and `src/ideas/IdeaEditRow.test.tsx`.
    - Commit message: `feat: add IdeaEditRow component`

- [ ] 4. Integrate editing into `IdeaList` and pass `onUpdate` from `IdeaBoard`
  - [ ] 4.1 Extend `src/ideas/IdeaList.tsx` and add the one-line wiring in `src/ideas/IdeaBoard.tsx`, with tests in `src/ideas/IdeaList.test.tsx`
    - `IdeaList` gains the required prop `onUpdate: (id: string, text: string) => UpdateResult`. Add `editingId` state, the `focusAfterRender` ref and the Edit-button `Map` ref, the focus-restoring effect, and `handleSave` / `finishEdit` as in the design. View mode shows the text span, an Edit button (`aria-label` "Edit idea: <text>", label "Edit") and Delete. Edit mode renders `IdeaEditRow` plus Delete and no Edit button. Keep `key={idea.id}` on each `<li>` and keep the `aria-live="polite"` wrapper and `<ul aria-label="Ideas">` unchanged.
    - Because the prop is required, `IdeaBoard.tsx` fails `tsc -b` until it passes `updateIdea` as `onUpdate`. That one-line change is part of this task so the build stays green for the commit. All board-level behaviour tests are in task 5.
    - Update every existing `render(<IdeaList ... />)` in `src/ideas/IdeaList.test.tsx` to pass `onUpdate={vi.fn()}`. Do not change what those tests assert.
    - Tests to add to `src/ideas/IdeaList.test.tsx` (render the list with a stateful wrapper or a mocked `onUpdate` that returns `'saved'` as each test needs):
      - Each idea in view mode has one button named "Edit idea: <text>" (R1.1).
      - Click Edit: field value equals the saved text exactly, with leading and trailing spaces, and the text span is gone (R1.2).
      - The edited idea's Delete button is still present (R1.5).
      - In edit mode no button named "Edit idea: <text>" exists for that idea (R1.10).
      - Saving with `onUpdate` returning `'saved'` leaves edit mode and the Edit button has focus (`document.activeElement`) (R2.6). Same with `'unchanged'` (R2.7 UI part). With `'invalid'` the row stays open (R2.9 list part).
      - Cancel leaves edit mode, shows the original text, and focus moves to that idea's Edit button (R4.1 display, R4.4). Escape does the same.
      - Error shown, Cancel, then Edit again: no alert present (R4.5).
      - Edit A, type, click Edit on B: A shows its saved text (R5.1), B has a field (R5.2), `getAllByRole('textbox')` within the list has length 1 (R5.3), and B's field has focus (R5.5).
      - A showed an error, switch to B: no alert in the document (R5.4).
      - Switch makes no `onUpdate` call, so the stored list is unchanged (R5.6 list part).
      - Rerender with the edited idea removed from `ideas` (delete the edited idea): no textbox remains (R6.1 list part). Rerender with a different idea removed: the edited row remains with the typed draft unchanged (R6.2 list part).
      - `aria-live="polite"` wrapper is present in view mode and in edit mode (R8.2).
      - Focused Edit button activated with Enter and with Space opens the field, via `it.each` (R8.5 Edit part).
      - Stored text `<b>x</b>` appears verbatim as the field value (R8.6).
    - _Requirements: 1.1, 1.2, 1.5, 1.10, 2.6, 2.7, 2.9, 4.1, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1, 6.2, 8.2, 8.5, 8.6_
  - [ ] 4.2 Run `npm test`, `npm run lint`, `npm run build`, then commit
    - Stage `src/ideas/IdeaList.tsx`, `src/ideas/IdeaList.test.tsx` and `src/ideas/IdeaBoard.tsx`.
    - Commit message: `feat: edit ideas in place from the list`

- [ ] 5. Add board-level tests through the real hook and storage
  - [ ] 5.1 Extend `src/ideas/IdeaBoard.test.tsx`
    - No production code changes unless a test exposes a defect; if it does, fix the code in this task and say so in the commit body-free summary. Seed ideas by saving to `localStorage` (via `saveIdeas` or direct `setItem` before render) and render `<IdeaBoard />`.
    - Tests to add (each uses `userEvent.setup()`; write counts via `vi.spyOn(Storage.prototype, 'setItem')`):
      - Save keeps the idea at the same index (R2.3).
      - Changed save writes once, and a fresh `render` of a new `<IdeaBoard />` after unmounting shows the edited text (R2.5).
      - After save, `document.activeElement` is the idea's Edit button (R2.6).
      - Saving the same text, also with extra surrounding spaces: row closes, text unchanged, zero `setItem` calls (R2.7).
      - Invalid save: zero `setItem` calls and stored text unchanged (R2.9, R3.5).
      - With `setItem` throwing: edited text shown, row closed, no textbox, no edit error, and "Could not save your ideas in this browser." visible right after the click (R2.10, R7.1, R7.2, R7.3).
      - Add form with empty input still shows "Enter an idea before adding it." (R3.10).
      - Type then Cancel shows the original text (R4.1), focus on the Edit button (R4.4), zero `setItem` calls and stored value unchanged (R4.6), and order and other texts unchanged (R4.7).
      - Switching edits makes zero `setItem` calls and leaves the stored list identical (R5.6).
      - Delete the edited idea: idea gone, no textbox, the draft is not in storage (R6.1). Delete a different idea: edited row remains with draft unchanged character for character (R6.2).
      - Add a valid idea while editing: new idea present, draft unchanged (R6.3). While editing, the Add input and Add button are enabled (R6.4). Invalid add during edit shows the Add message, adds nothing, draft unchanged (R6.5).
      - After a failed write, a successful add, delete and changed save each clear the Save_Error, via `it.each` (R7.4).
      - With Save_Error shown, Cancel and starting another edit keep it shown (R7.5).
      - `user.tab()` from the top visits each Edit button, then in edit mode the field, Save and Cancel, each exactly once in visual order with no trap (R8.1).
      - Save `<b>x</b>`: shown as text and `document.querySelector('b')` is null (R8.3).
      - After a changed save, buttons named with the new text exist and buttons named with the previous text do not, for both Edit and Delete (R8.4).
    - _Requirements: 2.3, 2.5, 2.6, 2.7, 2.9, 2.10, 3.5, 3.10, 4.1, 4.4, 4.6, 4.7, 5.6, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.3, 8.4_
  - [ ] 5.2 Run `npm test`, `npm run lint`, `npm run build`, then commit
    - Stage `src/ideas/IdeaBoard.test.tsx` (and any production file changed in 5.1, by name).
    - Commit message: `test: cover editing an idea end to end on the board`

- [ ] 6. Add edit styles
  - [ ] 6.1 Add the CSS classes to `src/App.css`
    - Add `.idea-edit` (flex row for field and buttons), `.idea-edit-label` (visually hidden label), `.idea-edit input` with an `[aria-invalid='true']` border using the existing `--danger` variable, `.idea-actions` only if the layout needs it, and `.button-secondary` for Cancel. Reuse `.idea-error`. Read the existing `src/App.css` first and match its variables and naming. If a class is used in a component but missing here, add the class name in the component only if it is already there; do not change component behaviour.
    - No test: CSS needs none under the testing rules.
    - _Requirements: 8.1 (visible, usable controls)_
  - [ ] 6.2 Run `npm test`, `npm run lint`, `npm run build`, then commit
    - Stage `src/App.css`.
    - Commit message: `feat: style the idea edit row`

- [ ] 7. Final verification
  - [ ] 7.1 Run the full checks and report results
    - Run `npm test`, `npm run lint` and `npm run build` and show the output.
    - Check whether `gitleaks` and `semgrep` are on the PATH (for example `command -v gitleaks semgrep`). If both exist, run `npm run check`. If either is missing, say which one and that `npm run check` was not run. Do not install them.
    - Confirm with `git status` and `git log --oneline main..HEAD` that the branch is `feat/edit-idea`, the tree is clean, and there is one commit per task 1 to 6.
    - Walk the traceability table below against the test names and report any criterion with no test.
    - Do not start the dev server. Ask the user to run `npm run dev` for any manual look.
    - No commit unless a fix was needed; a fix gets its own commit with the same checks first.
    - _Requirements: 1 to 9_

## Requirement traceability

Each criterion maps to the task whose tests cover it. Criteria listed under more than one task are covered at both levels.

| Requirement | Criteria and covering task |
|---|---|
| 1 Start editing | 1.1 task 4; 1.2 tasks 3, 4; 1.3 task 3; 1.4 task 3; 1.5 task 4; 1.6 task 3; 1.7 task 3; 1.8 task 3; 1.9 task 3; 1.10 task 4 |
| 2 Save an edit | 2.1 tasks 1, 2, 3; 2.2 task 3; 2.3 task 5; 2.4 task 2; 2.5 tasks 2, 5; 2.6 tasks 4, 5; 2.7 tasks 2, 4, 5; 2.8 task 2; 2.9 tasks 3, 4, 5; 2.10 tasks 2, 5 |
| 3 Validate an edit | 3.1 tasks 1, 3; 3.2 tasks 1, 3; 3.3 tasks 1, 3; 3.4 tasks 1, 3; 3.5 task 5; 3.6 task 3; 3.7 task 3; 3.8 task 3; 3.9 task 3; 3.10 tasks 1, 5 |
| 4 Cancel an edit | 4.1 tasks 3, 4, 5; 4.2 tasks 3, 4; 4.3 task 3; 4.4 tasks 4, 5; 4.5 task 4; 4.6 task 5; 4.7 task 5; 4.8 task 3 |
| 5 One edit at a time | 5.1 task 4; 5.2 task 4; 5.3 task 4; 5.4 task 4; 5.5 tasks 3, 4; 5.6 tasks 4, 5 |
| 6 Add and delete | 6.1 tasks 4, 5; 6.2 tasks 4, 5; 6.3 task 5; 6.4 task 5; 6.5 task 5 |
| 7 Storage failure | 7.1 task 5; 7.2 task 5; 7.3 task 5; 7.4 tasks 2, 5; 7.5 task 5 |
| 8 Accessibility and safe display | 8.1 task 5; 8.2 task 4; 8.3 tasks 3, 5; 8.4 task 5; 8.5 tasks 3, 4; 8.6 tasks 3, 4 |
| 9 Update operation | 9.1 to 9.6 task 2; 9.7 task 2 (Property 1 table); 9.8 task 2 (Property 2 table) |

## Notes

- No task is optional. Every test is written in the same task as the code it covers and is part of that task's commit.
- Deviation from the suggested order: the one-line `onUpdate={updateIdea}` wiring in `IdeaBoard.tsx` moves from task 5 into task 4. `onUpdate` is a required prop, so without it `npm run build` fails at task 4 and the commit would be blocked. Task 5 is board-level tests only.
- The design has no generated-input properties, so Properties 1 and 2 are table-driven `it.each` cases in task 2, as the design states.
- Edit state is derived, so deleting the edited idea needs no cleanup handler (design decision 5).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2.1"] },
    { "id": 3, "tasks": ["2.2"] },
    { "id": 4, "tasks": ["3.1"] },
    { "id": 5, "tasks": ["3.2"] },
    { "id": 6, "tasks": ["4.1"] },
    { "id": 7, "tasks": ["4.2"] },
    { "id": 8, "tasks": ["5.1"] },
    { "id": 9, "tasks": ["5.2"] },
    { "id": 10, "tasks": ["6.1"] },
    { "id": 11, "tasks": ["6.2"] },
    { "id": 12, "tasks": ["7.1"] }
  ]
}
```
