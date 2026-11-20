package be.essers.services.versioncontrol.domain.proposal.service;

import be.essers.services.versioncontrol.domain.proposal.api.dto.CompanyProposalOverviewDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDataDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDetailsDto;

import java.util.List;
import tools.jackson.databind.JsonNode;

public interface ProposalStorageService {
    List<CompanyProposalOverviewDto> listProposals(String company);
    List<CompanyProposalOverviewDto> listProposals(String company, String proposalType);
    ProposalFileDetailsDto getProposalFile(String company, String version, String proposalType);
    ProposalFileDataDto getProposalFileData(String company, String version, String proposalType);
    ProposalFileDetailsDto overwriteProposalFile(String company, String version, String proposalType, byte[] fileBytes, String originalFilename);
    void deleteProposal(String company, String version, String proposalType);
    JsonNode saveAiReview(String company, String version, String proposalType, JsonNode review);

    default ProposalFileDetailsDto getProposalFile(String company, String version) {
        return getProposalFile(company, version, null);
    }

    default ProposalFileDataDto getProposalFileData(String company, String version) {
        return getProposalFileData(company, version, null);
    }

    default ProposalFileDetailsDto overwriteProposalFile(String company, String version, byte[] fileBytes, String originalFilename) {
        return overwriteProposalFile(company, version, null, fileBytes, originalFilename);
    }

    default void deleteProposal(String company, String version) {
        deleteProposal(company, version, null);
    }
}
