import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import InterfaceUpload from '../../components/InterfaceUpload'

function xmlFile(name = 'order.xml') {
  return new File(['<Order/>'], name, { type: 'text/xml' })
}

function renderUpload(onUpload?: (customer: string, files: File[]) => void | Promise<void>) {
  render(<InterfaceUpload onUpload={onUpload} />)
  return {
    customer: screen.getByLabelText('Klantnaam'),
    fileInput: screen.getByTestId('file-input') as HTMLInputElement,
    uploadButton: screen.getByRole('button', { name: 'Uploaden' }),
  }
}

function chooseFiles(input: HTMLInputElement, files: File[]) {
  fireEvent.change(input, { target: { files } })
}

describe('InterfaceUpload', () => {
  it('asks for a customer name when it is empty', async () => {
    // Arrange
    const onUpload = vi.fn()
    const { fileInput, uploadButton } = renderUpload(onUpload)
    chooseFiles(fileInput, [xmlFile()])

    // Act
    await userEvent.click(uploadButton)

    // Assert
    expect(screen.getByRole('alert')).toHaveTextContent('Vul eerst een klant in.')
    expect(onUpload).not.toHaveBeenCalled()
  })

  it('treats a name with only spaces as empty', async () => {
    // Arrange
    const { customer, uploadButton } = renderUpload(vi.fn())
    await userEvent.type(customer, '   ')

    // Act
    await userEvent.click(uploadButton)

    // Assert
    expect(screen.getByRole('alert')).toHaveTextContent('Vul eerst een klant in.')
  })

  it('asks for a file when none is chosen', async () => {
    // Arrange
    const onUpload = vi.fn()
    const { customer, uploadButton } = renderUpload(onUpload)
    await userEvent.type(customer, 'Brunos')

    // Act
    await userEvent.click(uploadButton)

    // Assert
    expect(screen.getByRole('alert')).toHaveTextContent('kies eerst een XML-bestand')
    expect(onUpload).not.toHaveBeenCalled()
  })

  it('refuses the upload when one of the files is not XML', async () => {
    // Arrange
    const onUpload = vi.fn()
    const { customer, fileInput, uploadButton } = renderUpload(onUpload)
    await userEvent.type(customer, 'Brunos')
    chooseFiles(fileInput, [xmlFile(), new File(['x'], 'notes.txt', { type: 'text/plain' })])

    // Act
    await userEvent.click(uploadButton)

    // Assert
    expect(screen.getByRole('alert')).toHaveTextContent('dit is geen XML-bestand')
    expect(onUpload).not.toHaveBeenCalled()
  })

  it('accepts files with an upper-case .XML extension', async () => {
    // Arrange
    const onUpload = vi.fn()
    const { customer, fileInput, uploadButton } = renderUpload(onUpload)
    await userEvent.type(customer, 'Brunos')
    chooseFiles(fileInput, [xmlFile('ORDER.XML')])

    // Act
    await userEvent.click(uploadButton)

    // Assert
    expect(onUpload).toHaveBeenCalledTimes(1)
  })

  it('sends the trimmed customer name and all files, then shows the success message', async () => {
    // Arrange
    const onUpload = vi.fn().mockResolvedValue(undefined)
    const { customer, fileInput, uploadButton } = renderUpload(onUpload)
    const files = [xmlFile('a.xml'), xmlFile('b.xml')]
    await userEvent.type(customer, '  Brunos  ')
    chooseFiles(fileInput, files)

    // Act
    await userEvent.click(uploadButton)

    // Assert
    expect(onUpload).toHaveBeenCalledWith('Brunos', files)
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Upload gelukt. De AI is bezig met een mapping proposal voor Brunos.',
    )
    expect(screen.queryByText('a.xml')).not.toBeInTheDocument()
  })

  it('also works without an onUpload handler', async () => {
    // Arrange
    const { customer, fileInput, uploadButton } = renderUpload()
    await userEvent.type(customer, 'Brunos')
    chooseFiles(fileInput, [xmlFile()])

    // Act
    await userEvent.click(uploadButton)

    // Assert
    expect(await screen.findByRole('status')).toBeInTheDocument()
  })

  it('shows the server message when the upload fails', async () => {
    // Arrange
    const onUpload = vi.fn().mockRejectedValue(new Error('Upload mislukt: de server is niet bereikbaar.'))
    const { customer, fileInput, uploadButton } = renderUpload(onUpload)
    await userEvent.type(customer, 'Brunos')
    chooseFiles(fileInput, [xmlFile()])

    // Act
    await userEvent.click(uploadButton)

    // Assert
    expect(await screen.findByRole('alert')).toHaveTextContent('Upload mislukt: de server is niet bereikbaar.')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.getByText('order.xml')).toBeInTheDocument()
  })

  it('shows a general message when the upload fails without an Error', async () => {
    // Arrange
    const onUpload = vi.fn().mockRejectedValue('kapot')
    const { customer, fileInput, uploadButton } = renderUpload(onUpload)
    await userEvent.type(customer, 'Brunos')
    chooseFiles(fileInput, [xmlFile()])

    // Act
    await userEvent.click(uploadButton)

    // Assert
    expect(await screen.findByRole('alert')).toHaveTextContent('Upload mislukt.')
  })

  it('adds files chosen one after another to the list', () => {
    // Arrange
    const { fileInput } = renderUpload()

    // Act
    chooseFiles(fileInput, [xmlFile('a.xml')])
    chooseFiles(fileInput, [xmlFile('b.xml')])

    // Assert
    expect(screen.getByText('a.xml')).toBeInTheDocument()
    expect(screen.getByText('b.xml')).toBeInTheDocument()
  })

  it('ignores an empty file selection', () => {
    // Arrange
    const { fileInput } = renderUpload()

    // Act
    chooseFiles(fileInput, [])

    // Assert
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('removes a chosen file with its remove button', async () => {
    // Arrange
    const { fileInput } = renderUpload()
    chooseFiles(fileInput, [xmlFile('a.xml'), xmlFile('b.xml')])

    // Act
    await userEvent.click(screen.getByRole('button', { name: 'Verwijder a.xml' }))

    // Assert
    expect(screen.queryByText('a.xml')).not.toBeInTheDocument()
    expect(screen.getByText('b.xml')).toBeInTheDocument()
  })

  it('adds dropped files to the list', () => {
    // Arrange
    renderUpload()
    const dropZone = screen.getByText('Sleep XML-bestanden hierheen').parentElement as HTMLElement

    // Act
    fireEvent.dragOver(dropZone)
    fireEvent.drop(dropZone, { dataTransfer: { files: [xmlFile('dropped.xml')] } })

    // Assert
    expect(screen.getByText('dropped.xml')).toBeInTheDocument()
  })

  it('opens the file picker with "Bestanden kiezen"', async () => {
    // Arrange
    const { fileInput } = renderUpload()
    const click = vi.spyOn(fileInput, 'click')

    // Act
    await userEvent.click(screen.getByRole('button', { name: 'Bestanden kiezen' }))

    // Assert
    expect(click).toHaveBeenCalled()
  })

  it('hides the error again when the customer name is changed', async () => {
    // Arrange
    const { customer, uploadButton } = renderUpload()
    await userEvent.click(uploadButton)
    expect(screen.getByRole('alert')).toBeInTheDocument()

    // Act
    await userEvent.type(customer, 'B')

    // Assert
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  })

  it('hides the success message when new files are chosen', async () => {
    // Arrange
    const { customer, fileInput, uploadButton } = renderUpload(vi.fn())
    await userEvent.type(customer, 'Brunos')
    chooseFiles(fileInput, [xmlFile()])
    await userEvent.click(uploadButton)
    expect(await screen.findByRole('status')).toBeInTheDocument()

    // Act
    chooseFiles(fileInput, [xmlFile('next.xml')])

    // Assert
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
