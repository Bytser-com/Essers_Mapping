import React from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from '../../App'

describe('Functional Tests - User Interactions & Workflows', () => {
  it('increments the interactive counter across multiple user clicks', async () => {
    const user = userEvent.setup()
    render(<App />)

    const button = screen.getByRole('button', { name: /count is 0/i })
    await user.click(button)
    expect(button).toHaveTextContent('Count is 1')

    await user.click(button)
    await user.click(button)
    expect(button).toHaveTextContent('Count is 3')
  })

  it('exposes valid external documentation links for Vite and React', () => {
    render(<App />)
    const viteLink = screen.getByRole('link', { name: /explore vite/i })
    const reactLink = screen.getByRole('link', { name: /learn more/i })

    expect(viteLink).toHaveAttribute('href', 'https://vite.dev/')
    expect(reactLink).toHaveAttribute('href', 'https://react.dev/')
  })
})
