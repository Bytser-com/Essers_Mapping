import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import ProposalResetPage from '../../pages/ProposalResetPage'
import { useHomeStore } from '../../stores/homeStore'

const mockNavigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

describe('ProposalResetPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok', retried_count: 1 }),
    }))
  })

  it('renders resetting indicator, calls both AI endpoints and redirects to /', async () => {
    const fetchProposalsMock = vi.fn().mockResolvedValue(undefined)
    useHomeStore.setState({ fetchProposals: fetchProposalsMock })

    render(
      <MemoryRouter>
        <ProposalResetPage />
      </MemoryRouter>
    )

    expect(screen.getByTestId('reset-spinner')).toBeInTheDocument()
    expect(screen.getByText('AI processen opnieuw opstarten…')).toBeInTheDocument()

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith('/api/proposal/ai-retry', { method: 'POST' })
      expect(global.fetch).toHaveBeenCalledWith('/api/converter/ai-retry', { method: 'POST' })
      expect(fetchProposalsMock).toHaveBeenCalled()
      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true })
    })
  })
})
