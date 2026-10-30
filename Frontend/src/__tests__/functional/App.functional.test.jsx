import React from 'react'
import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import router from '../../router/index'

describe('Functional Tests - User Interactions & Workflows', () => {
  it('renders the Home page layout and navigation properly at root path', () => {
    const memoryRouter = createMemoryRouter(router.routes, {
      initialEntries: ['/'],
    })
    render(<RouterProvider router={memoryRouter} />)

    expect(screen.getByTestId('home-page')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /essers mapping/i })).toBeInTheDocument()
    expect(screen.getByText(/welcome to essers mapping platform/i)).toBeInTheDocument()
  })
})
