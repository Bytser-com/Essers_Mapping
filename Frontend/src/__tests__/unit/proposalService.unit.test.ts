import { afterEach, describe, expect, it, vi } from 'vitest'
import { getProposal, getProposalFile, VERSION_CONTROL_API } from '../../services/proposalService'

// Fake fetch response: only the fields proposalService reads
function respond(status: number, body?: unknown) {
  return vi.fn().mockResolvedValue({ ok: status >= 200 && status < 300, status, json: async () => body })
}

const DTO = {
  company: 'Brunos',
  latestVersion: 'v3',
  createdDate: '2026-10-30T10:00:00',
  status: 'IN_REVIEW',
  mappings: [{ id: 'MP-001', bronveld: 'A', doelveld: 'B', zekerheid: 90, opmerking: '' }],
}

describe('proposalService', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    vi.useRealTimers()
  })

  describe('getProposal', () => {
    it('calls the version-control API with the encoded company name', async () => {
      // Arrange
      vi.stubGlobal('fetch', respond(200, [DTO]))

      // Act
      await getProposal('Bruno & Co')

      // Assert
      expect(fetch).toHaveBeenCalledWith(`${VERSION_CONTROL_API}/proposals?company=Bruno%20%26%20Co`)
    })

    it.each([502, 503])('throws a "temporarily unreachable" error on status %i', async (status) => {
      // Arrange
      vi.stubGlobal('fetch', respond(status))

      // Act + Assert
      await expect(getProposal('brunos')).rejects.toThrow(
        `De bestanden zijn tijdelijk niet bereikbaar (status ${status})`,
      )
    })

    it.each([404, 500])('throws "geen mapping gevonden" on status %i', async (status) => {
      // Arrange
      vi.stubGlobal('fetch', respond(status))

      // Act + Assert
      await expect(getProposal('brunos')).rejects.toThrow(`geen mapping gevonden (status ${status})`)
    })

    it('returns a response that already has the Proposal shape unchanged', async () => {
      // Arrange
      const proposal = { klant: 'brunos', versie: 2, status: 'In review', geupload: '2026-10-30', mappings: [] }
      vi.stubGlobal('fetch', respond(200, proposal))

      // Act
      const result = await getProposal('brunos')

      // Assert
      expect(result).toEqual(proposal)
    })

    it('converts an overview item into a Proposal', async () => {
      // Arrange
      vi.stubGlobal('fetch', respond(200, [DTO]))

      // Act
      const result = await getProposal('brunos')

      // Assert
      expect(result).toEqual({
        klant: 'Brunos',
        versie: 3,
        status: 'In review',
        geupload: '2026-10-30T10:00:00',
        mappings: DTO.mappings,
      })
    })

    it('picks the item of the requested company, ignoring case', async () => {
      // Arrange
      const other = { ...DTO, company: 'Other', latestVersion: 'v1' }
      vi.stubGlobal('fetch', respond(200, [other, DTO]))

      // Act
      const result = await getProposal('BRUNOS')

      // Assert
      expect(result.klant).toBe('Brunos')
      expect(result.versie).toBe(3)
    })

    it('falls back to the first item when no company matches', async () => {
      // Arrange
      vi.stubGlobal('fetch', respond(200, [{ ...DTO, company: 'Other' }]))

      // Act
      const result = await getProposal('brunos')

      // Assert
      expect(result.klant).toBe('Other')
    })

    it('reads the items from a { proposals: [...] } response', async () => {
      // Arrange
      vi.stubGlobal('fetch', respond(200, { proposals: [DTO] }))

      // Act
      const result = await getProposal('brunos')

      // Assert
      expect(result.klant).toBe('Brunos')
    })

    it('accepts a single overview object', async () => {
      // Arrange
      vi.stubGlobal('fetch', respond(200, DTO))

      // Act
      const result = await getProposal('brunos')

      // Assert
      expect(result.versie).toBe(3)
    })

    it('throws "geen mapping gevonden (status 404)" when the list is empty', async () => {
      // Arrange
      vi.stubGlobal('fetch', respond(200, []))

      // Act + Assert
      await expect(getProposal('brunos')).rejects.toThrow('geen mapping gevonden (status 404)')
    })

    it('uses defaults when optional fields are missing', async () => {
      // Arrange
      vi.useFakeTimers()
      vi.setSystemTime(new Date('2026-11-12T08:00:00.000Z'))
      vi.stubGlobal('fetch', respond(200, [{ company: '', latestVersion: undefined }]))

      // Act
      const result = await getProposal('brunos')

      // Assert
      expect(result).toEqual({
        klant: 'brunos',
        versie: 1,
        status: 'Klaar om na te kijken',
        geupload: '2026-11-12T08:00:00.000Z',
        mappings: [],
      })
    })

    it('uses version 1 when the version is not a number', async () => {
      // Arrange
      vi.stubGlobal('fetch', respond(200, [{ ...DTO, latestVersion: 'abc' }]))

      // Act
      const result = await getProposal('brunos')

      // Assert
      expect(result.versie).toBe(1)
    })

    it('accepts a version without the "v" prefix', async () => {
      // Arrange
      vi.stubGlobal('fetch', respond(200, [{ ...DTO, latestVersion: '7' }]))

      // Act
      const result = await getProposal('brunos')

      // Assert
      expect(result.versie).toBe(7)
    })

    it('shows "Klaar om na te kijken" for every status other than IN_REVIEW', async () => {
      // Arrange
      vi.stubGlobal('fetch', respond(200, [{ ...DTO, status: 'DRAFT' }]))

      // Act
      const result = await getProposal('brunos')

      // Assert
      expect(result.status).toBe('Klaar om na te kijken')
    })
  })

  describe('getProposalFile', () => {
    it('requests the file of a company and version', async () => {
      // Arrange
      const file = { company: 'brunos', version: 'v1', filename: 'MProposal-brunos_V1.xlsx' }
      vi.stubGlobal('fetch', respond(200, file))

      // Act
      const result = await getProposalFile('brunos', 'v1')

      // Assert
      expect(result).toEqual(file)
      expect(fetch).toHaveBeenCalledWith(`${VERSION_CONTROL_API}/proposals/file?company=brunos&version=v1`)
    })

    it('throws when the file cannot be fetched', async () => {
      // Arrange
      vi.stubGlobal('fetch', respond(404))

      // Act + Assert
      await expect(getProposalFile('brunos', 'v1')).rejects.toThrow('Bestand kon niet worden opgehaald (status 404)')
    })
  })

  describe('VERSION_CONTROL_API', () => {
    it('uses the default path without VITE_VERSION_CONTROL_API', () => {
      expect(VERSION_CONTROL_API).toBe('/api/version-control')
    })

    it('uses VITE_VERSION_CONTROL_API when it is set', async () => {
      // Arrange
      vi.stubEnv('VITE_VERSION_CONTROL_API', 'http://version-control:8085')
      vi.resetModules()

      // Act
      const service = await import('../../services/proposalService')

      // Assert
      expect(service.VERSION_CONTROL_API).toBe('http://version-control:8085')
    })
  })
})
