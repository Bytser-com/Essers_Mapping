import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useProposalStore } from '../../stores/proposalStore'
import { getProposal, deleteProposal } from '../../services/proposalService'

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

    it('sets deleteSuccessMessage and clears proposal when deleteProposal succeeds', async () => {
        // Arrange
        useProposalStore.setState({ proposal: PROPOSAL, deleteSuccessMessage: null })
        deleteProposal.mockResolvedValue(true)

        // Act
        const result = await useProposalStore.getState().deleteProposal('brunos', 'v1', 'brunos')

        // Assert
        expect(result).toBe(true)
        const state = useProposalStore.getState()
        expect(state.proposal).toBeNull()
        expect(state.deleteSuccessMessage).toBe('Voorstel voor brunos (v1) is succesvol verwijderd.')
        expect(deleteProposal).toHaveBeenCalledWith('brunos', 'v1', 'brunos')
    })

    it('clears deleteSuccessMessage when clearDeleteSuccessMessage is called', () => {
        // Arrange
        useProposalStore.setState({ deleteSuccessMessage: 'Voorstel voor brunos (v1) is succesvol verwijderd.' })

        // Act
        useProposalStore.getState().clearDeleteSuccessMessage()

        // Assert
        expect(useProposalStore.getState().deleteSuccessMessage).toBeNull()
    })

    it('sets actionError and leaves deleteSuccessMessage unchanged when deleteProposal fails', async () => {
        // Arrange
        useProposalStore.setState({ proposal: PROPOSAL, deleteSuccessMessage: null })
        deleteProposal.mockRejectedValue(new Error('Delete failed'))

        // Act
        const result = await useProposalStore.getState().deleteProposal('brunos', 'v1', 'wrong')

        // Assert
        expect(result).toBe(false)
        const state = useProposalStore.getState()
        expect(state.actionError).toBe('Delete failed')
        expect(state.deleteSuccessMessage).toBeNull()
    })
})