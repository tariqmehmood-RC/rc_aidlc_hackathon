import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Button, Card, ErrorBanner } from '../components/ui'
import { inviteKey, MAX_INVITE } from '../lib/flow'

export function NewBriefPage() {
  const { api } = useAuth()
  const navigate = useNavigate()
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const tooLong = text.length > MAX_INVITE
  const empty = !text.trim()

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const { briefId } = await api.createBrief(text)
      // Kept only in this browser tab, so the preview can show the original text next to what was read.
      sessionStorage.setItem(inviteKey(briefId), text)
      navigate(`/briefs/${briefId}`)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not start the brief.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto max-w-4xl px-6 py-8">
      <h1 className="text-2xl font-bold">New discovery brief</h1>
      <p className="mt-1 text-muted">Step 1 of 2: paste the meeting invite. You will check what we read before any research starts.</p>
      <Card className="mt-6 p-6">
        <label htmlFor="invite" className="text-sm font-semibold">Meeting invite</label>
        <textarea id="invite" value={text} onChange={(e) => setText(e.target.value)} rows={16}
                  placeholder={'Subject: Discovery call - Company - topic\nDate: ...\nCompany: Company name (company.com)\n\nAttendees:\n- Name, Title, email@company.com\n\nNotes: ...'}
                  className={`mt-2 w-full rounded-lg border bg-page/50 p-4 font-mono text-sm leading-relaxed outline-none focus:border-brand ${tooLong ? 'border-bad' : 'border-line'}`} />
        <div className="mt-3 flex items-center justify-between gap-4">
          <div className="text-xs">
            <span data-testid="char-count" className={tooLong ? 'font-semibold text-bad' : 'text-muted'}>
              {text.length.toLocaleString()} / {MAX_INVITE.toLocaleString()} characters
            </span>
            {tooLong && <span className="ml-2 text-bad">The invite can be at most 10,000 characters.</span>}
            <p className="mt-1 text-muted">Demo attendee data is synthetic. Do not paste customer data.</p>
          </div>
          <Button onClick={submit} disabled={busy || empty || tooLong}>{busy ? 'Sending…' : 'Read invite'}</Button>
        </div>
        {error && <div className="mt-4"><ErrorBanner message={error} /></div>}
      </Card>
    </main>
  )
}
