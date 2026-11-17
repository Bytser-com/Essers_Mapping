package be.essers.services.versioncontrol.domain.proposal.repository;

import be.essers.services.versioncontrol.domain.proposal.model.Proposal;
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Repository
public class InMemoryProposalRepository implements ProposalRepository {

    private final Map<UUID, Proposal> storage = new ConcurrentHashMap<>();

    @PostConstruct
    void initSampleData() {
        Proposal sampleProposal = Proposal.createNew(
                "Initial Logistics Mapping Proposal",
                "Baseline version control proposal for Essers supply chain route mapping."
        );
        save(sampleProposal);
    }

    @Override
    public List<Proposal> findAll() {
        return List.copyOf(storage.values());
    }

    @Override
    public Optional<Proposal> findById(UUID id) {
        return Optional.ofNullable(storage.get(id));
    }

    @Override
    public Proposal save(Proposal proposal) {
        storage.put(proposal.getId(), proposal);
        return proposal;
    }

    @Override
    public void deleteById(UUID id) {
        storage.remove(id);
    }
}
