package be.essers.services.versioncontrol.domain.proposal.api;

import be.essers.services.versioncontrol.domain.proposal.api.dto.CompanyProposalOverviewDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDataDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDetailsDto;
import be.essers.services.versioncontrol.domain.proposal.service.ProposalStorageService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping({"/proposals", "/Proposals"})
public class ProposalController {

    private final ProposalStorageService proposalStorageService;

    public ProposalController(ProposalStorageService proposalStorageService) {
        this.proposalStorageService = proposalStorageService;
    }

    /**
     * GET /proposals
     * GET /proposals?company=VanRoey
     * GET /Proposals
     *
     * Retrieves all companies with their latest proposal version, creation date, and creator.
     */
    @GetMapping
    public ResponseEntity<List<CompanyProposalOverviewDto>> getProposals(
            @RequestParam(required = false) String company
    ) {
        List<CompanyProposalOverviewDto> proposals = proposalStorageService.listProposals(company);
        return ResponseEntity.ok(proposals);
    }

    /**
     * GET /proposals/file?company=vanroey&version=v3
     * GET /Proposals/file?company=vanroey&version=v3
     *
     * Retrieves the Excel proposal file (Base64) and metadata as a JSON response.
     */
    @GetMapping("/file")
    public ResponseEntity<ProposalFileDetailsDto> getProposalFile(
            @RequestParam String company,
            @RequestParam String version
    ) {
        ProposalFileDetailsDto fileDetails = proposalStorageService.getProposalFile(company, version);
        return ResponseEntity.ok(fileDetails);
    }

    /**
     * GET /proposals/filedata?company=bedrijfsnaam&version=versie
     * GET /Proposals/filedata?company=bedrijfsnaam&version=versie
     *
     * Retrieves parsed proposal file metadata and rows as a JSON response.
     */
    @GetMapping("/filedata")
    public ResponseEntity<ProposalFileDataDto> getProposalFileData(
            @RequestParam String company,
            @RequestParam String version
    ) {
        ProposalFileDataDto fileData = proposalStorageService.getProposalFileData(company, version);
        return ResponseEntity.ok(fileData);
    }
}
