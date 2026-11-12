import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Mock, MockInstance } from 'vitest'
import ProposalPage from '../../pages/ProposalPage'
import { approveProposal, deleteProposal, getProposalFile } from '../../services/proposalService'
import { useProposalStore } from '../../stores/proposalStore'
import type { Proposal } from '../../types/proposal'

vi.mock('../../services/proposalService', () => ({
  getProposal: vi.fn(),
  getProposalFile: vi.fn(),
  uploadProposalFile: vi.fn(),
  approveProposal: vi.fn(),
  deleteProposal: vi.fn(),
}))

const PROPOSAL: Proposal = {
  klant: 'brunos',
  versie: 2,
  status: 'Klaar om na te kijken',
  geupload: '2026-10-30T10:00:00',
  mappings: [{ id: 'MP-001', bronveld: 'Klant/Nummer', doelveld: 'Klantnummer', zekerheid: 92, opmerking: '' }],
}

const FILE = {
  company: 'brunos',
  version: 'v2',
  filename: 'MProposal-brunos_V2.xlsx',
  fullPath: '/Proposals/brunos/v2/MProposal-brunos_V2.xlsx',
  contentType: 'application/test',
  sizeBytes: 5,
  createdDate: '2026-10-30T10:00:00',
  createdBy: 'ai',
  fileContentBase64: btoa('hello'),
}

type Props = Parameters<typeof ProposalPage>[0]

