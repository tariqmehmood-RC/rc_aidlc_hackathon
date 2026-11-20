import { useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ErrorBanner } from '../components/ui'
import { useBriefPolling } from '../hooks/useBriefPolling'
import { BriefView } from './BriefView'
import { ParsePreview } from './ParsePreview'
import { ProgressView } from './ProgressView'

/** One URL per brief. What it shows depends on the brief's status. */
export function BriefPage({ pollMs }: { pollMs?: number }) {
  const { id = '' } = useParams()
  const { api } = useAuth()
  const { view, error, refresh, setView } = useBriefPolling(api, id, pollMs)

  if (error && !view) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-10">
        <ErrorBanner message={error.status === 404 ? 'This brief was not found.' : error.message} onRetry={error.status === 404 ? undefined : refresh} />
      </main>
    )
  }
  if (!view) return <main className="mx-auto max-w-3xl px-6 py-10 text-muted" role="status">Loading…</main>

  switch (view.status) {
    case 'awaiting_confirmation':
      return <ParsePreview key={view.briefId} view={view} api={api} onConfirmed={refresh} />
    case 'ready':
    case 'approved':
      return <BriefView view={view} api={api} setView={setView} onRefresh={refresh} />
    default:
      return <ProgressView view={view} onRetry={async () => { await api.retry(view.briefId); refresh() }} />
  }
}
