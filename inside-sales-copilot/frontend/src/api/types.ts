// Shapes returned by the API (design 6 and 5). Kept in one place so the mock and the
// real API stay in step.

export type BriefStatus = 'queued' | 'processing' | 'awaiting_confirmation' | 'ready' | 'approved' | 'failed'
export type Step = 'Parsing' | 'Researching' | 'Checking attendees' | 'Matching case studies' | 'Writing brief'
export type RulesStatus = 'none' | 'pending' | 'ready' | 'failed'
export type BU = 'AWS' | 'ServiceNow' | 'Salesforce' | 'Data & AI'

export const STEPS: Step[] = ['Parsing', 'Researching', 'Checking attendees', 'Matching case studies', 'Writing brief']

export interface Attendee {
  name: string
  title: string | null
  email: string
}

export interface ParsedInvite {
  subject: string | null
  company: { name: string | null; domain: string | null }
  attendees: Attendee[]
  meetingDate: string | null
  notes: string | null
  warnings?: Array<'company_domain_mismatch' | 'only_free_email_domains'>
}

export interface Fact {
  id: string
  text: string
  sourceUrls: string[]
}

export interface Research {
  company: { name: string; domain: string; matchConfidence: 'confirmed' | 'unverified_match' }
  facts: Fact[]
  industry: { value: string; factId: string } | null
  headquarters: { value: string; factId: string } | null
  sizeTier: {
    tier: 'Enterprise' | 'Mid-market' | 'SMB' | 'Boutique' | 'Unknown'
    rule: string
    basis: { employees: number | null; revenueUsd: number | null; sourceUrls: string[] }
  }
  news: Array<{ title: string; date: string | null; url: string }>
  painPoints: Array<{ id: string; hypothesis: string; basedOnFactIds: string[] }>
}

export type UnverifiedReason = 'employer_mismatch' | 'title_mismatch' | 'no_profile_found' | 'title_missing' | 'ambiguous'

export interface BriefAttendee {
  email: string
  name: string
  title: string | null
  status: 'verified' | 'unverified'
  reason: UnverifiedReason | null
}

export interface CaseStudyMatch {
  caseStudyId: string
  title: string
  url: string
  score: number
  reason: string
}

export interface BriefContent {
  companySnapshot: Array<{ id: string; text: string; sourceUrls: string[] }>
  attendees: BriefAttendee[]
  painPointHypotheses: Array<{ id: string; text: string; basedOnFactIds: string[]; sourceUrls: string[] }>
  agenda: Array<{ id: string; minutes: number; topic: string; note: string }>
  discoveryQuestions: Array<{ id: string; text: string }>
  caseStudies: Array<{ caseStudyId: string; title: string; url: string; reason: string }>
  caseStudiesNote?: string | null
  sources: Array<{ url: string; label: string }>
}

export interface RuleProposal {
  proposalId: string
  text: string
  rationale: string
}

export interface BriefView {
  briefId: string
  status: BriefStatus
  step?: Step
  queuePosition?: number
  createdAt: number
  version: number
  rulesStatus: RulesStatus
  parsedInvite?: ParsedInvite
  confirmedInvite?: ParsedInvite
  research?: Research
  attendeeChecks?: unknown[]
  caseStudyMatches?: { matches: CaseStudyMatch[]; message: string | null }
  content?: BriefContent
  rulesApplied?: Array<{ ruleId: string; text: string }>
  ruleProposals?: RuleProposal[]
  error?: { code: string; step: Step | null; message: string }
}

export interface BriefSummary {
  briefId: string
  companyName: string | null
  meetingDate: string | null
  status: BriefStatus
  createdAt: number
  error?: { code: string; message: string }
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: Array<{ code: string; message: string }> }
}
