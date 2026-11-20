// Mapping packages overview on Version Control – functional tests for src/pages/VersionControl.tsx:
// loading, the table with one row per company and package type, empty list, error + retry.
// The backend is replaced by a mock of fetchPackages; the list lives in stores/mappingPackageStore.ts.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import VersionControl from '../../pages/VersionControl'
import { fetchPackages, type MappingPackageOverview } from '../../services/mappingPackageOverviewService'
import { useMappingPackageStore } from '../../stores/mappingPackageStore'

// Keep the real types and helpers but replace the API call
vi.mock('../../services/mappingPackageOverviewService', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/mappingPackageOverviewService')>()),
  fetchPackages: vi.fn(),
}))

const fetchMock = vi.mocked(fetchPackages)

// createdAt without timezone: shown as is, whatever the timezone of the test machine
const brevalis: MappingPackageOverview = {
  company: 'brevalis',
  latestVersion: 'v4',
  createdAt: '2026-10-11T14:32:00',
  createdBy: 'Analist B',
  customerName: 'Brevalis',
  packageType: 'outbound',
}
const nouryonInbound: MappingPackageOverview = {
  company: 'nouryon',
  latestVersion: 'v2',
  createdAt: '2026-11-12T10:00:00',
  createdBy: 'Analist A',
  customerName: 'Nouryon',
  packageType: 'inbound',
}
const nouryonOutbound: MappingPackageOverview = { ...nouryonInbound, latestVersion: 'v1', packageType: 'outbound' }

