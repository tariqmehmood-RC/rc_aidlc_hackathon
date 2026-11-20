# Product: Inside Sales Copilot

Team 5, AWS AI-DLC Hackathon, November 20, 2026. Source of truth for requirements: `docs/brd-inside-sales-copilot.md`. Rules for all work: `AGENTS.md`.

## Product
Inside Sales Copilot turns a pasted meeting invite into a cited discovery brief in minutes, and learns from the SE's edits. Domain: presales at Royal Cyber, an IT services company.

## Personas
Account executives, sales engineers (SE), and solution architects who prepare for discovery calls with new prospects. The demo persona is the SE who pastes the invite, edits the brief, and approves it.

## Problem
Before every discovery call the team researches the prospect by hand: company identity and size tier (Enterprise, Mid-market, SMB, Boutique), who attends and in what role, likely pain points, and relevant Royal Cyber case studies. This takes hours per call across many browser tabs. Mistakes happen, such as opening the wrong person's profile. Notes have no standard format.

## Outcome
- Prep goes from hours to minutes.
- Every fact has a source URL.
- Relevant case studies show up every time.
- Every call is prepared to one standard format.

## The 6-step flow
1. **Paste invite.** Free text: subject, company, attendees (name, title, email), notes.
2. **Company research.** Public sources only. Industry, size tier, recent news, likely pain points. Every fact has a source URL. A fact without a source is not shown.
3. **Attendees.** Listed as written in the invite (name, title, email). No verification.
4. **Case study match.** Top 3 from Royal Cyber's library, filtered by the user's business unit (BU), each with a "why relevant" explanation.
5. **Draft brief.** Agenda, discovery questions, pain-point hypotheses, case studies to mention. Same format every time.
6. **Edit and approve.** The SE edits and approves. Edits are saved as rules (for example "always ask about budget cycle") and fed into the next brief.

## Scope
In scope today:
- Paste invite, research, case study match, brief, edit and approve.
- Case studies seeded from the public Royal Cyber website as a JSON file.
- BU filter with two demo users (stretch).
- Run locally first, then deploy to AWS with CDK.

Out of scope (roadmap, do not build):
- Outlook integration.
- Case study management screens.
- Full RBAC.
- RFP response copilot.

## Non-negotiables
- Synthetic attendee data only. Real public companies may be researched. No customer data.
- Every fact is cited. Never invent a source URL.
- Each BU user sees only their BU's case studies, enforced on the server.

## Demo script (10 minutes)
1. **Problem (2 min).** Hours of manual prep, wrong profiles, no standard notes.
2. **Live demo (3 min).**
   1. Sign in as a demo SE.
   2. Paste an invite for a real public company with synthetic attendees.
   3. Show progress while the brief builds.
   4. Show the brief: cited facts, size tier, the attendee list, 3 matching case studies.
   5. Edit one line and approve. Show that it is saved as a rule.
3. **Result (2 min).** Prep time, citations, standard format, Well-Architected and cost summary.
4. **Next steps (3 min).** Outlook integration, case study management, full RBAC, RFP response copilot.

The full script lives in `docs/demo-script.md`.
