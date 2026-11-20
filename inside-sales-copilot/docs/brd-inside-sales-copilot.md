# Inside Sales Copilot

Team 5, AWS AI-DLC Hackathon, November 20, 2026. Domain: presales at Royal Cyber (IT services).

## Why
Before every discovery call, account executives, sales engineers (SE), and solution architects research the prospect by hand. They look up the company, its size tier, who is attending and in what role, likely pain points, and which Royal Cyber case studies fit. This takes hours per call across many browser tabs. Mistakes happen, such as opening the wrong person's profile. Notes have no standard format, so every call is prepared differently.

Inside Sales Copilot turns a pasted meeting invite into a cited discovery brief in minutes, and learns from the SE's edits.

## Who it is for
- Account executives, sales engineers, and solution architects who prepare for discovery calls with new prospects.
- Primary user in the demo: the SE who pastes the invite, reviews, edits, and approves the brief.

## Outcome
- Prep time goes from hours to minutes.
- Every fact in the brief has a source URL.
- Relevant case studies appear every time.
- Every call is prepared to one standard format.

## User flow
1. **Paste invite.** The SE pastes a meeting invite as free text: subject, company, attendees (names, titles, emails), and notes.
2. **Company research.** The system researches the company from public sources: industry, size tier, recent news, likely pain points. Every fact carries a source URL.
3. **Attendee check.** An attendee is "verified" only if both employer and title match the invite. Otherwise the attendee is "unverified". The system never guesses.
4. **Case study match.** The system picks the top 3 case studies from Royal Cyber's library, filtered by the user's business unit (BU), such as ServiceNow, AWS, Salesforce, or Data & AI. Each has a "why relevant" explanation.
5. **Draft brief.** The system produces a discovery brief: agenda, discovery questions, pain-point hypotheses, and case studies to mention.
6. **Edit and approve.** The SE edits and approves the brief. The SE's edits are saved as rules (for example, "always ask about budget cycle") and applied to the next brief.

## In scope (today)
- Paste invite, research, case study match, brief, edit and approve.
- Case study library seeded from the public Royal Cyber website, stored as a JSON seed file.
- BU filter with two demo users (AWS and ServiceNow). Part of the demo.
- Run locally first, then deploy to AWS with CDK.

## Out of scope (roadmap)
- Outlook integration.
- Case study management screens.
- Full role-based access control (RBAC).
- RFP response copilot.

## Functional requirements

### FR1. Invite intake
1. The user can paste free-text invite content into a form and submit it.
2. The system extracts: meeting subject, company name, attendees (name, title, email), and notes.
3. If the company name or attendees cannot be extracted, the system tells the user what is missing and does not continue.
4. Input is limited to 10,000 characters and validated before processing.
5. The system shows what it parsed, and the SE can correct it before research starts.

### FR2. Company research
1. The system returns industry, size tier, recent news, and likely pain points for the company.
2. Size tier is one of: Enterprise, Mid-market, SMB, Boutique, or Unknown when the data is missing. The rule and source are shown next to the tier (criteria in the Decisions table).
3. Every fact carries at least one source URL. A fact with no source is not shown.
4. Research results are cached in DynamoDB by company domain for 7 days, so repeat requests do not call Bedrock again.
5. Only real public companies are researched. If no reliable public information is found, the brief says so instead of inventing facts.

### FR3. Attendee verification
1. Attendee profiles are synthetic data. No real person data is used.
2. An attendee is "verified" only when employer AND title both match the invite.
3. Any other result (mismatch, missing, ambiguous) is "unverified". The system never guesses.
4. The brief shows the status of each attendee and the reason for "unverified".

### FR4. Case study match
1. The library is loaded from a JSON seed file built from the public Royal Cyber website. Each entry has an id, title, a 1 to 2 sentence summary in our own words, BU, industry, tags, and the public URL of the case study.
2. The system returns the top 3 matches for the prospect, each with a "why relevant" explanation.
3. Results are filtered by the signed-in user's BU. A user never sees case studies from another BU.
4. If fewer than 3 case studies match, the system returns what it has and says so.

