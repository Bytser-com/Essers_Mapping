import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useHomeStore } from '../../stores/homeStore'
import { fetchProposals } from '../../services/proposals'
import { uploadInterface } from '../../services/uploadService'

vi.mock('../../services/uploadService')
vi.mock('../../services/proposals')

const LIST = { total: 0, proposals: [] }

describe('homeStore', () => {
    beforeEach(() => {
        useHomeStore.setState({ proposalList: null, loading: false, error: null, uploadError: null, waitUntil: 0 })
        vi.clearAllMocks()
    })

    it('fetchProposals stores the list', async () => {
        // Arrange
        fetchProposals.mockResolvedValue(LIST)

        // Act
        await useHomeStore.getState().fetchProposals()

        // Assert
        const state = useHomeStore.getState()
        expect(state.proposalList).toEqual(LIST)
        expect(state.loading).toBe(false)
    })

    it('sets loading while fetching', async () => {
        // Arrange
        fetchProposals.mockResolvedValue(LIST)

        // Act
        const promise = useHomeStore.getState().fetchProposals()

        // Assert
        const state = useHomeStore.getState()
        expect(state.loading).toBe(true)

        await promise
    })

    it('stores the error when fetching fails', async () => {
        // Arrange
        fetchProposals.mockRejectedValue(new Error('geen mappings gevonden'))

        // Act
        await useHomeStore.getState().fetchProposals()

        // Assert
        const state = useHomeStore.getState()
        expect(state.proposalList).toBeNull()
        expect(state.loading).toBe(false)
        expect(state.error).toBe('geen mappings gevonden')
    })

    it('keeps the list and shows no error when a refresh fails', async () => {
        // Arrange
        useHomeStore.setState({ proposalList: LIST })
        fetchProposals.mockRejectedValue(new Error('down'))

        // Act
        await useHomeStore.getState().fetchProposals(true)

        // Assert
        const state = useHomeStore.getState()
        expect(state.proposalList).toEqual(LIST)
        expect(state.error).toBeNull()
    })

    it('does not set loading when refreshing quietly', async () => {
        // Arrange
        fetchProposals.mockResolvedValue(LIST)

        // Act
        const promise = useHomeStore.getState().fetchProposals(true)

        // Assert
        const state = useHomeStore.getState()
        expect(state.loading).toBe(false)

        await promise
    })

    it('uploads the xmls and returns true', async () => {
        // Arrange
        uploadInterface.mockResolvedValue(undefined)
        fetchProposals.mockResolvedValue(LIST)
        const files = [new File(['<Order/>'], 'order.xml')]

        // Act
        const result = await useHomeStore.getState().uploadInterface('Brunos', 'markdown', files)

        // Assert
        expect(uploadInterface).toHaveBeenCalledWith('Brunos', 'markdown', files)
        expect(result).toBe(true)
    })

    it('list is reloaded after uploading', async () => {
        // Arrange
        uploadInterface.mockResolvedValue(undefined)
        fetchProposals.mockResolvedValue(LIST)
        const files = [new File(['<Order/>'], 'order.xml')]

        // Act
        await useHomeStore.getState().uploadInterface('Brunos', 'markdown', files)

        // Assert
        expect(useHomeStore.getState().waitUntil).toBeGreaterThan(Date.now())
        expect(fetchProposals).toHaveBeenCalledTimes(1)
    })

    it('stores the error when uploading fails', async () => {
        // Arrange
        uploadInterface.mockRejectedValue(new Error('Upload mislukt: dit is geen XML-bestand.'))

        // Act
        const result = await useHomeStore.getState().uploadInterface('Brunos', 'markdown', [])

        // Assert
        expect(result).toBe(false)
        expect(useHomeStore.getState().uploadError).toBe('Upload mislukt: dit is geen XML-bestand.')
        expect(fetchProposals).not.toHaveBeenCalled()
    })

    it('does not set loading when refreshing quietly', async () => {
        // Arrange
        uploadInterface.mockRejectedValue('broken')

        // Act
        const result = await useHomeStore.getState().uploadInterface('wrong', 'wrong', [])

        // Assert
        expect(result).toBe(false)
        expect(useHomeStore.getState().uploadError).toBe('Upload mislukt.')
        expect(fetchProposals).not.toHaveBeenCalled()
    })
})