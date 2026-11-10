package be.essers.services.versioncontrol.domain.proposal.api;

import be.essers.services.versioncontrol.domain.proposal.api.dto.CreateProposalRequest;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalResponse;
import be.essers.services.versioncontrol.domain.proposal.model.ProposalStatus;
import be.essers.services.versioncontrol.domain.proposal.service.ProposalService;
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

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class ProposalControllerTest {

    private MockMvc mockMvc;

    @Mock
    private ProposalService proposalService;

    @InjectMocks
    private ProposalController proposalController;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(proposalController)
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();
    }

    @Test
    @DisplayName("GET /proposals should return HTTP 200 with list of proposals")
    void getAllProposals_returnsListOfProposals() throws Exception {
        UUID id = UUID.randomUUID();
        ProposalResponse response = new ProposalResponse(
                id,
                "Route Optimization Proposal",
                "Automated transit route planning",
                ProposalStatus.DRAFT,
                Instant.now(),
                Instant.now()
        );

        when(proposalService.getAllProposals()).thenReturn(List.of(response));

        mockMvc.perform(get("/proposals")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value(id.toString()))
                .andExpect(jsonPath("$[0].title").value("Route Optimization Proposal"))
                .andExpect(jsonPath("$[0].status").value("DRAFT"));
    }

    @Test
    @DisplayName("POST /proposals should return HTTP 201 when request is valid")
    void createProposal_returnsCreated() throws Exception {
        UUID id = UUID.randomUUID();
        ProposalResponse response = new ProposalResponse(
                id,
                "New Proposal",
                "Description here",
                ProposalStatus.DRAFT,
                Instant.now(),
                Instant.now()
        );

        when(proposalService.createProposal(any(CreateProposalRequest.class))).thenReturn(response);

        String payload = """
                {
                    "title": "New Proposal",
                    "description": "Description here"
                }
                """;

        mockMvc.perform(post("/proposals")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(payload))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(id.toString()))
                .andExpect(jsonPath("$.title").value("New Proposal"));
    }
}
