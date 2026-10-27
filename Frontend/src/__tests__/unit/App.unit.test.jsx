import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from '../../App'
import Home from '../../pages/Home'

describe('Unit Tests - Frontend Components', () => {
  it('renders the main App heading and initial counter state', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: /get started/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /count is 0/i })).toBeInTheDocument()
  })

  it('renders the Documentation and Connect sections', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: /documentation/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /connect with us/i })).toBeInTheDocument()
  })

  it('renders the Home page component with expected heading', () => {
    render(<Home />)
    expect(screen.getByTestId('home-page')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /essers mapping/i })).toBeInTheDocument()
  })
})
