// Proposals overview on Home – unit tests for the table (src/components/ProposalTable.tsx).
// Every test name starts with its Jira test case (TC-57-xx).
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import ProposalTable from '../../components/ProposalTable'
import { formatUploadedAt, type Proposal } from '../../services/proposals'

function proposal(overrides: Partial<Proposal> = {}): Proposal {
  return {
    id: 'ostavel/v1',
    customer: 'Ostavel',
    version: 1,
    uploaded_at: '2026-10-30T13:30:00+01:00',
    status: 'READY_FOR_REVIEW',
    ai_status: null,
    can_open: true,
    ...overrides,
  }
}

function rows() {
  // The first row is the header
  return screen.getAllByRole('row').slice(1)
}

describe('ProposalTable', () => {
  it('TC-57-04 shows the columns KLANT, VERSIE, GEÜPLOAD OP, STATUS, AI-STATUS and ACTIE', () => {
    render(<ProposalTable proposals={[proposal()]} />)

    const headers = screen.getAllByRole('columnheader').map((header) => header.textContent)
    expect(headers).toEqual(['KLANT', 'VERSIE', 'GEÜPLOAD OP', 'STATUS', 'AI-STATUS', 'ACTIE'])
  })

  it('TC-57-04 one row per proposal with customer, version, upload time and status', () => {
    render(
      <ProposalTable
        proposals={[
          proposal(),
          proposal({ id: 'brunos/v3', customer: 'Brunos', version: 3, status: 'IN_REVIEW' }),
        ]}
      />,
    )

    expect(rows()).toHaveLength(2)
    const first = within(rows()[0]!)
    expect(first.getByText('Ostavel')).toBeInTheDocument()
    expect(first.getByText('v1')).toBeInTheDocument()
    expect(first.getByText(formatUploadedAt('2026-10-30T13:30:00+01:00'))).toBeInTheDocument()
    expect(first.getByText('Klaar om na te kijken')).toBeInTheDocument()
    const second = within(rows()[1]!)
    expect(second.getByText('Brunos')).toBeInTheDocument()
    expect(second.getByText('v3')).toBeInTheDocument()
    expect(second.getByText('In review')).toBeInTheDocument()
  })

  it.each([
    ['AI_GENERATING', 'AI maakt voorstel'],
    ['READY_FOR_REVIEW', 'Klaar om na te kijken'],
    ['IN_REVIEW', 'In review'],
    ['In review', 'In review'],
    ['in review', 'In review'],
    ['Klaar om na te kijken', 'Klaar om na te kijken'],
    ['AI_CHECKING_REVIEW', 'AI controleert review van analist'],
    ['RETURNED', 'Teruggestuurd'],
  ] as const)('TC-57-05 status %s is shown as "%s"', (status, label) => {
    render(<ProposalTable proposals={[proposal({ status: status as any })]} />)

    expect(within(rows()[0]!).getByText(label)).toBeInTheDocument()
  })

  it.each([
    ['RUNNING', 'Bezig'],
    ['FAILED', 'Mislukt'],
    [null, '—'],
  ] as const)('TC-57-05 AI status %s is shown as "%s"', (aiStatus, label) => {
    render(<ProposalTable proposals={[proposal({ ai_status: aiStatus })]} />)

    expect(within(rows()[0]!).getByText(label)).toBeInTheDocument()
  })

  it('TC-57-06 "Openen" is disabled while the AI is making the proposal', () => {
    render(
      <ProposalTable
        proposals={[
          proposal({ id: 'busy/v1', customer: 'Busy', status: 'AI_GENERATING', ai_status: 'RUNNING', can_open: false }),
          proposal({ id: 'ready/v1', customer: 'Ready' }),
        ]}
      />,
    )

    expect(within(rows()[0]!).getByRole('button', { name: 'Openen' })).toBeDisabled()
    expect(within(rows()[1]!).getByRole('button', { name: 'Openen' })).toBeEnabled()
  })

  it('TC-57-06 "Openen" goes to the page of that customer', async () => {
    function CustomerPage() {
      const { customer } = useParams()
      return <p>Pagina van {customer}</p>
    }
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<ProposalTable proposals={[proposal({ id: 'voorbeeldbedrijf-a/v2' })]} />} />
          <Route path="/proposals/:customer" element={<CustomerPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Openen' }))

    expect(screen.getByText('Pagina van voorbeeldbedrijf-a')).toBeInTheDocument()
  })

  it('TC-57-06 a disabled "Openen" does not navigate', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route
            path="/"
            element={<ProposalTable proposals={[proposal({ status: 'AI_GENERATING', can_open: false })]} />}
          />
          <Route path="/proposals/:customer" element={<p>Pagina van de klant</p>} />
        </Routes>
      </MemoryRouter>,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Openen' }))

    expect(screen.queryByText('Pagina van de klant')).not.toBeInTheDocument()
  })

  it('TC-57-06 without a router "Openen" is still shown and follows can_open', () => {
    render(<ProposalTable proposals={[proposal({ can_open: false })]} />)

    expect(screen.getByRole('button', { name: 'Openen' })).toBeDisabled()
  })

  it('TC-57-09 an empty list shows only the header', () => {
    render(<ProposalTable proposals={[]} />)

    expect(rows()).toHaveLength(0)
  })
})
