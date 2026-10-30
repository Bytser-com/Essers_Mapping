import React from 'react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../../App'
import Home from '../../pages/Home'

describe('Unit Tests - Frontend Components', () => {
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
    expect(screen.getByRole('heading', { name: /essers mapping/i })).toBeInTheDocument()
  })
})
