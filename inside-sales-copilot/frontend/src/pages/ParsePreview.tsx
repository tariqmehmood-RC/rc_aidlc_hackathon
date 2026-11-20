import { useState } from 'react'
import { ApiError, type ApiClient } from '../api/client'
import type { Attendee, BriefView, ParsedInvite } from '../api/types'
import { Button, Card, ErrorBanner, Pill } from '../components/ui'
import { inviteKey, MAX_ATTENDEES, validateInvite } from '../lib/flow'

const empty = (v: string) => (v.trim() ? v.trim() : null)

export function ParsePreview({ view, api, onConfirmed }: { view: BriefView; api: ApiClient; onConfirmed: () => void }) {
  const [invite, setInvite] = useState<ParsedInvite>(() => structuredClone(view.parsedInvite!))
  const [confirmedCompany, setConfirmedCompany] = useState(false)
  const [busy, setBusy] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)
  const [mismatch, setMismatch] = useState(view.parsedInvite?.warnings?.includes('company_domain_mismatch') ?? false)
  const original = sessionStorage.getItem(inviteKey(view.briefId))
  const problems = validateInvite(invite)
  const freeOnly = invite.warnings?.includes('only_free_email_domains')

  const set = (patch: Partial<ParsedInvite>) => setInvite((p) => ({ ...p, ...patch }))
  const setCompany = (patch: Partial<ParsedInvite['company']>) => setInvite((p) => ({ ...p, company: { ...p.company, ...patch } }))
  const setAttendee = (i: number, patch: Partial<Attendee>) =>
    setInvite((p) => ({ ...p, attendees: p.attendees.map((a, j) => (j === i ? { ...a, ...patch } : a)) }))

  async function start() {
    setBusy(true)
    setServerError(null)
    try {
      // Save the corrections first; the server recomputes the warnings from the edited data.
      const saved = await api.saveParsedInvite(view.briefId, invite)
      const nowMismatch = saved.parsedInvite?.warnings?.includes('company_domain_mismatch') ?? false
      setMismatch(nowMismatch)
      if (nowMismatch && !confirmedCompany) {
        setServerError('The company name and the attendees\u2019 email domains do not match. Tick "I confirm the company" to continue.')
        return
      }
      await api.confirm(view.briefId, saved.parsedInvite ?? invite, confirmedCompany)
      onConfirmed()
    } catch (e) {
      setServerError(e instanceof ApiError ? e.message : 'Could not start research.')
    } finally {
      setBusy(false)
    }
  }

  const input = 'mt-1 w-full rounded-lg border border-line px-3 py-2 text-sm outline-none focus:border-brand'
  return (
    <main className="mx-auto max-w-7xl px-6 py-8">
      <h1 className="text-2xl font-bold">Check what we read</h1>
      <p className="mt-1 text-muted">Step 2 of 2: fix anything that is wrong. Nothing is researched until you click Start research.</p>
      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <Card className="p-6">
          <h2 className="font-semibold">Pasted invite</h2>
          <pre className="mt-3 max-h-[34rem] overflow-auto whitespace-pre-wrap rounded-lg bg-page p-4 font-mono text-[13px] leading-relaxed text-ink">
            {original ?? 'The original text is shown only in the tab where it was pasted.'}
          </pre>
        </Card>
        <Card className="p-6">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">What we read</h2>
            <Pill tone="purple">AI extracted · please check</Pill>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-4">
            <label className="text-xs font-medium text-muted">Company
              <input aria-label="Company" className={input} value={invite.company.name ?? ''} onChange={(e) => setCompany({ name: empty(e.target.value) })} />
            </label>
            <label className="text-xs font-medium text-muted">Company domain
              <input aria-label="Company domain" className={input} value={invite.company.domain ?? ''} onChange={(e) => setCompany({ domain: empty(e.target.value.toLowerCase()) })} />
            </label>
            <label className="text-xs font-medium text-muted">Meeting date (optional)
              <input aria-label="Meeting date" type="date" className={input} value={invite.meetingDate ?? ''} onChange={(e) => set({ meetingDate: empty(e.target.value) })} />
            </label>
            <label className="text-xs font-medium text-muted">Subject
              <input aria-label="Subject" className={input} value={invite.subject ?? ''} onChange={(e) => set({ subject: empty(e.target.value) })} />
            </label>
          </div>

          <div className="mt-6 flex items-center justify-between">
            <h3 className="text-sm font-semibold">Attendees ({invite.attendees.length})</h3>
            <span className="text-xs text-muted">Attendee data is synthetic in demos</span>
          </div>
          <table className="mt-2 w-full text-sm">
            <thead><tr className="bg-page text-left text-xs text-muted"><th className="p-2">Name</th><th className="p-2">Title</th><th className="p-2">Email</th><th className="w-8" /></tr></thead>
            <tbody>
              {invite.attendees.map((a, i) => (
                <tr key={i} className="border-b border-line">
                  <td className="p-1"><input aria-label={`Attendee ${i + 1} name`} className={input + ' mt-0'} value={a.name} onChange={(e) => setAttendee(i, { name: e.target.value })} /></td>
                  <td className="p-1"><input aria-label={`Attendee ${i + 1} title`} className={input + ' mt-0'} value={a.title ?? ''} placeholder="(no title)" onChange={(e) => setAttendee(i, { title: empty(e.target.value) })} /></td>
                  <td className="p-1"><input aria-label={`Attendee ${i + 1} email`} className={input + ' mt-0'} value={a.email} onChange={(e) => setAttendee(i, { email: e.target.value.trim() })} /></td>
                  <td className="p-1 text-center">
                    <button type="button" aria-label={`Remove attendee ${i + 1}`} className="text-muted hover:text-bad" onClick={() => set({ attendees: invite.attendees.filter((_, j) => j !== i) })}>✕</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Button variant="link" className="mt-2 text-sm" disabled={invite.attendees.length >= MAX_ATTENDEES}
                  onClick={() => set({ attendees: [...invite.attendees, { name: '', title: null, email: '' }] })}>+ Add attendee</Button>

          <label className="mt-5 block text-xs font-medium text-muted">Notes (used for research and case study matching)
            <textarea aria-label="Notes" rows={3} className={input} value={invite.notes ?? ''} onChange={(e) => set({ notes: empty(e.target.value) })} />
          </label>

          {freeOnly && (
            <div className="mt-4 rounded-lg border border-warn-line bg-warn-soft px-4 py-3 text-sm text-warn">
              Only free email addresses were found. Add the company name or the company domain.
            </div>
          )}
          {mismatch && (
            <div className="mt-4 rounded-lg border border-warn-line bg-warn-soft px-4 py-3 text-sm text-warn">
              <p className="font-semibold">The company name and the attendees&apos; email domains do not match.</p>
              <label className="mt-2 flex items-center gap-2">
                <input type="checkbox" checked={confirmedCompany} onChange={(e) => setConfirmedCompany(e.target.checked)} />
                I confirm the company is correct
              </label>
            </div>
          )}
          {problems.length > 0 && (
            <ul aria-label="Problems to fix" className="mt-4 list-disc space-y-1 pl-5 text-sm text-bad">
              {problems.map((p) => <li key={p}>{p}</li>)}
            </ul>
          )}
          {serverError && <div className="mt-4"><ErrorBanner message={serverError} /></div>}
          <div className="mt-6 flex items-center justify-end gap-3">
            <Button onClick={start} disabled={busy || problems.length > 0}>{busy ? 'Starting…' : 'Start research'}</Button>
          </div>
        </Card>
      </div>
    </main>
  )
}
