// In-memory stand-in for the backend, used by MSW in development and tests (task 4.1).
// It follows the real status flow (design 3) with time-based steps, and serves a brief that
// was produced by a real run of the Allstate sample invite (scripts/make_mock_fixture.py).
import fixture from './fixtures/allstate.json'
import type { BriefContent, BriefStatus, BriefView, ParsedInvite, RuleProposal, Step } from '../api/types'

const PIPELINE: Step[] = ['Researching', 'Checking attendees', 'Matching case studies', 'Writing brief']
const FREE_MAIL = new Set(['gmail.com', 'outlook.com', 'yahoo.com', 'hotmail.com', 'icloud.com', 'proton.me', 'aol.com'])
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

interface MockBrief {
  briefId: string
  owner: string
  bu: string
  inviteText: string
  createdAt: number
  phase: 'parse' | 'pipeline' | 'done'
  phaseStart: number
  parsedInvite?: ParsedInvite
  confirmedInvite?: ParsedInvite
  content?: BriefContent
  draft?: BriefContent
  version: number
  approved: boolean
  approvedAt?: number
  rulesStatus: 'none' | 'pending' | 'ready' | 'failed'
  ruleProposals: RuleProposal[]
  failAt?: Step
  error?: BriefView['error']
}

export interface MockOptions {
  /** Duration of each simulated step. */
  stepMs?: number
  now?: () => number
}

export class MockDb {
  briefs = new Map<string, MockBrief>()
  rules = new Map<string, Array<{ ruleId: string; text: string; createdAt: number }>>()
  stepMs: number
  now: () => number
  private counter = 0

  constructor({ stepMs = 1500, now = () => Date.now() }: MockOptions = {}) {
    this.stepMs = stepMs
    this.now = now
  }

  private newId() {
    this.counter += 1
    return (this.counter.toString(16) + 'a'.repeat(32)).slice(0, 32)
  }

  create(owner: string, bu: string, inviteText: string): string {
    const briefId = this.newId()
    // An invite that mentions "Nonexistent Corp" fails at research, to show the failed state.
    const failAt = /nonexistent corp/i.test(inviteText) ? ('Researching' as Step) : undefined
    this.briefs.set(briefId, {
      briefId, owner, bu, inviteText, createdAt: this.now(), phase: 'parse', phaseStart: this.now(),
      version: 0, approved: false, rulesStatus: 'none', ruleProposals: [], failAt,
    })
    return briefId
  }

  get(id: string, owner: string): MockBrief | null {
    const b = this.briefs.get(id)
    return b && b.owner === owner ? b : null
  }

  /** What GET /briefs/{id} returns at this moment. */
  view(b: MockBrief): BriefView {
    const elapsed = this.now() - b.phaseStart
    const base = { briefId: b.briefId, createdAt: b.createdAt, version: b.version, rulesStatus: b.rulesStatus }
    const out: BriefView = { ...base, status: 'queued' }
    if (b.parsedInvite) out.parsedInvite = b.parsedInvite
    if (b.confirmedInvite) out.confirmedInvite = b.confirmedInvite

    if (b.error) return { ...out, status: 'failed', error: b.error }

    if (b.phase === 'parse') {
      if (elapsed < this.stepMs / 2) return { ...out, status: 'queued', queuePosition: 1 }
      if (elapsed < this.stepMs) return { ...out, status: 'processing', step: 'Parsing' }
      b.parsedInvite = b.parsedInvite ?? structuredClone(fixture.brief.parsedInvite as ParsedInvite)
      return { ...out, parsedInvite: b.parsedInvite, status: 'awaiting_confirmation' }
    }

    if (b.phase === 'pipeline') {
      if (elapsed < this.stepMs / 2) return { ...out, status: 'queued', queuePosition: 1 }
      const index = Math.floor((elapsed - this.stepMs / 2) / this.stepMs)
      const failIndex = b.failAt ? PIPELINE.indexOf(b.failAt) : -1
      if (failIndex >= 0 && index >= failIndex) {
        b.error = { code: 'NO_PUBLIC_INFO', step: PIPELINE[failIndex], message: 'No public information was found for this company.' }
        return { ...out, status: 'failed', error: b.error }
      }
      if (index < PIPELINE.length) return { ...out, status: 'processing', step: PIPELINE[index] }
      b.phase = 'done'
      b.draft = structuredClone(fixture.brief.content as BriefContent)
      b.content = structuredClone(b.draft)
    }

    // done: ready or approved
    if (b.approved && b.rulesStatus === 'pending' && this.now() - (b.approvedAt ?? 0) >= this.stepMs) {
      b.ruleProposals = this.proposeRules(b)
      b.rulesStatus = b.ruleProposals.length ? 'ready' : 'none'
    }
    const status: BriefStatus = b.approved ? 'approved' : 'ready'
    return {
      ...out, ...base, rulesStatus: b.rulesStatus, status,
      research: fixture.brief.research as BriefView['research'],
      caseStudyMatches: fixture.brief.caseStudyMatches as BriefView['caseStudyMatches'],
      content: b.content,
      rulesApplied: (this.rules.get(b.owner) ?? []).slice(0, 10).map((r) => ({ ruleId: r.ruleId, text: r.text })),
      ruleProposals: b.ruleProposals,
    }
  }

