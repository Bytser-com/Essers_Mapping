// Proposals overview on Home – integration test: the Home page, the overview component and
// the real API service together. Only the network (fetch) is replaced by a fake backend that
// answers like the Mapping_Proposal API. Every test name starts with its Jira test case (TC-57-xx).
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Home from '../../pages/Home'
import type { Proposal } from '../../services/proposals'

const brunos: Proposal = {
  id: 'brunos/v1',
  customer: 'Brunos',
  version: 1,
  uploaded_at: '2026-11-10T09:39:02+00:00',
  status: 'READY_FOR_REVIEW',
  ai_status: null,
  can_open: true,
}
const ostavelBusy: Proposal = {
  id: 'ostavel/v1',
  customer: 'Ostavel',
  version: 1,
  uploaded_at: '2026-11-10T10:00:00+00:00',
  status: 'AI_GENERATING',
  ai_status: 'RUNNING',
  can_open: false,
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

// Fake backend: GET /api/proposal/proposals returns the current list; POST /upload adds a row.
function fakeBackend(initial: Proposal[]) {
  let proposals = [...initial]
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/proposals')) return json({ total: proposals.length, proposals })
    if (url.endsWith('/upload') && init?.method === 'POST') {
      proposals = [ostavelBusy, ...proposals]
      return json({ upload_id: 'x', customer: 'Ostavel', files: ['order.xml'] }, 201)
    }
    return json({ detail: 'not found' }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Home – proposals overview', () => {
  it('TC-57-02 Home loads the proposals from the API and shows them under "Proposals"', async () => {
    const fetchMock = fakeBackend([brunos])
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>,
    )

    const row = (await screen.findByText('Brunos')).closest('tr') as HTMLElement
    expect(within(row).getByText('v1')).toBeInTheDocument()
    expect(within(row).getByText('Klaar om na te kijken')).toBeInTheDocument()
    expect(screen.getByTestId('proposal-count')).toHaveTextContent('1')
    expect(fetchMock).toHaveBeenCalledWith('/api/proposal/proposals', expect.anything())
  })

  it('TC-57-08 after an upload the new proposal appears in the list without reloading the page', async () => {
    fakeBackend([brunos])
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>,
    )
    await screen.findByText('Brunos')

    await userEvent.type(screen.getByLabelText('Klantnaam'), 'Ostavel')
    await userEvent.upload(screen.getByTestId('file-input'), new File(['<root />'], 'order.xml', { type: 'text/xml' }))
    await userEvent.click(screen.getByRole('button', { name: 'Uploaden' }))

    const row = (await screen.findByText('Ostavel', { selector: 'td' })).closest('tr') as HTMLElement
    expect(within(row).getByText('AI maakt voorstel')).toBeInTheDocument()
    expect(within(row).getByText('Bezig')).toBeInTheDocument()
    expect(within(row).getByRole('button', { name: 'Openen' })).toBeDisabled()
    expect(screen.getByTestId('proposal-count')).toHaveTextContent('2')
  })

  it('TC-57-06 "Openen" on Home goes to the page of that customer', async () => {
    fakeBackend([brunos])
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/proposals/:customer" element={<p>Pagina van de klant</p>} />
        </Routes>
      </MemoryRouter>,
    )

    await userEvent.click(await screen.findByRole('button', { name: 'Openen' }))

    expect(screen.getByText('Pagina van de klant')).toBeInTheDocument()
  })

  it('TC-57-10 Home shows the error message when the backend cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>,
    )

    expect(await screen.findByText('De proposals konden niet geladen worden.')).toBeInTheDocument()
  })
})