// The fake backend answers with the given lists in order; the last one keeps repeating.
function answers(...responses: Array<MappingPackageOverview[] | Error>) {
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

describe('VersionControl', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    // Every test starts with an empty store
    useMappingPackageStore.setState({ packages: null, loading: false, error: null })
  })

  it('shows the title, the explanation and the search field', () => {
    fetchMock.mockImplementation(() => new Promise<MappingPackageOverview[]>(() => {}))
    render(<VersionControl />)

    expect(screen.getByRole('heading', { name: 'Version Control' })).toBeInTheDocument()
    expect(screen.getByText('Alle klanten en hun mapping packages.')).toBeInTheDocument()
    expect(screen.getByRole('searchbox', { name: 'Zoek een klant op naam' })).toBeInTheDocument()
  })

  it('shows "Mapping packages laden…" while the list is loading', () => {
    fetchMock.mockImplementation(() => new Promise<MappingPackageOverview[]>(() => {}))
    render(<VersionControl />)

    expect(screen.getByText('Mapping packages laden…')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('loads all packages once when the page opens', async () => {
    answers([brevalis])
    render(<VersionControl />)

    await screen.findByText('Brevalis')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(undefined)
  })

  it('shows the packages in a table with the columns KLANT, TYPE, ACTIEVE VERSIE, LAATSTE WIJZIGING and ACTIE', async () => {
    answers([brevalis, nouryonInbound])
    render(<VersionControl />)

    await screen.findByText('Brevalis')

    const headers = screen.getAllByRole('columnheader').map((th) => th.textContent)
    expect(headers).toEqual(['KLANT', 'TYPE', 'ACTIEVE VERSIE', 'LAATSTE WIJZIGING', 'ACTIE'])
    expect(screen.getAllByRole('row')).toHaveLength(3) // header + 2 rows
  })

  it('shows customer, type, version, date and author of a package in one row', async () => {
    answers([brevalis])
    render(<VersionControl />)

    await screen.findByText('Brevalis')

    const cells = within(bodyRows()[0]!).getAllByRole('cell')
    expect(cells[0]).toHaveTextContent('Brevalis')
    expect(cells[1]).toHaveTextContent('outbound')
    expect(cells[2]).toHaveTextContent('v4')
    expect(cells[3]).toHaveTextContent('11/10/2026 14:32')
    expect(cells[3]).toHaveTextContent('door Analist B')
    expect(within(cells[4]!).getByRole('button', { name: 'Bekijken' })).toBeInTheDocument()
  })

  it('shows a company once per package type, each with the latest version of that type', async () => {
    answers([brevalis, nouryonInbound, nouryonOutbound])
    render(<VersionControl />)

    await screen.findByText('Brevalis')

    const rows = bodyRows().map((tr) => within(tr).getAllByRole('cell').slice(0, 3).map((td) => td.textContent))
    expect(rows).toEqual([
      ['Brevalis', 'outbound', 'v4'],
      ['Nouryon', 'inbound', 'v2'],
      ['Nouryon', 'outbound', 'v1'],
    ])
  })

  it('every row has its own "Bekijken" button', async () => {
    answers([brevalis, nouryonInbound, nouryonOutbound])
    render(<VersionControl />)

    await screen.findByText('Brevalis')

    expect(screen.getAllByRole('button', { name: 'Bekijken' })).toHaveLength(3)
  })

  it('shows the company folder when the package has no customer name', async () => {
    answers([{ ...brevalis, customerName: null }])
    render(<VersionControl />)

    expect(await screen.findByText('brevalis')).toBeInTheDocument()
  })

  it('shows "—" for a missing type or date and leaves out "door" without author', async () => {
    answers([{ ...brevalis, packageType: null, createdAt: null, createdBy: null }])
    render(<VersionControl />)

    await screen.findByText('Brevalis')

    const cells = within(bodyRows()[0]!).getAllByRole('cell')
    expect(cells[1]).toHaveTextContent('—')
    expect(cells[3]).toHaveTextContent('—')
    expect(cells[3]).not.toHaveTextContent('door')
  })

  it('shows the full type as tooltip, since a long type is cut off', async () => {
    answers([{ ...brevalis, packageType: 'inbound-accept-delivery' }])
    render(<VersionControl />)

    expect(await screen.findByText('inbound-accept-delivery')).toHaveAttribute('title', 'inbound-accept-delivery')
  })

  it('without packages it says there are no mapping packages yet', async () => {
    answers([])
    render(<VersionControl />)

    expect(await screen.findByText('Er zijn nog geen mapping packages.')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows an error with "Opnieuw proberen" when the list cannot be loaded, and retrying works', async () => {
    answers(new Error('HTTP 502'), [brevalis])
    render(<VersionControl />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('De mapping packages konden niet geladen worden.')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()

    await userEvent.click(within(alert).getByRole('button', { name: 'Opnieuw proberen' }))

    expect(await screen.findByText('Brevalis')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('keeps showing the error when retrying fails again', async () => {
    answers(new Error('HTTP 502'))
    render(<VersionControl />)

    const alert = await screen.findByRole('alert')
    await userEvent.click(within(alert).getByRole('button', { name: 'Opnieuw proberen' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('De mapping packages konden niet geladen worden.')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  describe('search functionality', () => {
    beforeEach(async () => {
      answers([brevalis, nouryonInbound, nouryonOutbound])
      render(<VersionControl />)
      await screen.findByText('Brevalis')
    })

    it('filters packages by company / customer name', async () => {
      const searchInput = screen.getByRole('searchbox', { name: 'Zoek een klant op naam' })
      await userEvent.type(searchInput, 'brev')

      expect(screen.getByText('Brevalis')).toBeInTheDocument()
      expect(screen.queryByText('Nouryon')).not.toBeInTheDocument()
    })

    it('filters packages by package type', async () => {
      const searchInput = screen.getByRole('searchbox', { name: 'Zoek een klant op naam' })
      await userEvent.type(searchInput, 'inbound')

      expect(screen.getByText('Nouryon')).toBeInTheDocument()
      expect(screen.queryByText('Brevalis')).not.toBeInTheDocument()
      expect(bodyRows()).toHaveLength(1)
    })

    it('filters packages by version', async () => {
      const searchInput = screen.getByRole('searchbox', { name: 'Zoek een klant op naam' })
      await userEvent.type(searchInput, 'v4')

      expect(screen.getByText('Brevalis')).toBeInTheDocument()
      expect(screen.queryByText('Nouryon')).not.toBeInTheDocument()
    })

    it('filters packages by createdBy user name', async () => {
      const searchInput = screen.getByRole('searchbox', { name: 'Zoek een klant op naam' })
      await userEvent.type(searchInput, 'Analist A')

      expect(screen.queryByText('Brevalis')).not.toBeInTheDocument()
      expect(screen.getAllByText('Nouryon')).toHaveLength(2)
    })

    it('filters packages by creation date', async () => {
      const searchInput = screen.getByRole('searchbox', { name: 'Zoek een klant op naam' })
      // Brevalis date: 11/10/2026 14:32
      await userEvent.type(searchInput, '11/10')

      expect(screen.getByText('Brevalis')).toBeInTheDocument()
      expect(screen.queryByText('Nouryon')).not.toBeInTheDocument()
    })

    it('filters packages by combining company and type (e.g. "nouryon outbound")', async () => {
      const searchInput = screen.getByRole('searchbox', { name: 'Zoek een klant op naam' })
      await userEvent.type(searchInput, 'nouryon outbound')

      expect(bodyRows()).toHaveLength(1)
      const cells = within(bodyRows()[0]!).getAllByRole('cell')
      expect(cells[0]).toHaveTextContent('Nouryon')
      expect(cells[1]).toHaveTextContent('outbound')
    })

    it('filters packages by combining author and year (e.g. "Analist B 2026")', async () => {
      const searchInput = screen.getByRole('searchbox', { name: 'Zoek een klant op naam' })
      await userEvent.type(searchInput, 'Analist B 2026')

      expect(bodyRows()).toHaveLength(1)
      expect(screen.getByText('Brevalis')).toBeInTheDocument()
      expect(screen.queryByText('Nouryon')).not.toBeInTheDocument()
    })

    it('filters packages by combining multiple terms across fields (e.g. "nouryon inbound v2")', async () => {
      const searchInput = screen.getByRole('searchbox', { name: 'Zoek een klant op naam' })
      await userEvent.type(searchInput, 'nouryon inbound v2')

      expect(bodyRows()).toHaveLength(1)
      const cells = within(bodyRows()[0]!).getAllByRole('cell')
      expect(cells[0]).toHaveTextContent('Nouryon')
      expect(cells[1]).toHaveTextContent('inbound')
      expect(cells[2]).toHaveTextContent('v2')
    })

    it('shows empty search result message when no packages match criteria', async () => {
      const searchInput = screen.getByRole('searchbox', { name: 'Zoek een klant op naam' })
      await userEvent.type(searchInput, 'nonexistent')

      expect(screen.getByText('Geen mapping packages gevonden die voldoen aan de zoekcriteria.')).toBeInTheDocument()
      expect(bodyRows()).toHaveLength(1)
    })

    it('restores all packages when search input is cleared', async () => {
      const searchInput = screen.getByRole('searchbox', { name: 'Zoek een klant op naam' })
      await userEvent.type(searchInput, 'Brevalis')
      expect(bodyRows()).toHaveLength(1)

      await userEvent.clear(searchInput)
      expect(bodyRows()).toHaveLength(3)
    })
  })
})
