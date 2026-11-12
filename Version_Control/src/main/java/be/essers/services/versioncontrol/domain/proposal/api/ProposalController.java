package be.essers.services.versioncontrol.domain.proposal.api;

import be.essers.services.versioncontrol.domain.proposal.api.dto.CompanyProposalOverviewDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.DeleteProposalRequest;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDataDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDetailsDto;
import be.essers.services.versioncontrol.domain.proposal.service.ProposalStorageService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.net.URI;
import java.time.Instant;
import java.util.List;

@RestController
@RequestMapping({"/proposals", "/Proposals"})
public class ProposalController {

    private static final String XLSX_EXTENSION = ".xlsx";
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

    /**
     * POST /proposals?company=vanroey&version=v3
     * POST /Proposals?company=vanroey&version=v3
     *
     * Approves a proposal. Currently returns HTTP 501 Not Implemented ("not implemented yet").
     */
    @PostMapping
    public ResponseEntity<ProblemDetail> approveProposal(
            @RequestParam String company,
            @RequestParam String version
    ) {
        if (company == null || company.isBlank()) {
            throw new IllegalArgumentException("Company parameter must not be empty");
        }
        if (version == null || version.isBlank()) {
            throw new IllegalArgumentException("Version parameter must not be empty");
        }
        ProblemDetail problemDetail = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_IMPLEMENTED,
                "Approving proposal for company '" + company + "' and version '" + version + "' is not implemented yet"
        );
        problemDetail.setTitle("Not Implemented");
        problemDetail.setType(URI.create("about:blank"));
        problemDetail.setProperty("timestamp", Instant.now());
        problemDetail.setProperty("company", company);
        problemDetail.setProperty("version", version);
        return ResponseEntity.status(HttpStatus.NOT_IMPLEMENTED).body(problemDetail);
    }

    /**
     * DELETE /proposals?company=vanroey&version=v2
     * DELETE /Proposals?company=vanroey&version=v2
     *
     * Completely deletes this proposal from the SFTP server.
     * Both query parameters (company, version) are required.
     * In the request body, expects a JSON object with a deleteCheck string
     * which must exactly match the company name to confirm deletion.
     */
    @DeleteMapping
    public ResponseEntity<Void> deleteProposal(
            @RequestParam String company,
            @RequestParam String version,
            @Valid @RequestBody DeleteProposalRequest request
    ) {
        if (company == null || company.isBlank()) {
            throw new IllegalArgumentException("Company parameter must not be empty");
        }
        if (version == null || version.isBlank()) {
            throw new IllegalArgumentException("Version parameter must not be empty");
        }
        if (request == null || request.deleteCheck() == null || request.deleteCheck().isBlank()) {
            throw new IllegalArgumentException("Request body must contain deleteCheck");
        }
        if (!company.equals(request.deleteCheck())) {
            throw new IllegalArgumentException(
                    "Confirmation check failed: deleteCheck ('" + request.deleteCheck() + "') must match company name ('" + company + "')"
            );
        }

        proposalStorageService.deleteProposal(company, version);
        return ResponseEntity.noContent().build();
    }
}
