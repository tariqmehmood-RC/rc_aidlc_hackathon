# Requirements: Idea board

Source of truth: `docs/brd-idea-board.md`. Each requirement cites the brief item it comes from.

## Ambiguities in the brief and how this spec resolves them
Review these. Change any you disagree with before approving.

1. **Length limit applies to what?** The brief says "at most 140 characters" without saying whether spaces around the text count. Resolved: the text is trimmed first, and the limit applies to the trimmed text.
2. **Duplicates.** The brief is silent. Resolved: duplicate text is allowed. Ideas are identified by a generated id, not by their text.
3. **Order of ideas created in the same millisecond.** "Newest first" needs a tie-break. Resolved: the list is stored newest first, so insertion order decides, not a timestamp.
4. **Storage key and format.** Not specified. Resolved: key `idea-board:ideas`, value a JSON array of `{ id, text, createdAt }`.

## Requirement 1: Add an idea
**Source:** brief requirement 1.
**User story:** As a user, I want to type an idea and submit it, so that it is saved on my board.

### Acceptance criteria
1. WHEN the user types text and clicks the Add button, THE SYSTEM SHALL add the trimmed text as a new idea at the top of the list.
2. WHEN the user types text and presses Enter in the input, THE SYSTEM SHALL add the idea exactly as if Add had been clicked.
3. WHEN an idea is added successfully, THE SYSTEM SHALL clear the input and move focus back to it.
4. WHEN an idea is added successfully, THE SYSTEM SHALL hide any earlier error message.

## Requirement 2: Validate input
**Source:** brief requirement 2.
**User story:** As a user, I want clear feedback when my input is not acceptable, so that I know why nothing was added.

### Acceptance criteria
1. WHEN the user submits empty input, THE SYSTEM SHALL NOT add an idea and SHALL show the message "Enter an idea before adding it."
2. WHEN the user submits input containing only whitespace, THE SYSTEM SHALL treat it as empty and show the same message.
3. WHEN the trimmed input is longer than 140 characters, THE SYSTEM SHALL NOT add an idea and SHALL show the message "Ideas can be at most 140 characters."
4. WHEN the trimmed input is exactly 140 characters, THE SYSTEM SHALL add the idea.
5. WHEN input is rejected, THE SYSTEM SHALL leave the list and the input text unchanged.
6. THE SYSTEM SHALL present validation messages with `role="alert"` so assistive technology announces them.

## Requirement 3: Show the list
**Source:** brief requirement 3.
**User story:** As a user, I want to see all my ideas, newest first, so that I can review them.

### Acceptance criteria
1. THE SYSTEM SHALL show every saved idea, with the most recently added idea first.
2. WHEN there are no saved ideas, THE SYSTEM SHALL show the message "No ideas yet. Add your first one above."
3. WHEN there is at least one idea, THE SYSTEM SHALL NOT show the empty-state message.
4. THE SYSTEM SHALL render ideas as plain text, so that markup typed by the user is shown literally and never interpreted.
5. WHEN an idea is longer than the available width, THE SYSTEM SHALL wrap it onto further lines.

## Requirement 4: Delete an idea
**Source:** brief requirement 4.
**User story:** As a user, I want to delete one idea, so that I can remove ones I no longer want.

### Acceptance criteria
1. WHEN the user clicks Delete on an idea, THE SYSTEM SHALL remove that idea and no other.
2. WHEN two ideas have identical text and the user deletes one, THE SYSTEM SHALL remove only the one that was clicked.
3. THE SYSTEM SHALL give each Delete button an accessible name that includes the idea's text, for example "Delete idea: Try pottery".
4. WHEN the last idea is deleted, THE SYSTEM SHALL show the empty-state message.

## Requirement 5: Remember ideas between visits
**Source:** brief requirement 5.
**User story:** As a user, I want my ideas to still be there when I come back, so that I do not lose them.

### Acceptance criteria
1. WHEN an idea is added or deleted, THE SYSTEM SHALL write the full list to local storage under the key `idea-board:ideas`.
2. WHEN the page loads, THE SYSTEM SHALL read the list from local storage and show it.
3. WHEN stored data is missing, THE SYSTEM SHALL start with an empty list.
4. IF stored data is not valid JSON or is not an array of ideas with string `id` and `text`, THEN THE SYSTEM SHALL ignore it and start with an empty list without throwing.
5. IF writing to local storage fails (for example it is full or blocked), THEN THE SYSTEM SHALL keep the idea on screen for this visit and show the message "Could not save your ideas in this browser."
6. THE SYSTEM SHALL NOT make any network request.

## Out of scope (carried over from the brief)
Editing, tags, search, sorting options, undo, clear-all, accounts, syncing, any backend, import and export.
