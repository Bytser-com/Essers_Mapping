import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import App from '../../App'
import InterfaceUpload from '../../components/InterfaceUpload'
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
    expect(screen.getByRole('heading', { name: 'Home' })).toBeInTheDocument()
  })

  it('does not upload a file when no customer is selected', () => {
    const onUpload = vi.fn()
    render(<InterfaceUpload onUpload={onUpload} />)

    const file = new File(['<interface />'], 'interface.xml', { type: 'text/xml' })
    fireEvent.change(screen.getByTestId('file-input'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: 'Uploaden' }))

    expect(onUpload).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(/selecteer eerst een klant/i)
  })

  it('uploads an XML file when a customer is provided', () => {
    const onUpload = vi.fn()
    render(<InterfaceUpload onUpload={onUpload} />)

    const file = new File(['<interface />'], 'interface.xml', { type: 'text/xml' })
    fireEvent.change(screen.getByLabelText('Klantnaam'), { target: { value: 'Klant A' } })
    fireEvent.change(screen.getByTestId('file-input'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: 'Uploaden' }))

    expect(onUpload).toHaveBeenCalledWith(file)
  })
})
