import React from 'react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProposalPage from '../../pages/ProposalPage'
import { useProposalStore } from '../../stores/proposalStore'

const MAPPING = { id: 'MP-001', bronveld: 'Klant/Nummer', doelveld: 'Klantnummer', zekerheid: 92, opmerking: '' }
const SECOND_MAPPING = { id: 'MP-002', bronveld: 'Klant/Naam', doelveld: 'Naam', zekerheid: 64, opmerking: '' }
const REVIEW_MAPPING = { id: 'MP-003', bronveld: null, doelveld: 'Leverdatum', zekerheid: null, opmerking: '' }

const PROPOSAL = {
    klant: 'brunos',
    versie: 1,
    status: 'Klaar om na te kijken',
    geupload: '2026-10-30T10:00:00',
    mappings: [MAPPING],
}

function renderPage() {
    render(
        <MemoryRouter initialEntries={['/proposals/brunos']}>
            <Routes>
                <Route path="/proposals/:company" element={<ProposalPage />} />
            </Routes>
        </MemoryRouter>
    )
}

describe('ProposalPage', () => {
    beforeEach(() => {
        useProposalStore.setState({ proposal: null, loading: false, error: null, fetchProposal: vi.fn() })
    })

    it('shows the company, version and upload date', () => {
        // Arrange
        useProposalStore.setState({ proposal: PROPOSAL })

        // Act
        renderPage()

        // Assert
        expect(screen.getByText('brunos · v1')).toBeInTheDocument()
        expect(screen.getByText('Geüpload op 30/10/2026 om 10:00')).toBeInTheDocument()
    })

    it('shows a row per mapping', () => {
        // Arrange
        useProposalStore.setState({ proposal: { ...PROPOSAL, mappings: [MAPPING, SECOND_MAPPING] } })

        // Act
        renderPage()

        // Assert
        expect(screen.getByText('Klant/Nummer')).toBeInTheDocument()
        expect(screen.getByText('Klant/Naam')).toBeInTheDocument()
        expect(screen.getByText('Klantnummer')).toBeInTheDocument()
        expect(screen.getByText('Naam')).toBeInTheDocument()
        expect(screen.getByText('92%')).toBeInTheDocument()
        expect(screen.getByText('64%')).toBeInTheDocument()
    })

    it('shows REVIEW_REQUIRED for a mapping without source', () => {
        // Arrange
        useProposalStore.setState({ proposal: { ...PROPOSAL, mappings: [REVIEW_MAPPING] } })

        // Act
        renderPage()

        // Assert
        expect(screen.getByText('REVIEW_REQUIRED')).toBeInTheDocument()
    })

    it('shows no confidence for a mapping without source', () => {
        // Arrange
        useProposalStore.setState({ proposal: { ...PROPOSAL, mappings: [REVIEW_MAPPING] } })

        // Act
        renderPage()

        // Assert
        expect(screen.queryByText(/%/)).not.toBeInTheDocument()
    })

    it('shows the notice when a field needs review', () => {
        // Arrange
        useProposalStore.setState({ proposal: { ...PROPOSAL, mappings: [REVIEW_MAPPING] } })

        // Act
        renderPage()

        // Assert
        expect(screen.getByText(/kon de AI niet invullen/)).toBeInTheDocument()
    })

    it('hides the notice when all fields are filled', () => {
        // Arrange
        useProposalStore.setState({ proposal: { ...PROPOSAL, mappings: [MAPPING] } })

        // Act
        renderPage()

        // Assert
        expect(screen.queryByText(/kon de AI niet invullen/)).not.toBeInTheDocument()
    })

    it('allows approving even when a field needs review', () => {
        // Arrange
        useProposalStore.setState({ proposal: { ...PROPOSAL, mappings: [REVIEW_MAPPING] } })

        // Act
        renderPage()

        // Assert
        expect(screen.getByRole('button', { name: 'Goedkeuren' })).toBeEnabled()
    })

    it('enables approving when all fields are filled', () => {
        // Arrange
        useProposalStore.setState({ proposal: { ...PROPOSAL, mappings: [MAPPING] } })

        // Act
        renderPage()

        // Assert
        expect(screen.getByRole('button', { name: 'Goedkeuren' })).toBeEnabled()
    })

    it('shows the ready label', () => {
        // Arrange
        useProposalStore.setState({ proposal: PROPOSAL })

        // Act
        renderPage()

        // Assert
        expect(screen.getByText('Klaar om na te kijken')).toHaveClass('status--ready')
    })

    it('shows the in-review label', () => {
        // Arrange
        useProposalStore.setState({ proposal: { ...PROPOSAL, status: 'In review' } })

        // Act
        renderPage()

        // Assert
        expect(screen.getByText('In review')).toHaveClass('status--review')
    })

    it('shows the loading text', () => {
        // Arrange
        useProposalStore.setState({ loading: true })

        // Act
        renderPage()

        // Assert
        expect(screen.getByText('Voorstel wordt geladen...')).toBeInTheDocument()
    })

    it('shows the error', () => {
        // Arrange
        useProposalStore.setState({ error: 'Testfout' })

        // Act
        renderPage()

        // Assert
        expect(screen.getByText('Testfout')).toBeInTheDocument()
    })

    it('fetches the proposal of the company in the url', () => {
        // Act
        renderPage()

        // Assert
        expect(useProposalStore.getState().fetchProposal).toHaveBeenCalledWith('brunos')
    })
})