function renderPage(props: Props = {}, url = '/proposals/brunos') {
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/proposals/:company" element={<ProposalPage {...props} />} />
        <Route path="/proposals" element={<ProposalPage {...props} />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ProposalPage actions', () => {
  let createObjectURL: Mock<(blob: Blob) => string>
  let revokeObjectURL: Mock<(url: string) => void>
  let anchorClick: MockInstance<() => void>

  beforeEach(() => {
    useProposalStore.setState({ proposal: PROPOSAL, loading: false, error: null, fetchProposal: vi.fn() })
    // jsdom has no object URLs and does not navigate on a link click
    createObjectURL = vi.fn<(blob: Blob) => string>(() => 'blob:test')
    revokeObjectURL = vi.fn<(url: string) => void>()
    Object.assign(URL, { createObjectURL, revokeObjectURL })
    anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.mocked(getProposalFile).mockReset()
    vi.restoreAllMocks()
  })

  it('calls onDownload instead of downloading itself', async () => {
    // Arrange
    const onDownload = vi.fn()
    renderPage({ onDownload })

    // Act
    await userEvent.click(screen.getByRole('button', { name: 'Download Excel' }))

    // Assert
    expect(onDownload).toHaveBeenCalledTimes(1)
    expect(getProposalFile).not.toHaveBeenCalled()
  })

  it('downloads the Excel of the shown version', async () => {
    // Arrange
    vi.mocked(getProposalFile).mockResolvedValue(FILE)
    renderPage()

    // Act
    await userEvent.click(screen.getByRole('button', { name: 'Download Excel' }))

    // Assert
    await waitFor(() => expect(anchorClick).toHaveBeenCalledTimes(1))
    expect(getProposalFile).toHaveBeenCalledWith('brunos', 'v2')
    const blob = createObjectURL.mock.calls[0]?.[0] as Blob
    expect(blob.type).toBe('application/test')
    expect(blob.size).toBe(5)
    const link = anchorClick.mock.contexts[0] as unknown as HTMLAnchorElement
    expect(link.download).toBe('MProposal-brunos_V2.xlsx')
    expect(link.href).toBe('blob:test')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test')
    expect(document.querySelector('a[download]')).toBeNull()
  })

  it('uses a default file name and Excel type when the API leaves them out', async () => {
    // Arrange
    vi.mocked(getProposalFile).mockResolvedValue({ ...FILE, filename: '', contentType: '' })
    renderPage()

    // Act
    await userEvent.click(screen.getByRole('button', { name: 'Download Excel' }))

    // Assert
    await waitFor(() => expect(anchorClick).toHaveBeenCalledTimes(1))
    const blob = createObjectURL.mock.calls[0]?.[0] as Blob
    expect(blob.type).toBe('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    const link = anchorClick.mock.contexts[0] as unknown as HTMLAnchorElement
    expect(link.download).toBe('MProposal-brunos_v2.xlsx')
  })

  it('does nothing when the file has no content', async () => {
    // Arrange
    vi.mocked(getProposalFile).mockResolvedValue({ ...FILE, fileContentBase64: '' })
    renderPage()

    // Act
    await userEvent.click(screen.getByRole('button', { name: 'Download Excel' }))

    // Assert
    await waitFor(() => expect(getProposalFile).toHaveBeenCalled())
    expect(createObjectURL).not.toHaveBeenCalled()
    expect(anchorClick).not.toHaveBeenCalled()
  })

  it('logs an error when the file cannot be fetched', async () => {
    // Arrange
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const error = new Error('Bestand kon niet worden opgehaald (status 500)')
    vi.mocked(getProposalFile).mockRejectedValue(error)
    renderPage()

    // Act
    await userEvent.click(screen.getByRole('button', { name: 'Download Excel' }))

    // Assert
    await waitFor(() =>
      expect(consoleError).toHaveBeenCalledWith('Failed to download proposal Excel file:', error),
    )
    expect(anchorClick).not.toHaveBeenCalled()
  })

  it('calls onUpload when "Aangepaste Excel uploaden" is clicked', async () => {
    // Arrange
    const onUpload = vi.fn()
    renderPage({ onUpload })

    // Act
    await userEvent.click(screen.getByRole('button', { name: 'Aangepaste Excel uploaden' }))

    // Assert
    expect(onUpload).toHaveBeenCalledTimes(1)
  })

  it('calls onApprove when "Goedkeuren" is clicked', async () => {
    // Arrange
    const onApprove = vi.fn()
    renderPage({ onApprove })

    // Act
    await userEvent.click(screen.getByRole('button', { name: 'Goedkeuren' }))

    // Assert
    expect(onApprove).toHaveBeenCalledTimes(1)
  })

  it('calls approveProposal with company and version when "Goedkeuren" is clicked without onApprove prop', async () => {
    // Arrange
    vi.mocked(approveProposal).mockResolvedValue(undefined)
    renderPage()

    // Act
    await userEvent.click(screen.getByRole('button', { name: 'Goedkeuren' }))

    // Assert
    await waitFor(() =>
      expect(approveProposal).toHaveBeenCalledWith('brunos', 'v2'),
    )
  })

  it('displays the error banner when approving fails', async () => {
    // Arrange
    const errorMsg = "Approving proposal for company 'brunos' and version 'v2' is not implemented yet"
    vi.mocked(approveProposal).mockRejectedValue(new Error(errorMsg))
    renderPage()

    // Act
    await userEvent.click(screen.getByRole('button', { name: 'Goedkeuren' }))

    // Assert
    await waitFor(() => {
      const alert = screen.getByRole('alert')
      expect(alert).toBeInTheDocument()
      expect(alert).toHaveTextContent(errorMsg)
    })
  })

  it('calls onDelete when "Verwijderen" is clicked with prop', async () => {
    // Arrange
    const onDelete = vi.fn()
    renderPage({ onDelete })

    // Act
    await userEvent.click(screen.getByRole('button', { name: 'Verwijderen' }))

    // Assert
    expect(onDelete).toHaveBeenCalledTimes(1)
  })

  it('opens delete confirmation dialog when "Verwijderen" is clicked', async () => {
    // Arrange
    renderPage()

    // Act
    await userEvent.click(screen.getByRole('button', { name: 'Verwijderen' }))

    // Assert
    expect(screen.getByText(/Are you sure you want to delete this/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Proceed' })).toBeDisabled()
  })

  it('sends delete request with entered deleteCheck when Proceed is clicked', async () => {
    // Arrange
    vi.mocked(deleteProposal).mockResolvedValue(undefined)
    renderPage()

    // Act
    await userEvent.click(screen.getByRole('button', { name: 'Verwijderen' }))
    const input = screen.getByPlaceholderText('brunos')
    await userEvent.type(input, 'brunos')

    const proceedBtn = screen.getByRole('button', { name: 'Proceed' })
    expect(proceedBtn).toBeEnabled()
    await userEvent.click(proceedBtn)

    // Assert
    await waitFor(() => {
      expect(deleteProposal).toHaveBeenCalledWith('brunos', 'v2', 'brunos')
    })
  })

  it('displays error banner when delete fails', async () => {
    // Arrange
    const errorMsg = "Confirmation check failed: deleteCheck ('wrong') must match company name ('brunos')"
    vi.mocked(deleteProposal).mockRejectedValue(new Error(errorMsg))
    renderPage()

    // Act
    await userEvent.click(screen.getByRole('button', { name: 'Verwijderen' }))
    const input = screen.getByPlaceholderText('brunos')
    await userEvent.type(input, 'wrong')
    await userEvent.click(screen.getByRole('button', { name: 'Proceed' }))

    // Assert
    await waitFor(() => {
      const alert = screen.getByRole('alert')
      expect(alert).toBeInTheDocument()
      expect(alert).toHaveTextContent(errorMsg)
    })
  })

  it('closes delete dialog when Annuleren is clicked', async () => {
    // Arrange
    renderPage()

    // Act
    await userEvent.click(screen.getByRole('button', { name: 'Verwijderen' }))
    expect(screen.getByText(/Are you sure you want to delete this/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Annuleren' }))

    // Assert
    expect(screen.queryByText(/Are you sure you want to delete this/i)).not.toBeInTheDocument()
  })

  it('shows a dash for an invalid upload date', () => {
    // Arrange
    useProposalStore.setState({ proposal: { ...PROPOSAL, geupload: 'geen datum' } })

    // Act
    renderPage()

    // Assert
    expect(screen.getByText('Geüpload op —')).toBeInTheDocument()
  })

  it('shows nothing when there is no proposal', () => {
    // Arrange
    useProposalStore.setState({ proposal: null })

    // Act
    renderPage()

    // Assert
    expect(screen.queryByRole('main')).not.toBeInTheDocument()
  })

  it('does not fetch anything without a company in the url', () => {
    // Act
    renderPage({}, '/proposals')

    // Assert
    expect(useProposalStore.getState().fetchProposal).not.toHaveBeenCalled()
  })

  it('links back to the home page', () => {
    // Act
    renderPage()

    // Assert
    expect(screen.getByRole('link', { name: 'Home' })).toHaveAttribute('href', '/')
  })
})
