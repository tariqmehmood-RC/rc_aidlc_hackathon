# Testing

Rules for the agent. "Done" means the checks below pass, not that the code compiled.

## Tooling
- Test runner: Vitest with jsdom and React Testing Library. Command: `npm test` (runs `vitest run`, no watch mode).
- MUST read `package.json` before running anything. If the `test` script or Vitest is missing, install it as the first task of the spec and tell the user which packages you are adding.
- NEVER start watch mode or the dev server from the agent shell.

## What MUST have a test
- Every pure function (storage read/write, validation, id generation).
- Every user-visible behaviour in a spec requirement: one test per `WHEN ... THE SYSTEM SHALL ...` criterion.
- Every edge case a requirement names: empty input, whitespace-only input, over-length input, empty list, corrupt storage.
- Every bug fix: a test that fails before the fix and passes after.

## What does NOT need a test
- Static markup with no logic, CSS, and Vite or ESLint config.

## Rules
- Tests live beside the code as `<name>.test.ts` or `<name>.test.tsx`.
- Tests MUST be independent: clear `localStorage` in `beforeEach`. NEVER depend on test order or on the network.
- NEVER delete or weaken a failing test to make it pass. Fix the code or ask the user.

## Done means all of these pass, with output shown
1. `npm test`
2. `npm run lint`
3. `npm run build`
