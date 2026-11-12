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
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.List;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
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
    @DisplayName("GET /proposals returns HTTP 200 with all companies and their latest versions")
    void getAllProposals_returnsList() throws Exception {
        CompanyProposalOverviewDto p1 = new CompanyProposalOverviewDto(
                "VanRoey", "v3", "mappingproposal.xlsx",
                "/Proposals/VanRoey/v3/mappingproposal.xlsx",
                "2026-11-10T14:30:00Z", "Jane Doe", "Initial proposal",
                "READY_FOR_REVIEW", null
        );
        CompanyProposalOverviewDto p2 = new CompanyProposalOverviewDto(
                "Google", "v1", "google_proposal.xlsx",
                "/Proposals/Google/v1/google_proposal.xlsx",
                "2026-11-09T10:00:00Z", "John Smith", null,
                "AI_GENERATING", "RUNNING"
        );

        when(proposalStorageService.listProposals(null)).thenReturn(List.of(p1, p2));

        mockMvc.perform(get("/proposals")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2))
                .andExpect(jsonPath("$[0].company").value("VanRoey"))
                .andExpect(jsonPath("$[0].latestVersion").value("v3"))
                .andExpect(jsonPath("$[0].filename").value("mappingproposal.xlsx"))
                .andExpect(jsonPath("$[0].createdDate").value("2026-11-10T14:30:00Z"))
                .andExpect(jsonPath("$[0].createdBy").value("Jane Doe"))
                .andExpect(jsonPath("$[0].status").value("READY_FOR_REVIEW"))
                .andExpect(jsonPath("$[1].company").value("Google"))
                .andExpect(jsonPath("$[1].latestVersion").value("v1"))
                .andExpect(jsonPath("$[1].status").value("AI_GENERATING"))
                .andExpect(jsonPath("$[1].aiStatus").value("RUNNING"));
    }

    @Test
    @DisplayName("GET /Proposals (capitalized) maps correctly")
    void getProposals_capitalizedPath_returnsList() throws Exception {
        CompanyProposalOverviewDto p1 = new CompanyProposalOverviewDto(
                "VanRoey", "v3", "mappingproposal.xlsx",
                "/Proposals/VanRoey/v3/mappingproposal.xlsx",
                "2026-11-10T14:30:00Z", "Jane Doe", null,
                "READY_FOR_REVIEW", null
        );

        when(proposalStorageService.listProposals(null)).thenReturn(List.of(p1));

        mockMvc.perform(get("/Proposals")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].company").value("VanRoey"));
    }

    @Test
    @DisplayName("GET /proposals?company=VanRoey filters by company")
    void getProposals_filteredByCompany_returnsCompanyOverview() throws Exception {
        CompanyProposalOverviewDto p1 = new CompanyProposalOverviewDto(
                "VanRoey", "v3", "mappingproposal.xlsx",
                "/Proposals/VanRoey/v3/mappingproposal.xlsx",
                "2026-11-10T14:30:00Z", "Jane Doe", null,
                "READY_FOR_REVIEW", null
        );

        when(proposalStorageService.listProposals("VanRoey")).thenReturn(List.of(p1));

        mockMvc.perform(get("/proposals")
                        .param("company", "VanRoey")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].company").value("VanRoey"))
                .andExpect(jsonPath("$[0].latestVersion").value("v3"));
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
    @DisplayName("GET /proposals/file returns Excel file and metadata")
    void getProposalFile_validParams_returnsFileDetails() throws Exception {
        ProposalFileDetailsDto details = new ProposalFileDetailsDto(
                "VanRoey", "v3", "mappingproposal.xlsx",
                "/Proposals/VanRoey/v3/mappingproposal.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                1024L, "2026-11-10T14:30:00Z", "Jane Doe", "Version 3 update",
                "UEsDBBQAAAAIA..."
        );

        when(proposalStorageService.getProposalFile("VanRoey", "v3")).thenReturn(details);

        mockMvc.perform(get("/proposals/file")
                        .param("company", "VanRoey")
                        .param("version", "v3")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.company").value("VanRoey"))
                .andExpect(jsonPath("$.version").value("v3"))
                .andExpect(jsonPath("$.filename").value("mappingproposal.xlsx"))
                .andExpect(jsonPath("$.contentType").value("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
                .andExpect(jsonPath("$.sizeBytes").value(1024))
                .andExpect(jsonPath("$.createdDate").value("2026-11-10T14:30:00Z"))
                .andExpect(jsonPath("$.createdBy").value("Jane Doe"))
                .andExpect(jsonPath("$.fileContentBase64").value("UEsDBBQAAAAIA..."));
    }

    @Test
    @DisplayName("GET /proposals/file with unknown company or version returns 404")
    void getProposalFile_notFound_returns404() throws Exception {
        when(proposalStorageService.getProposalFile("NonExisting", "v1"))
                .thenThrow(new EntityNotFoundException("Company directory 'NonExisting' does not exist"));

        mockMvc.perform(get("/proposals/file")
                        .param("company", "NonExisting")
                        .param("version", "v1")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.title").value("Entity Not Found"));
    }

    @Test
    @DisplayName("GET /Proposals/filedata returns file metadata and rows")
    void getProposalFileData_validParams_returnsFileData() throws Exception {
        ProposalRowDto row1 = new ProposalRowDto("OrderNo", "DeliveryNumber", 95, "Direct match");
        ProposalRowDto row2 = new ProposalRowDto(null, "DefaultFlag", 100, "Fixed value");

        ProposalFileDataDto fileData = new ProposalFileDataDto(
                "v3",
                "VanRoey",
                "2026-11-10",
                "14:30:00",
                "15:00:00",
                "2026-11-10",
                "Jane Doe",
                "READY_FOR_REVIEW",
                List.of(row1, row2)
        );

        when(proposalStorageService.getProposalFileData("VanRoey", "v3")).thenReturn(fileData);

        mockMvc.perform(get("/Proposals/filedata")
                        .param("company", "VanRoey")
                        .param("version", "v3")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value("v3"))
                .andExpect(jsonPath("$.comapnyname").value("VanRoey"))
                .andExpect(jsonPath("$.companyname").value("VanRoey"))
                .andExpect(jsonPath("$.upload_date").value("2026-11-10"))
                .andExpect(jsonPath("$.upload_time").value("14:30:00"))
                .andExpect(jsonPath("$.updated_time").value("15:00:00"))
                .andExpect(jsonPath("$.updated_date").value("2026-11-10"))
                .andExpect(jsonPath("$.upload_user").value("Jane Doe"))
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
                "2026-11-09",
                "10:00:00",
                null,
                null,
                "John Smith",
                List.of()
        );

        when(proposalStorageService.getProposalFileData("Google", "v1")).thenReturn(fileData);

        mockMvc.perform(get("/proposals/filedata")
                        .param("company", "Google")
                        .param("version", "v1")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value("v1"))
                .andExpect(jsonPath("$.comapnyname").value("Google"))
                .andExpect(jsonPath("$.rows").isArray());
    }

    @Test
    @DisplayName("GET /proposals/filedata with unknown company returns 404")
    void getProposalFileData_notFound_returns404() throws Exception {
        when(proposalStorageService.getProposalFileData("NonExisting", "v1"))
                .thenThrow(new EntityNotFoundException("Company directory 'NonExisting' does not exist"));

        mockMvc.perform(get("/Proposals/filedata")
                        .param("company", "NonExisting")
                        .param("version", "v1")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.title").value("Entity Not Found"));
    }
}
