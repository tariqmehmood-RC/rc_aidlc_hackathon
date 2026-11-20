# Requirements Document

## Introduction

This document specifies editing an idea in place. Ambiguities in the brief and their chosen resolutions are listed first, below.

### Ambiguities and chosen resolutions

No questions were asked. Each item below is an ambiguity in `docs/brd-edit-idea.md` and the resolution this document uses. Overrule any of them before approving.

| # | Ambiguity | Chosen resolution |
|---|---|---|
| A1 | Error wording for an empty edit. The existing `EMPTY_MESSAGE` reads "Enter an idea before adding it.", which is wrong for an edit. | Reuse `validateIdea` for the trim and length rules. When the result is empty, show a new edit-specific message, "Enter some text before saving." (new constant `EDIT_EMPTY_MESSAGE`). Over-length reuses `TOO_LONG_MESSAGE`. The Add form keeps its current wording. |
| A2 | Saving text that equals the current text (after trimming). | No change is written. Edit mode closes. Storage is not written and `saveError` is untouched. |
| A3 | Clicking Edit on idea B while idea A is being edited (BRD rule 4). | The edit of A is discarded without saving, A shows its original text, and B enters edit mode. The click is not blocked. |
| A4 | Deleting the idea that is being edited. | Delete stays enabled during edit. Deleting removes the idea and ends edit mode. Deleting a different idea leaves the edit open. |
| A5 | Whether `createdAt` changes on edit. | `createdAt` and `id` never change. Only `text` changes. |
| A6 | Focus on entering edit. | Focus moves to the text field and the existing text is selected. |
| A7 | Focus after save or cancel. | Focus returns to that idea's Edit button. |
| A8 | Enter key. | Enter in the edit field saves. |
| A9 | Blur (clicking or tabbing away). | Nothing happens. The edit stays open with its current text. |
| A10 | Storage write failure on save. | Same as add: the in-memory list takes the new text, edit mode closes, and the existing `saveError` message is shown. |
| A11 | Edit field element and length limit. | Single-line `<input type="text">`. No `maxLength` attribute, so over-length text is rejected with a message instead of being silently truncated. |
| A12 | Lifetime of the edit error message. | The message clears when an edit starts, is cancelled, or is saved successfully. It also clears when the user changes the field text. |
| A13 | Accessible names. | Edit button: "Edit idea: <text>". Save button: "Save idea: <text>". Cancel button: "Cancel editing idea: <text>". The text is the idea's saved text. The edit field is labelled "Edit idea". |
| A14 | Whether the Add form is disabled during edit. | No. The Add form keeps working. Adding an idea does not close or change the open edit. |
| A15 | Live region. | The existing `aria-live="polite"` wrapper around the list is kept unchanged. The edit error uses `role="alert"`, `aria-invalid` and `aria-describedby`, as the Add form does. |
| A16 | Stale or corrupt storage. | Storage loading is unchanged. Corrupt data loads as an empty list, so there is nothing to edit. Edit never reads storage. It works on the in-memory list and writes the whole list back. |
| A17 | Escape key scope. | Escape cancels only while focus is inside the edit field or its Save and Cancel buttons. |
| A18 | Disabled Edit controls. | Edit buttons stay enabled while an edit is open (see A3). The Edit button of the idea being edited is not shown, because the field and Save and Cancel replace it. |

### About this feature

This feature lets the single user of the idea board change the text of a saved idea in place. The idea keeps its position, `id` and `createdAt`. The change is validated with the same trim and length rules as adding, saved to local storage, and survives a page refresh. The scope is `docs/brd-edit-idea.md`. Edit history, undo, reordering, edited timestamps, tags and any backend are out of scope.

## Glossary

- **Idea_Board**: The single-page React app that shows the Add form, the list of ideas and the save error message.
- **Idea**: A record `{id, text, createdAt}`. `text` is 1 to 140 characters after trimming.
- **Idea_List**: The list of ideas, newest first.
- **Edit_Button**: The per-idea button that starts editing that idea.
- **Edit_Field**: The single-line text input that replaces an idea's text while that idea is in edit mode.
- **Save_Button**: The per-idea button that applies the edit.
- **Cancel_Button**: The per-idea button that discards the edit.
- **Edit_Mode**: The state of one idea while its text is shown in the Edit_Field.
- **Edit_Error**: The validation message shown beside the Edit_Field when saving is rejected.
- **Save_Error**: The existing message "Could not save your ideas in this browser." shown when a local storage write fails.
- **Validator**: The existing `validateIdea` function that trims text and checks the 1 to 140 character rule.
- **Storage**: The browser `localStorage` entry that holds the list of ideas.

