package be.essers.services.versioncontrol.service;

import java.util.List;
import java.util.UUID;

import be.essers.services.versioncontrol.domain.dto.CreateProposalRequest;
import be.essers.services.versioncontrol.domain.dto.ProposalResponse;

public interface ProposalService {
    List<ProposalResponse> getAllProposals();
    ProposalResponse getProposalById(UUID id);
    ProposalResponse createProposal(CreateProposalRequest request);
}
