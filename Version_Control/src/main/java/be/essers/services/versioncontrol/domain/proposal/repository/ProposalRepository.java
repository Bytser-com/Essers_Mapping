package be.essers.services.versioncontrol.domain.proposal.repository;

import be.essers.services.versioncontrol.domain.proposal.model.Proposal;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface ProposalRepository {
    List<Proposal> findAll();
    Optional<Proposal> findById(UUID id);
    Proposal save(Proposal proposal);
    void deleteById(UUID id);
}
