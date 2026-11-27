package be.essers.services.versioncontrol.service;

import be.essers.services.versioncontrol.domain.dto.MappingPackage;
import org.apache.sshd.sftp.client.SftpClient;

import java.nio.file.attribute.FileTime;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeParseException;
import java.util.List;

/**
 * One package type folder of a version, {@code <company>/<version>/<type>/}, with the
 * {@code meta} block of its MPackage.json ({@code null} when the file is missing or unreadable).
 */
record PackageFolder(String typeName, List<SftpClient.DirEntry> entries, MappingPackage.Meta metadata) {

    static final String METADATA_FILENAME = "MPackage.json";

    PackageFolder {
        entries = List.copyOf(entries);
    }

    /** Why this package cannot be shown, or null when it is valid. */
    String problem() {
        if (metadata == null) {
            return METADATA_FILENAME + " is missing, not valid JSON or has no \"meta\" block";
        }
        if (parseCreationTime(metadata.dateCreated()) == null) {
            return "creation time is missing or not an ISO 8601 timestamp";
        }
        return null;
    }

    boolean isValid() {
        return problem() == null;
    }

    /** meta.date_created, or the newest modify time of the files when the metadata has none. */
    String createdAt() {
        return metadata != null && metadata.dateCreated() != null ? metadata.dateCreated() : latestFileTime();
    }

    String createdBy() {
        return metadata != null ? metadata.userCreated() : null;
    }

    String customerName() {
        return metadata != null ? metadata.clientName() : null;
    }

    String description() {
        return metadata != null ? metadata.description() : null;
    }

    /** meta.package_type, or the type folder name when it is missing; lowercase. */
    String packageType() {
        boolean hasType = metadata != null && metadata.packageType() != null && !metadata.packageType().isBlank();
        return (hasType ? metadata.packageType().trim() : typeName).toLowerCase();
    }

    /** ISO 8601 time, e.g. 2026-10-22T14:05:00+02:00; a time without timezone is taken as UTC. */
    static Instant parseCreationTime(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        String text = value.trim();
        try {
            return OffsetDateTime.parse(text).toInstant();
        } catch (DateTimeParseException withoutZone) {
            try {
                return LocalDateTime.parse(text).toInstant(ZoneOffset.UTC);
            } catch (DateTimeParseException notIso) {
                return null;
            }
        }
    }

    private String latestFileTime() {
        Instant latest = null;
        for (SftpClient.DirEntry entry : entries) {
            Instant modified = modifyTime(entry);
            if (modified != null && (latest == null || modified.isAfter(latest))) {
                latest = modified;
            }
        }
        return latest != null ? latest.toString() : null;
    }

    private static Instant modifyTime(SftpClient.DirEntry entry) {
        if (SftpFolders.isDirectory(entry) || entry.getAttributes() == null) {
            return null;
        }
        FileTime time = entry.getAttributes().getModifyTime();
        return time != null ? time.toInstant() : null;
    }
}
