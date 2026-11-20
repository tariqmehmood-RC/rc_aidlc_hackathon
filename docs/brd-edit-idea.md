# Edit an idea

## Why
Ideas get typos or need rewording. Today the only fix is to delete the idea and type it again, which loses its place in the list.

## Who it is for
The same single user of the idea board, correcting or rewording an idea they already saved.

## In scope
- Edit the text of one existing idea in place.
- Save the change, or cancel it and keep the original text.
- The edited idea keeps its position in the list.
- The change is saved to local storage like any other change.

## Out of scope
Editing more than one idea at a time, edit history or undo, changing the order of ideas, timestamps showing when an idea was edited, tags, and any backend.

## Requirements
1. Each idea has an Edit control that turns that idea into an editable text field holding its current text.
2. Saving applies the same rules as adding: trimmed, 1 to 140 characters. Invalid text is rejected with a visible message and the idea keeps its original text.
3. Cancelling (button or Escape key) leaves the idea unchanged.
4. Only one idea can be in edit mode at a time.
5. A saved edit keeps the idea's position and id, and survives a page refresh.

## Success criteria
- Edit "Try poterry" to "Try pottery", save, and see the corrected text in the same position.
- Start an edit, press Escape, and see the original text.
- Clear the text and save: an error appears and the original text is kept.
- Refresh after an edit: the edited text is still there.

## Constraints
React and TypeScript, as already set up. Local storage only. No new runtime dependencies. Vitest and Testing Library are already installed. Keyboard and screen-reader usable.
