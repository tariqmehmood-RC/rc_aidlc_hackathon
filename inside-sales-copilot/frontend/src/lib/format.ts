import type { BriefView, UnverifiedReason } from '../api/types'

export const REASON_LABEL: Record<UnverifiedReason, string> = {
  title_mismatch: 'Title does not match',
  employer_mismatch: 'Employer does not match',
  no_profile_found: 'No profile found',
  title_missing: 'No title in the invite',
  ambiguous: 'More than one possible profile',
}

export interface SourceInfo {
  url: string
  /** Short text for the chip, never the raw URL. */
  chip: string
  /** Full text for the tooltip and the sources list. */
  title: string
  kind: 'wikipedia' | 'news' | 'web' | 'casestudy'
  date?: string | null
}

const host = (url: string) => {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

/** One lookup for every URL the brief cites, so chips and the sources list agree. */
export function buildSourceIndex(view: BriefView): Map<string, SourceInfo> {
  const index = new Map<string, SourceInfo>()
  const news = new Map((view.research?.news ?? []).map((n) => [n.url, n]))
  for (const s of view.content?.sources ?? []) {
    const h = host(s.url)
    const item = news.get(s.url)
    if (item) {
      const outlet = item.title.includes(' - ') ? item.title.slice(item.title.lastIndexOf(' - ') + 3) : 'News'
      index.set(s.url, { url: s.url, chip: outlet, title: item.title, kind: 'news', date: item.date })
    } else if (h.endsWith('wikipedia.org')) {
      index.set(s.url, { url: s.url, chip: 'Wikipedia', title: s.label === 'Wikipedia' ? `Wikipedia: ${decodeURIComponent(s.url.split('/wiki/')[1] ?? '').replace(/_/g, ' ')}` : s.label, kind: 'wikipedia' })
    } else if (h.endsWith('royalcyber.com')) {
      index.set(s.url, { url: s.url, chip: 'Royal Cyber', title: s.label, kind: 'casestudy' })
    } else {
      index.set(s.url, { url: s.url, chip: h, title: s.label || h, kind: 'web' })
    }
  }
  return index
}

export function sourceFor(index: Map<string, SourceInfo>, url: string): SourceInfo {
  return index.get(url) ?? { url, chip: host(url), title: url, kind: 'web' }
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso + 'T00:00:00Z')
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

export function longDate(iso: string | null | undefined): string {
  if (!iso) return 'Date not given'
  const d = new Date(iso + 'T00:00:00Z')
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })
}
