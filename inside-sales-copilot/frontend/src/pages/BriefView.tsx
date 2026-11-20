import { useMemo, useState, type ReactNode } from 'react'
import { ApiError, type ApiClient } from '../api/client'
import type { BriefContent, BriefView as View } from '../api/types'
import { AttendeeBadge, Button, Card, EditableText, ErrorBanner, Pill, SourceChip } from '../components/ui'
import { buildSourceIndex, longDate, sourceFor } from '../lib/format'
import { ApproveDialog, RulesReview } from './RulesReview'

const SECTIONS = [
  ['snapshot', 'Company snapshot'],
  ['attendees', 'Attendees'],
  ['pain', 'Pain-point hypotheses'],
  ['agenda', 'Agenda (30 min)'],
  ['questions', 'Discovery questions'],
  ['cases', 'Case studies'],
  ['sources', 'Sources'],
] as const

function Section({ id, n, title, tag, children }: { id: string; n: number; title: string; tag?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="scroll-mt-20 border-b border-line px-6 py-6 last:border-0">
      <div className="mb-4 flex items-center justify-between gap-4">
        <h2 id={`${id}-h`} className="text-lg font-bold">{n}. {title}</h2>
        {tag}
      </div>
      {children}
    </section>
  )
}

const AI_TAG = <Pill tone="purple">AI draft · click a line to edit</Pill>

