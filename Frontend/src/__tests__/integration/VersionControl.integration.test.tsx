// Mapping packages overview on Version Control – integration test: the Version Control page, the
// mapping package store and the real API service together. Only the network (fetch) is replaced
// by a fake backend that answers like the Version_Control API (GET /packages).
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import VersionControl from '../../pages/VersionControl'
import type { MappingPackageOverview } from '../../services/mappingPackageOverviewService'
import { useMappingPackageStore } from '../../stores/mappingPackageStore'

// createdAt without timezone: shown as is, whatever the timezone of the test machine
const brevalis: MappingPackageOverview = {
  company: 'brevalis',
  latestVersion: 'v4',
  createdAt: '2026-10-11T14:32:00',
  createdBy: 'analist_b',
  customerName: 'Brevalis',
  packageType: 'outbound',
}
const nouryonInbound: MappingPackageOverview = {
  company: 'nouryon',
  latestVersion: 'v2',
  createdAt: '2026-11-12T10:00:00',
  createdBy: 'analist_a',
  customerName: 'Nouryon',
  packageType: 'inbound',
}
const nouryonOutbound: MappingPackageOverview = {
  company: 'nouryon',
  latestVersion: 'v1',
  createdAt: '2026-10-02T09:15:00',
  createdBy: 'analist_a',
  customerName: 'Nouryon',
  packageType: 'outbound',
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

// Fake backend: GET /api/version-control/packages returns the current list.
function fakeBackend(packages: MappingPackageOverview[]) {
  const fetchMock = vi.fn(async (url: string) => {
    if (url.endsWith('/packages')) return json(packages)
    return json({ detail: 'not found' }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function renderPage() {
  render(
    <MemoryRouter>
      <VersionControl />
    </MemoryRouter>,
  )
}

function rowOf(cellText: string, index = 0) {
  return screen.getAllByText(cellText, { selector: 'td' })[index]?.closest('tr') as HTMLElement
}

beforeEach(() => {
  // Every test starts with an empty store: the list of the previous test must not stay behind
  useMappingPackageStore.setState({ packages: null, loading: false, error: null })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Version Control – mapping packages overview', () => {
  it('Version Control loads the packages from the API and shows them in the list', async () => {
    const fetchMock = fakeBackend([brevalis])
    renderPage()

    await screen.findByText('Brevalis', { selector: 'td' })
    const row = rowOf('Brevalis')
    expect(within(row).getByText('outbound')).toBeInTheDocument()
    expect(within(row).getByText('v4')).toBeInTheDocument()
    expect(within(row).getByText('11/10/2026 14:32')).toBeInTheDocument()
    expect(within(row).getByText('door analist_b')).toBeInTheDocument()
    expect(within(row).getByRole('button', { name: 'Bekijken' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/version-control/packages', expect.anything())
  })

  it('shows the columns KLANT, TYPE, ACTIEVE VERSIE, LAATSTE WIJZIGING and ACTIE in that order', async () => {
    fakeBackend([brevalis])
    renderPage()
    await screen.findByText('Brevalis', { selector: 'td' })

    const headers = screen.getAllByRole('columnheader').map((th) => th.textContent)
    expect(headers).toEqual(['KLANT', 'TYPE', 'ACTIEVE VERSIE', 'LAATSTE WIJZIGING', 'ACTIE'])
  })

  it('a company with several package types is listed once per type with the latest version of that type', async () => {
    fakeBackend([brevalis, nouryonInbound, nouryonOutbound])
    renderPage()
    await screen.findAllByText('Nouryon', { selector: 'td' })

    expect(screen.getAllByText('Nouryon', { selector: 'td' })).toHaveLength(2)
    const inbound = rowOf('Nouryon', 0)
    expect(within(inbound).getByText('inbound')).toBeInTheDocument()
    expect(within(inbound).getByText('v2')).toBeInTheDocument()
    const outbound = rowOf('Nouryon', 1)
    expect(within(outbound).getByText('outbound')).toBeInTheDocument()
    expect(within(outbound).getByText('v1')).toBeInTheDocument()
  })

  it('shows the packages in the order the backend sends them (alphabetical)', async () => {
    fakeBackend([brevalis, nouryonInbound, nouryonOutbound])
    renderPage()
    await screen.findByText('Brevalis', { selector: 'td' })

    const customers = screen.getAllByRole('row').slice(1).map((tr) => within(tr).getAllByRole('cell')[0]?.textContent)
    expect(customers).toEqual(['Brevalis', 'Nouryon', 'Nouryon'])
  })

  it('shows the company folder and "—" when the package has no customer name, type or date', async () => {
    fakeBackend([
      { company: 'quorvia', latestVersion: 'v1', createdAt: null, createdBy: null, customerName: null, packageType: null },
    ])
    renderPage()

    await screen.findByText('quorvia', { selector: 'td' })
    const row = rowOf('quorvia')
    expect(within(row).getAllByText('—')).toHaveLength(2)
    expect(within(row).queryByText(/^door /)).not.toBeInTheDocument()
  })

  it('shows a loading message while the packages are being loaded', async () => {
    let answer: (response: Response) => void = () => {}
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => { answer = resolve })))
    renderPage()

    expect(await screen.findByText('Mapping packages laden…')).toBeInTheDocument()

    answer(json([brevalis]))
    expect(await screen.findByText('Brevalis', { selector: 'td' })).toBeInTheDocument()
    expect(screen.queryByText('Mapping packages laden…')).not.toBeInTheDocument()
  })

  it('shows a message when there are no mapping packages yet', async () => {
    fakeBackend([])
    renderPage()

    expect(await screen.findByText('Er zijn nog geen mapping packages.')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('Version Control shows the error message when the backend cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    renderPage()

    expect(await screen.findByText('De mapping packages konden niet geladen worden.')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('Version Control shows the error message when the backend answers with an error (HTTP 502)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ title: 'SFTP Storage Error' }, 502)))
    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('De mapping packages konden niet geladen worden.')
  })

  it('"Opnieuw proberen" loads the packages again and shows them', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(json([brevalis]))
    vi.stubGlobal('fetch', fetchMock)
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Opnieuw proberen' }))

    expect(await screen.findByText('Brevalis', { selector: 'td' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
