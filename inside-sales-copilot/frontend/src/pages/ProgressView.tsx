import { useEffect, useState } from 'react'
import { STEPS, type BriefView, type Step } from '../api/types'
import { Button, Card } from '../components/ui'
import { stepStates } from '../lib/flow'

const LABEL: Record<Step, string> = {
  Parsing: 'Parsing',
  Researching: 'Researching',
  'Checking attendees': 'Checking attendees',
  'Matching case studies': 'Matching case studies',
  'Writing brief': 'Writing brief',
}
const DETAIL: Record<Step, string> = {
  Parsing: 'Reading the invite',
  Researching: 'Company website, Wikipedia, and recent news',
  'Checking attendees': 'Employer and title against the profile directory',
  'Matching case studies': 'Scoring case studies from your business unit',
  'Writing brief': 'Agenda, questions, and hypotheses',
}

export function ProgressView({ view, onRetry, companyHint }: { view: BriefView; onRetry: () => void; companyHint?: string | null }) {
  const [started] = useState(() => Date.now())
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  const elapsed = Math.floor((now - started) / 1000)
  const states = stepStates(view)
  const company = companyHint ?? view.confirmedInvite?.company.name ?? view.parsedInvite?.company.name
  const failed = view.status === 'failed'

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <Card className="p-8">
        <h1 className="text-2xl font-bold">{failed ? 'The brief could not be finished' : `Preparing your brief${company ? ` for ${company}` : ''}`}</h1>
        <p className="mt-1 text-muted">
          {failed ? 'Finished steps are kept, so a retry continues where it stopped.' : 'Usually under a minute. You can leave this page; the brief keeps building.'}
        </p>

        {view.status === 'queued' && (
          <div role="status" className="mt-6 rounded-lg bg-brand-soft px-4 py-3 text-sm text-brand-dark">
            Queued{view.queuePosition ? ` · position ${view.queuePosition} in line` : ''}. Another brief may be in progress.
          </div>
        )}

        <ol aria-label="Progress" className="mt-6 space-y-1">
          {STEPS.map((s, i) => {
            const st = states[s]
            return (
              <li key={s} data-state={st} className="relative flex gap-4 pb-5">
                {i < STEPS.length - 1 && <span aria-hidden className={`absolute left-[15px] top-8 h-[calc(100%-1.5rem)] w-0.5 ${st === 'done' ? 'bg-ok' : 'bg-line'}`} />}
                <span aria-hidden className={`z-10 grid h-8 w-8 shrink-0 place-items-center rounded-full text-sm font-bold ${
                  st === 'done' ? 'bg-ok text-white' : st === 'current' ? 'border-[3px] border-brand bg-white text-brand' : st === 'failed' ? 'bg-bad text-white' : 'border-2 border-line bg-white text-muted'}`}>
                  {st === 'done' ? '✓' : st === 'failed' ? '!' : i + 1}
                </span>
                <div className="pt-1">
                  <p className={`font-semibold ${st === 'pending' ? 'text-muted' : st === 'current' ? 'text-brand' : st === 'failed' ? 'text-bad' : ''}`}>
                    {LABEL[s]}{st === 'current' && <span className="ml-2 animate-pulse text-xs font-normal">in progress…</span>}
                  </p>
                  <p className="text-xs text-muted">{DETAIL[s]}</p>
                </div>
              </li>
            )
          })}
        </ol>

        {failed && (
          <div role="alert" className="mt-2 flex items-center justify-between gap-4 rounded-lg border border-red-200 bg-bad-soft px-4 py-3 text-sm text-bad">
            <span><strong>Stopped at {view.error?.step ?? 'a step'}:</strong> {view.error?.message}</span>
            <Button variant="danger" onClick={onRetry}>Retry</Button>
          </div>
        )}
        {!failed && (
          <p className="text-xs text-muted">
            Elapsed {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, '0')}
            {elapsed > 60 && ' · Taking longer than usual. It stops automatically after 2 minutes without progress.'}
          </p>
        )}
      </Card>
    </main>
  )
}
