# Requirements: Inside Sales Copilot

Status: **approved** with the decisions below.
Source: `docs/brd-inside-sales-copilot.md`, `AGENTS.md`, and `.kiro/steering/*.md`.
Format: user stories with acceptance criteria in EARS style ("WHEN ... THE SYSTEM SHALL ...").

## Decisions on the requirements analysis

| # | Gap | Decision |
|---|---|---|
| G1 | "All" BUs | Dropped. Each user sees only case studies of their own BU, taken from the JWT `custom:bu` claim on the server. The demo shows this by signing in as both users. |
| G2 | 1 rps across containers | SQS standard queue. `POST /briefs` writes status `queued` and sends a message. One worker Lambda (reserved concurrency 1, batch size 1) keeps an in-process token bucket (1 rps) as a second guard. Rule extraction on approve is also an SQS job on the same worker. Every Bedrock call goes through this worker. API Lambdas never call Bedrock. DLQ with `maxReceiveCount` 3 and an alarm on DLQ depth above 0. |
| G3 | 60-second target | Applies to one brief when the queue is empty. Statuses: `queued` -> `processing` (with current step) -> `ready` or `failed`. The UI shows the queue position or "queued". |
| G4 | Attendee profiles | `data/attendee_profiles.json`, synthetic, keyed by email (name, employer, employer_domain, title, `source_url` = `synthetic://profiles`). Sample invites cover: one verified, one unverified for title mismatch, one unverified for no profile. |
| G5 | Matching rules | Deterministic, with an abbreviation table (VP = Vice President, CTO = Chief Technology Officer, Sr = Senior, and similar). |
| G6 | Size tiers | As written in R3, including "Unknown". The rule and source are shown next to the tier. |
| G7 | Pain points | Hypotheses, each linked to the sourced facts it is based on. |
| G8, G9, G11 | Invite input | Free-mail domains do not count as a company. A company and domain mismatch must be confirmed. Max 20 attendees. Duplicates merged. Meeting date optional. Invite text is data, never instructions. |
| G10 | Partial research | Allowed. |
| G12, G13 | Ownership and statuses | Another user's brief returns 404. Stuck-job timeout is 120 seconds, then `failed` with a Retry button. |
| G14, G15 | Saved rules | View and delete list. At most 10 rules applied per brief. |
| G16 | Wording | "The system". |
| G17 | Retention | Briefs expire 30 days after creation (DynamoDB TTL). Logs never contain invite text or attendee emails. CloudWatch log retention is 14 days. |
| G18 | Case study scraping | Store only title, a 1 to 2 sentence summary in our own words, BU, industry, tags, and the public URL. If the site blocks fetching, write the seed by hand from the public pages and say so in the README. |
| G19 | Sign-in | Cognito user pool, self sign-up disabled, admin-created users only, email + password with a custom login form (`aws-amplify` Auth), access token valid 1 hour, sign-out button. Demo passwords are set at deploy time from a command-line parameter and never stored in git. |
| G20 | "No good match" | The model scores each candidate 0 to 100 with a reason. Show those scoring 60 or more, up to 3. |

### Flow note: where parsing happens
Parsing the invite needs a Bedrock call, and API Lambdas never call Bedrock (G2). So the parse step also runs in the worker. The flow is:

1. `POST /briefs` with the invite text: the API checks length and type, saves the brief as `queued`, and queues a parse job.
2. The worker parses the invite and sets status `awaiting_confirmation`.
3. The SE reviews and corrects the parsed fields, then confirms. The API validates the fields (including "names a company or a company email domain") and queues the research job.
4. The worker runs the remaining steps and sets `ready` or `failed`.

The requirement "must name a company or company email domain" is therefore checked at confirmation, after the parse, because a company name can only be found by parsing.

## Glossary
- **SE**: sales engineer, the main user. Also covers account executives and solution architects.
- **BU**: business unit (AWS, ServiceNow, Salesforce, Data & AI).
- **Brief**: the discovery brief for one call.
- **Draft**: the brief as first written by the system. **Final**: the brief as approved.
- **Rule**: a short reusable instruction learned from SE edits.
- **Size tier**: Enterprise, Mid-market, SMB, Boutique, or Unknown.
- **Worker**: the single Lambda that reads the queue and runs all Bedrock calls.

## Brief statuses
`queued` -> `processing` (with a current step) -> `awaiting_confirmation` -> `queued` -> `processing` -> `ready` -> `approved`. Any processing state can go to `failed`.

---

## R1. Sign in

**User story:** As an SE, I want to sign in with my work account so that only authorized people can use the copilot.

