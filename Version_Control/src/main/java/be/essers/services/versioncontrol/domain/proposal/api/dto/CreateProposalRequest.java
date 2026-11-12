package be.essers.services.versioncontrol.domain.proposal.api.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateProposalRequest(
        @NotBlank(message = "Title must not be blank")
        @Size(max = 150, message = "Title must not exceed 150 characters")
        String title,

        @Size(max = 2000, message = "Description must not exceed 2000 characters")
        String description
) {
}
