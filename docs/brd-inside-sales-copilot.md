# Inside Sales Copilot

Sources: `docs/Inside-Sales-Copilot-One-Pager.md` and `docs/Inside-Sales-Copilot-Draft-Plan.md`. Where they differ, this brief follows the draft plan. Draft for a person to review before the spec is written.

## Why
Before every discovery call, the presales team researches the prospect by hand across many browser tabs. It takes hours per call. Mistakes happen, such as reading the wrong person's profile, and there is no standard format for call notes.

Time spent on call prep today: <to be filled in by Sravani from SE research>.

## Who it is for
Account executives (AEs), sales engineers (SEs) and solution architects (SAs) at IT services companies such as Royal Cyber, preparing for discovery calls with new prospects. The SE is the main user: they paste the invite, then edit and approve the brief.

## In scope
- Paste a meeting invite for any public company. The company is entered at runtime.
- Research the company from public web sources: industry, size tier (enterprise, mid-market, SMB or boutique), recent news and likely pain points. Each fact has a source link.
- Check each attendee using public information only. A profile counts as verified only if the employer and title match the invite. Anything else is marked "unverified" and is not guessed.
- Match case studies from a pre-scraped snapshot of the public Royal Cyber website, tagged by business unit (BU), with a reason for each match. The BU filter is optional. The BU list is decided after the scrape.
- Draft a discovery brief: agenda, questions to ask, pain-point hypotheses and case studies to mention.
- The SE edits sections inline and approves. Approval locks the brief, and a Markdown export with source links is available only after approval.
- Keep the original and the edited text, so edit history exists for a later "learn from edits" feature.
- Mask PII, such as email addresses, in model input and output using Amazon Bedrock Guardrails.
- Run locally. Deploy to AWS if time allows.

## Out of scope (roadmap)
Learning rules from SE edits, Outlook integration, case study management screens, full RBAC (including the two-demo-user BU filter and Cognito), an RFP response copilot, and any feature not listed above.

## Requirements
1. Given a pasted invite, the system produces a draft brief for the invite's company.
2. Every fact in the brief (company facts, news, pain points) has a source link. A fact with no source is not shown.
3. The company has a size tier of enterprise, mid-market, SMB or boutique.
4. Each attendee is shown as verified or unverified, with a reason when unverified. Verified requires both employer and title to match the invite. The system never guesses.
5. Case studies come from the Royal Cyber snapshot, each with a stated reason for the match. Choosing a BU limits matches to that BU.
6. The brief contains an agenda, questions to ask, pain-point hypotheses and case studies to mention.
7. The SE can edit each section inline and approve the brief. An approved brief cannot be edited.
8. The Markdown export is available only after approval and includes every source link.
9. PII such as email addresses is masked in model input and output.
10. If one research step fails, the brief is still returned with that section clearly flagged.
11. Call prep goes from hours to minutes. A full draft brief returns in under about 2 minutes.

## Success criteria
- Paste an invite for a real public company and see a brief with cited facts, a size tier, flagged attendees and three matching case studies.
- A deliberately wrong attendee shows as "unverified".
- Choose a BU and see only that BU's case studies.
- The SE edits one line, approves the brief, and downloads the Markdown export. After approval, further edits are rejected.
- The full flow runs in the 3-minute demo, on a company chosen at runtime. A backup recording or cached run is ready if the network fails.

## Constraints
- us-east-1 only, and no more than one Bedrock call per second.
- Attendee search covers public information only. The mentor is confirming at kickoff whether this conflicts with the one-pager's "test data only" line. Attendee search stays behind one function so a guardrail can be added quickly.
- Case studies come from a direct scrape of royalcyber.com. The web search tool's terms do not allow bulk storage of its results or building an index from them, and require source citations to be kept and shown.
- Demo time: 3 minutes inside a 10-minute presentation. Build time: one day.

## Decisions taken from the draft plan
- Web research uses the AgentCore Web Search tool, through an AgentCore Gateway target.
- Learning from SE edits is on the roadmap, not in this build.
- Real-attendee search uses public information only, pending the mentor's answer.
- PII masking, approval locking and the Markdown export are in scope.
- Suggested owners are in the draft plan and can be adjusted.

## Open questions
1. Which prospect company for the demo? It is a runtime input.
2. Mentor's answer on searching for real attendees.
3. Mentor's confirmation of the PII masking decision (from the team lead).
4. The final BU list, decided after the case study scrape.
5. The "hours saved per call" figure, from Sravani's SE research.
