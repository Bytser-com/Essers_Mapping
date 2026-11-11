package be.essers.services.versioncontrol.domain.proposal.service;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class VersionComparatorTest {

    private final VersionComparator comparator = VersionComparator.INSTANCE;

    @Test
    @DisplayName("Sorts versions naturally so v10 is greater than v2")
    void sortsVersionsNaturally() {
        List<String> versions = new ArrayList<>(List.of("v1", "v10", "v2", "v3"));
        versions.sort(comparator);
        assertEquals(List.of("v1", "v2", "v3", "v10"), versions);
    }

    @Test
    @DisplayName("Handles dot separated semver versions")
    void handlesSemverVersions() {
        List<String> versions = new ArrayList<>(List.of("v1.10.0", "v1.2.0", "v2.0.0", "v1.2.1"));
        versions.sort(comparator);
        assertEquals(List.of("v1.2.0", "v1.2.1", "v1.10.0", "v2.0.0"), versions);
    }

    @Test
    @DisplayName("Handles versions without 'v' prefix")
    void handlesNumbersWithoutPrefix() {
        List<String> versions = new ArrayList<>(List.of("10", "1", "2"));
        versions.sort(comparator);
        assertEquals(List.of("1", "2", "10"), versions);
    }

    @Test
    @DisplayName("Compares identical versions as equal")
    void identicalVersionsEqual() {
        assertEquals(0, comparator.compare("v3", "v3"));
        assertEquals(0, comparator.compare(null, null));
    }

    @Test
    @DisplayName("Null handling")
    void nullHandling() {
        assertTrue(comparator.compare(null, "v1") < 0);
        assertTrue(comparator.compare("v1", null) > 0);
    }
}
