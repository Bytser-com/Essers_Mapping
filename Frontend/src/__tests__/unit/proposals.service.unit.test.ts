// Proposals overview on Home – unit tests for src/services/proposals.ts
// (API call, Dutch labels, date format and the link behind "Openen").
// Every test name starts with its Jira test case (TC-57-xx).
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  AI_STATUS_LABELS,
  POLL_INTERVAL_MS,
  STATUS_LABELS,
  fetchProposalFile,
  fetchProposals,
  formatUploadedAt,
  proposalPath,
} from '../../services/proposals'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchProposals', () => {
  it('TC-57-02 loads the list from GET /api/version-control/proposals', async () => {
    const vcList = [
      {
        company: 'Ostavel',
        latestVersion: 'v1',
        filename: 'MProposal-Ostavel_V1.xlsx',
        createdDate: '2026-10-30T13:30:00+01:00',
        status: 'READY_FOR_REVIEW',
        aiStatus: null,
      },
    ]
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(vcList), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const controller = new AbortController()

    const result = await fetchProposals(controller.signal)
    expect(result.total).toBe(1)
    expect(result.proposals[0].customer).toBe('Ostavel')
    expect(result.proposals[0].version).toBe(1)
    expect(result.proposals[0].status).toBe('READY_FOR_REVIEW')

    expect(fetchMock).toHaveBeenCalledWith('/api/version-control/proposals', { signal: controller.signal })
  })

  it('TC-57-02 works without an abort signal', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchProposals()

    expect(fetchMock).toHaveBeenCalledWith('/api/version-control/proposals', { signal: null })
  })

  it('TC-57-10 throws when the backend answers with an error (e.g. 503: SFTP unreachable)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 503 })))

    await expect(fetchProposals()).rejects.toThrow('HTTP 503')
  })
})

describe('labels', () => {
  it('TC-57-05 every status code has its Dutch label', () => {
    expect(STATUS_LABELS).toEqual({
      AI_GENERATING: 'AI maakt voorstel',
      READY_FOR_REVIEW: 'Klaar om na te kijken',
      IN_REVIEW: 'In review',
      AI_CHECKING_REVIEW: 'AI controleert review van analist',
      RETURNED: 'Teruggestuurd',
    })
    expect(AI_STATUS_LABELS).toEqual({ RUNNING: 'Bezig', FAILED: 'Mislukt' })
  })
})

describe('formatUploadedAt', () => {
  it('TC-57-04 shows the upload time as dd/mm/jjjj uu:mm in the timezone of the analist', () => {
    expect(formatUploadedAt('2026-10-22T14:05:00+02:00', 'Europe/Brussels')).toBe('22/10/2026 14:05')
    expect(formatUploadedAt('2026-10-22T12:05:00Z', 'Europe/Brussels')).toBe('22/10/2026 14:05')
  })

  it('TC-57-04 uses the 24-hour clock and leading zeros', () => {
    expect(formatUploadedAt('2026-01-05T08:07:00+01:00', 'Europe/Brussels')).toBe('05/01/2026 08:07')
    expect(formatUploadedAt('2026-01-05T23:59:00+01:00', 'Europe/Brussels')).toBe('05/01/2026 23:59')
  })

  it('TC-57-04 handles the change to winter time', () => {
    // 25 October 2026: clocks go back from +02:00 to +01:00
    expect(formatUploadedAt('2026-10-25T09:00:00Z', 'Europe/Brussels')).toBe('25/10/2026 10:00')
  })

  it('TC-57-04 shows a dash for an invalid date', () => {
    expect(formatUploadedAt('niet-een-datum')).toBe('—')
  })

  it("TC-57-04 uses the browser's timezone when none is given", () => {
    expect(formatUploadedAt('2026-10-22T14:05:00+02:00')).toMatch(/^\d{2}\/\d{2}\/2026 \d{2}:\d{2}$/)
  })
})

describe('proposalPath', () => {
  it('TC-57-06 "Openen" goes to the page of the customer: /proposals/<customer folder>', () => {
    expect(proposalPath({ id: 'ostavel/v1' })).toBe('/proposals/ostavel')
    expect(proposalPath({ id: 'voorbeeldbedrijf-a/v3' })).toBe('/proposals/voorbeeldbedrijf-a')
  })

  it('TC-57-06 encodes unusual characters and works without a version', () => {
    expect(proposalPath({ id: 'a b/v1' })).toBe('/proposals/a%20b')
    expect(proposalPath({ id: 'ostavel' })).toBe('/proposals/ostavel')
  })
})

describe('refresh interval', () => {
  it('TC-57-07 a status change is visible within 10 seconds (refresh at most every 10 s)', () => {
    expect(POLL_INTERVAL_MS).toBeGreaterThan(0)
    expect(POLL_INTERVAL_MS).toBeLessThanOrEqual(10_000)
  })
})

describe('fetchProposalFile', () => {
  it('loads proposal file details from GET /api/version-control/proposals/file', async () => {
    const fileDetails = {
      company: 'Ostavel',
      version: 'v1',
      filename: 'MProposal-Ostavel_V1.xlsx',
      fullPath: '/Proposals/Ostavel/v1/MProposal-Ostavel_V1.xlsx',
      contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      fileBase64: 'UEsDBBQAAAAIA...',
    }
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(fileDetails), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchProposalFile('Ostavel', 'v1')
    expect(result).toEqual(fileDetails)
    expect(fetchMock).toHaveBeenCalledWith('/api/version-control/proposals/file?company=Ostavel&version=v1')
  })
})
