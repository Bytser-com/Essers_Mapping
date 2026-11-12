// Proposals overview on Home – functional tests for src/components/ProposalOverview.tsx:
// loading, empty list, error + retry, automatic refresh while the AI is busy and after an upload.
// The backend is replaced by a fake loader. Every test name starts with its Jira test case (TC-57-xx).
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import ProposalOverview from '../../components/ProposalOverview'
import type { Proposal, ProposalList } from '../../services/proposals'

// Short refresh interval, so the tests do not have to wait 2 seconds.
const FAST = 20

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

// A fake backend that answers with the given lists in order; the last one keeps repeating.
function loader(...responses: Array<ProposalList | Error>) {
  let call = 0
  return vi.fn(async () => {
    const response = responses[Math.min(call, responses.length - 1)]
    call += 1
    if (response instanceof Error) throw response
    return response
  })
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

describe('ProposalOverview', () => {
  it('TC-57-10 shows "Proposals laden…" while the list is loading', () => {
    const neverAnswers = vi.fn(() => new Promise<ProposalList>(() => {}))
    render(<ProposalOverview loadProposals={neverAnswers} />)

    expect(screen.getByText('Proposals laden…')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Proposals' })).toBeInTheDocument()
  })

  it('TC-57-02 shows the proposals in a table with the number of proposals in the badge', async () => {
    render(<ProposalOverview loadProposals={loader(list(ready, brunos))} />)

    expect(await screen.findByText('Ostavel')).toBeInTheDocument()
    expect(screen.getByText('Brunos')).toBeInTheDocument()
    expect(screen.getByTestId('proposal-count')).toHaveTextContent('2')
    expect(screen.getAllByRole('row')).toHaveLength(3) // header + 2 rows
  })

  it('TC-57-09 without proposals it says to upload an interface', async () => {
    render(<ProposalOverview loadProposals={loader(list())} />)

    expect(await screen.findByText('Er zijn nog geen proposals. Upload een interface om te beginnen.')).toBeInTheDocument()
    expect(screen.getByTestId('proposal-count')).toHaveTextContent('0')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('TC-57-10 shows an error with "Opnieuw proberen" when the list cannot be loaded, and retrying works', async () => {
    const load = loader(new Error('HTTP 503'), list(ready))
    render(<ProposalOverview loadProposals={load} />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('De proposals konden niet geladen worden.')

    await userEvent.click(within(alert).getByRole('button', { name: 'Opnieuw proberen' }))

    expect(await screen.findByText('Ostavel')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('TC-57-07 refreshes by itself while the AI is busy and shows "Klaar om na te kijken" when it is done', async () => {
    const load = loader(list(busy), list(busy), list(ready))
    render(<ProposalOverview loadProposals={load} pollIntervalMs={FAST} />)

    expect(await screen.findByText('AI maakt voorstel')).toBeInTheDocument()
    expect(screen.getByText('Bezig')).toBeInTheDocument()

    expect(await screen.findByText('Klaar om na te kijken')).toBeInTheDocument()
    expect(screen.queryByText('Bezig')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Openen' })).toBeEnabled()
  })

  it('TC-57-07 shows "Mislukt" when the AI run failed and then stops refreshing', async () => {
    const load = loader(list(busy), list(failed))
    render(<ProposalOverview loadProposals={load} pollIntervalMs={FAST} />)

    expect(await screen.findByText('Mislukt')).toBeInTheDocument()
    const calls = load.mock.calls.length
    await sleep(FAST * 5)
    expect(load).toHaveBeenCalledTimes(calls)
  })

  it('TC-57-07 does not keep refreshing when no AI is busy', async () => {
    const load = loader(list(ready))
    render(<ProposalOverview loadProposals={load} pollIntervalMs={FAST} />)

    await screen.findByText('Ostavel')
    await sleep(FAST * 5)

    expect(load).toHaveBeenCalledTimes(1)
  })

  it('TC-57-07 a failed refresh keeps the table that is already shown and tries again', async () => {
    const load = loader(list(busy), new Error('network down'), list(ready))
    render(<ProposalOverview loadProposals={load} pollIntervalMs={FAST} />)

    expect(await screen.findByText('Bezig')).toBeInTheDocument()

    expect(await screen.findByText('Klaar om na te kijken')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(load.mock.calls.length).toBeGreaterThanOrEqual(3)
  })

  it('TC-57-08 after an upload the list reloads and keeps checking until the new proposal appears', async () => {
    // Before the upload: only Brunos. The backend creates the new row a moment after the upload.
    const load = loader(list(brunos), list(brunos), list(brunos), list(busy, brunos))
    const { rerender } = render(<ProposalOverview loadProposals={load} pollIntervalMs={FAST} />)
    await screen.findByText('Brunos')
    await sleep(FAST * 3)
    expect(load).toHaveBeenCalledTimes(1) // nothing busy: no refreshing yet

    rerender(<ProposalOverview loadProposals={load} pollIntervalMs={FAST} refreshKey={1} />)

    expect(await screen.findByText('Ostavel')).toBeInTheDocument()
    expect(screen.getByText('AI maakt voorstel')).toBeInTheDocument()
    expect(screen.getByTestId('proposal-count')).toHaveTextContent('2')
    // The table stayed visible during the refresh
    expect(screen.queryByText('Proposals laden…')).not.toBeInTheDocument()
  })

  it('TC-57-08 the waiting after an upload stops after a while (30 seconds in the app)', async () => {
    const load = loader(list(brunos))
    const props = { loadProposals: load, pollIntervalMs: FAST, waitAfterUploadMs: FAST * 10 }
    const { rerender } = render(<ProposalOverview {...props} />)
    await screen.findByText('Brunos')

    rerender(<ProposalOverview {...props} refreshKey={1} />)
    await sleep(FAST * 20) // well past the waiting time
    const calls = load.mock.calls.length
    expect(calls).toBeGreaterThan(2) // it did keep checking for the new proposal

    await sleep(FAST * 10)
    expect(load).toHaveBeenCalledTimes(calls) // and then it stopped
  })

  it('TC-57-10 the request is cancelled when the page is left', async () => {
    let receivedSignal: AbortSignal | undefined
    const load = vi.fn((signal: AbortSignal) => {
      receivedSignal = signal
      return new Promise<ProposalList>(() => {})
    })
    const { unmount } = render(<ProposalOverview loadProposals={load} />)

    unmount()

    await waitFor(() => expect(receivedSignal?.aborted).toBe(true))
  })
})