**Acceptance criteria**
1. WHEN a user opens the app without a valid session, THE SYSTEM SHALL show the sign-in page and no brief data.
2. WHEN a user submits a valid email and password on the sign-in form, THE SYSTEM SHALL start a session through Cognito and show the home page.
3. WHEN a user submits invalid credentials, THE SYSTEM SHALL show a generic error and SHALL NOT say whether the email or the password was wrong.
4. WHEN any API request has no token, an invalid token, or an expired token, THE SYSTEM SHALL reject it with HTTP 401 and return no data.
5. THE SYSTEM SHALL issue access tokens valid for 1 hour.
6. WHEN a token expires during use, THE SYSTEM SHALL return the user to sign-in.
7. WHEN the user presses sign-out, THE SYSTEM SHALL clear the session on the device.
8. THE SYSTEM SHALL NOT allow self sign-up, and users SHALL be created by an administrator only.
9. THE SYSTEM SHALL read the user's id and BU from the verified token claims (`sub` and `custom:bu`), and SHALL NOT accept either from the request body, query string, or headers.
10. THE SYSTEM SHALL NOT let a user change their own `custom:bu` attribute.
11. THE SYSTEM SHALL set demo user passwords at deploy time from a command-line parameter, and SHALL NOT store any password in git.
12. THE SYSTEM SHALL serve the app and API over HTTPS only.

**Edge cases:** a user without a BU attribute is rejected for case study and brief access. Two demo users exist: `se-aws@demo.local` (AWS) and `se-servicenow@demo.local` (ServiceNow).

---

## R2. Paste invite

**User story:** As an SE, I want to paste a meeting invite and see how the system read it, so that I can fix mistakes before research starts.

**Acceptance criteria**
1. WHEN the SE submits invite text longer than 10,000 characters, THE SYSTEM SHALL reject it with HTTP 400 and a message that states the limit, and SHALL NOT call Bedrock.
2. WHEN the SE submits empty or whitespace-only text, THE SYSTEM SHALL reject it with HTTP 400.
3. WHEN the invite text is accepted, THE SYSTEM SHALL save a brief with status `queued` and return its id, without waiting for parsing.
4. WHEN the worker parses the invite, THE SYSTEM SHALL extract: company name, company domain, attendees (name, title, email), meeting date, and notes.
5. WHEN a field is not in the invite, THE SYSTEM SHALL leave it empty and SHALL NOT infer it.
6. WHEN parsing finishes, THE SYSTEM SHALL set the status to `awaiting_confirmation` and show every parsed field in an editable form. THE SYSTEM SHALL NOT start research before the SE confirms.
7. WHEN the SE edits a parsed field, THE SYSTEM SHALL validate it (email format, domain format) before accepting it.
8. WHEN the SE confirms and the parsed data names neither a company nor a company email domain, THE SYSTEM SHALL reject the confirmation and ask the SE to add one.
9. WHEN the only email domains in the invite are free email domains (for example gmail.com) and no company name is given, THE SYSTEM SHALL treat the invite as naming no company.
10. WHEN the parsed company name and the email domains disagree, THE SYSTEM SHALL flag the mismatch in the preview and SHALL NOT accept the confirmation until the SE confirms which company is correct.
11. WHEN the invite lists more than 20 attendees, THE SYSTEM SHALL reject the confirmation with a message that states the limit.
12. WHEN two attendees have the same email, THE SYSTEM SHALL merge them into one.
13. THE SYSTEM SHALL treat the meeting date as optional.
14. WHEN the invite text contains instructions aimed at the model, THE SYSTEM SHALL treat them as invite content and SHALL NOT follow them.
15. IF the parse call fails after retries, THEN THE SYSTEM SHALL set the brief to `failed` with a message, keep the pasted text, and offer Retry.

---

## R3. Company research

**User story:** As an SE, I want sourced facts about the prospect company, so that I can trust and check what the brief says.

