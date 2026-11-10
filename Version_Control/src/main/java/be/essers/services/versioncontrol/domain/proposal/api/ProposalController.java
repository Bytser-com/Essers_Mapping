package be.essers.services.versioncontrol.domain.proposal.api;

import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDto;
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
     *
     * Retrieves all proposal files from the SFTP server, optionally filtered by company.
     */
    @GetMapping
    public ResponseEntity<List<ProposalFileDto>> getProposals(
            @RequestParam(required = false) String company
    ) {
        List<ProposalFileDto> files = proposalStorageService.listProposals(company);
        return ResponseEntity.ok(files);
    }

    /**
     * GET /proposals/filenames
     * GET /proposals/filenames?company=VanRoey
     *
     * Returns purely a list of filename strings from the SFTP server.
     */
    @GetMapping("/filenames")
    public ResponseEntity<List<String>> getProposalFilenames(
            @RequestParam(required = false) String company
    ) {
        List<String> filenames = proposalStorageService.listProposalFilenames(company);
        return ResponseEntity.ok(filenames);
    }
}
