import React from 'react'
import { render, screen } from '@testing-library/react'
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
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/proposals/brunos'))
  })

  it('shows the error when the API returns 404', async () => {
    // Arrange
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }))

    // Act
    renderPage()

    // Assert
    expect(await screen.findByText('geen mapping gevonden (status 404)')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/proposals/brunos'))
  })

  it('shows the error when the API returns 503', async () => {
    // Arrange
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }))

    // Act
    renderPage()

    // Assert
    expect(await screen.findByText('De bestanden zijn tijdelijk niet bereikbaar (status 503)')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/proposals/brunos'))
  })
})