import { useState } from 'react'
import { ApiError, type ApiClient } from '../api/client'
import type { BriefView } from '../api/types'
import { Button, Card, ErrorBanner, Pill } from '../components/ui'

export function ApproveDialog({ edited, onCancel, onApprove }: { edited: boolean; onCancel: () => void; onApprove: () => Promise<void> }) {
  const [busy, setBusy] = useState(false)
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="approve-h" className="fixed inset-0 z-50 grid place-items-center bg-navy/50 p-4">
      <Card className="w-full max-w-md p-6">
        <h2 id="approve-h" className="text-xl font-bold">Approve this brief?</h2>
        <p className="mt-3 text-sm text-muted">The brief will be locked and can no longer be edited.</p>
        <p className="mt-2 text-sm text-muted">
          {edited
            ? 'You changed the draft. We will suggest rules from your edits for your future briefs. You decide which to keep.'
            : 'You did not change the draft, so no rules will be suggested.'}
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" onClick={onCancel} disabled={busy}>Cancel</Button>
          <Button variant="success" disabled={busy} onClick={async () => { setBusy(true); await onApprove(); setBusy(false) }}>
            {busy ? 'Approving…' : 'Approve'}
          </Button>
        </div>
      </Card>
    </div>
  )
}

/** After approval: show the rules suggested from the SE's edits, each kept or discarded (R7.6 to R7.13). */
export function RulesReview({ view, api, onDone }: { view: BriefView; api: ApiClient; onDone: () => void }) {
  const proposals = view.ruleProposals ?? []
  // Proposals arrive after this panel first shows (while rules are checked), so a missing choice means "keep".
  const [choice, setKeep] = useState<Record<string, boolean>>({})
  const keep = (id: string) => choice[id] ?? true
  const [saved, setSaved] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const frame = (body: React.ReactNode) => (
    <Card className="border-l-4 border-l-ok p-5">
      <div className="flex items-center gap-3">
        <Pill tone="green">✓ Approved</Pill>
        <h2 className="font-bold">Learn from your edits</h2>
      </div>
      <div className="mt-3">{body}</div>
    </Card>
  )

  if (saved !== null) {
    return frame(<p className="text-sm">{saved === 0 ? 'No rules saved.' : `Saved ${saved} rule${saved > 1 ? 's' : ''}. It will be applied to your next briefs.`}</p>)
  }
  if (view.rulesStatus === 'pending') {
    return frame(<p role="status" className="animate-pulse text-sm text-muted">Checking your edits for reusable rules…</p>)
  }
  if (view.rulesStatus === 'failed') {
    return frame(<p className="text-sm text-muted">Rules could not be checked this time. The brief is approved.</p>)
  }
  if (view.rulesStatus === 'none' || proposals.length === 0) {
    return frame(<p className="text-sm text-muted">No rules suggested. The brief is approved and locked.</p>)
  }

  return frame(
    <>
      <p className="text-sm text-muted">Kept rules are applied to your next briefs. Only you see your rules.</p>
      <ul className="mt-4 space-y-3">
        {proposals.map((p) => (
          <li key={p.proposalId} data-testid="rule-proposal" className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-blue-200 bg-brand-soft/40 px-4 py-3">
            <div>
              <p className="font-semibold">&ldquo;{p.text}&rdquo;</p>
              <p className="text-xs text-muted">Why: {p.rationale}</p>
            </div>
            <div role="group" aria-label={`Keep or discard: ${p.text}`} className="flex gap-2">
              <Button variant={keep(p.proposalId) ? 'secondary' : 'primary'} onClick={() => setKeep((k) => ({ ...k, [p.proposalId]: false }))}
                      aria-pressed={!keep(p.proposalId)}>Discard</Button>
              <Button variant={keep(p.proposalId) ? 'primary' : 'secondary'} onClick={() => setKeep((k) => ({ ...k, [p.proposalId]: true }))}
                      aria-pressed={keep(p.proposalId)}>Keep rule</Button>
            </div>
          </li>
        ))}
      </ul>
      {error && <div className="mt-3"><ErrorBanner message={error} /></div>}
      <div className="mt-4 flex justify-end">
        <Button disabled={busy} onClick={async () => {
          setBusy(true)
          try {
            const res = await api.decideRules(view.briefId, proposals.map((p) => ({ proposalId: p.proposalId, keep: keep(p.proposalId) })))
            setSaved(res.saved.length)
            onDone()
          } catch (e) {
            setError(e instanceof ApiError ? e.message : 'Could not save your choices.')
          } finally {
            setBusy(false)
          }
        }}>Save choices</Button>
      </div>
    </>,
  )
}