## Requirements

### Requirement 1: Start editing

**User Story:** As a user, I want to turn a saved idea into an editable field, so that I can correct or reword it.

#### Acceptance Criteria

1. WHILE an idea is not in Edit_Mode, THE Idea_Board SHALL show exactly one Edit_Button for that idea, with the accessible name "Edit idea: <text>", where <text> is the idea's saved text.
2. WHEN the user activates an Edit_Button, THE Idea_Board SHALL put that idea in Edit_Mode and replace the display of that idea's text with an Edit_Field whose value equals the idea's saved text exactly, with no trimming or other change.
3. WHEN an idea enters Edit_Mode, THE Idea_Board SHALL move keyboard focus to that idea's Edit_Field.
4. WHILE an idea is in Edit_Mode, THE Idea_Board SHALL show exactly one Save_Button for that idea, with the accessible name "Save idea: <text>", where <text> is the idea's saved text.
5. WHILE an idea is in Edit_Mode, THE Idea_Board SHALL keep that idea's Delete button visible.
6. WHILE an idea is in Edit_Mode, THE Idea_Board SHALL give that idea's Edit_Field the accessible label "Edit idea".
7. WHILE an idea is in Edit_Mode, THE Edit_Field SHALL be a single-line text input without a `maxLength` attribute.
8. WHEN an idea enters Edit_Mode, THE Idea_Board SHALL select the entire text in that idea's Edit_Field, so that the selection starts at character 0 and ends at the last character of the field's value.
9. WHILE an idea is in Edit_Mode, THE Idea_Board SHALL show exactly one Cancel_Button for that idea, with the accessible name "Cancel editing idea: <text>", where <text> is the idea's saved text.
10. WHILE an idea is in Edit_Mode, THE Idea_Board SHALL hide that idea's Edit_Button, so that no element with the accessible name "Edit idea: <text>" for that idea is present.

### Requirement 2: Save an edit

**User Story:** As a user, I want to save my change, so that the corrected text replaces the old text.

#### Acceptance Criteria

1. WHEN the user activates the Save_Button with text that passes the Validator, THE Idea_Board SHALL replace the idea's text with the trimmed text and leave Edit_Mode.
2. WHEN the user presses Enter in the Edit_Field with text that passes the Validator, THE Idea_Board SHALL replace the idea's text with the trimmed text and leave Edit_Mode, the same result as activating the Save_Button.
3. WHEN an edit is saved, THE Idea_Board SHALL keep the idea at the same zero-based index in the Idea_List.
4. WHEN an edit is saved, THE Idea_Board SHALL keep the idea's `id` and `createdAt` values identical to their values before the edit.
5. WHEN an edit is saved with text that differs from the idea's current text, THE Idea_Board SHALL write the full list to Storage once, so that reading Storage after a page reload returns the edited text.
6. WHEN an edit is saved, THE Idea_Board SHALL move keyboard focus to that idea's Edit_Button, and `document.activeElement` SHALL be that button.
7. WHEN the user saves text that, after trimming, equals the idea's current text, THE Idea_Board SHALL leave Edit_Mode, keep the idea's text unchanged, and make zero writes to Storage.
8. WHEN an edit is saved, THE Idea_Board SHALL keep the text, `id`, `createdAt`, and position of every other idea identical to their values before the edit.
9. IF the user activates the Save_Button or presses Enter in the Edit_Field with text that fails the Validator, THEN THE Idea_Board SHALL stay in Edit_Mode, display the Validator's visible error message, keep the idea's stored text unchanged, and make zero writes to Storage.
10. IF writing to Storage fails when an edit is saved, THEN THE Idea_Board SHALL leave Edit_Mode and show the edited text in the Idea_List for the current session, and SHALL display a visible message that the change was not saved.

### Requirement 3: Validate an edit

**User Story:** As a user, I want bad edits rejected with a clear message, so that I never lose a good idea to an invalid change.

#### Acceptance Criteria