  private proposeRules(b: MockBrief): RuleProposal[] {
    const before = JSON.stringify(b.draft?.discoveryQuestions ?? [])
    const after = JSON.stringify(b.content?.discoveryQuestions ?? [])
    const agendaChanged = JSON.stringify(b.draft?.agenda) !== JSON.stringify(b.content?.agenda)
    if (before === after && !agendaChanged) return []
    if (/budget/i.test(after) && !/budget cycle/i.test(before)) {
      return [{ proposalId: 'p1', text: 'Always ask about the budget cycle.', rationale: 'You added a budget question to the discovery list.' }]
    }
    return [{ proposalId: 'p1', text: 'Keep discovery questions short and specific.', rationale: 'You rewrote a discovery question.' }]
  }

  warningsFor(p: ParsedInvite): ParsedInvite['warnings'] {
    const warnings: NonNullable<ParsedInvite['warnings']> = []
    const domains = p.attendees.map((a) => a.email.split('@')[1]?.toLowerCase()).filter(Boolean) as string[]
    const nonFree = domains.filter((d) => !FREE_MAIL.has(d))
    if (domains.length && !nonFree.length) warnings.push('only_free_email_domains')
    const dom = p.company.domain?.toLowerCase()
    if (dom && nonFree.length && !nonFree.some((d) => d === dom || d.endsWith('.' + dom))) warnings.push('company_domain_mismatch')
    return warnings
  }

  confirmErrors(p: ParsedInvite, companyConfirmed: boolean): Array<{ code: string; message: string }> {
    const errors = []
    const domain = p.company.domain?.trim().toLowerCase() || null
    if (!p.company.name?.trim() && (!domain || FREE_MAIL.has(domain))) {
      errors.push({ code: 'COMPANY_REQUIRED', message: 'Add a company name or a company email domain.' })
    }
    if (p.attendees.length > 20) errors.push({ code: 'TOO_MANY_ATTENDEES', message: 'An invite can list at most 20 attendees.' })
    if (p.attendees.some((a) => !EMAIL_RE.test(a.email))) errors.push({ code: 'INVALID_EMAIL', message: 'An attendee email address is not valid.' })
    if (this.warningsFor(p)?.includes('company_domain_mismatch') && !companyConfirmed) {
      errors.push({ code: 'COMPANY_DOMAIN_MISMATCH', message: "The company name and the attendees' email domains do not match. Confirm which company is correct." })
    }
    return errors
  }

  startPipeline(b: MockBrief, invite: ParsedInvite) {
    b.confirmedInvite = invite
    b.parsedInvite = invite
    b.phase = 'pipeline'
    b.phaseStart = this.now()
  }

  addRule(owner: string, text: string) {
    const list = this.rules.get(owner) ?? []
    if (list.some((r) => r.text.toLowerCase() === text.toLowerCase())) return null
    const rule = { ruleId: ('01J' + (this.counter++).toString().padStart(23, '0')).slice(0, 26), text, createdAt: this.now() }
    this.rules.set(owner, [rule, ...list])
    return rule
  }
}
