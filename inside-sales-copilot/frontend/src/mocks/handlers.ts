// MSW handlers that follow the API contract (design 6), backed by MockDb.
import { http, HttpResponse } from 'msw'
import { readMockToken } from '../auth/auth'
import type { BriefContent, ParsedInvite } from '../api/types'
import { MockDb } from './db'

const err = (status: number, code: string, message: string, details?: unknown[]) =>
  HttpResponse.json({ error: { code, message, ...(details ? { details } : {}) } }, { status })

function caller(request: Request) {
  const auth = request.headers.get('Authorization') ?? ''
  const payload = readMockToken(auth.startsWith('Bearer ') ? auth.slice(7) : null)
  return payload ? { sub: payload.sub, bu: payload['custom:bu'] } : null
}

export function createHandlers(db: MockDb, base = '/api') {
  // Every route needs a valid token, like the Cognito JWT authorizer.
  const guard = <A extends unknown[]>(fn: (who: { sub: string; bu: string }, ...args: A) => Response | Promise<Response>) =>
    async (request: Request, ...args: A) => {
      const who = caller(request)
      if (!who) return err(401, 'UNAUTHORIZED', 'Sign in to continue.')
      return fn(who, ...args)
    }

  const owned = (who: { sub: string }, id: string) => db.get(id, who.sub)

  return [
    http.post(`${base}/briefs`, async ({ request }) =>
      guard(async (who) => {
        const body = (await request.json().catch(() => ({}))) as { inviteText?: unknown }
        const text = body.inviteText
        if (typeof text !== 'string') return err(400, 'INVALID_BODY', "Send the invite text as 'inviteText'.")
        if (text.length > 10_000) return err(400, 'INVITE_TOO_LONG', 'The invite is longer than 10,000 characters.')
        if (!text.trim()) return err(400, 'INVITE_EMPTY', 'Paste the meeting invite first.')
        const id = db.create(who.sub, who.bu, text)
        return HttpResponse.json({ briefId: id, status: 'queued' }, { status: 202 })
      })(request)),

    http.get(`${base}/briefs`, ({ request }) =>
      guard((who) => {
        const items = [...db.briefs.values()].filter((b) => b.owner === who.sub).sort((a, b) => b.createdAt - a.createdAt)
          .map((b) => {
            const v = db.view(b)
            return { briefId: b.briefId, companyName: v.confirmedInvite?.company.name ?? v.parsedInvite?.company.name ?? null,
                     meetingDate: v.confirmedInvite?.meetingDate ?? null, status: v.status, createdAt: b.createdAt }
          })
        return HttpResponse.json({ items, nextCursor: null })
      })(request)),

    http.get(`${base}/briefs/:id`, ({ request, params }) =>
      guard((who) => {
        const b = owned(who, String(params.id))
        return b ? HttpResponse.json(db.view(b)) : err(404, 'NOT_FOUND', 'Not found.')
      })(request)),

    http.put(`${base}/briefs/:id`, async ({ request, params }) =>
      guard(async (who) => {
        const b = owned(who, String(params.id))
        if (!b) return err(404, 'NOT_FOUND', 'Not found.')
        const v = db.view(b)
        const body = (await request.json().catch(() => ({}))) as { parsedInvite?: ParsedInvite; content?: BriefContent; version?: number }
        if (v.status === 'awaiting_confirmation' && body.parsedInvite) {
          b.parsedInvite = { ...body.parsedInvite, warnings: db.warningsFor(body.parsedInvite) }
          return HttpResponse.json(db.view(b))
        }
        if (v.status === 'ready' && body.content) {
          if (body.version !== b.version) return err(409, 'CONFLICT', 'The brief changed since you opened it. Reload and try again.')
          const total = body.content.agenda.reduce((sum, a) => sum + a.minutes, 0)
          if (total !== 30) return err(400, 'INVALID_CONTENT', `The agenda adds up to ${total} minutes. It must add up to 30.`)
          b.content = body.content
          b.version += 1
          return HttpResponse.json(db.view(b))
        }
        return err(409, 'BRIEF_NOT_EDITABLE', 'This brief cannot be edited now.')
      })(request)),

    http.post(`${base}/briefs/:id/confirm`, async ({ request, params }) =>
      guard(async (who) => {
        const b = owned(who, String(params.id))
        if (!b) return err(404, 'NOT_FOUND', 'Not found.')
        if (db.view(b).status !== 'awaiting_confirmation') return err(409, 'BRIEF_NOT_CONFIRMABLE', 'This brief is not waiting for confirmation.')
        const body = (await request.json().catch(() => ({}))) as { parsedInvite?: ParsedInvite; companyConfirmed?: boolean }
        if (!body.parsedInvite) return err(400, 'INVALID_BODY', 'The parsed invite is not valid.')
        const errors = db.confirmErrors(body.parsedInvite, body.companyConfirmed === true)
        if (errors.length) return err(400, errors[0].code, errors[0].message, errors)
        db.startPipeline(b, { ...body.parsedInvite, warnings: db.warningsFor(body.parsedInvite) })
        return HttpResponse.json({ briefId: b.briefId, status: 'queued' }, { status: 202 })
      })(request)),

    http.post(`${base}/briefs/:id/approve`, ({ request, params }) =>
      guard((who) => {
        const b = owned(who, String(params.id))
        if (!b) return err(404, 'NOT_FOUND', 'Not found.')
        if (db.view(b).status !== 'ready') return err(409, 'BRIEF_NOT_APPROVABLE', 'Only a ready brief can be approved.')
        b.approved = true
        b.approvedAt = db.now()
        b.rulesStatus = 'pending'
        return HttpResponse.json({ briefId: b.briefId, status: 'approved', rulesStatus: 'pending' }, { status: 202 })
      })(request)),

    http.post(`${base}/briefs/:id/retry`, ({ request, params }) =>
      guard((who) => {
        const b = owned(who, String(params.id))
        if (!b) return err(404, 'NOT_FOUND', 'Not found.')
        if (!b.error) return err(409, 'BRIEF_NOT_FAILED', 'Only a failed brief can be retried.')
        b.error = undefined
        b.failAt = undefined
        b.phaseStart = db.now()
        return HttpResponse.json({ briefId: b.briefId, status: 'queued' }, { status: 202 })
      })(request)),

    http.post(`${base}/briefs/:id/rules`, async ({ request, params }) =>
      guard(async (who) => {
        const b = owned(who, String(params.id))
        if (!b) return err(404, 'NOT_FOUND', 'Not found.')
        if (b.rulesStatus !== 'ready') return err(409, 'NO_PROPOSALS', 'There are no rule proposals to review.')
        const body = (await request.json().catch(() => ({}))) as { decisions?: Array<{ proposalId: string; keep: boolean }> }
        const saved: string[] = []
        for (const d of body.decisions ?? []) {
          const proposal = b.ruleProposals.find((p) => p.proposalId === d.proposalId)
          if (proposal && d.keep === true) {
            const rule = db.addRule(who.sub, proposal.text)
            if (rule) saved.push(rule.ruleId)
          }
        }
        b.ruleProposals = []
        b.rulesStatus = 'none'
        return HttpResponse.json({ saved })
      })(request)),

    http.get(`${base}/rules`, ({ request }) =>
      guard((who) => HttpResponse.json({ items: db.rules.get(who.sub) ?? [] }))(request)),
  ]
}
