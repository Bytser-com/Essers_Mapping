package be.pxl.services.runtime.storage;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.apache.sshd.sftp.client.SftpClient;
import org.apache.sshd.sftp.common.SftpConstants;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.integration.file.remote.InputStreamCallback;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;
import tools.jackson.databind.ObjectMapper;

import be.pxl.services.runtime.config.SharedSftpProperties;
import be.pxl.services.runtime.domain.ActiveMappingPackage;
import be.pxl.services.runtime.exception.MappingPackageNotFoundException;
import be.pxl.services.runtime.exception.SharedStorageException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SftpMappingPackageStorageTest {

    private static final String ROOT = "/Packages";

    private SftpRemoteFileTemplate template;
    private SftpMappingPackageStorage storage;

    @BeforeEach
    void setUp() {
        template = mock(SftpRemoteFileTemplate.class);
        // By default nothing exists on the mocked SFTP
        when(template.exists(anyString())).thenReturn(false);
        SharedSftpProperties properties = new SharedSftpProperties("localhost", 22, "shareduser", "", ROOT, true);
        storage = new SftpMappingPackageStorage(template, properties, new ObjectMapper());
    }

    @Test
    @DisplayName("TC-52-01 a known customer gets the package that is active in active.json, with status ACTIVE")
    void getActivePackageReturnsVersionFromActiveJson() {
        folder(ROOT, "nouryon");
        folder(ROOT + "/nouryon", "v1", "v2");
        folder(ROOT + "/nouryon/v1", "inbound");
        folder(ROOT + "/nouryon/v2", "inbound");
        packageFolder(ROOT + "/nouryon/v1/inbound", "v1");
        packageFolder(ROOT + "/nouryon/v2/inbound", "v2");
        file(ROOT + "/nouryon/active.json", """
                { "inbound": { "version": "v2", "updated_at": "2026-11-20T10:00:00Z", "updated_by": "lead_analyst" } }
                """);

        ActiveMappingPackage result = storage.getActivePackage("nouryon", "inbound");

        assertEquals("nouryon", result.customer());
        assertEquals("inbound", result.packageType());
        assertEquals("v2", result.version());
        assertEquals(ActiveMappingPackage.STATUS_ACTIVE, result.status());
        assertEquals("2026-11-20T10:00:00Z", result.activatedAt());
        assertEquals("lead_analyst", result.activatedBy());
        assertEquals("v2", result.mappingPackage().path("meta").path("package_version").asString());
        assertTrue(result.mappingPackage().path("mappings").isArray());
    }

    @Test
    @DisplayName("TC-52-02 only the active version is returned, not an older or newer version")
    void getActivePackageReturnsOnlyActiveVersion() {
        nouryonWithThreeVersions();
        file(ROOT + "/nouryon/active.json", """
                { "inbound": { "version": "v2" } }
                """);

        ActiveMappingPackage result = storage.getActivePackage("nouryon", "inbound");

        assertEquals("v2", result.version());
        assertEquals("v2", result.mappingPackage().path("meta").path("package_version").asString());
    }

    @Test
    @DisplayName("Without active.json the newest version is active, like on the Version Control page")
    void getActivePackageWithoutActiveJsonReturnsNewestVersion() {
        nouryonWithThreeVersions();

        ActiveMappingPackage result = storage.getActivePackage("nouryon", "inbound");

        assertEquals("v3", result.version());
        // No active.json: date and user come from the meta block of MPackage.json
        assertEquals("2024-06-19T12:00:00Z", result.activatedAt());
        assertEquals("analist_a", result.activatedBy());
    }

    @Test
    @DisplayName("active.json pointing to a version that does not exist falls back to the newest version")
    void getActivePackageWithMissingActiveVersionReturnsNewestVersion() {
        nouryonWithThreeVersions();
        file(ROOT + "/nouryon/active.json", """
                { "inbound": { "version": "v9" } }
                """);

        assertEquals("v3", storage.getActivePackage("nouryon", "inbound").version());
    }

    @Test
    @DisplayName("A broken active.json is ignored and the newest version is used")
    void getActivePackageWithBrokenActiveJsonReturnsNewestVersion() {
        nouryonWithThreeVersions();
        file(ROOT + "/nouryon/active.json", "not json");

        assertEquals("v3", storage.getActivePackage("nouryon", "inbound").version());
    }

    @Test
    @DisplayName("v10 is newer than v9 (versions are compared as numbers, not as text)")
    void getActivePackageComparesVersionsAsNumbers() {
        folder(ROOT, "nouryon");
        folder(ROOT + "/nouryon", "v9", "v10");
        folder(ROOT + "/nouryon/v9", "inbound");
        folder(ROOT + "/nouryon/v10", "inbound");
        packageFolder(ROOT + "/nouryon/v9/inbound", "v9");
        packageFolder(ROOT + "/nouryon/v10/inbound", "v10");

        assertEquals("v10", storage.getActivePackage("nouryon", "inbound").version());
    }

    @Test
    @DisplayName("Customer and type are found regardless of upper/lower case")
    void getActivePackageIgnoresCase() {
        nouryonWithThreeVersions();

        ActiveMappingPackage result = storage.getActivePackage("Nouryon", "INBOUND");

        assertEquals("nouryon", result.customer());
        assertEquals("inbound", result.packageType());
    }

    @Test
    @DisplayName("An outbound package is not returned when inbound is asked")
    void getActivePackageForOtherTypeThrowsNotFound() {
        folder(ROOT, "nouryon");
        folder(ROOT + "/nouryon", "v1");
        folder(ROOT + "/nouryon/v1", "outbound");
        packageFolder(ROOT + "/nouryon/v1/outbound", "v1");

        assertThrows(MappingPackageNotFoundException.class, () -> storage.getActivePackage("nouryon", "inbound"));
    }

    @Test
    @DisplayName("An unknown customer gives MappingPackageNotFoundException")
    void getActivePackageForUnknownCustomerThrowsNotFound() {
        folder(ROOT, "nouryon");

        assertThrows(MappingPackageNotFoundException.class,
                () -> storage.getActivePackage("onbekendeklant123", "inbound"));
    }

    @Test
    @DisplayName("A path in the customer or type is refused, so no other folder can be read")
    void getActivePackageRefusesPathTraversal() {
        assertThrows(IllegalArgumentException.class, () -> storage.getActivePackage("../secret", "inbound"));
        assertThrows(IllegalArgumentException.class, () -> storage.getActivePackage("nouryon", "in/bound"));
    }

    @Test
    @DisplayName("An empty customer or type gives IllegalArgumentException")
    void getActivePackageRefusesEmptyParameters() {
        assertThrows(IllegalArgumentException.class, () -> storage.getActivePackage(" ", "inbound"));
        assertThrows(IllegalArgumentException.class, () -> storage.getActivePackage("nouryon", null));
    }

    @Test
    @DisplayName("A broken MPackage.json gives SharedStorageException")
    void getActivePackageWithBrokenPackageJsonThrowsStorageException() {
        folder(ROOT, "nouryon");
        folder(ROOT + "/nouryon", "v1");
        folder(ROOT + "/nouryon/v1", "inbound");
        when(template.exists(ROOT + "/nouryon/v1/inbound")).thenReturn(true);
        when(template.list(ROOT + "/nouryon/v1/inbound")).thenReturn(new SftpClient.DirEntry[] {fileEntry("MPackage.json")});
        file(ROOT + "/nouryon/v1/inbound/MPackage.json", "{ not json");

        assertThrows(SharedStorageException.class, () -> storage.getActivePackage("nouryon", "inbound"));
    }

    @Test
    @DisplayName("An SFTP server that cannot be reached gives SharedStorageException")
    void getActivePackageWithSftpDownThrowsStorageException() {
        when(template.exists(ROOT)).thenThrow(new IllegalStateException("Connection refused"));

        assertThrows(SharedStorageException.class, () -> storage.getActivePackage("nouryon", "inbound"));
    }

    // nouryon with v1, v2 and v3 for inbound
    private void nouryonWithThreeVersions() {
        folder(ROOT, "nouryon");
        folder(ROOT + "/nouryon", "v1", "v2", "v3");
        for (String version : new String[] {"v1", "v2", "v3"}) {
            folder(ROOT + "/nouryon/" + version, "inbound");
            packageFolder(ROOT + "/nouryon/" + version + "/inbound", version);
        }
    }

    // A folder with the given subfolders
    private void folder(String path, String... subfolders) {
        SftpClient.DirEntry[] entries = new SftpClient.DirEntry[subfolders.length];
        for (int i = 0; i < subfolders.length; i++) {
            entries[i] = dirEntry(subfolders[i]);
        }
        when(template.exists(path)).thenReturn(true);
        when(template.list(path)).thenReturn(entries);
    }

    // A type folder (e.g. /Packages/nouryon/v2/inbound) with an MPackage.json
    private void packageFolder(String typePath, String version) {
        when(template.exists(typePath)).thenReturn(true);
        when(template.list(typePath)).thenReturn(new SftpClient.DirEntry[] {fileEntry("MPackage.json")});
        file(typePath + "/MPackage.json", """
                {
                  "schema_version": "1.0",
                  "meta": {
                    "client_name": "nouryon",
                    "package_version": "%s",
                    "package_type": "inbound",
                    "date_created": "2024-06-19T12:00:00Z",
                    "user_created": "analist_a"
                  },
                  "mappings": [ { "target": "Order/DeliveryDate", "source": "E1EDK03/DATUM" } ]
                }
                """.formatted(version));
    }

    // A file with the given content
    private void file(String path, String content) {
        when(template.exists(path)).thenReturn(true);
        doAnswer(invocation -> {
            InputStreamCallback callback = invocation.getArgument(1);
            try (InputStream in = new ByteArrayInputStream(content.getBytes(StandardCharsets.UTF_8))) {
                callback.doWithInputStream(in);
            }
            return true;
        }).when(template).get(eq(path), any(InputStreamCallback.class));
    }

    private static SftpClient.DirEntry dirEntry(String name) {
        SftpClient.Attributes attributes = new SftpClient.Attributes();
        attributes.setType(SftpConstants.SSH_FILEXFER_TYPE_DIRECTORY);
        attributes.setPermissions(0040755);
        return new SftpClient.DirEntry(name, name, attributes);
    }

    private static SftpClient.DirEntry fileEntry(String name) {
        SftpClient.Attributes attributes = new SftpClient.Attributes();
        attributes.setType(SftpConstants.SSH_FILEXFER_TYPE_REGULAR);
        attributes.setPermissions(0100644);
        return new SftpClient.DirEntry(name, name, attributes);
    }
}
