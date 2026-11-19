# Implementation plan: Idea board

- [x] 1. Add the test tooling
  - Install dev dependencies: `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom`
  - Add the `test` script (`vitest run`), a `test` block in `vite.config.ts` (jsdom, setup file), and `src/test/setup.ts`
  - _Requirements: testing.md_

- [x] 2. Define the idea type and validation
  - [x] 2.1 Create `src/ideas/types.ts` with `Idea` and `MAX_IDEA_LENGTH`
  - [x] 2.2 Create `src/ideas/validate.ts`
  - [x] 2.3 Write `validate.test.ts`: empty, whitespace-only, 1 char, exactly 140, 141, surrounding spaces trimmed
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 3. Build local storage persistence
  - [x] 3.1 Create `src/ideas/storage.ts` with `loadIdeas` and `saveIdeas`
  - [x] 3.2 Write `storage.test.ts`: missing key, round trip, invalid JSON, wrong shape, write failure returns false
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 4. Build the state hook
  - [x] 4.1 Create `src/ideas/useIdeas.ts` (add, delete, save error)
  - [x] 4.2 Write `useIdeas.test.tsx`: newest first, delete by id with duplicate text, persistence after each change
  - _Requirements: 1.1, 3.1, 4.1, 4.2, 5.1_

- [x] 5. Build the form
  - [x] 5.1 Create `src/ideas/IdeaForm.tsx` (label, input, Add button, `role="alert"` error)
  - [x] 5.2 Write `IdeaForm.test.tsx`: click add, Enter add, clears and refocuses, empty and whitespace errors, 140/141 limits, error cleared on success
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 6. Build the list
  - [x] 6.1 Create `src/ideas/IdeaList.tsx` (empty state, Delete buttons with accessible names)
  - [x] 6.2 Write `IdeaList.test.tsx`: empty state, order, markup shown literally, delete button names
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.3, 4.4_

- [x] 7. Compose the board and replace the starter page
  - [x] 7.1 Create `src/ideas/IdeaBoard.tsx`; point `src/App.tsx` at it; replace `App.css` and `index.css`
  - [x] 7.2 Remove the unused Vite starter assets
  - [x] 7.3 Write `IdeaBoard.test.tsx`: add two, delete the older, remount and see the rest, corrupt storage starts empty, no network call
  - _Requirements: 1, 3, 4, 5.2, 5.4, 5.6_

- [x] 8. Verify everything
  - Run `npm test`, `npm run lint` and `npm run build`; all must pass
  - Open the app through the proxy URL and confirm it, including a refresh
