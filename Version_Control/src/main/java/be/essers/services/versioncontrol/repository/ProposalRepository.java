package be.essers.services.versioncontrol.repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import be.essers.services.versioncontrol.domain.Proposal;

public interface ProposalRepository {
    List<Proposal> findAll();
    Optional<Proposal> findById(UUID id);
    Proposal save(Proposal proposal);
    void deleteById(UUID id);
}
