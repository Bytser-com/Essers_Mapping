// Proposals overview on Home – functional tests for src/components/ProposalOverview.tsx:
// loading, empty list, error + retry, automatic refresh while the AI is busy and after an upload.
// The backend is replaced by a mock of fetchProposals; the list lives in stores/homeStore.ts.
// Every test name starts with its Jira test case (TC-57-xx).
import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProposalOverview from '../../components/ProposalOverview'
import { fetchProposals, type Proposal, type ProposalList } from '../../services/proposals'
import { useHomeStore } from '../../stores/homeStore'

// Keep the real helpers (labels, formatting) but replace the API call,
// and use a short refresh interval so the tests do not have to wait 2 seconds.
vi.mock('../../services/proposals', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/proposals')>()),
  POLL_INTERVAL_MS: 20,
  fetchProposals: vi.fn(),
}))

// Same value as POLL_INTERVAL_MS in the mock above.
const FAST = 20

const fetchMock = vi.mocked(fetchProposals)

const busy: Proposal = {
  id: 'ostavel/v1',
  customer: 'Ostavel',
  version: 1,
  uploaded_at: '2026-10-30T13:30:00+01:00',
  status: 'AI_GENERATING',
  ai_status: 'RUNNING',
  can_open: false,
}
const ready: Proposal = { ...busy, status: 'READY_FOR_REVIEW', ai_status: null, can_open: true }
const failed: Proposal = { ...busy, ai_status: 'FAILED' }
const brunos: Proposal = { ...ready, id: 'brunos/v2', customer: 'Brunos', version: 2 }

function list(...proposals: Proposal[]): ProposalList {
  return { total: proposals.length, proposals }
}

// The fake backend answers with the given lists in order; the last one keeps repeating.
function answers(...responses: Array<ProposalList | Error>) {
  let call = 0
  fetchMock.mockImplementation(async () => {
    const response = responses[Math.min(call, responses.length - 1)]!
    call += 1
    if (response instanceof Error) throw response
    return { ...response }
  })
}

// What the store does after a successful upload: keep checking for the new row for a while.
function simulateUpload(waitMs: number) {
  act(() => {
    useHomeStore.setState({ waitUntil: Date.now() + waitMs })
  })
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

describe('ProposalOverview', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    // Every test starts with an empty store
    useHomeStore.setState({ proposalList: null, loading: false, error: null, uploadError: null, waitUntil: 0 })
  })

  it('TC-57-10 shows "Proposals laden…" while the list is loading', () => {
    fetchMock.mockImplementation(() => new Promise<ProposalList>(() => {}))
    render(<ProposalOverview />)

    expect(screen.getByText('Proposals laden…')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Proposals' })).toBeInTheDocument()
  })

  it('TC-57-02 shows the proposals in a table with the number of proposals in the badge', async () => {
    answers(list(ready, brunos))
    render(<ProposalOverview />)

    expect(await screen.findByText('Ostavel')).toBeInTheDocument()
    expect(screen.getByText('Brunos')).toBeInTheDocument()
    expect(screen.getByTestId('proposal-count')).toHaveTextContent('2')
    expect(screen.getAllByRole('row')).toHaveLength(3) // header + 2 rows
  })

  it('TC-57-09 without proposals it says to upload an interface', async () => {
    answers(list())
    render(<ProposalOverview />)

    expect(await screen.findByText('Er zijn nog geen proposals. Upload een interface om te beginnen.')).toBeInTheDocument()
    expect(screen.getByTestId('proposal-count')).toHaveTextContent('0')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('TC-57-10 shows an error with "Opnieuw proberen" when the list cannot be loaded, and retrying works', async () => {
    answers(new Error('HTTP 503'), list(ready))
    render(<ProposalOverview />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('De proposals konden niet geladen worden.')

    await userEvent.click(within(alert).getByRole('button', { name: 'Opnieuw proberen' }))

    expect(await screen.findByText('Ostavel')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('TC-57-07 refreshes by itself while the AI is busy and shows "Klaar om na te kijken" when it is done', async () => {
    answers(list(busy), list(busy), list(ready))
    render(<ProposalOverview />)

    expect(await screen.findByText('AI maakt voorstel')).toBeInTheDocument()
    expect(screen.getByText('Bezig')).toBeInTheDocument()

    expect(await screen.findByText('Klaar om na te kijken')).toBeInTheDocument()
    expect(screen.queryByText('Bezig')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Openen' })).toBeEnabled()
  })

  it('TC-57-07 shows "Mislukt" when the AI run failed and then stops refreshing', async () => {
    answers(list(busy), list(failed))
    render(<ProposalOverview />)

    expect(await screen.findByText('Mislukt')).toBeInTheDocument()
    const calls = fetchMock.mock.calls.length
    await sleep(FAST * 5)
    expect(fetchMock).toHaveBeenCalledTimes(calls)
  })

  it('TC-57-07 does not keep refreshing when no AI is busy', async () => {
    answers(list(ready))
    render(<ProposalOverview />)

    await screen.findByText('Ostavel')
    await sleep(FAST * 5)

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('TC-57-07 a failed refresh keeps the table that is already shown and tries again', async () => {
    answers(list(busy), new Error('network down'), list(ready))
    render(<ProposalOverview />)

    expect(await screen.findByText('Bezig')).toBeInTheDocument()

    expect(await screen.findByText('Klaar om na te kijken')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(3)
  })

  it('TC-57-08 after an upload the list reloads and keeps checking until the new proposal appears', async () => {
    // Before the upload: only Brunos. The backend creates the new row a moment after the upload.
    answers(list(brunos), list(brunos), list(brunos), list(busy, brunos))
    render(<ProposalOverview />)
    await screen.findByText('Brunos')
    await sleep(FAST * 3)
    expect(fetchMock).toHaveBeenCalledTimes(1) // nothing busy: no refreshing yet

    simulateUpload(30_000)

    expect(await screen.findByText('Ostavel')).toBeInTheDocument()
    expect(screen.getByText('AI maakt voorstel')).toBeInTheDocument()
    expect(screen.getByTestId('proposal-count')).toHaveTextContent('2')
    // The table stayed visible during the refresh
    expect(screen.queryByText('Proposals laden…')).not.toBeInTheDocument()
  })

  it('TC-57-08 the waiting after an upload stops after a while (30 seconds in the app)', async () => {
    answers(list(brunos))
    render(<ProposalOverview />)
    await screen.findByText('Brunos')

    simulateUpload(FAST * 10)
    await sleep(FAST * 20) // well past the waiting time
    const calls = fetchMock.mock.calls.length
    expect(calls).toBeGreaterThan(2) // it did keep checking for the new proposal

    await sleep(FAST * 10)
    expect(fetchMock).toHaveBeenCalledTimes(calls) // and then it stopped
  })
})