export function BriefView({ view, api, setView, onRefresh }: { view: View; api: ApiClient; setView: (v: View) => void; onRefresh: () => void }) {
  const content = view.content!
  const research = view.research
  const sources = useMemo(() => buildSourceIndex(view), [view])
  const editable = view.status === 'ready'
  const [approving, setApproving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scores = new Map((view.caseStudyMatches?.matches ?? []).map((m) => [m.caseStudyId, m.score]))
  const invite = view.confirmedInvite ?? view.parsedInvite
  const unverified = content.attendees.filter((a) => a.status !== 'verified').length

  async function save(mutate: (c: BriefContent) => void) {
    const next = structuredClone(content)
    mutate(next)
    try {
      setView(await api.saveContent(view.briefId, next, view.version))
    } catch (e) {
      throw new Error(e instanceof ApiError ? e.message : 'Could not save the change.')
    }
  }

  const tierItem = content.companySnapshot.find((i) => i.text.startsWith('Size tier:'))
  const news = content.companySnapshot.filter((i) => i.text.startsWith('Recent news:'))
  const unknown = content.companySnapshot.filter((i) => i.text.startsWith('Unknown'))
  const facts = content.companySnapshot.filter((i) => i !== tierItem && !news.includes(i) && !unknown.includes(i))
  const tier = research?.sizeTier

  return (
    <main className="mx-auto max-w-7xl px-6 py-6">
      {/* title bar */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold">{research?.company.name ?? invite?.company.name}</h1>
            {tier && <Pill tone="blue">{tier.tier}</Pill>}
            {view.status === 'approved' ? <Pill tone="green">✓ Approved</Pill> : <Pill tone="grey">Draft</Pill>}
          </div>
          <p className="mt-1 text-sm text-muted">
            {invite?.subject ?? 'Discovery call'} · {longDate(invite?.meetingDate)} · 30 min · {research?.company.domain}
            {research?.company.matchConfidence === 'unverified_match' ? ' · company match not confirmed' : ' · company match confirmed'}
          </p>
        </div>
        <div className="flex gap-2">
          {editable && <Button variant="success" onClick={() => setApproving(true)}>Approve brief</Button>}
        </div>
      </div>
      {error && <div className="mt-4"><ErrorBanner message={error} /></div>}
      {view.status === 'approved' && <div className="mt-4"><RulesReview view={view} api={api} onDone={onRefresh} /></div>}

      <div className="mt-6 grid gap-6 lg:grid-cols-[13rem_minmax(0,1fr)_18rem]">
        {/* section nav */}
        <nav aria-label="Brief sections" className="hidden lg:block">
          <Card className="sticky top-4 p-3 text-sm">
            {SECTIONS.map(([id, label]) => (
              <a key={id} href={`#${id}`} className="flex items-center justify-between rounded-md px-3 py-2 hover:bg-brand-soft">
                <span>{label}</span>
                {id === 'attendees' && unverified > 0 && <span className="text-xs font-semibold text-warn">{unverified} ⚠</span>}
                {id === 'cases' && <span className="text-xs text-muted">{content.caseStudies.length}</span>}
                {id === 'sources' && <span className="text-xs text-muted">{content.sources.length}</span>}
              </a>
            ))}
            {view.rulesApplied && view.rulesApplied.length > 0 && (
              <div className="mt-3 border-t border-line px-3 pt-3 text-xs text-muted">
                <p className="font-semibold text-ink">Your rules applied ({view.rulesApplied.length})</p>
                {view.rulesApplied.map((r) => <p key={r.ruleId} className="mt-1">• {r.text}</p>)}
              </div>
            )}
          </Card>
        </nav>

        {/* the brief */}
        <Card>
          <Section id="snapshot" n={1} title="Company snapshot">
            {tier && (
              <div data-testid="size-tier" className="mb-4 rounded-lg border border-blue-200 bg-brand-soft/60 px-4 py-3">
                <div className="flex flex-wrap items-center gap-1">
                  <span className="font-bold">Size tier: {tier.tier}</span>
                  {tier.basis.sourceUrls.map((u) => <SourceChip key={u} source={sourceFor(sources, u)} />)}
                </div>
                <p className="mt-1 text-sm text-muted">Rule used: {tier.rule.replace(/^[A-Za-z-]+: /, '')}</p>
              </div>
            )}
            <ul className="space-y-2.5">
              {facts.map((item) => (
                <li key={item.id} className="flex gap-2">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
                  <div className="flex-1">
                    <EditableText label={`snapshot item ${item.id}`} value={item.text} disabled={!editable}
                                  onSave={(t) => save((c) => { c.companySnapshot.find((x) => x.id === item.id)!.text = t })} />
                    <div>{item.sourceUrls.map((u) => <SourceChip key={u} source={sourceFor(sources, u)} />)}</div>
                  </div>
                </li>
              ))}
            </ul>
            {news.length > 0 && (
              <>
                <h3 className="mt-5 text-xs font-bold uppercase tracking-wide text-muted">Recent news</h3>
                <ul className="mt-2 space-y-2">
                  {news.map((item) => (
                    <li key={item.id} className="text-sm">
                      {item.text.replace(/^Recent news: /, '')}
                      {item.sourceUrls.map((u) => <SourceChip key={u} source={sourceFor(sources, u)} />)}
                    </li>
                  ))}
                </ul>
              </>
            )}
            {unknown.map((item) => <p key={item.id} className="mt-4 rounded-md bg-page px-3 py-2 text-sm text-muted">{item.text}</p>)}
          </Section>

          <Section id="attendees" n={2} title="Attendees">
            <ul className="space-y-2">
              {content.attendees.map((a) => (
                <li key={a.email} data-testid="attendee" className={`flex flex-wrap items-center justify-between gap-3 rounded-lg px-4 py-3 ${a.status === 'verified' ? 'bg-ok-soft/60' : 'border border-warn-line bg-warn-soft/60'}`}>
                  <div>
                    <p className="font-semibold">{a.name}</p>
                    <p className="text-sm text-muted">{a.status === 'verified' ? a.title : <>Invite says: &ldquo;{a.title ?? 'no title'}&rdquo;</>}</p>
                  </div>
                  <AttendeeBadge attendee={a} />
                </li>
              ))}
            </ul>
            {unverified > 0 && <p className="mt-3 text-xs text-muted">Unverified roles are not used as facts anywhere in this brief. Confirm them on the call.</p>}
          </Section>

          <Section id="pain" n={3} title="Pain-point hypotheses" tag={AI_TAG}>
            <ul className="space-y-3">
              {content.painPointHypotheses.map((h) => (
                <li key={h.id} className="rounded-lg border border-line px-4 py-3">
                  <EditableText label={`hypothesis ${h.id}`} value={h.text} disabled={!editable}
                                onSave={(t) => save((c) => { c.painPointHypotheses.find((x) => x.id === h.id)!.text = t })} />
                  {h.sourceUrls.length > 0 && <div className="mt-1 text-xs text-muted">Based on: {h.sourceUrls.map((u) => <SourceChip key={u} source={sourceFor(sources, u)} />)}</div>}
                </li>
              ))}
            </ul>
          </Section>

          <Section id="agenda" n={4} title="Agenda (30 min)" tag={AI_TAG}>
            <ol className="space-y-2">
              {content.agenda.map((a) => (
                <li key={a.id} className="flex gap-4 rounded-lg bg-page/70 px-4 py-3">
                  <span className="w-14 shrink-0 font-bold text-brand">{a.minutes} min</span>
                  <div className="flex-1">
                    <p className="font-semibold">{a.topic}</p>
                    <div className="text-sm text-muted">
                      <EditableText label={`agenda note ${a.id}`} value={a.note} disabled={!editable}
                                    onSave={(t) => save((c) => { c.agenda.find((x) => x.id === a.id)!.note = t })} />
                    </div>
                  </div>
                </li>
              ))}
            </ol>
            <p className="mt-2 text-right text-xs text-muted">Total {content.agenda.reduce((s, a) => s + a.minutes, 0)} min</p>
          </Section>

          <Section id="questions" n={5} title="Discovery questions" tag={AI_TAG}>
            <ol className="space-y-2">
              {content.discoveryQuestions.map((q, i) => (
                <li key={q.id} className="flex gap-3">
                  <span className="w-6 shrink-0 pt-0.5 text-right font-semibold text-muted">{i + 1}.</span>
                  <div className="flex-1">
                    <EditableText label={`question ${i + 1}`} value={q.text} disabled={!editable}
                                  onSave={(t) => save((c) => { c.discoveryQuestions.find((x) => x.id === q.id)!.text = t })} />
                  </div>
                </li>
              ))}
            </ol>
            {editable && (
              <Button variant="link" className="mt-3 text-sm" onClick={() =>
                save((c) => { c.discoveryQuestions.push({ id: `new-${Date.now()}`, text: 'New question (click to edit)' }) }).catch((e) => setError(e.message))}>
                + Add question
              </Button>
            )}
          </Section>

          <Section id="cases" n={6} title="Case studies to mention">
            {content.caseStudies.length > 0 ? (
              <div className="grid gap-4 md:grid-cols-3">
                {content.caseStudies.map((cs) => (
                  <div key={cs.caseStudyId} data-testid="case-study" className="flex flex-col rounded-lg border border-line p-4">
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="font-semibold leading-snug">{cs.title}</h3>
                      <span title="Relevance score (0 to 100)" className="shrink-0 rounded-full bg-ok-soft px-2 py-0.5 text-xs font-bold text-ok">{scores.get(cs.caseStudyId) ?? '–'}</span>
                    </div>
                    <p className="mt-2 flex-1 text-sm text-muted"><span className="font-semibold text-ink">Why: </span>{cs.reason}</p>
                    <a href={cs.url} target="_blank" rel="noopener noreferrer" className="mt-3 text-sm font-semibold text-brand hover:underline">Open case study ↗</a>
                  </div>
                ))}
              </div>
            ) : null}
            {content.caseStudiesNote && <p className="mt-3 rounded-md bg-warn-soft px-3 py-2 text-sm text-warn">{content.caseStudiesNote}</p>}
          </Section>

          <Section id="sources" n={7} title="Sources">
            <ul className="space-y-1.5 text-sm">
              {content.sources.map((s) => {
                const info = sourceFor(sources, s.url)
                return (
                  <li key={s.url}>
                    <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-brand hover:underline">{info.title}</a>
                  </li>
                )
              })}
            </ul>
          </Section>
        </Card>

        {/* right rail */}
        <aside className="hidden lg:block">
          <Card className="sticky top-4 p-4">
            <h2 className="font-bold">Sources ({content.sources.length})</h2>
            <ul className="mt-3 space-y-2">
              {content.sources.map((s) => {
                const info = sourceFor(sources, s.url)
                const tone = info.kind === 'news' ? 'bg-amber-50' : info.kind === 'casestudy' ? 'bg-emerald-50' : 'bg-blue-50'
                return (
                  <li key={s.url}>
                    <a href={s.url} target="_blank" rel="noopener noreferrer" className={`block rounded-lg px-3 py-2 text-xs hover:underline ${tone}`}>
                      <span className="block font-semibold text-ink">{info.chip}</span>
                      <span className="line-clamp-2 text-muted">{info.title}</span>
                    </a>
                  </li>
                )
              })}
            </ul>
            <p className="mt-4 text-xs text-muted">Every fact in the brief links to one of these pages.</p>
          </Card>
        </aside>
      </div>

      {approving && (
        <ApproveDialog edited={view.version > 0} onCancel={() => setApproving(false)} onApprove={async () => {
          try {
            await api.approve(view.briefId)
            setApproving(false)
            onRefresh()
          } catch (e) {
            setApproving(false)
            setError(e instanceof ApiError ? e.message : 'Could not approve the brief.')
          }
        }} />
      )}
    </main>
  )
}
