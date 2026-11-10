package be.essers.services.versioncontrol.domain.proposal.api;

import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDto;
import be.essers.services.versioncontrol.domain.proposal.service.ProposalStorageService;
import be.essers.services.versioncontrol.shared.exception.EntityNotFoundException;
import be.essers.services.versioncontrol.shared.exception.GlobalExceptionHandler;
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
    @DisplayName("GET /proposals returns HTTP 200 with all files across companies")
    void getAllProposals_returnsList() throws Exception {
        ProposalFileDto f1 = new ProposalFileDto("VanRoey", "route1.xml", "/Proposals/VanRoey/route1.xml");
        ProposalFileDto f2 = new ProposalFileDto("Google", "route2.json", "/Proposals/Google/route2.json");

        when(proposalStorageService.listProposals(null)).thenReturn(List.of(f1, f2));

        mockMvc.perform(get("/proposals")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2))
                .andExpect(jsonPath("$[0].company").value("VanRoey"))
                .andExpect(jsonPath("$[0].filename").value("route1.xml"))
                .andExpect(jsonPath("$[0].fullPath").value("/Proposals/VanRoey/route1.xml"))
                .andExpect(jsonPath("$[1].company").value("Google"));
    }

    @Test
    @DisplayName("GET /Proposals (capitalized) also maps correctly")
    void getProposals_capitalizedPath_returnsList() throws Exception {
        ProposalFileDto f1 = new ProposalFileDto("VanRoey", "route1.xml", "/Proposals/VanRoey/route1.xml");

        when(proposalStorageService.listProposals(null)).thenReturn(List.of(f1));

        mockMvc.perform(get("/Proposals")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].company").value("VanRoey"));
    }

    @Test
    @DisplayName("GET /proposals?company=VanRoey filters by company")
    void getProposals_filteredByCompany_returnsCompanyFiles() throws Exception {
        ProposalFileDto f1 = new ProposalFileDto("VanRoey", "route1.xml", "/Proposals/VanRoey/route1.xml");

        when(proposalStorageService.listProposals("VanRoey")).thenReturn(List.of(f1));

        mockMvc.perform(get("/proposals")
                        .param("company", "VanRoey")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].company").value("VanRoey"))
                .andExpect(jsonPath("$[0].filename").value("route1.xml"));
    }

    @Test
    @DisplayName("GET /proposals/filenames?company=VanRoey returns list of filename strings")
    void getProposalFilenames_returnsFilenameStrings() throws Exception {
        when(proposalStorageService.listProposalFilenames("VanRoey")).thenReturn(List.of("route1.xml", "route2.xml"));

        mockMvc.perform(get("/proposals/filenames")
                        .param("company", "VanRoey")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2))
                .andExpect(jsonPath("$[0]").value("route1.xml"))
                .andExpect(jsonPath("$[1]").value("route2.xml"));
    }

    @Test
    @DisplayName("GET /proposals with unknown company returns 404 Not Found")
    void getProposals_unknownCompany_returnsNotFound() throws Exception {
        when(proposalStorageService.listProposals("NonExisting"))
                .thenThrow(new EntityNotFoundException("Company directory 'NonExisting' does not exist"));

        mockMvc.perform(get("/proposals")
                        .param("company", "NonExisting")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.title").value("Entity Not Found"));
    }
}
