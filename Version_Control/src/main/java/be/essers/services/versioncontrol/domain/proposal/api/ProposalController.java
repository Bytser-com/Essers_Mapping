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

    private final ProposalStorageService proposalStorageService;

    public ProposalController(ProposalStorageService proposalStorageService) {
        this.proposalStorageService = proposalStorageService;
    }

    /**
     * GET /proposals
     * GET /proposals?company=VanRoey
     * GET /proposals?company=VanRoey&proposalType=inbound
     * GET /Proposals
     *
     * Retrieves all companies with their latest proposal version, creation date, creator, and proposalType.
     */
    @GetMapping
    public ResponseEntity<List<CompanyProposalOverviewDto>> getProposals(
            @RequestParam(required = false) String company,
            @RequestParam(required = false) String proposalType
    ) {
        List<CompanyProposalOverviewDto> proposals = (proposalType != null && !proposalType.isBlank())
                ? proposalStorageService.listProposals(company, proposalType)
                : proposalStorageService.listProposals(company);
        return ResponseEntity.ok(proposals);
    }

    /**
     * GET /proposals/file?company=vanroey&version=v3&proposalType=inbound
     * GET /Proposals/file?company=vanroey&version=v3&proposalType=inbound
     *
     * Retrieves the Excel proposal file (Base64) and metadata as a JSON response.
     */
    @GetMapping("/file")
    public ResponseEntity<ProposalFileDetailsDto> getProposalFile(
            @RequestParam String company,
            @RequestParam String version,
            @RequestParam String proposalType
    ) {
        if (company == null || company.isBlank()) {
            throw new IllegalArgumentException("Company parameter must not be empty");
        }
        if (version == null || version.isBlank()) {
            throw new IllegalArgumentException("Version parameter must not be empty");
        }
        if (proposalType == null || proposalType.isBlank()) {
            throw new IllegalArgumentException("Proposal type parameter must not be empty");
        }
        ProposalFileDetailsDto fileDetails = proposalStorageService.getProposalFile(company, version, proposalType);
        return ResponseEntity.ok(fileDetails);
    }

    /**
     * GET /proposals/filedata?company=bedrijfsnaam&version=versie&proposalType=type
     * GET /Proposals/filedata?company=bedrijfsnaam&version=versie&proposalType=type
     *
     * Retrieves parsed proposal file metadata and rows as a JSON response.
     */
    @GetMapping("/filedata")
    public ResponseEntity<ProposalFileDataDto> getProposalFileData(
            @RequestParam String company,
            @RequestParam String version,
            @RequestParam String proposalType
    ) {
        if (company == null || company.isBlank()) {
            throw new IllegalArgumentException("Company parameter must not be empty");
        }
        if (version == null || version.isBlank()) {
            throw new IllegalArgumentException("Version parameter must not be empty");
        }
        if (proposalType == null || proposalType.isBlank()) {
            throw new IllegalArgumentException("Proposal type parameter must not be empty");
        }
        ProposalFileDataDto fileData = proposalStorageService.getProposalFileData(company, version, proposalType);
        return ResponseEntity.ok(fileData);
    }

    /**
     * PUT /proposals/file?company=vanroey&version=v3&proposalType=inbound
     * PUT /Proposals/file?company=vanroey&version=v3&proposalType=inbound
     *
     * Overwrites the current Excel proposal on SFTP, updates updated_time / updated_date,
     * and sets status to "In review" in the metadata file. Supports multipart/form-data ("file").
     */
    @PutMapping(value = "/file", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<ProposalFileDetailsDto> overwriteProposalFileMultipart(
            @RequestParam String company,
            @RequestParam String version,
            @RequestParam String proposalType,
            @RequestPart("file") MultipartFile file
    ) throws IOException {
        if (company == null || company.isBlank()) {
            throw new IllegalArgumentException("Company parameter must not be empty");
        }
        if (version == null || version.isBlank()) {
            throw new IllegalArgumentException("Version parameter must not be empty");
        }
        if (proposalType == null || proposalType.isBlank()) {
            throw new IllegalArgumentException("Proposal type parameter must not be empty");
        }
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("Uploaded file cannot be empty");
        }
        ProposalFileDetailsDto details = proposalStorageService.overwriteProposalFile(
                company, version, proposalType, file.getBytes(), file.getOriginalFilename());
        return ResponseEntity.ok(details);
    }

    /**
     * PUT /proposals/file?company=vanroey&version=v3&proposalType=inbound
     * PUT /Proposals/file?company=vanroey&version=v3&proposalType=inbound
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
            @RequestParam String proposalType,
            @RequestBody byte[] fileBytes
    ) {
        if (company == null || company.isBlank()) {
            throw new IllegalArgumentException("Company parameter must not be empty");
        }
        if (version == null || version.isBlank()) {
            throw new IllegalArgumentException("Version parameter must not be empty");
        }
        if (proposalType == null || proposalType.isBlank()) {
            throw new IllegalArgumentException("Proposal type parameter must not be empty");
        }
        if (fileBytes == null || fileBytes.length == 0) {
            throw new IllegalArgumentException("Uploaded file content cannot be empty");
        }
        ProposalFileDetailsDto details = proposalStorageService.overwriteProposalFile(
                company, version, proposalType, fileBytes, null);
        return ResponseEntity.ok(details);
    }

    /**
     * POST /proposals?company=vanroey&version=v3&proposalType=inbound
     * POST /Proposals?company=vanroey&version=v3&proposalType=inbound
     *
     * Approves a proposal. Currently returns HTTP 501 Not Implemented ("not implemented yet").
     */
    @PostMapping
    public ResponseEntity<ProblemDetail> approveProposal(
            @RequestParam String company,
            @RequestParam String version,
            @RequestParam String proposalType
    ) {
        if (company == null || company.isBlank()) {
            throw new IllegalArgumentException("Company parameter must not be empty");
        }
        if (version == null || version.isBlank()) {
            throw new IllegalArgumentException("Version parameter must not be empty");
        }
        if (proposalType == null || proposalType.isBlank()) {
            throw new IllegalArgumentException("Proposal type parameter must not be empty");
        }
        ProblemDetail problemDetail = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_IMPLEMENTED,
                "Approving proposal for company '" + company + "', version '" + version + "', and proposalType '" + proposalType + "' is not implemented yet"
        );
        problemDetail.setTitle("Not Implemented");
        problemDetail.setType(URI.create("about:blank"));
        problemDetail.setProperty("timestamp", Instant.now());
        problemDetail.setProperty("company", company);
        problemDetail.setProperty("version", version);
        problemDetail.setProperty("proposalType", proposalType);
        return ResponseEntity.status(HttpStatus.NOT_IMPLEMENTED).body(problemDetail);
    }

    /**
     * DELETE /proposals?company=vanroey&version=v2&proposalType=inbound
     * DELETE /Proposals?company=vanroey&version=v2&proposalType=inbound
     *
     * Completely deletes this proposal from the SFTP server.
     * Query parameters (company, version, proposalType) are required.
     * In the request body, expects a JSON object with a deleteCheck string
     * which must exactly match the company name to confirm deletion.
     */
    @DeleteMapping
    public ResponseEntity<Void> deleteProposal(
            @RequestParam String company,
            @RequestParam String version,
            @RequestParam String proposalType,
            @Valid @RequestBody DeleteProposalRequest request
    ) {
        if (company == null || company.isBlank()) {
            throw new IllegalArgumentException("Company parameter must not be empty");
        }
        if (version == null || version.isBlank()) {
            throw new IllegalArgumentException("Version parameter must not be empty");
        }
        if (proposalType == null || proposalType.isBlank()) {
            throw new IllegalArgumentException("Proposal type parameter must not be empty");
        }
        if (request == null || request.deleteCheck() == null || request.deleteCheck().isBlank()) {
            throw new IllegalArgumentException("Request body must contain deleteCheck");
        }
        if (!company.equals(request.deleteCheck())) {
            throw new IllegalArgumentException(
                    "Confirmation check failed: deleteCheck ('" + request.deleteCheck() + "') must match company name ('" + company + "')"
            );
        }

        proposalStorageService.deleteProposal(company, version, proposalType);
        return ResponseEntity.noContent().build();
    }
}
