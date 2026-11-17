import { afterEach, describe, expect, it, vi } from 'vitest'
import { uploadInterface } from '../../services/uploadService'

function xmlFile(name: string) {
  return new File(['<Order/>'], name, { type: 'text/xml' })
}

describe('uploadService', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('posts the customer name and all files in one request', async () => {
    // Arrange
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 })
    vi.stubGlobal('fetch', fetchMock)
    const files = [xmlFile('a.xml'), xmlFile('b.xml')]

    // Act
    await uploadInterface('Brunos', files)

    // Assert
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] ?? []
    expect(url).toBe('/api/proposal/upload')
    expect(init.method).toBe('POST')
    const body = init.body as FormData
    expect(body.get('customer_name')).toBe('Brunos')
    expect(body.getAll('files').map((file) => (file as File).name)).toEqual(['a.xml', 'b.xml'])
  })

  it('throws a clear message when the server cannot be reached', async () => {
    // Arrange
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    // Act + Assert
    await expect(uploadInterface('Brunos', [xmlFile('a.xml')])).rejects.toThrow(
      'Upload mislukt: de server is niet bereikbaar.',
    )
  })

  it('throws the reason the API sends in "detail"', async () => {
    // Arrange
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'Upload mislukt: dit is geen XML-bestand.' }),
    }))

    // Act + Assert
    await expect(uploadInterface('Brunos', [xmlFile('a.xml')])).rejects.toThrow(
      'Upload mislukt: dit is geen XML-bestand.',
    )
  })

  it('throws a message with the status when the error has no detail', async () => {
    // Arrange
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) }))

    // Act + Assert
    await expect(uploadInterface('Brunos', [xmlFile('a.xml')])).rejects.toThrow('Upload mislukt (status 500).')
  })

  it('throws a message with the status when the error body is not JSON', async () => {
    // Arrange
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => {
        throw new SyntaxError('Unexpected token <')
      },
    }))

    // Act + Assert
    await expect(uploadInterface('Brunos', [xmlFile('a.xml')])).rejects.toThrow('Upload mislukt (status 502).')
  })
})
