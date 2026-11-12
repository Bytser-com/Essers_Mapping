import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ProposalPage from '../../pages/ProposalPage'
import { useProposalStore } from '../../stores/proposalStore'

const PROPOSAL = {
  klant: 'brunos',
  versie: 1,
  status: 'Klaar om na te kijken',
  geupload: '2026-10-30T10:00:00',
  mappings: [{ id: 'MP-001', bronveld: 'Klant/Nummer', doelveld: 'Klantnummer', zekerheid: 92, opmerking: '' }],
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={['/proposals/brunos']}>
      <Routes>
        <Route path="/proposals/:company" element={<ProposalPage />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('ProposalPage integration', () => {
  beforeEach(() => {
    useProposalStore.setState({ proposal: null, loading: false, error: null })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows the proposal returned by the API', async () => {
    // Arrange
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => PROPOSAL }))

    // Act
    renderPage()

    // Assert
    expect(await screen.findByText('brunos · v1')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/proposals?company=brunos'))
  })

  it('shows the error when the API returns 404', async () => {
    // Arrange
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }))

    // Act
    renderPage()

    // Assert
    expect(await screen.findByText('geen mapping gevonden (status 404)')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/proposals?company=brunos'))
  })

  it('shows the error when the API returns 503', async () => {
    // Arrange
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }))

    // Act
    renderPage()

    // Assert
    expect(await screen.findByText('De bestanden zijn tijdelijk niet bereikbaar (status 503)')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/proposals?company=brunos'))
  })

  it('displays the 501 error alert banner when clicking Goedkeuren', async () => {
    // Arrange
    const problemDetail = {
      type: 'about:blank',
      title: 'Not Implemented',
      status: 501,
      detail: "Approving proposal for company 'brunos' and version 'v1' is not implemented yet",
      company: 'brunos',
      version: 'v1',
    }

    const fetchMock = vi.fn().mockImplementation((url, options) => {
      if (options?.method === 'POST') {
        return Promise.resolve({
          ok: false,
          status: 501,
          json: async () => problemDetail,
        })
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => PROPOSAL,
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    // Act
    renderPage()
    expect(await screen.findByText('brunos · v1')).toBeInTheDocument()

    const button = screen.getByRole('button', { name: 'Goedkeuren' })
    await userEvent.click(button)

    // Assert
    await waitFor(() => {
      const alert = screen.getByRole('alert')
      expect(alert).toBeInTheDocument()
      expect(alert).toHaveTextContent(
        "Approving proposal for company 'brunos' and version 'v1' is not implemented yet"
      )
    })

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/proposals?company=brunos&version=v1'),
      { method: 'POST' }
    )
  })
})