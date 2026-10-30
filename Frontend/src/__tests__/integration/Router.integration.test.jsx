import React from 'react'
import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import router from '../../router/index'

describe('Integration Tests - Router & Page Resolution', () => {
  it('defines the root route in the application router configuration', () => {
    expect(router).toBeDefined()
    expect(Array.isArray(router.routes)).toBe(true)
    expect(router.routes[0].path).toBe('/')
  })

  it('mounts and renders the root route via RouterProvider', () => {
    const memoryRouter = createMemoryRouter(router.routes, {
      initialEntries: ['/'],
    })
    render(<RouterProvider router={memoryRouter} />)
    expect(screen.getByTestId('home-page')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /essers mapping/i })).toBeInTheDocument()
  })
})
