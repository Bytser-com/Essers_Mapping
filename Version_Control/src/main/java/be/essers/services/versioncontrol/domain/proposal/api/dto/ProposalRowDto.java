package be.essers.services.versioncontrol.domain.proposal.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonPropertyOrder;

@JsonPropertyOrder({
        "source_field",
        "target_field",
        "score",
        "comment"
})
public record ProposalRowDto(
        @JsonProperty("source_field")
        String sourceField,

        @JsonProperty("target_field")
        String targetField,

        @JsonProperty("score")
        Number score,

        @JsonProperty("comment")
        String comment
) {
}
