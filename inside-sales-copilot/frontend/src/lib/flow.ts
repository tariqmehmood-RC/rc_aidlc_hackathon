// Small pure helpers shared by pages and tests.
import { STEPS, type BriefView, type ParsedInvite, type Step } from '../api/types'

export const MAX_INVITE = 10_000
export const MAX_ATTENDEES = 20

export function inviteKey(briefId: string) {
  return `isc.invite.${briefId}`
}

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const DOMAIN_RE = /^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$/
const FREE_MAIL = new Set(['gmail.com', 'outlook.com', 'yahoo.com', 'hotmail.com', 'icloud.com', 'proton.me', 'aol.com'])

/** The checks the server also makes (R2.7 to R2.11), shown before the request is sent. */
export function validateInvite(p: ParsedInvite): string[] {
  const problems: string[] = []
  const domain = (p.company.domain ?? '').trim().toLowerCase()
  if (!p.company.name?.trim() && (!domain || FREE_MAIL.has(domain))) problems.push('Add a company name or a company email domain (a free mail domain does not count).')
  if (domain && !DOMAIN_RE.test(domain)) problems.push('The company domain is not a valid domain name.')
  if (p.attendees.length > MAX_ATTENDEES) problems.push(`An invite can list at most ${MAX_ATTENDEES} attendees.`)
  p.attendees.forEach((a, i) => {
    if (!EMAIL_RE.test(a.email.trim())) problems.push(`Attendee ${i + 1}: the email address is not valid.`)
    if (!a.name.trim()) problems.push(`Attendee ${i + 1}: add a name.`)
  })
  if (p.meetingDate && !/^\d{4}-\d{2}-\d{2}$/.test(p.meetingDate)) problems.push('The meeting date must be YYYY-MM-DD.')
  return problems
}

export type StepState = 'done' | 'current' | 'pending' | 'failed'

/** Each step's state, from what the API reports (status, step, and whether the invite was confirmed). */
export function stepStates(view: BriefView): Record<Step, StepState> {
  const out = Object.fromEntries(STEPS.map((s) => [s, 'pending'])) as Record<Step, StepState>
  const confirmed = Boolean(view.confirmedInvite)
  let current: Step | null = null
  if (view.status === 'processing' && view.step) current = view.step
  if (view.status === 'failed') current = view.error?.step ?? (confirmed ? 'Researching' : 'Parsing')
  if (view.status === 'queued' && confirmed) out.Parsing = 'done'
  if (current) {
    const idx = STEPS.indexOf(current)
    STEPS.forEach((s, i) => {
      if (i < idx) out[s] = 'done'
    })
    out[current] = view.status === 'failed' ? 'failed' : 'current'
  }
  return out
}
