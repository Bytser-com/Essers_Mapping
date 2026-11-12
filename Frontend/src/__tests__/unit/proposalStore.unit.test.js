import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useProposalStore } from '../../stores/proposalStore'
import { getProposal } from '../../services/proposalService'

vi.mock('../../services/proposalService')

const PROPOSAL = {
    klant: 'brunos',
    versie: 1,
    status: 'Klaar om na te kijken',
    geupload: '2026-10-30T10:00:00',
    mappings: [],
}

describe('proposalStore', () => {
    beforeEach(() => {
        useProposalStore.setState({ proposal: null, loading: false, error: null })
        vi.clearAllMocks()
    })

    it('fetches and stores the proposal when fetching succeeds', async () => {
        // Arrange
        getProposal.mockResolvedValue(PROPOSAL)

        // Act
        await useProposalStore.getState().fetchProposal('brunos')

        // Assert
        const state = useProposalStore.getState()
        expect(state.proposal).toEqual(PROPOSAL)
        expect(state.loading).toBe(false)
        expect(state.error).toBe(null)
        expect(getProposal).toHaveBeenCalledWith('brunos')
    })

    it('stores the error when fetching fails', async () => {
        // Arrange
        getProposal.mockRejectedValue(new Error('geen mapping gevonden'))

        // Act
        await useProposalStore.getState().fetchProposal('wrong')

        // Assert
        const state = useProposalStore.getState()
        expect(state.proposal).toBeNull()
        expect(state.loading).toBe(false)
        expect(state.error).toBe('geen mapping gevonden')
    })

    it('uses a default message when the error is not an Error', async () => {
        // Arrange
        getProposal.mockRejectedValue('broken')

        // Act
        await useProposalStore.getState().fetchProposal('wrong')

        // Assert
        const state = useProposalStore.getState()
        expect(state.proposal).toBeNull()
        expect(state.loading).toBe(false)
        expect(state.error).toBe("Onbekende fout")
    })

    it('sets loading while fetching', async () => {
        // Arrange
        getProposal.mockResolvedValue(PROPOSAL)

        // Act
        const promise = useProposalStore.getState().fetchProposal('brunos')

        // Assert
        const state = useProposalStore.getState()
        expect(state.loading).toBe(true)

        await promise
    })

    it('sets loading while fetching', async () => {
        // Arrange
        getProposal.mockResolvedValue(PROPOSAL)

        // Act
        const promise = useProposalStore.getState().fetchProposal('brunos')

        // Assert
        const state = useProposalStore.getState()
        expect(state.loading).toBe(true)

        await promise
    })

    it('clears a previous error when fetching again', async () => {
        // Arrange
        useProposalStore.setState({ error: 'geen mapping gevonden' })
        getProposal.mockResolvedValue(PROPOSAL)
        
        // Act
        await useProposalStore.getState().fetchProposal('brunos')
        
        // Assert
        const state = useProposalStore.getState()
        expect(state.error).toBe(null)
    })
})