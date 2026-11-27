// Version history of one mapping package – functional tests for src/pages/PackageVersions.tsx:
// loading, the table with one row per version, the active version, empty list, error + retry.
// The backend is replaced by a mock of fetchPackageVersions; the list lives in stores/mappingPackageStore.ts.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import PackageVersions from '../../pages/PackageVersions'
import { fetchPackageVersions, type PackageVersion } from '../../services/mappingPackageOverviewService'
import { useMappingPackageStore } from '../../stores/mappingPackageStore'

// Keep the real types and helpers but replace the API call
vi.mock('../../services/mappingPackageOverviewService', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/mappingPackageOverviewService')>()),
  fetchPackageVersions: vi.fn(),
}))

const fetchMock = vi.mocked(fetchPackageVersions)

// createdAt without timezone: shown as is, whatever the timezone of the test machine
const v3: PackageVersion = {
  version: 'v3',
  isActive: false,
  createdAt: '2026-11-12T10:00:00',
  createdBy: 'Analist A',
  description: '2 mappings gewijzigd',
}
const v2: PackageVersion = { ...v3, version: 'v2', isActive: true, createdAt: '2026-10-02T10:00:00', createdBy: 'Analist B', description: '1 mapping toegevoegd' }
const v1: PackageVersion = { ...v3, version: 'v1', createdAt: '2026-09-29T09:30:00', description: 'Eerste versie' }

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/package-versions/brevalis/inbound']}>
      <Routes>
        <Route path="/package-versions/:company/:packageType" element={<PackageVersions />} />
        <Route path="/version-control" element={<p>Overzicht</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

// The fake backend answers with the given lists in order; the last one keeps repeating.
function answers(...responses: Array<PackageVersion[] | Error>) {
  let call = 0
  fetchMock.mockImplementation(async () => {
    const response = responses[Math.min(call, responses.length - 1)]!
    call += 1
    if (response instanceof Error) throw response
    return [...response]
  })
}

// The data rows of the table, without the header row
function bodyRows() {
  return screen.getAllByRole('row').slice(1)
}

describe('PackageVersions', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    // Every test starts with an empty store
    useMappingPackageStore.setState({ versions: null, versionsLoading: false, versionsError: null })
  })

  it('shows the breadcrumb, the company as title and the section title', () => {
    fetchMock.mockImplementation(() => new Promise<PackageVersion[]>(() => { }))
    renderPage()

    expect(screen.getByRole('link', { name: 'Version Control' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'brevalis' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Versiegeschiedenis' })).toBeInTheDocument()
  })

  it('shows "Versies laden…" while the versions are loading', () => {
    fetchMock.mockImplementation(() => new Promise<PackageVersion[]>(() => { }))
    renderPage()

    expect(screen.getByText('Versies laden…')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('loads the versions of the company and type from the URL once when the page opens', async () => {
    answers([v3, v2, v1])
    renderPage()

    await screen.findByText('v3')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith('brevalis', 'inbound')
  })

  it('shows the active version next to the title', async () => {
    answers([v3, v2, v1])
    renderPage()

    expect(await screen.findByText('Actief: v2')).toBeInTheDocument()
  })

  it('shows the package type and the number of versions under the title', async () => {
    answers([v3, v2, v1])
    renderPage()

    expect(await screen.findByText('Mapping package · inbound · 3 versies')).toBeInTheDocument()
  })

  it('shows no active label next to the title when no version is active', async () => {
    answers([{ ...v2, isActive: false }, v1])
    renderPage()

    await screen.findByText('v2')

    expect(screen.queryByText(/^Actief:/)).not.toBeInTheDocument()
  })

  it('goes back to the overview via the breadcrumb', async () => {
    answers([v3, v2, v1])
    renderPage()

    await userEvent.click(await screen.findByRole('link', { name: 'Version Control' }))

    expect(screen.getByText('Overzicht')).toBeInTheDocument()
  })

  it('shows the versions in a table with the columns VERSIE, OMSCHRIJVING, GOEDGEKEURD OP, DOOR and ACTIE', async () => {
    answers([v3, v2, v1])
    renderPage()

    await screen.findByText('v3')

    const headers = screen.getAllByRole('columnheader').map((th) => th.textContent)
    expect(headers).toEqual(['VERSIE', 'OMSCHRIJVING', 'GOEDGEKEURD OP', 'DOOR', 'ACTIE'])
    expect(screen.getAllByRole('row')).toHaveLength(4) // header + 3 rows
  })

  it('shows version, date and author of a version in one row', async () => {
    answers([v3])
    renderPage()

    await screen.findByText('v3')

    const cells = within(bodyRows()[0]!).getAllByRole('cell')
    expect(cells[0]).toHaveTextContent('v3')
    expect(cells[1]).toHaveTextContent('—')
    expect(cells[2]).toHaveTextContent('12/11/2026 10:00')
    expect(cells[3]).toHaveTextContent('Analist A')
    expect(within(cells[4]!).getByRole('button', { name: 'Openen' })).toBeInTheDocument()
  })

  it('shows one row per version in the order of the backend', async () => {
    answers([v3, v2, v1])
    renderPage()  

    await screen.findByText('v3')

    const rows = bodyRows().map((tr) => within(tr).getAllByRole('cell')[2]!.textContent)
    expect(rows).toEqual(['12/11/2026 10:00', '02/10/2026 10:00', '29/09/2026 09:30'])
  })

  it('only the active version has the "Actief" label in the table', async () => {
    answers([v3, v2, v1])
    renderPage()

    await screen.findByText('v3')

    const versionCells = bodyRows().map((tr) => within(tr).getAllByRole('cell')[0]!)
    expect(versionCells[0]).not.toHaveTextContent('Actief')
    expect(versionCells[1]).toHaveTextContent('Actief')
    expect(versionCells[2]).not.toHaveTextContent('Actief')
  })

  it('every row has its own "Openen" button', async () => {
    answers([v3, v2, v1])
    renderPage()

    await screen.findByText('v3')

    expect(screen.getAllByRole('button', { name: 'Openen' })).toHaveLength(3)
  })

  it('shows "—" for a missing date or author', async () => {
    answers([{ ...v3, createdAt: null, createdBy: null }])
    renderPage()

    await screen.findByText('v3')

    const cells = within(bodyRows()[0]!).getAllByRole('cell')
    expect(cells[2]).toHaveTextContent('—')
    expect(cells[3]).toHaveTextContent('—')
  })

  it('without versions it says there are no versions yet', async () => {
    answers([])
    renderPage()

    expect(await screen.findByText('Er zijn nog geen versies voor dit mapping package.')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows an error with "Opnieuw proberen" when the versions cannot be loaded, and retrying works', async () => {
    answers(new Error('HTTP 502'), [v3, v2, v1])
    renderPage()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('De versies konden niet geladen worden.')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()

    await userEvent.click(within(alert).getByRole('button', { name: 'Opnieuw proberen' }))

    expect(await screen.findByText('v3')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('keeps showing the error when retrying fails again', async () => {
    answers(new Error('HTTP 502'))
    renderPage()

    const alert = await screen.findByRole('alert')
    await userEvent.click(within(alert).getByRole('button', { name: 'Opnieuw proberen' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('De versies konden niet geladen worden.')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})