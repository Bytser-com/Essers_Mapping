package be.essers.services.versioncontrol.domain.proposal.api;

import be.essers.services.versioncontrol.domain.proposal.api.dto.CompanyProposalOverviewDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDataDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDetailsDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalRowDto;
import be.essers.services.versioncontrol.domain.proposal.service.ProposalStorageService;
import be.essers.services.versioncontrol.shared.exception.EntityNotFoundException;
import be.essers.services.versioncontrol.shared.exception.GlobalExceptionHandler;
import be.essers.services.versioncontrol.shared.exception.StorageException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class ProposalControllerTest {

    private MockMvc mockMvc;

    @Mock
    private ProposalStorageService proposalStorageService;

    @InjectMocks
    private ProposalController proposalController;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(proposalController)
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();
    }

    @Test
    @DisplayName("GET /proposals returns HTTP 200 with all companies, their latest versions, and proposalType")
    void getAllProposals_returnsList() throws Exception {
        CompanyProposalOverviewDto p1 = new CompanyProposalOverviewDto(
                "VanRoey", "v3", "mappingproposal.xlsx",
                "/Proposals/VanRoey/v3/inbound/mappingproposal.xlsx",
                "2026-11-10T14:30:00Z", "Jane Doe", "Initial proposal",
                "READY_FOR_REVIEW", null, "VanRoey BV", "inbound"
        );
        CompanyProposalOverviewDto p2 = new CompanyProposalOverviewDto(
                "Google", "v1", "google_proposal.xlsx",
                "/Proposals/Google/v1/outbound/google_proposal.xlsx",
                "2026-11-09T10:00:00Z", "John Smith", null,
                "AI_GENERATING", "RUNNING", "Google Inc", "outbound"
        );

        when(proposalStorageService.listProposals(null)).thenReturn(List.of(p1, p2));

        mockMvc.perform(get("/proposals")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2))
                .andExpect(jsonPath("$[0].company").value("VanRoey"))
                .andExpect(jsonPath("$[0].latestVersion").value("v3"))
                .andExpect(jsonPath("$[0].filename").value("mappingproposal.xlsx"))
                .andExpect(jsonPath("$[0].fullPath").value("/Proposals/VanRoey/v3/inbound/mappingproposal.xlsx"))
                .andExpect(jsonPath("$[0].createdDate").value("2026-11-10T14:30:00Z"))
                .andExpect(jsonPath("$[0].createdBy").value("Jane Doe"))
                .andExpect(jsonPath("$[0].status").value("READY_FOR_REVIEW"))
                .andExpect(jsonPath("$[0].customerName").value("VanRoey BV"))
                .andExpect(jsonPath("$[0].proposalType").value("inbound"))
                .andExpect(jsonPath("$[1].company").value("Google"))
                .andExpect(jsonPath("$[1].latestVersion").value("v1"))
                .andExpect(jsonPath("$[1].status").value("AI_GENERATING"))
                .andExpect(jsonPath("$[1].aiStatus").value("RUNNING"))
                .andExpect(jsonPath("$[1].proposalType").value("outbound"));
    }

    @Test
    @DisplayName("GET /Proposals (capitalized) maps correctly")
    void getProposals_capitalizedPath_returnsList() throws Exception {
        CompanyProposalOverviewDto p1 = new CompanyProposalOverviewDto(
                "VanRoey", "v3", "mappingproposal.xlsx",
                "/Proposals/VanRoey/v3/inbound/mappingproposal.xlsx",
                "2026-11-10T14:30:00Z", "Jane Doe", null,
                "READY_FOR_REVIEW", null, null, "inbound"
        );

        when(proposalStorageService.listProposals(null)).thenReturn(List.of(p1));

        mockMvc.perform(get("/Proposals")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].company").value("VanRoey"))
                .andExpect(jsonPath("$[0].proposalType").value("inbound"));
    }

    @Test
    @DisplayName("GET /proposals?company=VanRoey filters by company")
    void getProposals_filteredByCompany_returnsCompanyOverview() throws Exception {
        CompanyProposalOverviewDto p1 = new CompanyProposalOverviewDto(
                "VanRoey", "v3", "mappingproposal.xlsx",
                "/Proposals/VanRoey/v3/inbound/mappingproposal.xlsx",
                "2026-11-10T14:30:00Z", "Jane Doe", null,
                "READY_FOR_REVIEW", null, null, "inbound"
        );

        when(proposalStorageService.listProposals("VanRoey")).thenReturn(List.of(p1));

        mockMvc.perform(get("/proposals")
                        .param("company", "VanRoey")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].company").value("VanRoey"))
                .andExpect(jsonPath("$[0].latestVersion").value("v3"))
                .andExpect(jsonPath("$[0].proposalType").value("inbound"));
    }

    @Test
    @DisplayName("GET /proposals?company=VanRoey&proposalType=inbound filters by company and proposalType")
    void getProposals_filteredByCompanyAndProposalType_returnsMatch() throws Exception {
        CompanyProposalOverviewDto p1 = new CompanyProposalOverviewDto(
                "VanRoey", "v3", "mappingproposal.xlsx",
                "/Proposals/VanRoey/v3/inbound/mappingproposal.xlsx",
                "2026-11-10T14:30:00Z", "Jane Doe", null,
                "READY_FOR_REVIEW", null, null, "inbound"
        );

        when(proposalStorageService.listProposals("VanRoey", "inbound")).thenReturn(List.of(p1));

        mockMvc.perform(get("/proposals")
                        .param("company", "VanRoey")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].company").value("VanRoey"))
                .andExpect(jsonPath("$[0].latestVersion").value("v3"))
                .andExpect(jsonPath("$[0].proposalType").value("inbound"));
    }

    @Test
    @DisplayName("TC-57-09 GET /proposals without proposals returns HTTP 200 with an empty list")
    void getProposals_noProposals_returnsEmptyList() throws Exception {
        when(proposalStorageService.listProposals(null)).thenReturn(List.of());

        mockMvc.perform(get("/proposals")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(0));
    }

    @Test
    @DisplayName("TC-57-10 GET /proposals returns 502 when the SFTP server cannot be reached")
    void getProposals_sftpUnreachable_returns502() throws Exception {
        when(proposalStorageService.listProposals(null))
                .thenThrow(new StorageException("Unable to read proposals from SFTP storage: connection refused"));

        mockMvc.perform(get("/proposals")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.title").value("SFTP Storage Error"));
    }

    @Test
    @DisplayName("GET /proposals/file returns Excel file and metadata with proposalType")
    void getProposalFile_validParams_returnsFileDetails() throws Exception {
        ProposalFileDetailsDto details = new ProposalFileDetailsDto(
                "VanRoey", "v3", "mappingproposal.xlsx",
                "/Proposals/VanRoey/v3/inbound/mappingproposal.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                1024L, "2026-11-10T14:30:00Z", "Jane Doe", "Version 3 update",
                "UEsDBBQAAAAIA...", "inbound"
        );

        when(proposalStorageService.getProposalFile("VanRoey", "v3", "inbound")).thenReturn(details);

        mockMvc.perform(get("/proposals/file")
                        .param("company", "VanRoey")
                        .param("version", "v3")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.company").value("VanRoey"))
                .andExpect(jsonPath("$.version").value("v3"))
                .andExpect(jsonPath("$.filename").value("mappingproposal.xlsx"))
                .andExpect(jsonPath("$.fullPath").value("/Proposals/VanRoey/v3/inbound/mappingproposal.xlsx"))
                .andExpect(jsonPath("$.contentType").value("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
                .andExpect(jsonPath("$.sizeBytes").value(1024))
                .andExpect(jsonPath("$.createdDate").value("2026-11-10T14:30:00Z"))
                .andExpect(jsonPath("$.createdBy").value("Jane Doe"))
                .andExpect(jsonPath("$.proposalType").value("inbound"))
                .andExpect(jsonPath("$.fileContentBase64").value("UEsDBBQAAAAIA..."));
    }

    @Test
    @DisplayName("GET /proposals/file with missing proposalType parameter returns 400")
    void getProposalFile_missingProposalType_returns400() throws Exception {
        mockMvc.perform(get("/proposals/file")
                        .param("company", "VanRoey")
                        .param("version", "v3")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Missing Required Parameter"));
    }

    @Test
    @DisplayName("GET /proposals/file with blank proposalType parameter returns 400")
    void getProposalFile_blankProposalType_returns400() throws Exception {
        mockMvc.perform(get("/proposals/file")
                        .param("company", "VanRoey")
                        .param("version", "v3")
                        .param("proposalType", "   ")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"));
    }

    @Test
    @DisplayName("GET /proposals/file with unknown company or version returns 404")
    void getProposalFile_notFound_returns404() throws Exception {
        when(proposalStorageService.getProposalFile("NonExisting", "v1", "inbound"))
                .thenThrow(new EntityNotFoundException("Company directory 'NonExisting' does not exist"));

        mockMvc.perform(get("/proposals/file")
                        .param("company", "NonExisting")
                        .param("version", "v1")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.title").value("Entity Not Found"));
    }

    @Test
    @DisplayName("GET /Proposals/filedata returns file metadata, proposalType, and rows")
    void getProposalFileData_validParams_returnsFileData() throws Exception {
        ProposalRowDto row1 = new ProposalRowDto("OrderNo", "DeliveryNumber", 95, "Direct match");
        ProposalRowDto row2 = new ProposalRowDto(null, "DefaultFlag", 100, "Fixed value");

        ProposalFileDataDto fileData = new ProposalFileDataDto(
                "v3",
                "VanRoey",
                "inbound",
                "2026-11-10",
                "14:30:00",
                "15:00:00",
                "2026-11-10",
                "Jane Doe",
                "READY_FOR_REVIEW",
                List.of(row1, row2)
        );

        when(proposalStorageService.getProposalFileData("VanRoey", "v3", "inbound")).thenReturn(fileData);

        mockMvc.perform(get("/Proposals/filedata")
                        .param("company", "VanRoey")
                        .param("version", "v3")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value("v3"))
                .andExpect(jsonPath("$.companyname").value("VanRoey"))
                .andExpect(jsonPath("$.proposalType").value("inbound"))
                .andExpect(jsonPath("$.upload_date").value("2026-11-10"))
                .andExpect(jsonPath("$.upload_time").value("14:30:00"))
                .andExpect(jsonPath("$.updated_time").value("15:00:00"))
                .andExpect(jsonPath("$.updated_date").value("2026-11-10"))
                .andExpect(jsonPath("$.createdBy").value("Jane Doe"))
                .andExpect(jsonPath("$.status").value("READY_FOR_REVIEW"))
                .andExpect(jsonPath("$.rows.length()").value(2))
                .andExpect(jsonPath("$.rows[0].source_field").value("OrderNo"))
                .andExpect(jsonPath("$.rows[0].target_field").value("DeliveryNumber"))
                .andExpect(jsonPath("$.rows[0].score").value(95))
                .andExpect(jsonPath("$.rows[0].comment").value("Direct match"))
                .andExpect(jsonPath("$.rows[1].source_field").doesNotExist())
                .andExpect(jsonPath("$.rows[1].target_field").value("DefaultFlag"))
                .andExpect(jsonPath("$.rows[1].score").value(100))
                .andExpect(jsonPath("$.rows[1].comment").value("Fixed value"));
    }

    @Test
    @DisplayName("GET /proposals/filedata (lowercase) maps correctly")
    void getProposalFileData_lowercasePath_returnsFileData() throws Exception {
        ProposalFileDataDto fileData = new ProposalFileDataDto(
                "v1",
                "Google",
                "outbound",
                "2026-11-09",
                "10:00:00",
                null,
                null,
                "John Smith",
                "IN_REVIEW",
                List.of()
        );

        when(proposalStorageService.getProposalFileData("Google", "v1", "outbound")).thenReturn(fileData);

        mockMvc.perform(get("/proposals/filedata")
                        .param("company", "Google")
                        .param("version", "v1")
                        .param("proposalType", "outbound")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value("v1"))
                .andExpect(jsonPath("$.companyname").value("Google"))
                .andExpect(jsonPath("$.proposalType").value("outbound"))
                .andExpect(jsonPath("$.rows").isArray());
    }

    @Test
    @DisplayName("GET /proposals/filedata with unknown company returns 404")
    void getProposalFileData_notFound_returns404() throws Exception {
        when(proposalStorageService.getProposalFileData("NonExisting", "v1", "inbound"))
                .thenThrow(new EntityNotFoundException("Company directory 'NonExisting' does not exist"));

        mockMvc.perform(get("/Proposals/filedata")
                        .param("company", "NonExisting")
                        .param("version", "v1")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.title").value("Entity Not Found"));
    }

    @Test
    @DisplayName("GET /Proposals/filedata with missing company parameter returns 400")
    void getProposalFileData_missingCompany_returns400() throws Exception {
        mockMvc.perform(get("/Proposals/filedata")
                        .param("version", "v1")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("GET /Proposals/filedata with missing version parameter returns 400")
    void getProposalFileData_missingVersion_returns400() throws Exception {
        mockMvc.perform(get("/Proposals/filedata")
                        .param("company", "VanRoey")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("GET /Proposals/filedata with missing proposalType parameter returns 400")
    void getProposalFileData_missingProposalType_returns400() throws Exception {
        mockMvc.perform(get("/Proposals/filedata")
                        .param("company", "VanRoey")
                        .param("version", "v1")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Missing Required Parameter"));
    }

    @Test
    @DisplayName("GET /Proposals/filedata with blank proposalType returns 400")
    void getProposalFileData_blankProposalType_returns400() throws Exception {
        mockMvc.perform(get("/Proposals/filedata")
                        .param("company", "VanRoey")
                        .param("version", "v1")
                        .param("proposalType", "  ")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"));
    }

    @Test
    @DisplayName("GET /Proposals/filedata with path traversal characters returns 400")
    void getProposalFileData_pathTraversal_returns400() throws Exception {
        when(proposalStorageService.getProposalFileData("../etc", "v1", "inbound"))
                .thenThrow(new IllegalArgumentException("Path segment contains illegal characters: ../etc"));

        mockMvc.perform(get("/Proposals/filedata")
                        .param("company", "../etc")
                        .param("version", "v1")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"));
    }

    @Test
    @DisplayName("GET /Proposals/filedata returns 502 when SFTP fails")
    void getProposalFileData_sftpFailure_returns502() throws Exception {
        when(proposalStorageService.getProposalFileData("VanRoey", "v3", "inbound"))
                .thenThrow(new StorageException("Failed to read file from SFTP storage"));

        mockMvc.perform(get("/Proposals/filedata")
                        .param("company", "VanRoey")
                        .param("version", "v3")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.title").value("SFTP Storage Error"));
    }

    @Test
    @DisplayName("PUT /Proposals/file with multipart file overwrites proposal and returns details with proposalType")
    void overwriteProposalFile_multipart_success() throws Exception {
        byte[] dummyContent = "dummy-excel".getBytes();
        MockMultipartFile multipartFile = new MockMultipartFile(
                "file",
                "mappingproposal.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                dummyContent
        );

        ProposalFileDetailsDto details = new ProposalFileDetailsDto(
                "VanRoey",
                "v3",
                "mappingproposal.xlsx",
                "/Proposals/VanRoey/v3/inbound/mappingproposal.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                dummyContent.length,
                "2026-11-10T12:00:00Z",
                "John Smith",
                "Initial proposal",
                "ZHVtbXktZXhjZWw=",
                "inbound"
        );

        when(proposalStorageService.overwriteProposalFile(eq("vanroey"), eq("v3"), eq("inbound"), any(byte[].class), eq("mappingproposal.xlsx")))
                .thenReturn(details);

        mockMvc.perform(MockMvcRequestBuilders.multipart("/Proposals/file")
                        .file(multipartFile)
                        .with(request -> {
                            request.setMethod("PUT");
                            return request;
                        })
                        .param("company", "vanroey")
                        .param("version", "v3")
                        .param("proposalType", "inbound"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.company").value("VanRoey"))
                .andExpect(jsonPath("$.version").value("v3"))
                .andExpect(jsonPath("$.filename").value("mappingproposal.xlsx"))
                .andExpect(jsonPath("$.proposalType").value("inbound"));
    }

    @Test
    @DisplayName("PUT /proposals/file (lowercase) with binary body overwrites proposal")
    void overwriteProposalFile_binary_success() throws Exception {
        byte[] dummyContent = "binary-excel".getBytes();

        ProposalFileDetailsDto details = new ProposalFileDetailsDto(
                "vanroey",
                "v3",
                "mappingproposal.xlsx",
                "/Proposals/vanroey/v3/inbound/mappingproposal.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                dummyContent.length,
                "2026-11-10T12:00:00Z",
                "John Smith",
                "Initial proposal",
                "YmluYXJ5LWV4Y2Vs",
                "inbound"
        );

        when(proposalStorageService.overwriteProposalFile(eq("vanroey"), eq("v3"), eq("inbound"), any(byte[].class), eq(null)))
                .thenReturn(details);

        mockMvc.perform(put("/proposals/file")
                        .param("company", "vanroey")
                        .param("version", "v3")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_OCTET_STREAM)
                        .content(dummyContent))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.company").value("vanroey"))
                .andExpect(jsonPath("$.version").value("v3"))
                .andExpect(jsonPath("$.proposalType").value("inbound"));
    }

    @Test
    @DisplayName("PUT /Proposals/file returns 404 when company or version not found")
    void overwriteProposalFile_notFound_returns404() throws Exception {
        byte[] dummyContent = "dummy-excel".getBytes();
        when(proposalStorageService.overwriteProposalFile(eq("NonExisting"), eq("v1"), eq("inbound"), any(byte[].class), eq(null)))
                .thenThrow(new EntityNotFoundException("Company directory 'NonExisting' does not exist"));

        mockMvc.perform(put("/Proposals/file")
                        .param("company", "NonExisting")
                        .param("version", "v1")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_OCTET_STREAM)
                        .content(dummyContent))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.title").value("Entity Not Found"));
    }

    @Test
    @DisplayName("PUT /Proposals/file returns 400 when missing proposalType parameter")
    void overwriteProposalFile_missingProposalType_returns400() throws Exception {
        mockMvc.perform(put("/Proposals/file")
                        .param("company", "vanroey")
                        .param("version", "v3")
                        .contentType(MediaType.APPLICATION_OCTET_STREAM)
                        .content(new byte[]{1, 2, 3}))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Missing Required Parameter"));
    }

    @Test
    @DisplayName("PUT /Proposals/file returns 400 when missing query parameter")
    void overwriteProposalFile_missingParams_returns400() throws Exception {
        mockMvc.perform(put("/Proposals/file")
                        .param("company", "vanroey")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_OCTET_STREAM)
                        .content(new byte[]{1, 2, 3}))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Missing Required Parameter"));
    }

    @Test
    @DisplayName("PUT /Proposals/file returns 400 when empty file uploaded")
    void overwriteProposalFile_emptyFile_returns400() throws Exception {
        mockMvc.perform(put("/Proposals/file")
                        .param("company", "vanroey")
                        .param("version", "v3")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_OCTET_STREAM)
                        .content(new byte[0]))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Body"));
    }

    @Test
    @DisplayName("POST /Proposals returns 501 Not Implemented with proposalType")
    void approveProposal_returns501NotImplemented() throws Exception {
        mockMvc.perform(post("/Proposals")
                        .param("company", "vanroey")
                        .param("version", "v3")
                        .param("proposalType", "inbound"))
                .andExpect(status().isNotImplemented())
                .andExpect(jsonPath("$.status").value(501))
                .andExpect(jsonPath("$.title").value("Not Implemented"))
                .andExpect(jsonPath("$.detail").value("Approving proposal for company 'vanroey', version 'v3', and proposalType 'inbound' is not implemented yet"))
                .andExpect(jsonPath("$.company").value("vanroey"))
                .andExpect(jsonPath("$.version").value("v3"))
                .andExpect(jsonPath("$.proposalType").value("inbound"));
    }

    @Test
    @DisplayName("POST /proposals (lowercase) returns 501 Not Implemented")
    void approveProposal_lowercase_returns501NotImplemented() throws Exception {
        mockMvc.perform(post("/proposals")
                        .param("company", "Google")
                        .param("version", "v1")
                        .param("proposalType", "outbound"))
                .andExpect(status().isNotImplemented())
                .andExpect(jsonPath("$.status").value(501))
                .andExpect(jsonPath("$.detail").value("Approving proposal for company 'Google', version 'v1', and proposalType 'outbound' is not implemented yet"))
                .andExpect(jsonPath("$.proposalType").value("outbound"));
    }

    @Test
    @DisplayName("POST /Proposals returns 400 when missing proposalType parameter")
    void approveProposal_missingProposalType_returns400() throws Exception {
        mockMvc.perform(post("/Proposals")
                        .param("company", "vanroey")
                        .param("version", "v3"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Missing Required Parameter"));
    }

    @Test
    @DisplayName("POST /Proposals returns 400 when missing query parameter")
    void approveProposal_missingParams_returns400() throws Exception {
        mockMvc.perform(post("/Proposals")
                        .param("company", "vanroey")
                        .param("proposalType", "inbound"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Missing Required Parameter"));
    }

    @Test
    @DisplayName("DELETE /Proposals with matching deleteCheck and proposalType returns 204 No Content")
    void deleteProposal_validRequest_returns204NoContent() throws Exception {
        mockMvc.perform(delete("/Proposals")
                        .param("company", "vanroey")
                        .param("version", "v2")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"deleteCheck\":\"vanroey\"}"))
                .andExpect(status().isNoContent());

        verify(proposalStorageService).deleteProposal("vanroey", "v2", "inbound");
    }

    @Test
    @DisplayName("DELETE /proposals (lowercase) with matching deleteCheck returns 204 No Content")
    void deleteProposal_lowercase_returns204NoContent() throws Exception {
        mockMvc.perform(delete("/proposals")
                        .param("company", "Google")
                        .param("version", "v1")
                        .param("proposalType", "outbound")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"deleteCheck\":\"Google\"}"))
                .andExpect(status().isNoContent());

        verify(proposalStorageService).deleteProposal("Google", "v1", "outbound");
    }

    @Test
    @DisplayName("DELETE /Proposals returns 400 when proposalType parameter is missing")
    void deleteProposal_missingProposalType_returns400() throws Exception {
        mockMvc.perform(delete("/Proposals")
                        .param("company", "vanroey")
                        .param("version", "v2")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"deleteCheck\":\"vanroey\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Missing Required Parameter"));
    }

    @Test
    @DisplayName("DELETE /Proposals returns 400 when deleteCheck does not match company")
    void deleteProposal_mismatchedDeleteCheck_returns400() throws Exception {
        mockMvc.perform(delete("/Proposals")
                        .param("company", "vanroey")
                        .param("version", "v2")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"deleteCheck\":\"wrong-company\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"))
                .andExpect(jsonPath("$.detail").value("Confirmation check failed: deleteCheck ('wrong-company') must match company name ('vanroey')"));
    }

    @Test
    @DisplayName("DELETE /Proposals returns 400 when deleteCheck is blank")
    void deleteProposal_blankDeleteCheck_returns400() throws Exception {
        mockMvc.perform(delete("/Proposals")
                        .param("company", "vanroey")
                        .param("version", "v2")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"deleteCheck\":\"\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("DELETE /Proposals returns 400 when body is missing")
    void deleteProposal_missingBody_returns400() throws Exception {
        mockMvc.perform(delete("/Proposals")
                        .param("company", "vanroey")
                        .param("version", "v2")
                        .param("proposalType", "inbound"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Body"));
    }

    @Test
    @DisplayName("DELETE /Proposals returns 400 when company param is missing")
    void deleteProposal_missingCompany_returns400() throws Exception {
        mockMvc.perform(delete("/Proposals")
                        .param("version", "v2")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"deleteCheck\":\"vanroey\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Missing Required Parameter"));
    }

    @Test
    @DisplayName("DELETE /Proposals returns 400 when version param is missing")
    void deleteProposal_missingVersion_returns400() throws Exception {
        mockMvc.perform(delete("/Proposals")
                        .param("company", "vanroey")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"deleteCheck\":\"vanroey\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Missing Required Parameter"));
    }

    @Test
    @DisplayName("DELETE /Proposals returns 404 when company, version, or proposalType does not exist")
    void deleteProposal_entityNotFound_returns404() throws Exception {
        doThrow(new EntityNotFoundException("Company directory 'vanroey' does not exist"))
                .when(proposalStorageService).deleteProposal("vanroey", "v2", "inbound");

        mockMvc.perform(delete("/Proposals")
                        .param("company", "vanroey")
                        .param("version", "v2")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"deleteCheck\":\"vanroey\"}"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.title").value("Entity Not Found"));
    }

    @Test
    @DisplayName("GET /proposals returns 400 when company exceeds 20 characters")
    void getProposals_companyExceeds20Chars_returns400() throws Exception {
        mockMvc.perform(get("/proposals")
                        .param("company", "123456789012345678901"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"))
                .andExpect(jsonPath("$.detail").value("Company parameter must not exceed 20 characters"));
    }

    @Test
    @DisplayName("GET /proposals returns 400 when proposalType exceeds 20 characters")
    void getProposals_proposalTypeExceeds20Chars_returns400() throws Exception {
        mockMvc.perform(get("/proposals")
                        .param("proposalType", "123456789012345678901"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"))
                .andExpect(jsonPath("$.detail").value("Proposal type parameter must not exceed 20 characters"));
    }

    @Test
    @DisplayName("GET /proposals returns 400 when proposal_type exceeds 20 characters")
    void getProposals_proposalTypeSnakeExceeds20Chars_returns400() throws Exception {
        mockMvc.perform(get("/proposals")
                        .param("proposal_type", "123456789012345678901"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"))
                .andExpect(jsonPath("$.detail").value("Proposal type parameter must not exceed 20 characters"));
    }

    @Test
    @DisplayName("GET /proposals/file returns 400 when company exceeds 20 characters")
    void getProposalFile_companyExceeds20Chars_returns400() throws Exception {
        mockMvc.perform(get("/proposals/file")
                        .param("company", "123456789012345678901")
                        .param("version", "v1")
                        .param("proposalType", "inbound"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"))
                .andExpect(jsonPath("$.detail").value("Company parameter must not exceed 20 characters"));
    }

    @Test
    @DisplayName("GET /proposals/file returns 400 when proposalType exceeds 20 characters")
    void getProposalFile_proposalTypeExceeds20Chars_returns400() throws Exception {
        mockMvc.perform(get("/proposals/file")
                        .param("company", "vanroey")
                        .param("version", "v1")
                        .param("proposalType", "123456789012345678901"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"))
                .andExpect(jsonPath("$.detail").value("Proposal type parameter must not exceed 20 characters"));
    }

    @Test
    @DisplayName("GET /proposals/file returns 400 when proposal_type (snake_case) exceeds 20 characters")
    void getProposalFile_proposalTypeSnakeExceeds20Chars_returns400() throws Exception {
        mockMvc.perform(get("/proposals/file")
                        .param("company", "vanroey")
                        .param("version", "v1")
                        .param("proposal_type", "123456789012345678901"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"))
                .andExpect(jsonPath("$.detail").value("Proposal type parameter must not exceed 20 characters"));
    }

    @Test
    @DisplayName("GET /proposals/file accepts proposal_type (snake_case) when valid")
    void getProposalFile_proposalTypeSnakeValid_returns200() throws Exception {
        ProposalFileDetailsDto dto = new ProposalFileDetailsDto(
                "vanroey", "v1", "file.xlsx", "/Proposals/vanroey/v1/inbound/file.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                100, "2026-11-10T12:00:00Z", "tester", null, "base64", "inbound"
        );
        when(proposalStorageService.getProposalFile("vanroey", "v1", "inbound")).thenReturn(dto);

        mockMvc.perform(get("/proposals/file")
                        .param("company", "vanroey")
                        .param("version", "v1")
                        .param("proposal_type", "inbound"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.company").value("vanroey"))
                .andExpect(jsonPath("$.proposalType").value("inbound"));
    }

    @Test
    @DisplayName("GET /proposals/filedata returns 400 when company exceeds 20 characters")
    void getProposalFileData_companyExceeds20Chars_returns400() throws Exception {
        mockMvc.perform(get("/proposals/filedata")
                        .param("company", "123456789012345678901")
                        .param("version", "v1")
                        .param("proposalType", "inbound"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"))
                .andExpect(jsonPath("$.detail").value("Company parameter must not exceed 20 characters"));
    }

    @Test
    @DisplayName("GET /proposals/filedata returns 400 when proposalType exceeds 20 characters")
    void getProposalFileData_proposalTypeExceeds20Chars_returns400() throws Exception {
        mockMvc.perform(get("/proposals/filedata")
                        .param("company", "vanroey")
                        .param("version", "v1")
                        .param("proposalType", "123456789012345678901"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"))
                .andExpect(jsonPath("$.detail").value("Proposal type parameter must not exceed 20 characters"));
    }

    @Test
    @DisplayName("PUT /proposals/file (multipart) returns 400 when company exceeds 20 characters")
    void overwriteProposalFile_multipart_companyExceeds20Chars_returns400() throws Exception {
        MockMultipartFile file = new MockMultipartFile("file", "test.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", new byte[]{1, 2, 3});
        mockMvc.perform(MockMvcRequestBuilders.multipart("/proposals/file")
                        .file(file)
                        .with(req -> { req.setMethod("PUT"); return req; })
                        .param("company", "123456789012345678901")
                        .param("version", "v1")
                        .param("proposalType", "inbound"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"))
                .andExpect(jsonPath("$.detail").value("Company parameter must not exceed 20 characters"));
    }

    @Test
    @DisplayName("PUT /proposals/file (multipart) returns 400 when proposalType exceeds 20 characters")
    void overwriteProposalFile_multipart_proposalTypeExceeds20Chars_returns400() throws Exception {
        MockMultipartFile file = new MockMultipartFile("file", "test.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", new byte[]{1, 2, 3});
        mockMvc.perform(MockMvcRequestBuilders.multipart("/proposals/file")
                        .file(file)
                        .with(req -> { req.setMethod("PUT"); return req; })
                        .param("company", "vanroey")
                        .param("version", "v1")
                        .param("proposalType", "123456789012345678901"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"))
                .andExpect(jsonPath("$.detail").value("Proposal type parameter must not exceed 20 characters"));
    }

    @Test
    @DisplayName("PUT /proposals/file (binary) returns 400 when company exceeds 20 characters")
    void overwriteProposalFile_binary_companyExceeds20Chars_returns400() throws Exception {
        mockMvc.perform(put("/proposals/file")
                        .param("company", "123456789012345678901")
                        .param("version", "v1")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_OCTET_STREAM)
                        .content(new byte[]{1, 2, 3}))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"))
                .andExpect(jsonPath("$.detail").value("Company parameter must not exceed 20 characters"));
    }

    @Test
    @DisplayName("PUT /proposals/file (binary) returns 400 when proposalType exceeds 20 characters")
    void overwriteProposalFile_binary_proposalTypeExceeds20Chars_returns400() throws Exception {
        mockMvc.perform(put("/proposals/file")
                        .param("company", "vanroey")
                        .param("version", "v1")
                        .param("proposalType", "123456789012345678901")
                        .contentType(MediaType.APPLICATION_OCTET_STREAM)
                        .content(new byte[]{1, 2, 3}))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"))
                .andExpect(jsonPath("$.detail").value("Proposal type parameter must not exceed 20 characters"));
    }

    @Test
    @DisplayName("POST /proposals returns 400 when company exceeds 20 characters")
    void approveProposal_companyExceeds20Chars_returns400() throws Exception {
        mockMvc.perform(post("/proposals")
                        .param("company", "123456789012345678901")
                        .param("version", "v1")
                        .param("proposalType", "inbound"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"))
                .andExpect(jsonPath("$.detail").value("Company parameter must not exceed 20 characters"));
    }

    @Test
    @DisplayName("POST /proposals returns 400 when proposalType exceeds 20 characters")
    void approveProposal_proposalTypeExceeds20Chars_returns400() throws Exception {
        mockMvc.perform(post("/proposals")
                        .param("company", "vanroey")
                        .param("version", "v1")
                        .param("proposalType", "123456789012345678901"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"))
                .andExpect(jsonPath("$.detail").value("Proposal type parameter must not exceed 20 characters"));
    }

    @Test
    @DisplayName("DELETE /proposals returns 400 when company exceeds 20 characters")
    void deleteProposal_companyExceeds20Chars_returns400() throws Exception {
        mockMvc.perform(delete("/proposals")
                        .param("company", "123456789012345678901")
                        .param("version", "v1")
                        .param("proposalType", "inbound")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"deleteCheck\":\"123456789012345678901\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"))
                .andExpect(jsonPath("$.detail").value("Company parameter must not exceed 20 characters"));
    }

    @Test
    @DisplayName("DELETE /proposals returns 400 when proposalType exceeds 20 characters")
    void deleteProposal_proposalTypeExceeds20Chars_returns400() throws Exception {
        mockMvc.perform(delete("/proposals")
                        .param("company", "vanroey")
                        .param("version", "v1")
                        .param("proposalType", "123456789012345678901")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"deleteCheck\":\"vanroey\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"))
                .andExpect(jsonPath("$.detail").value("Proposal type parameter must not exceed 20 characters"));
    }

    @Test
    @DisplayName("GET /proposals normalizes uppercase proposalType to lowercase")
    void getProposals_normalizesProposalTypeToLowercase() throws Exception {
        when(proposalStorageService.listProposals(eq("vanroey"), eq("inbound"))).thenReturn(List.of());

        mockMvc.perform(get("/proposals")
                        .param("company", "vanroey")
                        .param("proposalType", "INBOUND"))
                .andExpect(status().isOk());

        verify(proposalStorageService).listProposals("vanroey", "inbound");
    }

    @Test
    @DisplayName("GET /proposals/file normalizes uppercase proposalType to lowercase")
    void getProposalFile_normalizesProposalTypeToLowercase() throws Exception {
        ProposalFileDetailsDto dto = new ProposalFileDetailsDto(
                "vanroey", "v1", "file.xlsx", "/Proposals/vanroey/v1/inbound/file.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                100, "2026-11-10T12:00:00Z", "tester", null, "base64", "inbound"
        );
        when(proposalStorageService.getProposalFile("vanroey", "v1", "inbound")).thenReturn(dto);

        mockMvc.perform(get("/proposals/file")
                        .param("company", "vanroey")
                        .param("version", "v1")
                        .param("proposalType", "InBound"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.proposalType").value("inbound"));

        verify(proposalStorageService).getProposalFile("vanroey", "v1", "inbound");
    }

    @Test
    @DisplayName("GET /proposals/file normalizes uppercase snake_case proposal_type to lowercase")
    void getProposalFile_normalizesProposalTypeSnakeToLowercase() throws Exception {
        ProposalFileDetailsDto dto = new ProposalFileDetailsDto(
                "vanroey", "v1", "file.xlsx", "/Proposals/vanroey/v1/outbound/file.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                100, "2026-11-10T12:00:00Z", "tester", null, "base64", "outbound"
        );
        when(proposalStorageService.getProposalFile("vanroey", "v1", "outbound")).thenReturn(dto);

        mockMvc.perform(get("/proposals/file")
                        .param("company", "vanroey")
                        .param("version", "v1")
                        .param("proposal_type", "OUTBOUND"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.proposalType").value("outbound"));

        verify(proposalStorageService).getProposalFile("vanroey", "v1", "outbound");
    }

    @Test
    @DisplayName("DELETE /proposals normalizes uppercase proposalType to lowercase")
    void deleteProposal_normalizesProposalTypeToLowercase() throws Exception {
        mockMvc.perform(delete("/proposals")
                        .param("company", "vanroey")
                        .param("version", "v1")
                        .param("proposalType", "INBOUND")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"deleteCheck\":\"vanroey\"}"))
                .andExpect(status().isNoContent());

        verify(proposalStorageService).deleteProposal("vanroey", "v1", "inbound");
    }
}
