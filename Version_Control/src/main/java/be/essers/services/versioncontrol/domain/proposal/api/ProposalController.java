package be.essers.services.versioncontrol.domain.proposal.api;

import be.essers.services.versioncontrol.domain.proposal.api.dto.CreateProposalRequest;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalResponse;
import be.essers.services.versioncontrol.domain.proposal.service.ProposalService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/proposals")
public class ProposalController {

    private final ProposalService proposalService;

    public ProposalController(ProposalService proposalService) {
        this.proposalService = proposalService;
    }

    @GetMapping
    public ResponseEntity<List<ProposalResponse>> getAllProposals() {
        List<ProposalResponse> proposals = proposalService.getAllProposals();
        return ResponseEntity.ok(proposals);
    }

    @GetMapping("/{id}")
    public ResponseEntity<ProposalResponse> getProposalById(@PathVariable UUID id) {
        ProposalResponse proposal = proposalService.getProposalById(id);
        return ResponseEntity.ok(proposal);
    }

    @PostMapping
    public ResponseEntity<ProposalResponse> createProposal(@Valid @RequestBody CreateProposalRequest request) {
        ProposalResponse created = proposalService.createProposal(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
