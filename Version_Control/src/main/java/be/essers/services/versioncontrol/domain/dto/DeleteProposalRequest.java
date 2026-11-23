package be.essers.services.versioncontrol.domain.dto;

import jakarta.validation.constraints.NotBlank;

public record DeleteProposalRequest(
        @NotBlank(message = "deleteCheck must not be blank")
        String deleteCheck
) {
}
