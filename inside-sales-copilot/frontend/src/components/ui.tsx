import { useState, type ReactNode } from 'react'
import type { BriefAttendee } from '../api/types'
import { REASON_LABEL, shortDate, type SourceInfo } from '../lib/format'

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-line bg-white shadow-sm ${className}`}>{children}</div>
}

export function Button({ children, variant = 'primary', className = '', ...props }:
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'success' | 'danger' | 'link' }) {
  const styles = {
    primary: 'bg-brand text-white hover:bg-brand-dark disabled:bg-brand/40',
    secondary: 'border border-line bg-white text-ink hover:bg-page disabled:text-muted',
    success: 'bg-ok text-white hover:brightness-95 disabled:opacity-50',
    danger: 'bg-bad text-white hover:brightness-95',
    link: 'text-brand hover:underline px-0 py-0',
  }[variant]
  const pad = variant === 'link' ? '' : 'px-4 py-2'
  return (
    <button type="button" className={`${pad} rounded-lg text-sm font-semibold transition disabled:cursor-not-allowed ${styles} ${className}`} {...props}>
      {children}
    </button>
  )
}

export function Pill({ children, tone = 'blue', title }: { children: ReactNode; tone?: 'blue' | 'green' | 'amber' | 'grey' | 'purple' | 'red'; title?: string }) {
  const styles = {
    blue: 'bg-brand-soft text-brand-dark',
    green: 'bg-ok-soft text-ok',
    amber: 'bg-warn-soft text-warn border border-warn-line',
    grey: 'bg-page text-muted border border-line',
    purple: 'bg-violet-50 text-violet-700',
    red: 'bg-bad-soft text-bad',
  }[tone]
  return <span title={title} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${styles}`}>{children}</span>
}

/** A link to the page a fact came from, labelled with the source name (never the raw URL). */
export function SourceChip({ source }: { source: SourceInfo }) {
  const tone = source.kind === 'news' ? 'border-amber-300 bg-amber-50 text-amber-800' : source.kind === 'casestudy'
    ? 'border-emerald-300 bg-emerald-50 text-emerald-800' : 'border-blue-200 bg-blue-50 text-brand-dark'
  return (
    <a href={source.url} target="_blank" rel="noopener noreferrer" title={source.title}
       className={`ml-1.5 inline-flex max-w-[16rem] items-center gap-1 truncate rounded-full border px-2 py-0.5 align-middle text-[11px] font-semibold hover:underline ${tone}`}>
      <span aria-hidden>↗</span>
      <span className="truncate">{source.chip}{source.date ? ` · ${shortDate(source.date)}` : ''}</span>
      <span className="sr-only">(source: {source.title})</span>
    </a>
  )
}

export function AttendeeBadge({ attendee }: { attendee: BriefAttendee }) {
  if (attendee.status === 'verified') return <Pill tone="green">✓ Verified</Pill>
  const reason = attendee.reason ? REASON_LABEL[attendee.reason] : 'Not verified'
  return <Pill tone="amber" title={reason}>⚠ Unverified · {reason}</Pill>
}

/** Click to edit a line in place. Saves through onSave, which may reject with a message. */
export function EditableText({ value, onSave, disabled, label }:
  { value: string; onSave: (next: string) => Promise<void>; disabled?: boolean; label: string }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!editing) {
    return (
      <button type="button" disabled={disabled} aria-label={`Edit ${label}`} onClick={() => { setDraft(value); setEditing(true); setError(null) }}
              className={`w-full rounded-md px-1 -mx-1 text-left ${disabled ? 'cursor-default' : 'hover:bg-brand-soft/60'}`}>
        {value}
      </button>
    )
  }
  return (
    <div className="space-y-1.5">
      <textarea aria-label={label} value={draft} autoFocus rows={2} maxLength={400} onChange={(e) => setDraft(e.target.value)}
                className="w-full rounded-md border-2 border-brand bg-white p-2 text-sm outline-none" />
      {error && <p role="alert" className="text-xs text-bad">{error}</p>}
      <div className="flex gap-2">
        <Button disabled={saving || !draft.trim()} onClick={async () => {
          setSaving(true)
          setError(null)
          try {
            await onSave(draft.trim())
            setEditing(false)
          } catch (e) {
            setError(e instanceof Error ? e.message : 'Could not save.')
          } finally {
            setSaving(false)
          }
        }}>{saving ? 'Saving…' : 'Save'}</Button>
        <Button variant="secondary" onClick={() => setEditing(false)}>Cancel</Button>
      </div>
    </div>
  )
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-center justify-between gap-4 rounded-lg border border-red-200 bg-bad-soft px-4 py-3 text-sm text-bad">
      <span>{message}</span>
      {onRetry && <Button variant="danger" onClick={onRetry}>Retry</Button>}
    </div>
  )
}