1. WHEN the user saves text that is empty (0 characters) after trimming leading and trailing whitespace, THE Idea_Board SHALL show the Edit_Error "Enter some text before saving." and keep the idea in Edit_Mode.
2. WHEN the user saves text that is longer than 140 characters after trimming leading and trailing whitespace, THE Idea_Board SHALL show the Edit_Error "Ideas can be at most 140 characters." and keep the idea in Edit_Mode.
3. WHEN the user saves text that is exactly 140 characters after trimming leading and trailing whitespace, THE Idea_Board SHALL accept the edit, leave Edit_Mode, and show no Edit_Error.
4. WHEN the user saves text that consists only of whitespace characters (such as spaces, tabs, or newlines, at least 1 character), THE Idea_Board SHALL show the Edit_Error "Enter some text before saving." and keep the idea in Edit_Mode.
5. WHEN an edit is rejected, THE Idea_Board SHALL keep the idea's saved text unchanged in the Idea_List and in Storage.
6. WHEN the Edit_Error is shown, THE Idea_Board SHALL expose the Edit_Error with `role="alert"`.
7. WHEN the Edit_Error is shown, THE Idea_Board SHALL set `aria-invalid` to `true` on the Edit_Field and reference the Edit_Error element from the Edit_Field with `aria-describedby`.
8. WHEN the Edit_Error is shown, THE Idea_Board SHALL keep keyboard focus in the Edit_Field.
9. WHEN the user changes the text in the Edit_Field while the Edit_Error is shown, THE Idea_Board SHALL remove the Edit_Error, remove `aria-invalid` (or set it to `false`) on the Edit_Field, and keep the idea in Edit_Mode.
10. WHEN the user submits the Add form with empty input, THE Idea_Board SHALL show the message "Enter an idea before adding it."

### Requirement 4: Cancel an edit

**User Story:** As a user, I want to cancel an edit, so that the original text stays as it was.

#### Acceptance Criteria

1. WHEN the user activates the Cancel_Button, THE Idea_Board SHALL leave Edit_Mode and show the idea's original text, which is the text the idea had when Edit_Mode was entered, discarding any changes typed in the Edit_Field.
2. WHEN the user presses Escape while focus is in the Edit_Field, THE Idea_Board SHALL cancel the edit with the same result as activating the Cancel_Button.
3. WHEN the user presses Escape while focus is on the Save_Button or the Cancel_Button, THE Idea_Board SHALL cancel the edit with the same result as activating the Cancel_Button.
4. WHEN an edit is cancelled, THE Idea_Board SHALL move keyboard focus to that idea's Edit_Button.
5. WHEN an edit is cancelled, THE Idea_Board SHALL remove any displayed Edit_Error.
6. WHEN an edit is cancelled, THE Idea_Board SHALL leave the stored ideas unchanged and make 0 write calls to Storage.
7. WHEN an edit is cancelled, THE Idea_Board SHALL keep the idea's position in the list and the text of all other ideas unchanged.
8. WHEN the Edit_Field loses focus, THE Idea_Board SHALL keep the idea in Edit_Mode with the current Edit_Field text and with any displayed Edit_Error unchanged.

### Requirement 5: One edit at a time

**User Story:** As a user, I want only one idea open for editing, so that the list stays easy to understand.

#### Acceptance Criteria

1. WHEN the user activates the Edit_Button of an idea while a different idea is in Edit_Mode, THE Idea_Board SHALL discard the unsaved text of the first idea, show the first idea's last saved text, and exit Edit_Mode for the first idea.
2. WHEN the user activates the Edit_Button of an idea while a different idea is in Edit_Mode, THE Idea_Board SHALL put the second idea in Edit_Mode.
3. WHILE an idea is in Edit_Mode, THE Idea_Board SHALL show exactly one Edit_Field in the whole list.
4. WHEN the user activates the Edit_Button of an idea while a different idea shows an Edit_Error, THE Idea_Board SHALL remove that Edit_Error so that no Edit_Error is visible after the switch.
5. WHEN the second idea enters Edit_Mode after a switch, THE Idea_Board SHALL move keyboard focus to the Edit_Field of the second idea.
6. WHEN the second idea enters Edit_Mode after a switch, THE Idea_Board SHALL leave the stored list of ideas unchanged, including the text, order, and count of all ideas.

### Requirement 6: Interaction with add and delete

**User Story:** As a user, I want adding and deleting to keep working during an edit, so that one action does not block another.

#### Acceptance Criteria

