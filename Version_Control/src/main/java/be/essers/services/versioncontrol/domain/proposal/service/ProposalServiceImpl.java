package be.essers.services.versioncontrol.domain.proposal.service;

import be.essers.services.versioncontrol.domain.proposal.api.dto.CreateProposalRequest;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalResponse;
import be.essers.services.versioncontrol.domain.proposal.model.Proposal;
import be.essers.services.versioncontrol.domain.proposal.repository.ProposalRepository;
import be.essers.services.versioncontrol.shared.exception.EntityNotFoundException;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.UUID;

@Service
public class ProposalServiceImpl implements ProposalService {

    private final ProposalRepository proposalRepository;

    public ProposalServiceImpl(ProposalRepository proposalRepository) {
        this.proposalRepository = proposalRepository;
    }

    @Override
    public List<ProposalResponse> getAllProposals() {
        return proposalRepository.findAll().stream()
                .map(ProposalResponse::from)
                .toList();
    }

    @Override
    public ProposalResponse getProposalById(UUID id) {
        return proposalRepository.findById(id)
                .map(ProposalResponse::from)
                .orElseThrow(() -> new EntityNotFoundException("Proposal with id " + id + " not found"));
    }

    @Override
    public ProposalResponse createProposal(CreateProposalRequest request) {
        Proposal proposal = Proposal.createNew(request.title(), request.description());
        Proposal saved = proposalRepository.save(proposal);
        return ProposalResponse.from(saved);
    }
}
