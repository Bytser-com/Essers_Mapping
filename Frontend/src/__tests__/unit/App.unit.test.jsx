import React from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, beforeEach } from 'vitest'
import App from '../../App'
import Home from '../../pages/Home'
import { useProposalStore } from '../../stores/proposalStore'

describe('Unit Tests - Frontend Components', () => {
  beforeEach(() => {
    useProposalStore.setState({ deleteSuccessMessage: null })
  })

  it('renders the main App container layout', () => {
    const { container } = render(
      <MemoryRouter>
        <App />
      </MemoryRouter>
    )
    expect(container.firstChild).toBeInTheDocument()
    expect(container.firstChild).toHaveClass('min-h-screen')
  })

  it('renders the Home page component with expected heading', () => {
    render(<Home />)
    expect(screen.getByTestId('home-page')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Home' })).toBeInTheDocument()
  })

  it('renders the deletion success message banner when deleteSuccessMessage is in the store', () => {
    useProposalStore.setState({
      deleteSuccessMessage: 'Voorstel voor vanroey (v2) is succesvol verwijderd.',
    })
    render(<Home />)
    const banner = screen.getByTestId('delete-success-banner')
    expect(banner).toBeInTheDocument()
    expect(screen.getByText('Voorstel succesvol verwijderd.')).toBeInTheDocument()
    expect(screen.getByText('Voorstel voor vanroey (v2) is succesvol verwijderd.')).toBeInTheDocument()
  })

  it('dismisses the deletion success banner when the close button is clicked', async () => {
    useProposalStore.setState({
      deleteSuccessMessage: 'Voorstel voor vanroey (v2) is succesvol verwijderd.',
    })
    render(<Home />)
    expect(screen.getByTestId('delete-success-banner')).toBeInTheDocument()

    const closeBtn = screen.getByRole('button', { name: 'Melding sluiten' })
    await userEvent.click(closeBtn)

    expect(screen.queryByTestId('delete-success-banner')).not.toBeInTheDocument()
    expect(useProposalStore.getState().deleteSuccessMessage).toBeNull()
  })
})
