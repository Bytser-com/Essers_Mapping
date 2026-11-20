package be.essers.services.versioncontrol.domain.proposal.api;

import be.essers.services.versioncontrol.domain.proposal.api.dto.CompanyProposalOverviewDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.DeleteProposalRequest;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDataDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDetailsDto;
import be.essers.services.versioncontrol.domain.proposal.service.ProposalStorageService;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.DeleteMapping;
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

    private static final int MAX_LENGTH = 20;
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
            @RequestParam(name = "proposalType", required = false) String proposalType,
            @RequestParam(name = "proposal_type", required = false) String proposalTypeSnake
    ) {
        if (company != null) {
            if (company.isBlank()) {
                throw new IllegalArgumentException("Company parameter must not be empty");
            }
            if (company.length() > MAX_LENGTH) {
                throw new IllegalArgumentException("Company parameter must not exceed " + MAX_LENGTH + " characters");
            }
        }
        String effectiveType = (proposalType != null && !proposalType.isBlank()) ? proposalType : proposalTypeSnake;
        if (effectiveType != null) {
            if (effectiveType.isBlank()) {
                throw new IllegalArgumentException("Proposal type parameter must not be empty");
            }
            if (effectiveType.length() > MAX_LENGTH) {
                throw new IllegalArgumentException("Proposal type parameter must not exceed " + MAX_LENGTH + " characters");
            }
            effectiveType = effectiveType.toLowerCase();
        }

        List<CompanyProposalOverviewDto> proposals = (effectiveType != null)
                ? proposalStorageService.listProposals(company, effectiveType)
                : proposalStorageService.listProposals(company);
        return ResponseEntity.ok(proposals);
    }

    /**
     * GET /proposals/file?company=vanroey&version=v3&proposalType=inbound
     * GET /Proposals/file?company=vanroey&version=v3&proposal_type=inbound
     *
     * Retrieves the Excel proposal file (Base64) and metadata as a JSON response.
     */
    @GetMapping("/file")
    public ResponseEntity<ProposalFileDetailsDto> getProposalFile(
            @RequestParam String company,
            @RequestParam String version,
            @RequestParam(name = "proposalType", required = false) String proposalType,
            @RequestParam(name = "proposal_type", required = false) String proposalTypeSnake
    ) throws MissingServletRequestParameterException {
        validateCompany(company);
        validateVersion(version);
        String effectiveProposalType = resolveProposalType(proposalType, proposalTypeSnake);
        ProposalFileDetailsDto fileDetails = proposalStorageService.getProposalFile(company, version, effectiveProposalType);
        return ResponseEntity.ok(fileDetails);
    }

    /**
     * GET /proposals/filedata?company=bedrijfsnaam&version=versie&proposalType=type
     * GET /Proposals/filedata?company=bedrijfsnaam&version=versie&proposal_type=type
     *
     * Retrieves parsed proposal file metadata and rows as a JSON response.
     */
    @GetMapping("/filedata")
    public ResponseEntity<ProposalFileDataDto> getProposalFileData(
            @RequestParam String company,
            @RequestParam String version,
            @RequestParam(name = "proposalType", required = false) String proposalType,
            @RequestParam(name = "proposal_type", required = false) String proposalTypeSnake
    ) throws MissingServletRequestParameterException {
        validateCompany(company);
        validateVersion(version);
        String effectiveProposalType = resolveProposalType(proposalType, proposalTypeSnake);
        ProposalFileDataDto fileData = proposalStorageService.getProposalFileData(company, version, effectiveProposalType);
        return ResponseEntity.ok(fileData);
    }

    /**
     * PUT /proposals/file?company=vanroey&version=v3&proposalType=inbound
     * PUT /Proposals/file?company=vanroey&version=v3&proposal_type=inbound
     *
     * Overwrites the current Excel proposal on SFTP, updates updated_time / updated_date,
     * and sets status to "In review" in the metadata file. Supports multipart/form-data ("file").
     */
    @PutMapping(value = "/file", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<ProposalFileDetailsDto> overwriteProposalFileMultipart(
            @RequestParam String company,
            @RequestParam String version,
            @RequestParam(name = "proposalType", required = false) String proposalType,
            @RequestParam(name = "proposal_type", required = false) String proposalTypeSnake,
            @RequestPart("file") MultipartFile file
    ) throws IOException, MissingServletRequestParameterException {
        validateCompany(company);
        validateVersion(version);
        String effectiveProposalType = resolveProposalType(proposalType, proposalTypeSnake);
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("Uploaded file cannot be empty");
        }
        ProposalFileDetailsDto details = proposalStorageService.overwriteProposalFile(
                company, version, effectiveProposalType, file.getBytes(), file.getOriginalFilename());
        return ResponseEntity.ok(details);
    }

    /**
     * PUT /proposals/file?company=vanroey&version=v3&proposalType=inbound
     * PUT /Proposals/file?company=vanroey&version=v3&proposal_type=inbound
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
            @RequestParam(name = "proposalType", required = false) String proposalType,
            @RequestParam(name = "proposal_type", required = false) String proposalTypeSnake,
            @RequestBody byte[] fileBytes
    ) throws MissingServletRequestParameterException {
        validateCompany(company);
        validateVersion(version);
        String effectiveProposalType = resolveProposalType(proposalType, proposalTypeSnake);
        if (fileBytes == null || fileBytes.length == 0) {
            throw new IllegalArgumentException("Uploaded file content cannot be empty");
        }
        ProposalFileDetailsDto details = proposalStorageService.overwriteProposalFile(
                company, version, effectiveProposalType, fileBytes, null);
        return ResponseEntity.ok(details);
    }

    /**
     * DELETE /proposals?company=vanroey&version=v2&proposalType=inbound
     * DELETE /Proposals?company=vanroey&version=v2&proposal_type=inbound
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
            @RequestParam(name = "proposalType", required = false) String proposalType,
            @RequestParam(name = "proposal_type", required = false) String proposalTypeSnake,
            @Valid @RequestBody DeleteProposalRequest request
    ) throws MissingServletRequestParameterException {
        validateCompany(company);
        validateVersion(version);
        String effectiveProposalType = resolveProposalType(proposalType, proposalTypeSnake);
        if (request == null || request.deleteCheck() == null || request.deleteCheck().isBlank()) {
            throw new IllegalArgumentException("Request body must contain deleteCheck");
        }
        if (!company.equals(request.deleteCheck())) {
            throw new IllegalArgumentException(
                    "Confirmation check failed: deleteCheck ('" + request.deleteCheck() + "') must match company name ('" + company + "')"
            );
        }

        proposalStorageService.deleteProposal(company, version, effectiveProposalType);
        return ResponseEntity.noContent().build();
    }

    private void validateCompany(String company) {
        if (company == null || company.isBlank()) {
            throw new IllegalArgumentException("Company parameter must not be empty");
        }
        if (company.length() > MAX_LENGTH) {
            throw new IllegalArgumentException("Company parameter must not exceed " + MAX_LENGTH + " characters");
        }
    }

    private void validateVersion(String version) {
        if (version == null || version.isBlank()) {
            throw new IllegalArgumentException("Version parameter must not be empty");
        }
    }

    private String resolveProposalType(String proposalType, String proposalTypeSnake)
            throws MissingServletRequestParameterException {
        if (proposalType == null && proposalTypeSnake == null) {
            throw new MissingServletRequestParameterException("proposalType", "String");
        }
        String type = (proposalType != null && !proposalType.isBlank()) ? proposalType : proposalTypeSnake;
        if (type == null || type.isBlank()) {
            throw new IllegalArgumentException("Proposal type parameter must not be empty");
        }
        if (type.length() > MAX_LENGTH) {
            throw new IllegalArgumentException("Proposal type parameter must not exceed " + MAX_LENGTH + " characters");
        }
        return type.toLowerCase();
    }
}
