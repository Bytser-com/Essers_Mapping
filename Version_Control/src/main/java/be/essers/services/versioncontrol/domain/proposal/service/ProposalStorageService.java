package be.essers.services.versioncontrol.domain.proposal.service;

import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDto;

import java.util.List;

public interface ProposalStorageService {
    List<ProposalFileDto> listProposals(String company);
    List<String> listProposalFilenames(String company);
}
