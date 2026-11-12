package be.essers.services.versioncontrol.domain.proposal.service;

import be.essers.services.versioncontrol.domain.proposal.api.dto.CompanyProposalOverviewDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDataDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDetailsDto;

import java.util.List;

public interface ProposalStorageService {
    List<CompanyProposalOverviewDto> listProposals(String company);
    ProposalFileDetailsDto getProposalFile(String company, String version);
    ProposalFileDataDto getProposalFileData(String company, String version);
}
