package be.essers.services.versioncontrol.service;

import be.essers.services.versioncontrol.domain.dto.MappingPackage;
import org.apache.sshd.sftp.client.SftpClient;
import org.apache.sshd.sftp.common.SftpConstants;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.nio.file.attribute.FileTime;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class PackageFolderTest {

    private static MappingPackage.Meta meta(String packageType, String dateCreated) {
        return new MappingPackage.Meta("nouryon", "1.0.0", packageType, dateCreated, "analist_a", "Eerste versie");
    }

    private static SftpClient.DirEntry file(String name, String modified) {
        SftpClient.Attributes attrs = new SftpClient.Attributes();
        attrs.setType(SftpConstants.SSH_FILEXFER_TYPE_REGULAR);
        attrs.setModifyTime(FileTime.from(Instant.parse(modified)));
        return new SftpClient.DirEntry(name, name, attrs);
    }

    private static SftpClient.DirEntry folder(String name, String modified) {
        SftpClient.Attributes attrs = new SftpClient.Attributes();
        attrs.setType(SftpConstants.SSH_FILEXFER_TYPE_DIRECTORY);
        attrs.setModifyTime(FileTime.from(Instant.parse(modified)));
        return new SftpClient.DirEntry(name, name, attrs);
    }

    @Test
    @DisplayName("a package with metadata and a valid creation time is valid and exposes its meta fields")
    void validPackage_exposesMeta() {
        PackageFolder pkg = new PackageFolder("inbound", List.of(), meta("inbound", "2026-11-20T10:00:00Z"));

        assertTrue(pkg.isValid());
        assertNull(pkg.problem());
        assertEquals("2026-11-20T10:00:00Z", pkg.createdAt());
        assertEquals("analist_a", pkg.createdBy());
        assertEquals("nouryon", pkg.customerName());
        assertEquals("Eerste versie", pkg.description());
    }

    @Test
    @DisplayName("a package without metadata or without a valid creation time is invalid")
    void invalidPackages_haveAProblem() {
        PackageFolder withoutMeta = new PackageFolder("inbound", List.of(), null);
        PackageFolder badDate = new PackageFolder("inbound", List.of(), meta("inbound", "22/10/2026"));

        assertTrue(withoutMeta.problem().contains(PackageFolder.METADATA_FILENAME));
        assertFalse(withoutMeta.isValid());
        assertTrue(badDate.problem().contains("ISO 8601"));
        assertNull(withoutMeta.createdBy());
        assertNull(withoutMeta.customerName());
        assertNull(withoutMeta.description());
    }

    @Test
    @DisplayName("createdAt falls back to the newest file time, ignoring folders")
    void createdAt_fallsBackToNewestFileTime() {
        PackageFolder pkg = new PackageFolder("inbound", List.of(
                file("MPackage.json", "2026-11-10T12:00:00Z"),
                folder("old", "2026-12-01T00:00:00Z"),
                file("notes.txt", "2026-11-12T08:00:00Z")), null);

        assertEquals("2026-11-12T08:00:00Z", pkg.createdAt());
        assertNull(new PackageFolder("inbound", List.of(), null).createdAt());
    }

    @Test
    @DisplayName("packageType comes from the metadata, else from the type folder, in lowercase")
    void packageType_fromMetaOrFolder() {
        assertEquals("outbound", new PackageFolder("Inbound", List.of(), meta("Outbound ", "2026-11-20T10:00:00Z")).packageType());
        assertEquals("inbound", new PackageFolder("Inbound", List.of(), meta(" ", "2026-11-20T10:00:00Z")).packageType());
        assertEquals("inbound", new PackageFolder("Inbound", List.of(), null).packageType());
    }

    @Test
    @DisplayName("the entries are copied, so later changes to the given list do not leak in")
    void entries_areCopied() {
        List<SftpClient.DirEntry> entries = new ArrayList<>();
        PackageFolder pkg = new PackageFolder("inbound", entries, null);
        entries.add(file("MPackage.json", "2026-11-10T12:00:00Z"));

        assertTrue(pkg.entries().isEmpty());
    }
}