1. WHEN the user deletes the idea that is in Edit_Mode, THE Idea_Board SHALL remove that idea from the list, leave Edit_Mode, and discard the unsaved field text without saving it to local storage.
2. WHEN the user deletes a different idea while an idea is in Edit_Mode, THE Idea_Board SHALL remove the deleted idea and keep the edited idea in Edit_Mode with its field text unchanged, character for character.
3. WHEN the user adds a valid new idea while an idea is in Edit_Mode, THE Idea_Board SHALL add the new idea to the list and keep the edited idea in Edit_Mode with its field text unchanged, character for character.
4. WHILE an idea is in Edit_Mode, THE Idea_Board SHALL keep the Add form's text input and submit control enabled.
5. IF the user submits invalid text (empty, whitespace-only, or longer than 140 characters after trimming) in the Add form while an idea is in Edit_Mode, THEN THE Idea_Board SHALL show the Add form's validation message, add no idea, and keep the edited idea in Edit_Mode with its field text unchanged.

### Requirement 7: Storage failure on save

**User Story:** As a user, I want to know when an edit could not be stored, so that I do not assume it survives a refresh.

#### Acceptance Criteria

1. IF writing to Storage fails when an edit with changed text is saved, THEN THE Idea_Board SHALL show the Save_Error within the same render in which the save completes.
2. IF writing to Storage fails when an edit with changed text is saved, THEN THE Idea_Board SHALL show the trimmed new text, in place of the original text and at the same position, in the Idea_List.
3. IF writing to Storage fails when an edit with changed text is saved, THEN THE Idea_Board SHALL leave Edit_Mode for that idea and show no Edit_Error.
4. WHEN a write to Storage succeeds after a failed write while the Save_Error is shown, whether the write comes from adding an idea, deleting an idea, or saving an edit with changed text, THE Idea_Board SHALL remove the Save_Error.
5. WHILE the Save_Error is shown, THE Idea_Board SHALL keep it shown until a write to Storage succeeds, including across cancelling an edit and starting another edit.

### Requirement 8: Accessibility and safe display

**User Story:** As a keyboard or screen-reader user, I want to edit ideas without a mouse, so that the feature is usable for me.

#### Acceptance Criteria

1. WHEN the user presses Tab repeatedly starting from the top of the page, THE Idea_Board SHALL move keyboard focus onto each displayed Edit_Button, Edit_Field, Save_Button and Cancel_Button exactly once, in visual order, with no keyboard trap.
2. THE Idea_Board SHALL keep the existing `aria-live="polite"` wrapper around the Idea_List in both view mode and edit mode.
3. WHEN the user saves an idea whose text contains markup characters (for example `<b>x</b>`), THE Idea_Board SHALL display those exact characters as text in the Idea_List and SHALL NOT create any HTML element from them.
4. WHEN an idea's text is saved with a value different from the previous text, THE Idea_Board SHALL, without a page reload, set the accessible names of that idea's Edit_Button and Delete button to include the new text and not the previous text.
5. WHEN a focused Edit_Button, Save_Button or Cancel_Button receives the Enter key or the Space key, THE Idea_Board SHALL perform the same action as a mouse click on that button.
6. WHEN the Edit_Field opens for an idea whose stored text contains markup characters, THE Idea_Board SHALL show in the Edit_Field a value identical, character for character, to the stored text.

### Requirement 9: Update operation on the idea list

**User Story:** As a developer, I want a tested update operation in the idea state, so that edits are applied and stored in one place.

#### Acceptance Criteria

1. WHEN `updateIdea` is called with the id of an idea in the Idea_List and new text that passes validation (1 to 140 characters after trimming), THE Idea_List state SHALL replace only that idea's `text` with the trimmed new text and keep that idea's `id` and `createdAt` unchanged.
2. WHEN `updateIdea` is called with the id of an idea in the Idea_List and valid new text, THE Idea_List state SHALL keep every other idea in the list unchanged.
3. WHEN `updateIdea` is called with the id of an idea in the Idea_List and valid new text, THE Idea_List state SHALL write the updated list to Storage exactly once.
4. IF `updateIdea` is called with an id that is not in the Idea_List, THEN THE Idea_List state SHALL keep the list unchanged and THE system SHALL not write to Storage.
5. IF `updateIdea` is called with new text that fails validation (empty, whitespace-only, or longer than 140 characters after trimming), THEN THE Idea_List state SHALL keep the list unchanged and THE system SHALL not write to Storage.
6. IF writing the updated list to Storage fails, THEN THE Idea_List state SHALL keep the updated list in memory and set `saveError` to true.
7. FOR ALL lists of ideas in a varied set of hand-written cases (list sizes 1, 2 and 5, the target idea at the first, middle and last position, and new text of 1, 70 and 140 characters), updating an idea SHALL keep the list length and the order of ids unchanged.
8. FOR ALL ideas in the same set of hand-written cases, saving an edit and then loading from Storage SHALL produce a list deeply equal to the in-memory list (round-trip property).
