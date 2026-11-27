// Version history of one mapping package – integration test: the PackageVersions page, the
// mapping package store and the real API service together. Only the network (fetch) is replaced
// by a fake backend that answers like the Version_Control API (GET /packages/versions).
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import PackageVersions from '../../pages/PackageVersions'
import type { PackageVersion } from '../../services/mappingPackageOverviewService'
import { useMappingPackageStore } from '../../stores/mappingPackageStore'

// createdAt without timezone: shown as is, whatever the timezone of the test machine
const v3: PackageVersion = {
  version: 'v3',
  isActive: false,
  createdAt: '2026-11-12T10:00:00',
  createdBy: 'analist_a',
  description: '2 mappings gewijzigd',
}
const v2: PackageVersion = {
  version: 'v2',
  isActive: true,
  createdAt: '2026-10-02T09:15:00',
  createdBy: 'analist_b',
  description: '1 mapping toegevoegd',
}
const v1: PackageVersion = {
  version: 'v1',
  isActive: false,
  createdAt: '2026-09-29T09:30:00',
  createdBy: 'analist_a',
  description: 'Eerste versie',
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

// Fake backend: GET /api/version-control/packages/versions returns the versions of the package.
function fakeBackend(versions: PackageVersion[]) {
  const fetchMock = vi.fn(async (url: string) => {
    if (url.includes('/packages/versions')) return json(versions)
    return json({ detail: 'not found' }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={['/package-versions/brevalis/inbound']}>
      <Routes>
        <Route path="/package-versions/:company/:packageType" element={<PackageVersions />} />
      </Routes>
    </MemoryRouter>,
  )
}

function rowOf(cellText: string, index = 0) {
  return screen.getAllByText(cellText)[index]?.closest('tr') as HTMLElement
}

beforeEach(() => {
  // Every test starts with an empty store: the versions of the previous test must not stay behind
  useMappingPackageStore.setState({ versions: null, versionsLoading: false, versionsError: null })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Version Control – version history of a mapping package', () => {
  it('the page loads the versions of the company and type from the API and shows them in the list', async () => {
    const fetchMock = fakeBackend([v3])
    renderPage()

    await screen.findByText('v3')
    const row = rowOf('v3')
    expect(within(row).getByText('12/11/2026 10:00')).toBeInTheDocument()
    expect(within(row).getByText('analist_a')).toBeInTheDocument()
    expect(within(row).getByRole('button', { name: 'Openen' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/version-control/packages/versions?company=brevalis&packageType=inbound',
      expect.anything(),
    )
  })

  it('shows the columns VERSIE, OMSCHRIJVING, GOEDGEKEURD OP, DOOR and ACTIE in that order', async () => {
    fakeBackend([v3])
    renderPage()
    await screen.findByText('v3')

    const headers = screen.getAllByRole('columnheader').map((th) => th.textContent)
    expect(headers).toEqual(['VERSIE', 'OMSCHRIJVING', 'GOEDGEKEURD OP', 'DOOR', 'ACTIE'])
  })

  it('shows the active version from the backend next to the title and as label in its row', async () => {
    fakeBackend([v3, v2, v1])
    renderPage()

    expect(await screen.findByText('Actief: v2')).toBeInTheDocument()
    expect(screen.getByText('Mapping package · inbound · 3 versies')).toBeInTheDocument()
    expect(within(rowOf('v2')).getByText('Actief')).toBeInTheDocument()
    expect(within(rowOf('v3')).queryByText('Actief')).not.toBeInTheDocument()
  })

  it('shows the versions in the order the backend sends them (newest first)', async () => {
    fakeBackend([v3, v2, v1])
    renderPage()
    await screen.findByText('v3')

    const dates = screen.getAllByRole('row').slice(1).map((tr) => within(tr).getAllByRole('cell')[2]?.textContent)
    expect(dates).toEqual(['12/11/2026 10:00', '02/10/2026 09:15', '29/09/2026 09:30'])
  })

  it('every version shows its own description from the backend', async () => {
    fakeBackend([v3, v2, v1])
    renderPage()
    await screen.findByText('v3')

    const descriptions = screen.getAllByRole('row').slice(1).map((tr) => within(tr).getAllByRole('cell')[1]?.textContent)
    expect(descriptions).toEqual(['2 mappings gewijzigd', '1 mapping toegevoegd', 'Eerste versie'])
  })

  it('shows "—" when the backend sends no description', async () => {
    fakeBackend([{ ...v3, description: null }])
    renderPage()

    await screen.findByText('v3')
    expect(within(rowOf('v3')).getAllByRole('cell')[1]).toHaveTextContent('—')
  })

  it('shows "—" when the version has no date or author', async () => {
    fakeBackend([{ ...v3, createdAt: null, createdBy: null }])
    renderPage()

    await screen.findByText('v3')
    const cells = within(rowOf('v3')).getAllByRole('cell')
    expect(cells[2]).toHaveTextContent('—')
    expect(cells[3]).toHaveTextContent('—')
  })

  it('shows a loading message while the versions are being loaded', async () => {
    let answer: (response: Response) => void = () => { }
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => { answer = resolve })))
    renderPage()

    expect(await screen.findByText('Versies laden…')).toBeInTheDocument()

    answer(json([v3]))
    expect(await screen.findByText('v3')).toBeInTheDocument()
    expect(screen.queryByText('Versies laden…')).not.toBeInTheDocument()
  })

  it('shows a message when the package has no versions yet', async () => {
    fakeBackend([])
    renderPage()

    expect(await screen.findByText('Er zijn nog geen versies voor dit mapping package.')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('the page shows the error message when the backend cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    renderPage()

    expect(await screen.findByText('De versies konden niet geladen worden.')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('the page shows the error message when the backend answers with an error (HTTP 502)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ title: 'SFTP Storage Error' }, 502)))
    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('De versies konden niet geladen worden.')
  })

  it('"Opnieuw proberen" loads the versions again and shows them', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(json([v3]))
    vi.stubGlobal('fetch', fetchMock)
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Opnieuw proberen' }))

    expect(await screen.findByText('v3')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})