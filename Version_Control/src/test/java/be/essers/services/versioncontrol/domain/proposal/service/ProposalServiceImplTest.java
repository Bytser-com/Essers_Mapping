package be.essers.services.versioncontrol.domain.proposal.service;

import be.essers.services.versioncontrol.domain.proposal.api.dto.CreateProposalRequest;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalResponse;
import be.essers.services.versioncontrol.domain.proposal.model.Proposal;
import be.essers.services.versioncontrol.domain.proposal.model.ProposalStatus;
import be.essers.services.versioncontrol.domain.proposal.repository.ProposalRepository;
import be.essers.services.versioncontrol.shared.exception.EntityNotFoundException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ProposalServiceImplTest {

    @Mock
    private ProposalRepository proposalRepository;

    private ProposalServiceImpl proposalService;

    @BeforeEach
    void setUp() {
        proposalService = new ProposalServiceImpl(proposalRepository);
    }

    @Test
    @DisplayName("getAllProposals should return mapped response list")
    void getAllProposals_returnsList() {
        Proposal p1 = Proposal.createNew("Title 1", "Desc 1");
        when(proposalRepository.findAll()).thenReturn(List.of(p1));

        List<ProposalResponse> result = proposalService.getAllProposals();

        assertEquals(1, result.size());
        assertEquals("Title 1", result.get(0).title());
        verify(proposalRepository).findAll();
    }

    @Test
    @DisplayName("getProposalById should return proposal when found")
    void getProposalById_found() {
        Proposal p1 = Proposal.createNew("Title 1", "Desc 1");
        when(proposalRepository.findById(p1.getId())).thenReturn(Optional.of(p1));

        ProposalResponse result = proposalService.getProposalById(p1.getId());

        assertNotNull(result);
        assertEquals(p1.getId(), result.id());
    }

    @Test
    @DisplayName("getProposalById should throw EntityNotFoundException when not found")
    void getProposalById_notFound() {
        UUID randomId = UUID.randomUUID();
        when(proposalRepository.findById(randomId)).thenReturn(Optional.empty());

        assertThrows(EntityNotFoundException.class, () -> proposalService.getProposalById(randomId));
    }

    @Test
    @DisplayName("createProposal should create and save draft proposal")
    void createProposal_savesAndReturns() {
        CreateProposalRequest request = new CreateProposalRequest("New", "Description");
        when(proposalRepository.save(any(Proposal.class))).thenAnswer(invocation -> invocation.getArgument(0));

        ProposalResponse result = proposalService.createProposal(request);

        assertNotNull(result.id());
        assertEquals("New", result.title());
        assertEquals("Description", result.description());
        assertEquals(ProposalStatus.DRAFT, result.status());
        verify(proposalRepository).save(any(Proposal.class));
    }
}
