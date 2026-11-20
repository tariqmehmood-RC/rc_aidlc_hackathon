import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, type ApiClient } from '../api/client'
import type { BriefView } from '../api/types'

export const POLL_MS = 2000

/** Keep polling while the brief is being built, or while rules are being checked (R9.5, R9.6). */
export function shouldPoll(view: BriefView | null): boolean {
  if (!view) return true
  return view.status === 'queued' || view.status === 'processing' || view.rulesStatus === 'pending'
}

export function useBriefPolling(api: ApiClient, briefId: string, intervalMs = POLL_MS) {
  const [view, setView] = useState<BriefView | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const alive = useRef(true)
  const loadRef = useRef<() => Promise<void>>(async () => {})
  const schedule = useCallback(() => {
    timer.current = setTimeout(() => void loadRef.current(), intervalMs)
  }, [intervalMs])

  const load = useCallback(async () => {
    try {
      const next = await api.getBrief(briefId)
      if (!alive.current) return
      setView(next)
      setError(null)
      if (shouldPoll(next)) schedule()
    } catch (e) {
      if (!alive.current) return
      setError(e instanceof ApiError ? e : new ApiError(0, 'UNKNOWN', 'Could not load the brief.'))
      if (!(e instanceof ApiError) || e.status >= 500 || e.status === 0) schedule()
    }
  }, [api, briefId, schedule])

  useEffect(() => {
    loadRef.current = load
  }, [load])

  /** Load now and start polling again (after confirm, approve, or retry). */
  const refresh = useCallback(() => {
    if (timer.current) clearTimeout(timer.current)
    void load()
  }, [load])

  useEffect(() => {
    alive.current = true
    void load()
    return () => {
      alive.current = false
      if (timer.current) clearTimeout(timer.current)
    }
  }, [load])

  return { view, error, refresh, setView }
}