**Acceptance criteria**
1. WHEN the SE confirms the parsed invite, THE SYSTEM SHALL research the company from public sources: the company website (home and about pages), the Wikipedia REST API (summary and page), and Google News RSS.
2. THE SYSTEM SHALL return these fields: industry, headquarters, size tier with the rule used, recent news (at most 3 items), and likely pain points.
3. THE SYSTEM SHALL attach at least one source URL to every fact it shows.
4. IF a fact cannot be sourced, THEN THE SYSTEM SHALL leave it out or mark it "unknown", and SHALL NOT estimate it.
5. THE SYSTEM SHALL assign the size tier by these rules: Enterprise when employees are above 5,000 or revenue is above $1B; otherwise Mid-market for 500 to 5,000 employees, SMB for 50 to 499, Boutique for fewer than 50.
6. WHEN the size tier is set, THE SYSTEM SHALL show, next to the tier, the employee count or revenue used, its source URL, and the rule that applied.
7. IF employee count is unknown and revenue does not place the company in Enterprise, THEN THE SYSTEM SHALL set the size tier to "Unknown" and show why.
8. WHEN employee count and revenue point to different tiers, THE SYSTEM SHALL apply the Enterprise rule first (either condition is enough) and show both values.
9. THE SYSTEM SHALL return at most 3 recent news items, newest first, each with title, date, and URL.
10. THE SYSTEM SHALL present pain points as hypotheses, each linked to the sourced facts it is based on, and SHALL drop a hypothesis with no supporting fact.
11. WHEN research for the same company domain was completed less than 7 days ago, THE SYSTEM SHALL use the cached result and SHALL NOT fetch pages or call Bedrock for research again.
12. WHEN a cached result is older than 7 days, THE SYSTEM SHALL research again and replace it.
13. IF one source fails or times out, THEN THE SYSTEM SHALL continue with the other sources and mark the missing facts "unknown".
14. IF no source returns any usable information, THEN THE SYSTEM SHALL fail the brief with a message that no public information was found.
15. WHEN the company name matches more than one company (for example a common name), THE SYSTEM SHALL use the invite's company domain to choose, and SHALL mark the result "unverified match" if the domain cannot confirm it.
16. WHEN fetching a page, THE SYSTEM SHALL apply a timeout and a size limit, SHALL fetch only http or https URLs, and SHALL refuse private and link-local addresses.
17. THE SYSTEM SHALL strip HTML from fetched pages and treat the text as data, not instructions.

---

## R4. Attendee check (REMOVED)

Removed by product owner decision on Nov 20, 2026. The brief lists attendees as written in the invite (name, title, email). There is no verified or unverified status, no reason, and no profile directory. R6.8 (unverified roles) is removed with it. The progress steps are Parsing, Researching, Matching case studies, Writing brief (R9.2).

---

## R5. Case study match

**User story:** As an SE, I want the most relevant Royal Cyber case studies from my own BU for this prospect, so that I can mention proof that fits.

**Acceptance criteria**
1. WHEN the pipeline reaches the case study step, THE SYSTEM SHALL select candidates only from the BU in the user's verified `custom:bu` claim.
2. WHEN a user requests case studies or a brief for another BU (for example with a `bu` parameter or body field), THE SYSTEM SHALL return only their own BU's case studies.
3. THE SYSTEM SHALL NOT offer an "All BUs" option.
4. THE SYSTEM SHALL prefilter candidates by BU, then industry and tags, and then have the model score each remaining candidate from 0 to 100 with a reason.
5. THE SYSTEM SHALL show only candidates that score 60 or more, ranked by score, up to 3.
6. THE SYSTEM SHALL show for each case study: title, a relevance reason, and a link to the public case study page.
7. THE SYSTEM SHALL write each relevance reason using only facts in the case study record and the company research.
8. WHEN fewer than 3 candidates score 60 or more, THE SYSTEM SHALL show those that do and the message "No strong match for <need>", where `<need>` is the pain point or topic left uncovered.
9. WHEN no candidate scores 60 or more, THE SYSTEM SHALL show "No strong match in your BU's library".
10. WHEN the user has no BU attribute, THE SYSTEM SHALL return no case studies and show an explanation.
11. WHEN `GET /case-studies` is called, THE SYSTEM SHALL return only case studies from the user's own BU.
12. THE SYSTEM SHALL read case studies from the bundled `data/case_studies.json` and SHALL NOT call external sources at match time.
13. THE SYSTEM SHALL store for each case study only: id, title, a 1 to 2 sentence summary in our own words, BU, industry, tags, and the public URL.
14. THE TEAM SHALL show the BU separation in the demo by signing in as both demo users and getting different case studies.

---

## R6. Discovery brief

**User story:** As an SE, I want a complete brief in one standard format, so that every call is prepared the same way.