### FR5. Discovery brief
1. The brief contains: agenda, discovery questions, pain-point hypotheses, and case studies to mention.
2. Facts in the brief carry their source URLs.
3. Saved rules from earlier edits are applied to the draft.
4. Brief format is identical for every call.

### FR6. Edit, approve, and rules
1. The SE can edit any part of the brief and approve it.
2. On approval, each edit is saved as a rule tied to the user (for example, "always ask about budget cycle").
3. The next brief for that user includes the saved rules.
4. The SE can see and delete their saved rules.
5. Approved briefs are stored and can be reopened.

### FR7. Progress and status
1. The UI shows progress while the brief is built (for example: researching, verifying attendees, matching case studies, drafting).
2. Progress is streamed or polled, so the user is never looking at a blank screen.
3. Failures show a clear message and a retry option.

### FR8. Users and BU access
1. Two demo users, each assigned to one BU.
2. Sign-in is through Amazon Cognito. The BU is stored as a custom attribute (`custom:bu`) and read from the verified token on the server.
3. There is no "All BUs" option. A request for another BU returns only the user's own BU's case studies.

## Non-functional requirements

### Hard rules from the hackathon
- Infrastructure is AWS CDK, committed to the local git repository (no remote).
- Synthetic data only. Real public companies may be researched. Attendee profiles are synthetic. No customer data. No secrets in code.
- Region is us-east-1 only.
- Amazon Bedrock is called at no more than 1 request per second. This is enforced in code, not by convention. The limiter applies to every Bedrock call across all concurrent requests.
- Demo is 10 minutes: problem, live demo, result, next steps.

### Operational excellence
- Deploy with `cdk deploy`.
- CloudWatch logs for all compute, and custom metrics (briefs generated, Bedrock calls, throttles, failures, brief duration).
- Error handling with retries and backoff for Bedrock and external calls, within the 1 rps limit.
- Fast perceived response: stream progress or show status (see FR7).
- README with architecture, local run steps, deploy steps, and demo script.

### Security
- Cognito sign-in for all API access.
- Each BU user sees only their BU's case studies, enforced on the server.
- Least-privilege IAM: each function gets only the actions and resources it needs.
- HTTPS only, served through CloudFront. HTTP redirects to HTTPS.
- Input validation on every API input, with length and type limits.
- No secrets in code or git. Prompt-injection text in an invite or fetched page is treated as data, not instructions.

### Cost
- Serverless services only.
- Bedrock cost controls: choose a small, low-cost model where quality allows, set max output tokens, and cache research in DynamoDB.
- Model choice (decided): Claude Haiku 4.5 for all five Bedrock calls, including writing the brief. Claude Sonnet 5 can be switched on for brief writing through configuration (`briefModel`). The cost estimate shows both: the default all-Haiku cost per brief and the cost with Sonnet writing the brief.
- Deliver a monthly cost estimate (see below).

### Reliability and performance
- Target time from confirming the parsed invite to a ready brief: under 60 seconds when no other brief is queued.
- Because of the 1 rps Bedrock limit, a brief uses a small, fixed number of Bedrock calls, and calls are queued rather than dropped.

## Well-Architected plan

| Pillar | Item | How we cover it |
|---|---|---|
| Operational excellence | CDK deploy | All infra in CDK, in git |
| Operational excellence | Logs and metrics | CloudWatch logs, custom metrics, one dashboard |
| Operational excellence | Errors and retries | Backoff retries, clear user errors |
| Operational excellence | Fast responses | Streamed progress or status polling |
| Operational excellence | README | Architecture, run, deploy, demo script |
| Security | Authentication | Cognito |
| Security | Data separation | Server-side BU filter on case studies |
| Security | IAM | Least privilege per function |
| Security | Transport | CloudFront, HTTPS only |
| Security | Input | Validation at the API boundary |
| Cost optimization | Serverless | No always-on compute |
| Cost optimization | Bedrock controls | Model choice, max tokens, DynamoDB cache |
| Cost optimization | Savings story | Hours saved per SE per week (below) |

