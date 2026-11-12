// Proposals overview: data retrieved from Version_Control backend (GET /api/version-control/proposals).

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

export type CompanyProposalOverview = {
  company: string
  latestVersion: string
  filename?: string | null
  fullPath?: string | null
  createdDate?: string | null
  createdBy?: string | null
  description?: string | null
  status?: ProposalStatus | string | null
  aiStatus?: AiStatus | string | null
}

export type ProposalFileDetails = {
  company: string
  version: string
  filename: string
  fullPath: string
  contentType: string
  fileBase64: string
  metadata?: Record<string, unknown> | null
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

// How often the overview is refreshed while the AI is busy with a proposal (and right after
// an upload). Fit criterion: a status change is visible within 10 seconds without reloading.
export const POLL_INTERVAL_MS = 2000

// Page of one customer's mapping proposal, opened with "Openen" (built in another user story,
// which loads the latest version from SFTP). Uses the customer's folder name on SFTP,
// e.g. "/proposals/ostavel" for the proposal with id "ostavel/v1".
export function proposalPath(proposal: Pick<Proposal, 'id'>): string {
  const customerFolder = proposal.id.split('/')[0] ?? proposal.id
  return `/proposals/${encodeURIComponent(customerFolder)}`
}

export function normalizeStatus(rawStatus?: string | null): ProposalStatus {
  if (!rawStatus) return 'READY_FOR_REVIEW'
  const trimmed = rawStatus.trim()
  const upper = trimmed.toUpperCase().replace(/[\s-]+/g, '_')

  if (upper === 'IN_REVIEW' || trimmed.toLowerCase() === 'in review') {
    return 'IN_REVIEW'
  }
  if (
    upper === 'READY_FOR_REVIEW' ||
    trimmed.toLowerCase() === 'klaar om na te kijken'
  ) {
    return 'READY_FOR_REVIEW'
  }
  if (
    upper === 'AI_GENERATING' ||
    trimmed.toLowerCase() === 'ai maakt voorstel' ||
    trimmed.toLowerCase() === 'wordt gegenereerd'
  ) {
    return 'AI_GENERATING'
  }
  if (
    upper === 'AI_CHECKING_REVIEW' ||
    trimmed.toLowerCase() === 'ai controleert review van analist' ||
    trimmed.toLowerCase() === 'ai controleert'
  ) {
    return 'AI_CHECKING_REVIEW'
  }
  if (upper === 'RETURNED' || trimmed.toLowerCase() === 'teruggestuurd') {
    return 'RETURNED'
  }

  return STATUS_LABELS[upper as ProposalStatus]
    ? (upper as ProposalStatus)
    : 'READY_FOR_REVIEW'
}

export function toProposal(item: CompanyProposalOverview | Proposal): Proposal {
  if ('customer' in item && typeof item.customer === 'string' && 'version' in item && typeof item.version === 'number') {
    const p = item as Proposal
    return {
      ...p,
      status: normalizeStatus(p.status),
    }
  }
  const ov = item as CompanyProposalOverview
  const versionNum = parseInt(String(ov.latestVersion ?? '').replace(/^v/i, ''), 10) || 1
  const status: ProposalStatus = normalizeStatus(ov.status)
  const aiStatus: AiStatus | null = (ov.aiStatus as AiStatus) || null
  const canOpen = status !== 'AI_GENERATING'

  return {
    id: `${ov.company}/${ov.latestVersion}`,
    customer: ov.company,
    version: versionNum,
    uploaded_at: ov.createdDate || new Date().toISOString(),
    status,
    ai_status: aiStatus,
    can_open: canOpen,
  }
}

// Version_Control API endpoint (proxied in Kubernetes by NGINX and in dev by Vite).
export const VERSION_CONTROL_API = '/api/version-control'

export async function fetchProposals(signal?: AbortSignal): Promise<ProposalList> {
  const response = await fetch(`${VERSION_CONTROL_API}/proposals`, { signal: signal ?? null })
  if (!response.ok) {
    throw new Error(`Loading proposals failed (HTTP ${response.status})`)
  }
  const data = await response.json()
  const rawList: (CompanyProposalOverview | Proposal)[] = Array.isArray(data)
    ? data
    : Array.isArray(data?.proposals)
      ? data.proposals
      : []
  const proposals = rawList.map(toProposal)
  return {
    total: proposals.length,
    proposals,
  }
}

export async function fetchProposalFile(company: string, version: string): Promise<ProposalFileDetails> {
  const params = new URLSearchParams({ company, version })
  const response = await fetch(`${VERSION_CONTROL_API}/proposals/file?${params.toString()}`)
  if (!response.ok) {
    throw new Error(`Loading proposal file failed (HTTP ${response.status})`)
  }
  return (await response.json()) as ProposalFileDetails
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
