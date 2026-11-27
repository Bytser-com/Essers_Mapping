import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useHomeStore } from '../../stores/homeStore'
import { fetchProposals } from '../../services/proposalOverviewService'
import { uploadInterface } from '../../services/uploadService'

vi.mock('../../services/uploadService')
vi.mock('../../services/proposalOverviewService')

const LIST = { total: 0, proposals: [] }

describe('homeStore', () => {
    beforeEach(() => {
        useHomeStore.setState({
            proposalList: null, loading: false, error: null, uploadError: null, waitUntil: 0, approvedNotices: [],
        })
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

    describe('IT2627T06-187 approved notices', () => {
        const row = (id, customer, status) => ({ id, customer, status })
        const list = (...proposals) => ({ total: proposals.length, proposals })

        it('adds a notice when a proposal becomes APPROVED', async () => {
            // Arrange
            useHomeStore.setState({ proposalList: list(row('nouryon/v2', 'Nouryon', 'AI_CHECKING_REVIEW')) })
            fetchProposals.mockResolvedValue(list(row('nouryon/v2', 'Nouryon', 'APPROVED')))

            // Act
            await useHomeStore.getState().fetchProposals(true)

            // Assert
            expect(useHomeStore.getState().approvedNotices).toEqual([{ id: 'nouryon/v2', customer: 'Nouryon' }])
        })

        it('shows nothing on the first load, so old approvals are not repeated', async () => {
            // Arrange
            fetchProposals.mockResolvedValue(list(row('nouryon/v2', 'Nouryon', 'APPROVED')))

            // Act
            await useHomeStore.getState().fetchProposals()

            // Assert
            expect(useHomeStore.getState().approvedNotices).toEqual([])
        })

        it('adds no second notice when the proposal was already APPROVED', async () => {
            // Arrange
            useHomeStore.setState({ proposalList: list(row('nouryon/v2', 'Nouryon', 'APPROVED')) })
            fetchProposals.mockResolvedValue(list(row('nouryon/v2', 'Nouryon', 'APPROVED')))

            // Act
            await useHomeStore.getState().fetchProposals(true)

            // Assert
            expect(useHomeStore.getState().approvedNotices).toEqual([])
        })

        it('adds no notice for a returned proposal', async () => {
            // Arrange
            useHomeStore.setState({ proposalList: list(row('nouryon/v2', 'Nouryon', 'AI_CHECKING_REVIEW')) })
            fetchProposals.mockResolvedValue(list(row('nouryon/v2', 'Nouryon', 'RETURNED')))

            // Act
            await useHomeStore.getState().fetchProposals(true)

            // Assert
            expect(useHomeStore.getState().approvedNotices).toEqual([])
        })

        it('dismissApprovedNotice removes only that notice', () => {
            // Arrange
            useHomeStore.setState({
                approvedNotices: [{ id: 'a/v1', customer: 'A' }, { id: 'b/v1', customer: 'B' }],
            })

            // Act
            useHomeStore.getState().dismissApprovedNotice('a/v1')

            // Assert
            expect(useHomeStore.getState().approvedNotices).toEqual([{ id: 'b/v1', customer: 'B' }])
        })
    })
})