## Cost estimate (deliverable)
The final document must include the items below. Numbers are filled in during design, using current prices from the AWS pricing pages for us-east-1.

1. **Assumptions.** Briefs per month, Bedrock calls per brief, average input and output tokens per call, cache hit rate, number of users.
2. **Per-service pricing table.** One row per service: Bedrock, Lambda, API Gateway (or equivalent), DynamoDB, Cognito, CloudFront, S3, CloudWatch. Columns: unit price, monthly usage, monthly cost.
3. **Bedrock token cost.** Input tokens, output tokens, with and without caching.
4. **Monthly total** for the demo and for an example production team.
5. **Estimated production savings.** Hours saved per SE per week = (current prep hours per call - copilot prep minutes per call) x calls per week. Baseline and assumptions are stated and marked as estimates.

## Success criteria
- Pasting an invite for a real public company produces a brief with cited facts, a size tier, attendee statuses, and 3 matching case studies.
- Every fact in the brief has a source URL.
- An attendee whose employer or title does not match is shown as "unverified".
- A BU user never sees another BU's case studies.
- Editing one line and approving saves a rule, and the next brief applies it.
- Bedrock calls never exceed 1 per second, shown by a test.
- The stack deploys to us-east-1 with `cdk deploy`, and the app is reachable only over HTTPS.
- README and cost estimate are complete.

## Demo plan (10 minutes)
| Time | Part |
|---|---|
| 2 min | Problem: hours of manual prep, wrong profiles, no standard notes |
| 3 min | Live demo: paste an invite for a real public company, the brief appears with cited facts, size tier, flagged attendees, and 3 case studies, then the SE edits one line and approves |
| 2 min | Result: prep time, citations, standard format, cost and Well-Architected summary |
| 3 min | Next steps: Outlook integration, case study management, full RBAC, RFP response copilot |

## Constraints
- Region us-east-1 only.
- Bedrock at most 1 request per second, enforced in code.
- Synthetic attendee data only. No customer data. No secrets in code.
- Infrastructure in AWS CDK.
- Runs locally first, then deploys to AWS.

## Decisions (previously open questions)
All earlier open questions are closed. Details are in `.kiro/specs/inside-sales-copilot/requirements.md` and `design.md`.

| Question | Decision |
|---|---|
| Bedrock models and research method | Claude Sonnet writes the brief. Claude Haiku does extraction, classification, and scoring. Research is a live fetch of the company website, the Wikipedia REST API, and Google News RSS, with the source URL kept for every fact. A `ResearchProvider` interface allows a later swap. |
| Streaming approach | Status polling every 2 seconds against a status stored in DynamoDB. |
| Size tier criteria | Enterprise: more than 5,000 employees or more than $1B revenue. Mid-market: 500 to 5,000. SMB: 50 to 499. Boutique: fewer than 50. "Unknown" when the data is missing. The rule and source are shown next to the tier. |
| Research cache TTL | 7 days. |
| Demo users and BUs | `se-aws@demo.local` (AWS) and `se-servicenow@demo.local` (ServiceNow). Each sees only their own BU's case studies. There is no "All" option. |
| Enforcing 1 Bedrock request per second | All Bedrock calls run in one worker Lambda fed by an SQS queue, with reserved concurrency 1 and batch size 1. An in-process token bucket is a second guard. API Lambdas never call Bedrock. |
| Data retention | Briefs expire 30 days after creation (DynamoDB TTL). Logs never contain invite text or attendee emails. CloudWatch log retention is 14 days. |
| Case study library | Stores only title, a short summary in our own words, BU, industry, tags, and the public URL. If the site blocks fetching, the seed is written by hand from the public pages and the README says so. |
| Attendee profiles | Synthetic directory in `data/attendee_profiles.json`, keyed by email. |
