package be.essers.services.versioncontrol.domain.proposal.api;

import be.essers.services.versioncontrol.domain.proposal.api.dto.CompanyProposalOverviewDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDataDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDetailsDto;
import be.essers.services.versioncontrol.domain.proposal.service.ProposalStorageService;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
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

    /**
     * PUT /proposals/file?company=vanroey&version=v3
     * PUT /Proposals/file?company=vanroey&version=v3
     *
     * Overwrites the current Excel proposal on SFTP, updates updated_time / updated_date,
     * and sets status to "In review" in the metadata file. Supports multipart/form-data ("file").
     */
    @PutMapping(value = "/file", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<ProposalFileDetailsDto> overwriteProposalFileMultipart(
            @RequestParam String company,
            @RequestParam String version,
            @RequestPart("file") MultipartFile file
    ) throws IOException {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("Uploaded file cannot be empty");
        }
        ProposalFileDetailsDto details = proposalStorageService.overwriteProposalFile(
                company, version, file.getBytes(), file.getOriginalFilename());
        return ResponseEntity.ok(details);
    }

    /**
     * PUT /proposals/file?company=vanroey&version=v3
     * PUT /Proposals/file?company=vanroey&version=v3
     *
     * Overwrites the current Excel proposal on SFTP, updates updated_time / updated_date,
     * and sets status to "In review" in the metadata file. Supports raw octet-stream / excel binary body.
     */
    @PutMapping(value = "/file", consumes = {
            MediaType.APPLICATION_OCTET_STREAM_VALUE,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel"
    })
    public ResponseEntity<ProposalFileDetailsDto> overwriteProposalFileBinary(
            @RequestParam String company,
            @RequestParam String version,
            @RequestBody byte[] fileBytes
    ) {
        if (fileBytes == null || fileBytes.length == 0) {
            throw new IllegalArgumentException("Uploaded file content cannot be empty");
        }
        ProposalFileDetailsDto details = proposalStorageService.overwriteProposalFile(
                company, version, fileBytes, null);
        return ResponseEntity.ok(details);
    }
}
