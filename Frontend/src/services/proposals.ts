// Proposals overview: data from the Mapping_Proposal backend (GET /proposals).

export type ProposalStatus =
  | 'AI_GENERATING'
  | 'READY_FOR_REVIEW'
  | 'IN_REVIEW'
  | 'AI_CHECKING_REVIEW'
  | 'RETURNED'

export type AiStatus = 'RUNNING' | 'FAILED'

export type Proposal = {
  id: string
  customer: string
  version: number
  uploaded_at: string // ISO 8601 with timezone
  status: ProposalStatus
  ai_status: AiStatus | null
  can_open: boolean
}

export type ProposalList = {
  total: number
  proposals: Proposal[]
}

// Dutch labels shown in the table; the backend only sends the codes.
export const STATUS_LABELS: Record<ProposalStatus, string> = {
  AI_GENERATING: 'AI maakt voorstel',
  READY_FOR_REVIEW: 'Klaar om na te kijken',
  IN_REVIEW: 'In review',
  AI_CHECKING_REVIEW: 'AI controleert review van analist',
  RETURNED: 'Teruggestuurd',
}

export const AI_STATUS_LABELS: Record<AiStatus, string> = {
  RUNNING: 'Bezig',
  FAILED: 'Mislukt',
}

// How often the overview is refreshed while the AI is busy with a proposal.
// Fit criterion: a status change is visible within 10 seconds without reloading the page.
export const POLL_INTERVAL_MS = 5000

// Page of one customer's mapping proposal, opened with "Openen" (built in another user story,
// which loads the latest version from SFTP). Uses the customer's folder name on SFTP,
// e.g. "/proposals/ostavel" for the proposal with id "ostavel/v1".
export function proposalPath(proposal: Pick<Proposal, 'id'>): string {
  const customerFolder = proposal.id.split('/')[0] ?? proposal.id
  return `/proposals/${encodeURIComponent(customerFolder)}`
}

// In Kubernetes the frontend proxies /api/proposal/* to the backend; during local
// development vite.config.js does the same. Override with VITE_PROPOSAL_API_URL.
const API_BASE: string = import.meta.env.VITE_PROPOSAL_API_URL ?? '/api/proposal'

export async function fetchProposals(signal?: AbortSignal): Promise<ProposalList> {
  const response = await fetch(`${API_BASE}/proposals`, { signal: signal ?? null })
  if (!response.ok) {
    throw new Error(`Loading proposals failed (HTTP ${response.status})`)
  }
  return (await response.json()) as ProposalList
}

// "22/10/2026 14:05" in the browser's timezone (or the given one, used by tests).
export function formatUploadedAt(isoDate: string, timeZone?: string): string {
  const date = new Date(isoDate)
  if (Number.isNaN(date.getTime())) return '—'
  const parts = new Intl.DateTimeFormat('nl-BE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
    ...(timeZone ? { timeZone } : {}),
  }).formatToParts(date)
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)?.value ?? ''
  return `${part('day')}/${part('month')}/${part('year')} ${part('hour')}:${part('minute')}`
}
