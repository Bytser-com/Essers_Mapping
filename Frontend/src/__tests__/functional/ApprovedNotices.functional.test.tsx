import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import ApprovedNotices from '../../components/ApprovedNotices'
import { useHomeStore } from '../../stores/homeStore'

function renderNotices() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<ApprovedNotices />} />
        <Route path="/version-control" element={<p>Version Control pagina</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ApprovedNotices (IT2627T06-187)', () => {
  beforeEach(() => {
    useHomeStore.setState({ approvedNotices: [] })
  })

  it('shows nothing without approved proposals', () => {
    // Act
    renderNotices()

    // Assert
    expect(screen.queryByTestId('approved-notice')).not.toBeInTheDocument()
  })

  it('tells the analyst the AI review passed and where the package is', () => {
    // Arrange
    useHomeStore.setState({ approvedNotices: [{ id: 'nouryon/v2', customer: 'Nouryon' }] })

    // Act
    renderNotices()

    // Assert
    const notice = screen.getByTestId('approved-notice')
    expect(notice).toHaveTextContent('De AI-controle is geslaagd.')
    expect(notice).toHaveTextContent(
      'Nouryon is goedgekeurd en omgezet naar een mapping package. Je vindt het in Version Control.',
    )
  })

  it('"Naar Version Control" opens Version Control and closes the notice', async () => {
    // Arrange
    useHomeStore.setState({ approvedNotices: [{ id: 'nouryon/v2', customer: 'Nouryon' }] })
    renderNotices()

    // Act
    await userEvent.click(screen.getByRole('button', { name: 'Naar Version Control' }))

    // Assert
    expect(screen.getByText('Version Control pagina')).toBeInTheDocument()
    expect(useHomeStore.getState().approvedNotices).toEqual([])
  })

  it('the close button removes the notice', async () => {
    // Arrange
    useHomeStore.setState({ approvedNotices: [{ id: 'nouryon/v2', customer: 'Nouryon' }] })
    renderNotices()

    // Act
    await userEvent.click(screen.getByRole('button', { name: 'Melding sluiten' }))

    // Assert
    expect(screen.queryByTestId('approved-notice')).not.toBeInTheDocument()
  })
})
