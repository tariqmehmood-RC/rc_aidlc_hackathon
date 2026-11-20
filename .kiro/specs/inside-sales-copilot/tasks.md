# Implementation Plan: Inside Sales Copilot

## Overview

The design uses TypeScript, so no language choice is needed. Server code goes in `src/server/`, UI code in `src/copilot/`. Pure domain code comes first, then adapters, then the pipeline steps, then HTTP, then UI.

Rules that apply to every task (from `git-workflow.md`, `testing.md`, `verify-first.md`):

- Work on branch `feat/inside-sales-copilot`. Never commit to `main`, never push or merge.
- One task is one commit, with the format `<type>: <imperative summary>`. Stage files by name. Do not use `--amend` or `--no-verify`.
- Before each commit, `npm test`, `npm run lint` and `npm run build` must pass, with output shown.
- Each task includes its own tests, written beside the code. Property tests are separate tasks, one per design property, using `fast-check`, at least 100 runs, with the comment `// Feature: inside-sales-copilot, Property N: <title>`.
- Read the installed package's `package.json` and type declarations before using any library API. Report the installed version.
- Fixtures and test data are synthetic only. Do not start the dev server from the agent shell.

## Tasks

- [ ] 1. Branch, dependencies and connectivity spike
  - [x] 1.1 Create the branch, install dependencies, and set up server build and test config
    - Run `git status`. If the tree is dirty, stop and ask the user. Then create `feat/inside-sales-copilot`.
    - Read `package.json` first. Tell the user which packages are added: `@aws-sdk/client-bedrock-runtime`, `@modelcontextprotocol/sdk`, `hono`, `@hono/node-server`, `cheerio`, and dev `fast-check` (plus `tsx` only if Node's native TypeScript stripping does not work with `erasableSyntaxOnly`).
    - Read each installed package's `package.json` and type declarations for the APIs the design lists as not yet verified (`hono`, `@hono/node-server`, `cheerio`, `fast-check`). Record installed versions in the commit body.
    - Add `tsconfig.server.json` (Node types, no DOM) referenced from `tsconfig.json`. Make `.gitignore` ignore `data/` except `data/case_studies.json`.
    - Configure Vitest so files under `src/server/` run in the Node environment (comment directive or a second project), after checking the installed Vitest.
    - Add a smoke test under `src/server/` that runs in Node and uses `fast-check`.
    - Confirm `npm run lint` and `npm run build` cover the new directory.
    - _Requirements: 12.1_

  - [~] 1.2 Write the connectivity spike script and its parsing helpers
    - Add `scripts/spike-connectivity.mjs` (not part of `npm test`). With the user's AWS credentials in `us-east-1`, it makes one `ApplyGuardrail` call, one `Converse` call, and one Gateway `tools/list` and `tools/call`, with at least 1 second between Bedrock requests. It prints, without secrets: the masking output shape, the `WebSearch` result shape, and which Gateway auth works (SigV4 via the SDK `fetch` option, or JWT).
    - If a credential, Guardrail ID, model ID or Gateway URL is missing, the script names exactly which one and exits. Do not guess values. Config comes from `.env.local`.
    - Probe the proxy by request: report whether `/absproxy/5173/api/...` reaches a stub server, instead of assuming it.
    - Put the parsing of the guardrail output and search result into pure helpers with unit tests on synthetic sample payloads.
    - Report which spike checks ran and which could not, and why. If masking does not return text through `outputs`, stop and ask the user.
    - _Requirements: 9.1, 9.2, 11.2, 11.3, 12.1_

- [ ] 2. Domain: invite, facts, size tier, attendees, case studies
  - [~] 2.1 Define shared domain types and implement `validateInvite`
    - Create `src/server/domain/types.ts` with the types from the design (`SizeTier`, `SectionId`, `StepId`, `Fact`, `SourceLink`, `Section`, `Brief`, `AttendeeResult`, `CaseStudyRecord`, `MatchedCaseStudy`, `ParsedInvite`).
    - Create `src/server/domain/invite.ts`. Example tests: empty, whitespace-only, exactly 10,000 characters, 10,001 characters, normal text.
    - _Requirements: 1.7, 1.8_

  - [~] 2.2 Write property test for invite validation
    - **Property 1: Invite validation**
    - **Validates: Requirements 1.7, 1.8**

  - [~] 2.3 Implement `validateFacts`
    - Create `src/server/domain/facts.ts`. Keep facts with 1 to 3 valid `http(s)` links, keep the first 3 links, drop the others, add no placeholder.
    - Unit tests: no links, 4 links, `ftp://`, relative URL, malformed URL, order kept.
    - _Requirements: 2.1, 2.2_

  - [~] 2.4 Write property test for fact validation
    - **Property 2: Fact validation keeps only cited facts**
    - **Validates: Requirements 2.1, 2.2**

  - [~] 2.5 Implement `sizeTierFor`
    - Create `src/server/domain/sizeTier.ts`. Unit tests at the boundaries 1, 49, 50, 499, 500, 5000, 5001, and for 0 and negative input (returns null).
    - _Requirements: 3.1, 3.2_

  - [~] 2.6 Write property test for size tier mapping
    - **Property 3: Size tier mapping**
    - **Validates: Requirements 3.1, 3.2**

  - [~] 2.7 Implement `decideAttendee`
    - Create `src/server/domain/attendeeMatch.ts` with the normalization (Unicode lower-case, trim, remove punctuation, collapse whitespace), the verified and unverified outcomes, the single stored link, and the four reasons. `search failed` is set by the caller, not here.
    - Unit tests: each reason, empty employer or title in the invite, several matching pages (first one used), no pages.
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6_

  - [~] 2.8 Write property test for attendee status decision
    - **Property 5: Attendee status decision**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.5, 4.6**

  - [~] 2.9 Write property test for attendee match normalization
    - **Property 6: Attendee match is invariant under normalization**
    - **Validates: Requirements 4.2**

  - [~] 2.10 Implement `selectCaseStudies`
    - Create `src/server/domain/caseStudies.ts`. Drop picks whose ID is not in the eligible snapshot, duplicates, and reasons that are empty or over 300 characters. Apply the BU filter. Trim to 3. Never fill from another BU. Set `shortfall`.
    - Unit tests: unknown ID, duplicate, long reason, BU filter, 2 matches gives shortfall, 0 matches.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.7_

  - [~] 2.11 Write property test for case study selection
    - **Property 7: Case study selection stays inside the eligible snapshot**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

- [ ] 3. Domain: brief state, export, partial results
  - [~] 3.1 Implement the brief state machine
    - Create `src/server/domain/brief.ts` with `editSection`, `approve`, `canExport`. Results are new objects or typed errors (`BLANK`, `LOCKED`). Edits append to `history`, never change `originalText`. Approval changes only `status` and `approvedAt`. No function returns an Approved Brief to Draft.
    - Unit tests: edit, cancel path (no state change), blank rejected, edit after approval returns `LOCKED`, approval keeps text.
    - _Requirements: 6.2, 6.3, 6.5, 6.7, 6.8, 7.1, 7.2, 7.3, 7.5_

  - [~] 3.2 Write property test for saving an edit
    - **Property 8: Saving an edit**
    - **Validates: Requirements 6.2, 6.3, 6.7**

  - [~] 3.3 Write property test for blank edits
    - **Property 9: Blank edits are rejected**
    - **Validates: Requirements 6.5**

  - [~] 3.4 Write property test for approved briefs
    - **Property 10: Approved briefs are immutable**
    - **Validates: Requirements 6.8, 7.1, 7.2, 7.3**

  - [~] 3.5 Implement `exportMarkdown`
    - Create `src/server/domain/exportMarkdown.ts`. Throws `NOT_APPROVED` for Draft. Each Section shows its edited text if present, otherwise the original, then a Sources list built from `sources`, all as Markdown links in the same Section.
    - Unit tests: Draft refused, edited versus unedited Section, one link per source, link in the right Section.
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [~] 3.6 Write property test for export gating
    - **Property 11: Export is available only for Approved briefs**
    - **Validates: Requirements 8.1, 8.2**

  - [~] 3.7 Write property test for export content
    - **Property 12: Export content is faithful**
    - **Validates: Requirements 8.3, 8.4, 8.5**

  - [~] 3.8 Implement `assembleSections`
    - Create `src/server/domain/partial.ts` with the section-to-step dependency table from the design. Flag a Section when any step it depends on failed. A flagged Section holds only the statement naming the step. When all steps fail, add the "no research content" notice.
    - Unit tests: one step fails, each step alone, all fail, none fail.
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [~] 3.9 Write property test for partial results
    - **Property 15: Partial results flag exactly the dependent sections**
    - **Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5**

- [~] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Adapters
  - [~] 5.1 Implement the rate limiter
    - Create `src/server/adapters/rateLimiter.ts` with an injected clock. Requests start in arrival order, at least 1,000 ms apart, none dropped.
    - Unit tests with a fake clock: burst of 3, idle gap, order kept.
    - _Requirements: 11.2_

  - [~] 5.2 Write property test for request spacing
    - **Property 16: Bedrock requests are spaced at least one second apart**
    - **Validates: Requirements 11.2**

  - [~] 5.3 Implement `ModelGateway`
    - Create `src/server/adapters/modelGateway.ts`. Order: limiter, input `ApplyGuardrail`, `Converse`, output `ApplyGuardrail`, each through the limiter. Read the installed `@aws-sdk/client-bedrock-runtime` types and the real throttling error names before coding. Fail closed with `PII_MASKING_FAILED` and no content in the error. Retry throttling at most 3 times, at least 1,000 ms apart, then `RATE_LIMITED`. Client region fixed to `us-east-1` in code. Model ID and Guardrail ID come from config.
    - Tests with fake client and masker: region in client config, masked prompt reaches the client, error carries no text, retry counts, and a source scan showing no other file imports `@aws-sdk/client-bedrock-runtime`.
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 11.2, 11.3, 11.6_

  - [~] 5.4 Write property test for masked content
    - **Property 13: Masked content is what crosses the gateway**
    - **Validates: Requirements 9.1, 9.2**

  - [~] 5.5 Write property test for fail-closed masking
    - **Property 14: Masking failure fails closed**
    - **Validates: Requirements 9.4**

  - [~] 5.6 Write property test for bounded retry
    - **Property 17: Retry on throttling is bounded**
    - **Validates: Requirements 11.6**

  - [~] 5.7 Implement `BriefStore` and `RunCache`
    - Create `src/server/adapters/briefStore.ts` and `runCache.ts`. Map in memory, mirrored to `data/briefs.json` by atomic write (temp file, then rename). A failed write returns `NOT_SAVED` or `APPROVAL_FAILED` and leaves the in-memory Brief unchanged. The cache is keyed by a hash of the normalized Invite text and stores `data/cache/<hash>.json`.
    - Tests use a temp directory removed in `beforeEach`/`afterEach`: failed write leaves state unchanged, cache hit sets `cached: true`, cache miss.
    - _Requirements: 6.6, 7.4, 12.5_

  - [~] 5.8 Write property test for storage round trip
    - **Property 18: Brief storage round trip**
    - **Validates: Requirements 6.7, 12.5**

  - [~] 5.9 Implement `WebSearchClient`
    - Create `src/server/adapters/webSearch.ts` using the MCP client and the auth and result shape found in task 1.2. Read the installed `@modelcontextprotocol/sdk` signatures first. The query is at most 200 characters and `maxResults` is 1 to 25. Results are held in memory only. Expose the single `searchAttendee` function with a 10-second `AbortSignal.timeout`. Add a fake implementation for tests.
    - Tests use a fake MCP client: parsing, query clamp, timeout becomes an error, only public result fields are returned.
    - _Requirements: 2.4, 4.4, 4.7, 4.9_

  - [~] 5.10 Implement the case study scraper and snapshot loader
    - Create `scripts/scrape-case-studies.ts` using `cheerio` and direct fetch of the public Royal Cyber site, never search results. Create `src/server/adapters/caseStudies.ts` to load `data/case_studies.json` and filter by BU, and to list BUs.
    - Tests use a saved synthetic HTML fixture for the parser, and a synthetic snapshot for the loader. Do not run the scraper against the live site from tests. Report whether a live scrape was run.
    - _Requirements: 5.3, 5.4, 5.6, 5.7_

- [~] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Pipeline steps
  - [~] 7.1 Implement `parseInvite`
    - Create `src/server/steps/parseInvite.ts` using an injected `ModelGateway`. Missing fields stay `null`. No company gives `NO_COMPANY`.
    - Tests with a fake gateway: missing title stays null, no company, three different fictitious companies (nothing hard-coded).
    - _Requirements: 1.1, 1.2, 1.5, 1.6_

  - [~] 7.2 Implement `researchCompany`
    - Create `src/server/steps/researchCompany.ts`. Three searches, one model call. Drop model URLs not in this run's results. Apply `validateFacts`. Compute the tier with `sizeTierFor`. Set the "no sourced facts" notice and the "size not found" state.
    - Tests with fakes: invented URL dropped, all facts dropped gives notice, no employee count gives null tier.
    - _Requirements: 2.1, 2.2, 2.4, 2.5, 3.1, 3.3, 3.4_

  - [~] 7.3 Write property test for size tier presence
    - **Property 4: Size tier is present only with a sourced employee count**
    - **Validates: Requirements 3.3, 3.4**

  - [~] 7.4 Implement `verifyAttendees`
    - Create `src/server/steps/verifyAttendees.ts`. Search through `searchAttendee` only, one batched model extraction call, status by `decideAttendee`. A search timeout or error gives `Unverified: search failed` and the others continue.
    - Tests with fakes: hanging search, mixed results, the verifier calls only the injected `searchAttendee`.
    - _Requirements: 4.1, 4.4, 4.7, 4.8, 4.9_

  - [~] 7.5 Implement `matchCaseStudies`
    - Create `src/server/steps/matchCaseStudies.ts`. Build the shortlist in code, one model call, then `selectCaseStudies`. The link comes from the snapshot record.
    - Tests with a fake gateway and snapshot: BU filter, shortfall notice, link equals the record URL.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.7_

  - [~] 7.6 Implement `generateBrief`
    - Create `src/server/steps/generateBrief.ts`. One model call produces agenda and questions. Each of the four content sections must hold at least 1 item.
    - Tests with a fake gateway: four sections non-empty, pain points and case studies pass through unchanged with their links.
    - _Requirements: 1.3_

  - [~] 7.7 Implement `runPipeline`
    - Create `src/server/pipeline.ts`. `parseInvite` first, then `researchCompany` and `verifyAttendees` concurrently, then matching, then generation. 120-second deadline through `AbortSignal`. A failed step feeds `assembleSections`. A `parseInvite` failure gives an error, not a Brief. New Briefs are Draft.
    - Tests with fakes and a fake clock: Draft status, one step failing still returns a Brief, all fail, deadline gives `TIME_LIMIT`, `parseInvite` failure gives no Brief.
    - _Requirements: 1.1, 1.4, 10.1, 10.5, 11.1, 11.5_

- [ ] 8. HTTP server
  - [~] 8.1 Implement the HTTP routes
    - Create `src/server/http/app.ts` with the routes and error codes from the design. Read the installed `hono` types first. Error bodies are `{ code, message }` with no prompt, response or attendee data. Test with `app.request` and fakes: each status code, export refused with 409 for Draft, `Content-Disposition` on export, no route reopens an Approved Brief.
    - _Requirements: 1.6, 1.7, 1.8, 5.3, 6.3, 6.5, 6.6, 7.2, 7.3, 7.4, 8.1, 8.2, 8.6, 11.5_

  - [~] 8.2 Add the server entry and the one-command start script
    - Create `src/server/main.ts` (binds `127.0.0.1`, loads config from `.env.local`, runs the connectivity check and cached replay) and `scripts/start-local.mjs`. Add `npm run start:local`. Add the `/api` proxy to `vite.config.ts` using the prefix verified in task 1.2. The agent does not run it.
    - Tests: cached replay when the connectivity check fails and an entry exists, network error when none exists, server binds only to `127.0.0.1`.
    - _Requirements: 12.1, 12.5_

- [ ] 9. User interface
  - [~] 9.1 Build the invite form, progress indicator and page shell
    - Create `src/copilot/CopilotPage.tsx`, `InviteForm.tsx`, `ProgressIndicator.tsx`, `useBrief.ts`. Fetch URLs use `import.meta.env.BASE_URL`. The client aborts at 120 s. The Invite text stays on every error. Progress shows within 2 s.
    - Tests (React Testing Library, fake timers): the Invite is kept after each error, progress appears within 2 s, empty submit shows the required message, the failed step is named.
    - _Requirements: 1.6, 1.7, 1.8, 11.4, 11.5, 12.6_

  - [~] 9.2 Build the brief view, source links and attendee list
    - Create `BriefView.tsx`, `SectionView.tsx`, `SourceLinks.tsx`, `AttendeeList.tsx`. Links sit in the same list item as the fact. Show tier or "size not found", attendee status with link or reason, the flag badge visible without expanding, notices and a cached banner.
    - Tests: link and fact in the same list item, tier and "size not found", verified link and unverified reason, flag badge, notices.
    - _Requirements: 2.3, 3.3, 3.4, 4.8, 5.5, 10.4, 12.5_

  - [~] 9.3 Add inline section editing
    - Extend `SectionView.tsx` with edit, save and cancel, only while Draft. Cancel restores the text. A blank save shows the "cannot be empty" message. A failed save keeps the field text and shows "not saved".
    - Tests for each criterion, including no edit control on an Approved Brief and the locked message.
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.8, 7.3_

  - [~] 9.4 Build the approve and export bar
    - Create `ApproveBar.tsx`. Approve is available for Draft. Export is disabled or hidden while Draft and enabled when Approved. Show "Approval failed" and "Export failed" messages, and allow export retry.
    - Tests: export disabled for Draft, enabled after approval, approval failure keeps Draft, export failure then retry.
    - _Requirements: 7.1, 7.4, 8.1, 8.2, 8.6_

  - [~] 9.5 Wire the Copilot page into the app
    - Update `src/App.tsx` to render `CopilotPage` alongside the idea board, and add the BU selector populated from `GET /api/case-studies/bus`. Do not change `src/ideas/`. Ask the user if the placement (alongside or replacing the idea board) is unclear.
    - Tests: App renders both features, the BU choice is sent with the request, existing idea board tests still pass.
    - _Requirements: 1.1, 5.3, 5.4, 12.3_

  - [~] 9.6 Extend the browser check for the full sequence
    - Extend `scripts/browser-check.mjs` with: paste a synthetic invite, see the Brief, edit one line, approve, export. It runs against a server started with fakes, and the dev server must already be running. If it cannot be run, state exactly why. Never report it as passed unrun.
    - Add a unit test for any pure helper in the script.
    - _Requirements: 12.3, 12.4_

- [ ] 10. Documentation of the run command and steering
  - [~] 10.1 Update README and steering for the new server
    - Update `README.md` with `npm run start:local`, required `.env.local` keys (names only, no values), and the spike script. Update `.kiro/steering/structure.md` and `product.md` to record `src/server/`, `src/copilot/` and that a backend now exists for this feature (decision D2). Ask the user to confirm before changing steering.
    - Test: a small test asserting `package.json` has the `start:local` script that the README names.
    - _Requirements: 12.1_

- [~] 11. Final checkpoint - Ensure all tests pass
  - Run `npm test`, `npm run lint` and `npm run build` and show the output. Ensure all tests pass, ask the user if questions arise.

## Notes

- Test sub-tasks marked `*` are the 18 property tests. `testing.md` says every spec requirement needs a test, and the property tests cover the universal rules. Run them too: the done-gate expects them. The `*` lets a person skip them for speed.
- Every implementation task already includes its example tests, so no task ships without a test.
- Live checks (spike, scrape, browser check, timing rehearsal) need AWS credentials, the network or the user's dev server. If one cannot run, report which and why.
- Open decisions D1 to D10 in `design.md` are assumed as written. Task 9.5 and 10.1 stop to ask because they depend on D2.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.5", "2.7", "2.10", "3.1", "3.5", "3.8", "5.1", "5.7", "5.9", "5.10"] },
    { "id": 3, "tasks": ["2.4", "2.6", "2.8", "2.9", "2.11", "3.2", "3.3", "3.4", "3.6", "3.7", "3.9", "5.2", "5.3", "5.8"] },
    { "id": 4, "tasks": ["5.4", "5.5", "5.6", "7.1", "7.2", "7.4", "7.5", "7.6"] },
    { "id": 5, "tasks": ["7.3", "7.7"] },
    { "id": 6, "tasks": ["8.1"] },
    { "id": 7, "tasks": ["8.2", "9.1", "9.2"] },
    { "id": 8, "tasks": ["9.3", "9.4"] },
    { "id": 9, "tasks": ["9.5"] },
    { "id": 10, "tasks": ["9.6", "10.1"] }
  ]
}
```
