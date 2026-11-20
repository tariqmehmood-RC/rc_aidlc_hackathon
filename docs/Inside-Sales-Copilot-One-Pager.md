# Inside Sales Copilot: One Pager

**Team 5** · AWS AI-DLC Hackathon · Friday, November 20, 2026

## Domain and persona

**Domain:** Presales at IT services companies such as Royal Cyber.

**Personas:** Account executives (AEs), sales engineers (SEs) and solution architects (SAs) who prepare for discovery calls with new prospects.

## Problem

Before every discovery call, the presales team researches the prospect by hand. They look up:

- who the company is and how big it is (enterprise, mid-market, SMB or boutique)
- who is joining the call and what their role is
- the prospect's likely pain points
- which Royal Cyber case studies are relevant

This takes hours per call and is spread across many browser tabs. Mistakes happen, such as reading the wrong person's profile, and there is no standard format for call notes.

_Time spent on call prep, from research: <to be filled in by Sravani>_

## Solution

The SE pastes the meeting invite. The copilot then:

1. **Researches the company** from public sources: industry, size tier, recent news and likely pain points, each with a source link.
2. **Checks the attendees.** A profile counts only if the employer and title match the invite. Anything else is marked "unverified" instead of guessed.
3. **Matches case studies** from Royal Cyber's library, filtered by business unit (BU), such as ServiceNow or AWS, and explains why each one is relevant.
4. **Drafts a discovery brief:** agenda, questions to ask, pain-point hypotheses and case studies to mention.
5. **Lets the SE edit and approve** the brief. Their corrections become rules for the next brief.

## Outcome

- Call prep goes from hours to minutes.
- Every fact in the brief has a source.
- Relevant case studies are found every time, not only when someone remembers them.
- Every call is prepared to the same standard.

## Scope for the day

| In | Out (roadmap) |
|---|---|
| Paste invite → research → case study match → brief → approve | Outlook integration |
| Case studies loaded from the public Royal Cyber website | Case study management screens |
| BU filter with two demo users, if time allows | Full RBAC with Cognito |
| Runs locally, deployed to AWS if time allows | RFP response copilot |

## Constraints

- Test data only. Research real companies, but use synthetic or consenting attendee profiles. We will confirm this with an AWS mentor at kickoff.
- us-east-1 only, and no more than one Bedrock call per second.

## Demo (3 minutes)

Paste an invite for a real public company. The brief appears with cited facts, a size tier, flagged attendees and three matching case studies. The SE edits one line and approves it.

## Open questions for the team

1. Which web research option should we use: AgentCore Browser, a search API, or company website plus Wikipedia?
2. Which prospect company should we use for the demo?
3. Who owns which stream?