**Acceptance criteria**
1. THE SYSTEM SHALL write the brief with these sections, in this order: Company snapshot, Attendees, Pain-point hypotheses, Agenda (30 min), Discovery questions, Case studies to mention, Sources.
2. THE SYSTEM SHALL write 8 to 10 discovery questions.
3. THE SYSTEM SHALL write an agenda whose time blocks add up to 30 minutes.
4. THE SYSTEM SHALL base every statement of fact in the brief on the research, attendee check, or case study results, and SHALL show its source URL.
5. THE SYSTEM SHALL list every source URL used in the Sources section, without duplicates.
6. WHEN the user has saved rules, THE SYSTEM SHALL apply up to the 10 most recent rules when writing the brief, and SHALL show which rules were applied.
7. WHEN a section's input is "unknown" or empty, THE SYSTEM SHALL say so in that section and SHALL NOT fill it with guesses.
8. (Removed with R4.)
9. WHEN the model output does not match the required structure, THE SYSTEM SHALL retry once and then mark the brief `failed` with a message.
10. THE SYSTEM SHALL save the brief with status `ready` when all sections are complete.

---

## R7. Edit and approve

**User story:** As an SE, I want to edit the brief and approve it, so that the final version is mine and the system learns my preferences.

**Acceptance criteria**
1. WHILE a brief has status `ready`, THE SYSTEM SHALL let the SE edit any section inline.
2. WHEN the SE saves an edit, THE SYSTEM SHALL store the change and keep the original draft unchanged.
3. WHILE a brief has any status other than `ready`, THE SYSTEM SHALL NOT allow edits to the brief content.
4. WHEN the SE approves, THE SYSTEM SHALL set the status to `approved` and lock the brief against further edits.
5. WHEN a request tries to edit or approve an `approved` brief, THE SYSTEM SHALL reject it and leave the brief unchanged.
6. WHEN the SE approves, THE SYSTEM SHALL queue a rule extraction job on the worker. THE SYSTEM SHALL NOT call Bedrock from the approve request.
7. WHEN the rule extraction job finishes, THE SYSTEM SHALL propose 0 to 3 reusable rules based on the difference between the draft and the final text.
8. WHILE the rule extraction job is running, THE SYSTEM SHALL show the brief as approved and the rules area as "checking for rules".
9. WHEN the draft and the final text are the same, THE SYSTEM SHALL propose no rules.
10. THE SYSTEM SHALL show each proposed rule and let the SE keep or discard each one separately.
11. WHEN the SE keeps a rule, THE SYSTEM SHALL save it for that user and apply it to that user's next briefs.
12. WHEN a proposed rule is the same as a saved rule, THE SYSTEM SHALL NOT save it twice.
13. IF rule extraction fails, THEN THE SYSTEM SHALL keep the brief approved and tell the SE that no rules were proposed.
14. THE SYSTEM SHALL let the SE view and delete their saved rules.
15. THE SYSTEM SHALL NOT share one user's rules with another user.
16. WHEN a user other than the owner tries to read, edit, approve, or retry a brief, THE SYSTEM SHALL return HTTP 404.

---

## R8. Brief history

**User story:** As an SE, I want to see my past briefs, so that I can reopen one before a follow-up call.

**Acceptance criteria**
1. WHEN the SE opens history, THE SYSTEM SHALL list only that user's briefs, newest first.
2. THE SYSTEM SHALL show for each brief: company, meeting date, status, and created time.
3. WHEN the SE selects a brief, THE SYSTEM SHALL open it. WHILE it is `approved`, it opens read-only.
4. WHEN the user has no briefs, THE SYSTEM SHALL show an empty-state message.
5. WHEN the list has more than 20 briefs, THE SYSTEM SHALL return them in pages of 20.
6. THE SYSTEM SHALL include briefs in every status, and show `failed` briefs with their error message.
7. THE SYSTEM SHALL expire each brief 30 days after its creation (DynamoDB TTL), and SHALL NOT show expired briefs.

---

## R9. Progress

**User story:** As an SE, I want to see what the system is doing, so that I know the brief is on its way.

**Acceptance criteria**
1. WHEN the SE submits an invite or confirms the parsed invite, THE SYSTEM SHALL return immediately with the brief id and status `queued`, without waiting for the pipeline.
2. WHILE a brief is `processing`, THE SYSTEM SHALL show the current step: Parsing, Researching, Matching case studies, Writing brief.
3. WHEN a step finishes, THE SYSTEM SHALL record the new step before the next step starts.
4. WHILE a brief is `queued`, THE SYSTEM SHALL show "queued", and the queue position when it is known.
5. WHILE a brief is `queued` or `processing`, THE UI SHALL poll `GET /briefs/{id}` every 2 seconds.
6. WHEN the status becomes `awaiting_confirmation`, `ready`, `approved`, or `failed`, THE UI SHALL stop polling.
7. WHEN the queue is empty, THE SYSTEM SHALL have a confirmed brief `ready` within 60 seconds.
8. WHEN other jobs are ahead in the queue, THE SYSTEM SHALL keep the brief `queued` until the worker takes it.
9. IF a brief makes no progress for 120 seconds, THEN THE SYSTEM SHALL mark it `failed` with a message and show a Retry button.
10. IF a step fails after retries, THEN THE SYSTEM SHALL mark the brief `failed`, name the step that failed, and show a Retry button.
11. WHEN the SE presses Retry, THE SYSTEM SHALL queue the brief again and reuse steps that already finished, including cached research.
12. WHEN the SE closes and reopens the page during processing, THE SYSTEM SHALL show the current progress of the same brief.
13. WHEN a queue message is delivered more than once, THE SYSTEM SHALL NOT run the same step twice or overwrite a newer status.

