# Idea board

## Why
People lose small ideas because capturing them takes too many steps. A one-screen list that remembers ideas between visits makes capturing one a few seconds of work.

## Who it is for
One person on one browser who wants to jot down a short idea and see all their ideas together.

## In scope
- Add a short text idea to a list.
- Show all ideas, newest first.
- Delete one idea.
- Keep ideas in the browser's local storage so they survive a page refresh.

## Out of scope
Editing an idea, tags, search, sorting options, undo, clear-all, accounts, syncing between devices, any backend or network call, import/export.

## Requirements
1. The user can add an idea by typing text and submitting the form (button or Enter key).
2. An idea must contain at least one non-space character and at most 140 characters. Anything else is rejected with a visible message and the list is unchanged.
3. The list shows every saved idea, newest first. When there are none, it shows a message saying so.
4. The user can delete a single idea, and only that idea is removed.
5. Ideas are saved in local storage after every change and loaded when the page opens. Unreadable or corrupt stored data is ignored and the board starts empty instead of crashing.

## Success criteria
- Add "Try pottery", see it at the top of the list, and the input is cleared.
- Submit an empty or spaces-only input and see an error. Nothing is added.
- Add two ideas, delete the older one, and the newer one remains.
- Refresh the page and the remaining ideas are still there.
- With no ideas, the page shows an empty-state message, not a blank area.

## Constraints
React and TypeScript with Vite, as already set up. Local storage only. No new runtime dependencies. Keyboard and screen-reader usable.
