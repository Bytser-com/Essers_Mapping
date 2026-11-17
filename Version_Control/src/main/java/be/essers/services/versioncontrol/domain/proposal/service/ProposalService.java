package be.essers.services.versioncontrol.domain.proposal.service;

import be.essers.services.versioncontrol.domain.proposal.api.dto.CreateProposalRequest;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalResponse;

import java.util.List;
import java.util.UUID;

public interface ProposalService {
    List<ProposalResponse> getAllProposals();
    ProposalResponse getProposalById(UUID id);
    ProposalResponse createProposal(CreateProposalRequest request);
}