---

## R10. Operations, security, and cost

**User story:** As the team, we want the system to be reliable, secure, and cheap, so that it passes review and is affordable in production.

**Acceptance criteria**

*Bedrock use*
1. THE SYSTEM SHALL send at most 1 Bedrock request per second across all briefs, by running every Bedrock call in one worker Lambda with reserved concurrency 1 and batch size 1, fed by an SQS queue.
2. THE SYSTEM SHALL keep an in-process token bucket of 1 request per second in the worker as a second guard.
3. THE SYSTEM SHALL run rule extraction on approve as an SQS job on the same worker.
4. THE SYSTEM SHALL NOT call Bedrock from the API Lambdas, and SHALL NOT grant them Bedrock permissions.
5. THE SYSTEM SHALL send every Bedrock call through one shared client and SHALL NOT call Bedrock anywhere else.
6. THE SYSTEM SHALL set `max_tokens` on every Bedrock call.
7. WHEN Bedrock returns a throttling error, THE SYSTEM SHALL retry with exponential backoff and jitter, up to a fixed number of attempts, without exceeding 1 request per second.
8. WHEN retries are used up, THE SYSTEM SHALL fail the step and SHALL NOT retry forever.
9. THE SYSTEM SHALL use Haiku for extraction, classification, and scoring, and Sonnet for writing the brief.
10. THE SYSTEM SHALL use only the `us-east-1` region for all resources and SDK clients.

*Queue and failures*
11. THE SYSTEM SHALL send a message to a dead-letter queue after 3 failed receives (`maxReceiveCount` 3).
12. WHEN the dead-letter queue holds one or more messages, THE SYSTEM SHALL raise a CloudWatch alarm (depth above 0).

*Logging and metrics*
13. THE SYSTEM SHALL write structured logs with a brief id and request id on every log line.
14. THE SYSTEM SHALL NOT write invite text, attendee emails, or tokens to logs.
15. THE SYSTEM SHALL keep CloudWatch logs for 14 days.
16. THE SYSTEM SHALL publish the metrics `BriefGenerated`, `BedrockCalls`, `BedrockThrottled`, and `ResearchLatencyMs`.

*Security*
17. THE SYSTEM SHALL give each function an IAM role limited to the tables, queues, and actions it needs.
18. THE SYSTEM SHALL keep the web bucket private, reachable only through CloudFront.
19. THE SYSTEM SHALL redirect HTTP to HTTPS and SHALL NOT serve any content over plain HTTP.
20. THE SYSTEM SHALL validate every API input for type, length, and allowed values, and SHALL reject invalid input with HTTP 400 and no stack trace.
21. THE SYSTEM SHALL NOT store secrets in code or git, and SHALL read configuration from environment variables set by CDK.

*Cost and delivery*
22. THE SYSTEM SHALL use serverless services only, with no always-on compute.
23. THE SYSTEM SHALL cache research results in DynamoDB for 7 days to avoid repeated Bedrock calls.
24. THE TEAM SHALL deliver `docs/cost-estimate.md` with a per-service pricing table, Bedrock token cost with and without caching, a monthly total, and estimated hours saved per SE per week, with assumptions stated.
25. THE TEAM SHALL define all infrastructure in AWS CDK (TypeScript) in git, and the stack SHALL deploy with `cdk deploy`.
26. THE TEAM SHALL provide a README with architecture, local run steps, deploy steps, and the demo script. THE README SHALL say if the case study seed was written by hand.

---

## Out of scope
- Outlook or calendar integration.
- Case study admin or management screens.
- Full role-based access control.
- RFP response copilot.
- Real attendee data or customer data of any kind.

## Traceability to the demo
The 3-minute demo uses R1 (sign in as two users), R2 (paste and preview), R9 (progress), R3 to R6 (brief with cited facts, size tier, flagged attendees, 3 case studies, different case studies per BU), and R7 (edit one line, approve, review rules).
