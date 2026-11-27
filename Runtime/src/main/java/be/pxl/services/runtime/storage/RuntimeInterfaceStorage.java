package be.pxl.services.runtime.storage;

import java.time.Duration;
import java.util.List;
import java.util.Optional;

import be.pxl.services.runtime.domain.ClaimedInterface;
import be.pxl.services.runtime.domain.IncomingInterface;

/**
 * Storage contract for discovering, atomically claiming, reading, and finalizing
 * customer XML interfaces on {@code sftp-runtime}.
 */
public interface RuntimeInterfaceStorage {

    /**
     * List all customer XML files in {@code incoming/} that have remained unmodified
     * for at least {@code minFileAge}.
     */
    List<IncomingInterface> listReadyIncoming(Duration minFileAge);

    /**
     * Atomically claim an incoming file for {@code instanceId} by renaming it into {@code processing/}.
     * Returns {@link Optional#empty()} when another pod or worker claimed it first.
     */
    Optional<ClaimedInterface> tryClaim(IncomingInterface candidate, String instanceId);

    /**
     * Read the full XML payload of a claimed interface in memory.
     */
    byte[] readBytes(ClaimedInterface claimed);

    /**
     * Move a successfully processed interface from {@code processing/} to {@code processed/}.
     */
    void moveToProcessed(ClaimedInterface claimed);

    /**
     * Move a failed interface from {@code processing/} to {@code error/} and record a readable reason.
     */
    void moveToError(ClaimedInterface claimed, String reason);

    /**
     * Return stale files stuck in {@code processing/} longer than {@code maxAge} back to {@code incoming/}.
     *
     * @return number of recovered files
     */
    int recoverStaleClaims(Duration maxAge);
}
