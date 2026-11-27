package be.essers.services.versioncontrol.service;

import be.essers.services.versioncontrol.domain.dto.MappingPackageOverviewDto;
import be.essers.services.versioncontrol.exception.EntityNotFoundException;
import be.essers.services.versioncontrol.exception.StorageException;
import tools.jackson.databind.ObjectMapper;
import org.apache.sshd.sftp.client.SftpClient;
import org.apache.sshd.sftp.common.SftpConstants;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.integration.file.remote.InputStreamCallback;
import org.springframework.integration.file.remote.SessionCallback;
import org.springframework.integration.file.remote.session.Session;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.attribute.FileTime;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class SftpPackageStorageServiceTest {

    private static final String PACKAGES_ROOT = "/Packages";

    @Mock
    private SftpRemoteFileTemplate template;

    private SftpPackageStorageService service;

    @BeforeEach
    void setUp() {
        service = new SftpPackageStorageService(template, new ObjectMapper(), PACKAGES_ROOT);
    }

    private SftpClient.DirEntry createEntry(String name, boolean isDir) {
        SftpClient.Attributes attrs = new SftpClient.Attributes();
        attrs.setType(isDir ? SftpConstants.SSH_FILEXFER_TYPE_DIRECTORY : SftpConstants.SSH_FILEXFER_TYPE_REGULAR);
        attrs.setPermissions(isDir ? 0040755 : 0100644);
        attrs.setModifyTime(FileTime.from(Instant.parse("2026-11-10T12:00:00Z")));
        return new SftpClient.DirEntry(name, name, attrs);
    }

    // Puts the given subdirectories in a folder on the mocked SFTP
    private void mockDirectories(String path, String... names) {
        SftpClient.DirEntry[] entries = new SftpClient.DirEntry[names.length];
        for (int i = 0; i < names.length; i++) {
            entries[i] = createEntry(names[i], true);
        }
        when(template.list(path)).thenReturn(entries);
    }

    // Puts a type folder with an MPackage.json with the given content on the mocked SFTP
    private void mockTypeWithPackage(String typePath, String packageJson) {
        mockTypeWithPackage(typePath, "MPackage.json", packageJson);
    }

    private void mockTypeWithPackage(String typePath, String filename, String packageJson) {
        when(template.list(typePath)).thenReturn(new SftpClient.DirEntry[]{createEntry(filename, false)});
        doAnswer(invocation -> {
            InputStreamCallback callback = invocation.getArgument(1);
            try (InputStream in = new ByteArrayInputStream(packageJson.getBytes(StandardCharsets.UTF_8))) {
                callback.doWithInputStream(in);
            }
            return true;
        }).when(template).get(eq(typePath + "/" + filename), any(InputStreamCallback.class));
    }

    // MPackage.json as written for a mapping package: a meta block and the mappings
    private String packageJson(String clientName, String packageType, String dateCreated, String userCreated) {
        return """
                {
                  "schema_version": "1.0",
                  "meta": {
                    "client_name": "%s",
                    "package_version": "1.0.0",
                    "package_type": "%s",
                    "date_created": "%s",
                    "user_created": "%s",
                    "description": "Mapping for inbound IDOC conversion"
                  },
                  "mappings": [
                    {
                      "source_path": "/DELVRY03/IDOC/@BEGIN",
                      "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/@BEGIN"
                    },
                    {
                      "source_path": null,
                      "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPADR1/NAME_3"
                    }
                  ]
                }
                """.formatted(clientName, packageType, dateCreated, userCreated);
    }

    @Test
    @DisplayName("listPackages for company returns the meta block of MPackage.json")
    void listPackages_forCompany_returnsMetaOfPackage() {
        when(template.exists("/Packages/Nouryon")).thenReturn(true);
        mockDirectories("/Packages/Nouryon", "v1");
        mockDirectories("/Packages/Nouryon/v1", "inbound");
        mockTypeWithPackage("/Packages/Nouryon/v1/inbound",
                packageJson("nouryon", "inbound", "2024-06-19T12:00:00Z", "analist_a"));

        List<MappingPackageOverviewDto> results = service.listPackages("Nouryon");

        assertEquals(1, results.size());
        MappingPackageOverviewDto dto = results.get(0);
        assertEquals("Nouryon", dto.company());
        assertEquals("v1", dto.latestVersion());
        assertEquals("2024-06-19T12:00:00Z", dto.createdAt());
        assertEquals("analist_a", dto.createdBy());
        assertEquals("nouryon", dto.customerName());
        assertEquals("inbound", dto.packageType());
    }

    @Test
    @DisplayName("listPackages returns the newest version per package type of a company")
    void listPackages_forCompany_returnsLatestVersionPerType() {
        when(template.exists("/Packages/Nouryon")).thenReturn(true);
        mockDirectories("/Packages/Nouryon", "v1", "v2");
        mockDirectories("/Packages/Nouryon/v2", "inbound");
        mockDirectories("/Packages/Nouryon/v1", "inbound", "outbound");
        mockTypeWithPackage("/Packages/Nouryon/v2/inbound",
                packageJson("nouryon", "inbound", "2026-11-12T10:00:00Z", "analist_b"));
        mockTypeWithPackage("/Packages/Nouryon/v1/inbound",
                packageJson("nouryon", "inbound", "2026-10-01T10:00:00Z", "analist_a"));
        mockTypeWithPackage("/Packages/Nouryon/v1/outbound",
                packageJson("nouryon", "outbound", "2026-10-02T10:00:00Z", "analist_a"));

        List<MappingPackageOverviewDto> results = service.listPackages("Nouryon");

        assertEquals(2, results.size());
        MappingPackageOverviewDto inbound = results.get(0);
        assertEquals("inbound", inbound.packageType());
        assertEquals("v2", inbound.latestVersion());
        assertEquals("analist_b", inbound.createdBy());

        // Only exists in v1, so v1 is the newest outbound package
        MappingPackageOverviewDto outbound = results.get(1);
        assertEquals("outbound", outbound.packageType());
        assertEquals("v1", outbound.latestVersion());
    }

    @Test
    @DisplayName("listPackages orders versions naturally: v10 is newer than v9")
    void listPackages_usesNaturalVersionOrder() {
        when(template.exists("/Packages/Nouryon")).thenReturn(true);
        mockDirectories("/Packages/Nouryon", "v10", "v9");
        mockDirectories("/Packages/Nouryon/v10", "inbound");
        mockDirectories("/Packages/Nouryon/v9", "inbound");
        mockTypeWithPackage("/Packages/Nouryon/v10/inbound",
                packageJson("nouryon", "inbound", "2026-11-12T10:00:00Z", "analist_b"));
        mockTypeWithPackage("/Packages/Nouryon/v9/inbound",
                packageJson("nouryon", "inbound", "2026-10-01T10:00:00Z", "analist_a"));

        List<MappingPackageOverviewDto> results = service.listPackages("Nouryon");

        assertEquals(1, results.size());
        assertEquals("v10", results.get(0).latestVersion());
    }

    @Test
    @DisplayName("listPackages without company returns all packages alphabetically on customer name, then type")
    void listPackages_withoutCompany_returnsAllPackagesAlphabetically() {
        when(template.exists(PACKAGES_ROOT)).thenReturn(true);
        mockDirectories(PACKAGES_ROOT, "zentrova", "nouryon", "brevalis");

        mockDirectories("/Packages/zentrova", "v1");
        mockDirectories("/Packages/zentrova/v1", "inbound");
        mockTypeWithPackage("/Packages/zentrova/v1/inbound",
                packageJson("Zentrova", "inbound", "2026-11-20T10:00:00Z", "analist_a"));

        mockDirectories("/Packages/nouryon", "v1");
        mockDirectories("/Packages/nouryon/v1", "outbound", "inbound");
        mockTypeWithPackage("/Packages/nouryon/v1/outbound",
                packageJson("Nouryon", "outbound", "2026-10-01T10:00:00Z", "analist_a"));
        mockTypeWithPackage("/Packages/nouryon/v1/inbound",
                packageJson("Nouryon", "inbound", "2026-10-02T10:00:00Z", "analist_a"));

        mockDirectories("/Packages/brevalis", "v1");
        mockDirectories("/Packages/brevalis/v1", "outbound");
        mockTypeWithPackage("/Packages/brevalis/v1/outbound",
                packageJson("brevalis", "outbound", "2026-09-01T10:00:00Z", "analist_b"));

        List<MappingPackageOverviewDto> results = service.listPackages(null);

        assertEquals(4, results.size());
        assertEquals("brevalis", results.get(0).customerName());
        assertEquals("outbound", results.get(0).packageType());
        assertEquals("Nouryon", results.get(1).customerName());
        assertEquals("inbound", results.get(1).packageType());
        assertEquals("Nouryon", results.get(2).customerName());
        assertEquals("outbound", results.get(2).packageType());
        assertEquals("Zentrova", results.get(3).customerName());
    }

    @Test
    @DisplayName("listPackages sorts on the company folder when the package has no client_name")
    void listPackages_sortsOnCompanyFolderWhenClientNameMissing() {
        when(template.exists(PACKAGES_ROOT)).thenReturn(true);
        mockDirectories(PACKAGES_ROOT, "quorvia", "brevalis");

        mockDirectories("/Packages/quorvia", "v1");
        mockDirectories("/Packages/quorvia/v1", "inbound");
        mockTypeWithPackage("/Packages/quorvia/v1/inbound", """
                { "meta": { "package_type": "inbound", "date_created": "2026-11-01T10:00:00Z" } }
                """);

        mockDirectories("/Packages/brevalis", "v1");
        mockDirectories("/Packages/brevalis/v1", "inbound");
        mockTypeWithPackage("/Packages/brevalis/v1/inbound", """
                { "meta": { "client_name": "Zeta Brevalis", "package_type": "inbound", "date_created": "2026-11-01T10:00:00Z" } }
                """);

        List<MappingPackageOverviewDto> results = service.listPackages(null);

        assertEquals(2, results.size());
        assertEquals("quorvia", results.get(0).company());
        assertNull(results.get(0).customerName());
        assertEquals("Zeta Brevalis", results.get(1).customerName());
    }

    @Test
    @DisplayName("packageType comes from meta.package_type, also when the type folder has another name")
    void listPackages_packageTypeComesFromMeta() {
        when(template.exists("/Packages/Brevalis")).thenReturn(true);
        mockDirectories("/Packages/Brevalis", "v1");
        mockDirectories("/Packages/Brevalis/v1", "outbound");
        mockTypeWithPackage("/Packages/Brevalis/v1/outbound",
                packageJson("brevalis", "INBOUND", "2025-07-15T12:00:00Z", "analist_b"));

        List<MappingPackageOverviewDto> results = service.listPackages("Brevalis");

        assertEquals(1, results.size());
        assertEquals("inbound", results.get(0).packageType());
    }

    @Test
    @DisplayName("packageType falls back to the type folder (lowercase) when meta.package_type is missing")
    void listPackages_packageTypeFallsBackToTypeFolder() {
        when(template.exists("/Packages/Brevalis")).thenReturn(true);
        mockDirectories("/Packages/Brevalis", "v1");
        mockDirectories("/Packages/Brevalis/v1", "Outbound");
        mockTypeWithPackage("/Packages/Brevalis/v1/Outbound", """
                { "meta": { "client_name": "brevalis", "date_created": "2025-07-15T12:00:00Z" } }
                """);

        List<MappingPackageOverviewDto> results = service.listPackages("Brevalis");

        assertEquals(1, results.size());
        assertEquals("outbound", results.get(0).packageType());
    }

    @Test
    @DisplayName("MPackage.json is found case-insensitively")
    void listPackages_findsPackageFileCaseInsensitively() {
        when(template.exists("/Packages/Nouryon")).thenReturn(true);
        mockDirectories("/Packages/Nouryon", "v1");
        mockDirectories("/Packages/Nouryon/v1", "inbound");
        mockTypeWithPackage("/Packages/Nouryon/v1/inbound", "mpackage.JSON",
                packageJson("nouryon", "inbound", "2024-06-19T12:00:00Z", "analist_a"));

        List<MappingPackageOverviewDto> results = service.listPackages("Nouryon");

        assertEquals(1, results.size());
        assertEquals("analist_a", results.get(0).createdBy());
    }

    @Test
    @DisplayName("when the newest version is broken, the newest valid version of that type is shown")
    void listPackages_skipsBrokenNewestVersion() {
        when(template.exists("/Packages/Nouryon")).thenReturn(true);
        mockDirectories("/Packages/Nouryon", "v1", "v2", "v3");
        mockDirectories("/Packages/Nouryon/v3", "inbound");
        mockDirectories("/Packages/Nouryon/v2", "inbound");
        mockDirectories("/Packages/Nouryon/v1", "inbound");
        // v3: not valid JSON, v2: no meta block, v1: valid
        mockTypeWithPackage("/Packages/Nouryon/v3/inbound", "{ this is not json");
        mockTypeWithPackage("/Packages/Nouryon/v2/inbound", """
                { "schema_version": "1.0", "mappings": [] }
                """);
        mockTypeWithPackage("/Packages/Nouryon/v1/inbound",
                packageJson("nouryon", "inbound", "2026-10-01T10:00:00Z", "analist_a"));

        List<MappingPackageOverviewDto> results = service.listPackages("Nouryon");

        assertEquals(1, results.size());
        assertEquals("v1", results.get(0).latestVersion());
    }

    @Test
    @DisplayName("a package without a valid date_created is skipped, the others are shown")
    void listPackages_skipsPackageWithInvalidDate() {
        when(template.exists(PACKAGES_ROOT)).thenReturn(true);
        mockDirectories(PACKAGES_ROOT, "nouryon", "brevalis");

        mockDirectories("/Packages/nouryon", "v1");
        mockDirectories("/Packages/nouryon/v1", "inbound");
        mockTypeWithPackage("/Packages/nouryon/v1/inbound",
                packageJson("nouryon", "inbound", "gisteren", "analist_a"));

        mockDirectories("/Packages/brevalis", "v1");
        mockDirectories("/Packages/brevalis/v1", "inbound");
        mockTypeWithPackage("/Packages/brevalis/v1/inbound",
                packageJson("brevalis", "inbound", "2026-10-01T10:00:00Z", "analist_b"));

        List<MappingPackageOverviewDto> results = service.listPackages(null);

        assertEquals(1, results.size());
        assertEquals("brevalis", results.get(0).company());
    }

    @Test
    @DisplayName("listPackages for company falls back to the file modify time when MPackage.json is absent")
    void listPackages_forCompany_fallbackWhenPackageFileMissing() {
        when(template.exists("/Packages/Nouryon")).thenReturn(true);
        mockDirectories("/Packages/Nouryon", "v1");
        mockDirectories("/Packages/Nouryon/v1", "Inbound");
        when(template.list("/Packages/Nouryon/v1/Inbound"))
                .thenReturn(new SftpClient.DirEntry[]{createEntry("notes.txt", false)});

        List<MappingPackageOverviewDto> results = service.listPackages("Nouryon");

        assertEquals(1, results.size());
        MappingPackageOverviewDto dto = results.get(0);
        assertEquals("Nouryon", dto.company());
        assertEquals("v1", dto.latestVersion());
        assertEquals("2026-11-10T12:00:00Z", dto.createdAt());
        assertNull(dto.createdBy());
        assertNull(dto.customerName());
        assertEquals("inbound", dto.packageType());
    }

    @Test
    @DisplayName("listPackages without company skips a company without valid packages")
    void listPackages_withoutCompany_skipsCompanyWithoutValidPackages() {
        when(template.exists(PACKAGES_ROOT)).thenReturn(true);
        mockDirectories(PACKAGES_ROOT, "nouryon");
        mockDirectories("/Packages/nouryon", "v1");
        mockDirectories("/Packages/nouryon/v1", "inbound");
        when(template.list("/Packages/nouryon/v1/inbound"))
                .thenReturn(new SftpClient.DirEntry[]{createEntry("notes.txt", false)});

        List<MappingPackageOverviewDto> results = service.listPackages(null);

        assertTrue(results.isEmpty());
    }

    @Test
    @DisplayName("listPackages resolves the company folder case-insensitively")
    void listPackages_resolvesCompanyCaseInsensitively() {
        when(template.exists("/Packages/nouryon")).thenReturn(false);
        mockDirectories(PACKAGES_ROOT, "Nouryon");
        mockDirectories("/Packages/Nouryon", "v1");
        mockDirectories("/Packages/Nouryon/v1", "inbound");
        mockTypeWithPackage("/Packages/Nouryon/v1/inbound",
                packageJson("nouryon", "inbound", "2024-06-19T12:00:00Z", "analist_a"));

        List<MappingPackageOverviewDto> results = service.listPackages("nouryon");

        assertEquals(1, results.size());
        assertEquals("Nouryon", results.get(0).company());
    }

    @Test
    @DisplayName("listPackages without company returns an empty list when the packages root does not exist")
    void listPackages_withoutCompany_emptyWhenRootMissing() {
        when(template.exists(PACKAGES_ROOT)).thenReturn(false);

        List<MappingPackageOverviewDto> results = service.listPackages(null);

        assertTrue(results.isEmpty());
    }

    @Test
    @DisplayName("listPackages ignores files next to the company folders")
    void listPackages_ignoresNonDirectoryEntries() {
        when(template.exists(PACKAGES_ROOT)).thenReturn(true);
        when(template.list(PACKAGES_ROOT)).thenReturn(new SftpClient.DirEntry[]{
                createEntry(".", true), createEntry("..", true), createEntry("readme.txt", false)});

        List<MappingPackageOverviewDto> results = service.listPackages(null);

        assertTrue(results.isEmpty());
    }

    @Test
    @DisplayName("listPackages with non-existent company throws EntityNotFoundException")
    void listPackages_unknownCompany_throwsNotFound() {
        when(template.exists("/Packages/UnknownCompany")).thenReturn(false);

        assertThrows(EntityNotFoundException.class, () -> service.listPackages("UnknownCompany"));
    }

    @Test
    @DisplayName("listPackages for company with no versions throws EntityNotFoundException")
    void listPackages_companyWithoutVersions_throwsNotFound() {
        when(template.exists("/Packages/EmptyCompany")).thenReturn(true);
        when(template.list("/Packages/EmptyCompany")).thenReturn(new SftpClient.DirEntry[0]);

        assertThrows(EntityNotFoundException.class, () -> service.listPackages("EmptyCompany"));
    }

    @Test
    @DisplayName("listPackages for company with an empty latest version throws EntityNotFoundException")
    void listPackages_companyWithoutTypes_throwsNotFound() {
        when(template.exists("/Packages/Nouryon")).thenReturn(true);
        mockDirectories("/Packages/Nouryon", "v1");

        assertThrows(EntityNotFoundException.class, () -> service.listPackages("Nouryon"));
    }

    @Test
    @DisplayName("listPackages with path traversal or a too long company throws IllegalArgumentException")
    void listPackages_invalidCompany_throwsIllegalArgument() {
        assertThrows(IllegalArgumentException.class, () -> service.listPackages("../etc"));
        assertThrows(IllegalArgumentException.class, () -> service.listPackages("Nouryon/sub"));
        assertThrows(IllegalArgumentException.class, () -> service.listPackages("Nouryon\\sub"));
        assertThrows(IllegalArgumentException.class, () -> service.listPackages("abcdefghijklmnopqrstu"));
    }

    @Test
    @DisplayName("listPackages handles general exception with StorageException")
    void listPackages_sftpFailure_throwsStorageException() {
        when(template.exists(PACKAGES_ROOT)).thenThrow(new RuntimeException("Connection lost"));

        assertThrows(StorageException.class, () -> service.listPackages(null));
    }

    @Test
    @DisplayName("parseCreationTime reads ISO 8601 with and without timezone and rejects other text")
    void parseCreationTime_parsesIsoTimes() {
        assertEquals(Instant.parse("2026-10-22T12:05:00Z"),
                PackageFolder.parseCreationTime("2026-10-22T14:05:00+02:00"));
        assertEquals(Instant.parse("2026-10-22T14:05:00Z"),
                PackageFolder.parseCreationTime("2026-10-22T14:05:00"));
        assertNull(PackageFolder.parseCreationTime("22/10/2026"));
        assertNull(PackageFolder.parseCreationTime(" "));
        assertNull(PackageFolder.parseCreationTime(null));
    }

    @Test
    @DisplayName("listPackages uses active.json to determine active version, updatedBy and updatedAt")
    void listPackages_withActiveJson_returnsActiveVersion() {
        when(template.exists("/Packages/Nouryon")).thenReturn(true);
        mockDirectories("/Packages/Nouryon", "v1", "v2");
        mockDirectories("/Packages/Nouryon/v1", "inbound");
        mockDirectories("/Packages/Nouryon/v2", "inbound");
        mockTypeWithPackage("/Packages/Nouryon/v1/inbound",
                packageJson("nouryon", "inbound", "2024-06-19T12:00:00Z", "analist_a"));
        mockTypeWithPackage("/Packages/Nouryon/v2/inbound",
                packageJson("nouryon", "inbound", "2024-07-20T12:00:00Z", "analist_b"));

        // active.json points inbound to v1
        String activeJson = """
                {
                  "inbound": {
                    "version": "v1",
                    "updated_at": "2024-08-01T15:00:00Z",
                    "updated_by": "lead_analyst"
                  }
                }
                """;
        when(template.exists("/Packages/Nouryon/active.json")).thenReturn(true);
        doAnswer(inv -> {
            InputStreamCallback cb = inv.getArgument(1);
            try (InputStream in = new ByteArrayInputStream(activeJson.getBytes(StandardCharsets.UTF_8))) {
                cb.doWithInputStream(in);
            }
            return true;
        }).when(template).get(eq("/Packages/Nouryon/active.json"), any(InputStreamCallback.class));

        List<MappingPackageOverviewDto> results = service.listPackages("Nouryon");
        assertEquals(1, results.size());
        MappingPackageOverviewDto dto = results.get(0);
        assertEquals("v1", dto.activeVersion());
        assertEquals("v1", dto.latestVersion());
        assertEquals("2024-08-01T15:00:00Z", dto.activeUpdatedAt());
        assertEquals("lead_analyst", dto.activeUpdatedBy());
        assertEquals("2024-06-19T12:00:00Z", dto.createdAt());
        assertEquals("analist_a", dto.createdBy());
    }

    @Test
    @DisplayName("setActivePackage updates active.json and returns updated overview")
    void setActivePackage_updatesActiveJson() {
        when(template.exists("/Packages/Nouryon")).thenReturn(true);
        when(template.exists("/Packages/Nouryon/v1")).thenReturn(true);
        when(template.exists("/Packages/Nouryon/v1/inbound")).thenReturn(true);
        mockTypeWithPackage("/Packages/Nouryon/v1/inbound",
                packageJson("nouryon", "inbound", "2024-06-19T12:00:00Z", "analist_a"));

        when(template.exists("/Packages/Nouryon/active.json")).thenReturn(false);

        MappingPackageOverviewDto updated = service.setActivePackage("Nouryon", "inbound", "v1", "analist_x");
        assertNotNull(updated);
        assertEquals("v1", updated.activeVersion());
        assertEquals("v1", updated.latestVersion());
        assertEquals("analist_x", updated.activeUpdatedBy());
        assertNotNull(updated.activeUpdatedAt());
        verify(template, atLeastOnce()).execute(any());
    }

    @Test
    @DisplayName("listVersions returns all versions for a type with active flag")
    void listVersions_returnsVersionsWithActiveFlag() {
        when(template.exists("/Packages/Nouryon")).thenReturn(true);
        mockDirectories("/Packages/Nouryon", "v1", "v2");
        mockDirectories("/Packages/Nouryon/v1", "inbound");
        mockDirectories("/Packages/Nouryon/v2", "inbound");
        mockTypeWithPackage("/Packages/Nouryon/v1/inbound",
                packageJson("nouryon", "inbound", "2024-06-19T12:00:00Z", "analist_a"));
        mockTypeWithPackage("/Packages/Nouryon/v2/inbound",
                packageJson("nouryon", "inbound", "2024-07-20T12:00:00Z", "analist_b"));

        String activeJson = """
                {
                  "inbound": {
                    "version": "v1",
                    "updated_at": "2024-08-01T15:00:00Z",
                    "updated_by": "analist_a"
                  }
                }
                """;
        when(template.exists("/Packages/Nouryon/active.json")).thenReturn(true);
        doAnswer(inv -> {
            InputStreamCallback cb = inv.getArgument(1);
            try (InputStream in = new ByteArrayInputStream(activeJson.getBytes(StandardCharsets.UTF_8))) {
                cb.doWithInputStream(in);
            }
            return true;
        }).when(template).get(eq("/Packages/Nouryon/active.json"), any(InputStreamCallback.class));

        var versions = service.listVersions("Nouryon", "inbound");
        assertEquals(2, versions.size());
        assertEquals("v2", versions.get(0).version());
        assertFalse(versions.get(0).isActive());
        assertEquals("v1", versions.get(1).version());
        assertTrue(versions.get(1).isActive());
    }

    // -------------------------------------------------------------------------
    // Safety net for the refactor (IT2627T06-248): setActivePackage, listVersions
    // and the reading of active.json, including the paths that were not tested yet.
    // -------------------------------------------------------------------------

    private static final String ACTIVE_PATH = "/Packages/Nouryon/active.json";
    private static final String TEMP_PATH = "/Packages/Nouryon/.active.json.tmp";

    // Puts an active.json with the given content on the mocked SFTP
    private void mockActiveJson(String json) {
        when(template.exists(ACTIVE_PATH)).thenReturn(true);
        doAnswer(inv -> {
            InputStreamCallback cb = inv.getArgument(1);
            try (InputStream in = new ByteArrayInputStream(json.getBytes(StandardCharsets.UTF_8))) {
                cb.doWithInputStream(in);
            }
            return true;
        }).when(template).get(eq(ACTIVE_PATH), any(InputStreamCallback.class));
    }

    // Nouryon/v1/inbound exists with a valid MPackage.json
    private void mockValidPackageV1Inbound() {
        when(template.exists("/Packages/Nouryon")).thenReturn(true);
        when(template.exists("/Packages/Nouryon/v1")).thenReturn(true);
        when(template.exists("/Packages/Nouryon/v1/inbound")).thenReturn(true);
        mockTypeWithPackage("/Packages/Nouryon/v1/inbound",
                packageJson("nouryon", "inbound", "2024-06-19T12:00:00Z", "analist_a"));
    }

    // Runs the session callback of template.execute on the given session and returns the bytes written to it
    @SuppressWarnings("unchecked")
    private byte[][] runWritesOn(Session<SftpClient.DirEntry> session) throws IOException {
        byte[][] written = new byte[1][];
        doAnswer(inv -> {
            written[0] = ((InputStream) inv.getArgument(0)).readAllBytes();
            return null;
        }).when(session).write(any(InputStream.class), eq(TEMP_PATH));
        when(template.execute(any())).thenAnswer(inv -> {
            SessionCallback<SftpClient.DirEntry, Object> callback = inv.getArgument(0);
            return callback.doInSession(session);
        });
        return written;
    }

    @Test
    @DisplayName("setActivePackage writes active.json via a temp file and keeps the active version of other types")
    @SuppressWarnings("unchecked")
    void setActivePackage_writesAtomicallyAndKeepsOtherTypes() throws IOException {
        mockValidPackageV1Inbound();
        mockActiveJson("""
                { "outbound": { "version": "v3", "updated_at": "2024-01-01T00:00:00Z", "updated_by": "analist_b" } }
                """);
        Session<SftpClient.DirEntry> session = mock(Session.class);
        byte[][] written = runWritesOn(session);

        service.setActivePackage("Nouryon", "inbound", "v1", "analist_x");

        verify(session).rename(TEMP_PATH, ACTIVE_PATH);
        Map<String, Map<String, String>> active = new ObjectMapper().readValue(written[0], Map.class);
        assertEquals("v3", active.get("outbound").get("version"));
        assertEquals("analist_b", active.get("outbound").get("updated_by"));
        assertEquals("v1", active.get("inbound").get("version"));
        assertEquals("analist_x", active.get("inbound").get("updated_by"));
    }

    @Test
    @DisplayName("setActivePackage replaces an existing active.json when the rename fails the first time")
    @SuppressWarnings("unchecked")
    void setActivePackage_renameFails_removesOldFileAndRenamesAgain() throws IOException {
        mockValidPackageV1Inbound();
        Session<SftpClient.DirEntry> session = mock(Session.class);
        runWritesOn(session);
        doThrow(new IOException("file exists")).doNothing().when(session).rename(TEMP_PATH, ACTIVE_PATH);

        service.setActivePackage("Nouryon", "inbound", "v1", "analist_x");

        verify(session).remove(ACTIVE_PATH);
        verify(session, times(2)).rename(TEMP_PATH, ACTIVE_PATH);
    }

    @Test
    @DisplayName("setActivePackage still renames when removing the old active.json fails")
    @SuppressWarnings("unchecked")
    void setActivePackage_removeFails_stillRenames() throws IOException {
        mockValidPackageV1Inbound();
        Session<SftpClient.DirEntry> session = mock(Session.class);
        runWritesOn(session);
        doThrow(new IOException("file exists")).doNothing().when(session).rename(TEMP_PATH, ACTIVE_PATH);
        when(session.remove(ACTIVE_PATH)).thenThrow(new IOException("no such file"));

        assertDoesNotThrow(() -> service.setActivePackage("Nouryon", "inbound", "v1", "analist_x"));

        verify(session, times(2)).rename(TEMP_PATH, ACTIVE_PATH);
    }

    @Test
    @DisplayName("setActivePackage throws StorageException when active.json cannot be written")
    void setActivePackage_writeFails_throwsStorageException() {
        mockValidPackageV1Inbound();
        when(template.execute(any())).thenThrow(new IllegalStateException("SFTP down"));

        StorageException error = assertThrows(StorageException.class,
                () -> service.setActivePackage("Nouryon", "inbound", "v1", "analist_x"));
        assertTrue(error.getMessage().contains("active.json"));
    }

    @Test
    @DisplayName("setActivePackage uses 'analist' when no user is given")
    void setActivePackage_blankUser_usesDefaultUser() {
        mockValidPackageV1Inbound();

        MappingPackageOverviewDto updated = service.setActivePackage("Nouryon", "inbound", "v1", "  ");

        assertEquals("analist", updated.activeUpdatedBy());
        assertEquals("inbound", updated.packageType());
        assertEquals("nouryon", updated.customerName());
        assertEquals("2024-06-19T12:00:00Z", updated.createdAt());
    }

    @Test
    @DisplayName("setActivePackage resolves company, version and type case-insensitively")
    void setActivePackage_resolvesFoldersCaseInsensitively() {
        mockDirectories("/Packages", "Nouryon");
        mockDirectories("/Packages/Nouryon", "V1");
        mockDirectories("/Packages/Nouryon/V1", "Inbound");
        mockTypeWithPackage("/Packages/Nouryon/V1/Inbound",
                packageJson("nouryon", "inbound", "2024-06-19T12:00:00Z", "analist_a"));

        MappingPackageOverviewDto updated = service.setActivePackage("nouryon", "INBOUND", "v1", "analist_x");

        assertEquals("Nouryon", updated.company());
        assertEquals("V1", updated.activeVersion());
        assertEquals("inbound", updated.packageType());
    }

    @Test
    @DisplayName("setActivePackage rejects empty, too long or unsafe parameters")
    void setActivePackage_invalidParameters_throwIllegalArgument() {
        assertThrows(IllegalArgumentException.class, () -> service.setActivePackage(null, "inbound", "v1", "u"));
        assertThrows(IllegalArgumentException.class, () -> service.setActivePackage(" ", "inbound", "v1", "u"));
        assertThrows(IllegalArgumentException.class,
                () -> service.setActivePackage("a".repeat(21), "inbound", "v1", "u"));
        assertThrows(IllegalArgumentException.class, () -> service.setActivePackage("Nouryon", " ", "v1", "u"));
        assertThrows(IllegalArgumentException.class, () -> service.setActivePackage("Nouryon", "inbound", null, "u"));
        assertThrows(IllegalArgumentException.class, () -> service.setActivePackage("../etc", "inbound", "v1", "u"));
        verifyNoInteractions(template);
    }

    @Test
    @DisplayName("setActivePackage throws EntityNotFoundException for an unknown company, version or type")
    void setActivePackage_unknownFolders_throwNotFound() {
        assertThrows(EntityNotFoundException.class, () -> service.setActivePackage("Onbekend", "inbound", "v1", "u"));

        when(template.exists("/Packages/Nouryon")).thenReturn(true);
        assertThrows(EntityNotFoundException.class, () -> service.setActivePackage("Nouryon", "inbound", "v9", "u"));

        when(template.exists("/Packages/Nouryon/v1")).thenReturn(true);
        assertThrows(EntityNotFoundException.class, () -> service.setActivePackage("Nouryon", "outbound", "v1", "u"));
    }

    @Test
    @DisplayName("setActivePackage throws EntityNotFoundException when the package has no valid MPackage.json")
    void setActivePackage_invalidPackage_throwsNotFound() {
        when(template.exists("/Packages/Nouryon")).thenReturn(true);
        when(template.exists("/Packages/Nouryon/v1")).thenReturn(true);
        when(template.exists("/Packages/Nouryon/v1/inbound")).thenReturn(true);
        when(template.list("/Packages/Nouryon/v1/inbound")).thenReturn(new SftpClient.DirEntry[0]);

        EntityNotFoundException error = assertThrows(EntityNotFoundException.class,
                () -> service.setActivePackage("Nouryon", "inbound", "v1", "u"));
        assertTrue(error.getMessage().contains("invalid"));
    }

    @Test
    @DisplayName("listVersions marks the newest version as active when there is no active.json")
    void listVersions_withoutActiveJson_newestIsActive() {
        when(template.exists("/Packages/Nouryon")).thenReturn(true);
        mockDirectories("/Packages/Nouryon", "v1", "v2");
        mockDirectories("/Packages/Nouryon/v1", "inbound");
        mockDirectories("/Packages/Nouryon/v2", "inbound", "outbound");
        mockTypeWithPackage("/Packages/Nouryon/v1/inbound",
                packageJson("nouryon", "inbound", "2024-06-19T12:00:00Z", "analist_a"));
        mockTypeWithPackage("/Packages/Nouryon/v2/inbound",
                packageJson("nouryon", "inbound", "2024-07-20T12:00:00Z", "analist_b"));

        var versions = service.listVersions("Nouryon", "inbound");

        assertEquals(List.of("v2", "v1"), versions.stream().map(v -> v.version()).toList());
        assertTrue(versions.get(0).isActive());
        assertFalse(versions.get(1).isActive());
        assertEquals("analist_b", versions.get(0).createdBy());
        assertEquals("Mapping for inbound IDOC conversion", versions.get(0).description());
    }

    @Test
    @DisplayName("listVersions skips a version without a valid MPackage.json")
    void listVersions_skipsInvalidPackage() {
        when(template.exists("/Packages/Nouryon")).thenReturn(true);
        mockDirectories("/Packages/Nouryon", "v1", "v2");
        mockDirectories("/Packages/Nouryon/v1", "inbound");
        mockDirectories("/Packages/Nouryon/v2", "inbound");
        mockTypeWithPackage("/Packages/Nouryon/v1/inbound",
                packageJson("nouryon", "inbound", "2024-06-19T12:00:00Z", "analist_a"));
        when(template.list("/Packages/Nouryon/v2/inbound")).thenReturn(new SftpClient.DirEntry[0]);

        var versions = service.listVersions("Nouryon", "inbound");

        assertEquals(1, versions.size());
        assertEquals("v1", versions.get(0).version());
    }

    @Test
    @DisplayName("listVersions rejects empty parameters and an unknown company")
    void listVersions_invalidParameters() {
        assertThrows(IllegalArgumentException.class, () -> service.listVersions(null, "inbound"));
        assertThrows(IllegalArgumentException.class, () -> service.listVersions("Nouryon", " "));
        assertThrows(EntityNotFoundException.class, () -> service.listVersions("Onbekend", "inbound"));
    }

    @Test
    @DisplayName("active.json in the older format with a \"types\" block is still read")
    void listPackages_readsActiveJsonWithTypesBlock() {
        when(template.exists("/Packages/Nouryon")).thenReturn(true);
        mockDirectories("/Packages/Nouryon", "v1", "v2");
        mockDirectories("/Packages/Nouryon/v1", "inbound");
        mockDirectories("/Packages/Nouryon/v2", "inbound");
        mockTypeWithPackage("/Packages/Nouryon/v1/inbound",
                packageJson("nouryon", "inbound", "2024-06-19T12:00:00Z", "analist_a"));
        mockTypeWithPackage("/Packages/Nouryon/v2/inbound",
                packageJson("nouryon", "inbound", "2024-07-20T12:00:00Z", "analist_b"));
        mockActiveJson("""
                { "types": { "Inbound": { "version": "v1", "updated_at": "2024-08-01T15:00:00Z" } } }
                """);

        MappingPackageOverviewDto dto = service.listPackages("Nouryon").get(0);

        assertEquals("v1", dto.activeVersion());
        assertEquals("2024-08-01T15:00:00Z", dto.activeUpdatedAt());
        assertEquals("analist_a", dto.activeUpdatedBy()); // no updated_by: the creator of v1
    }

    @Test
    @DisplayName("an unreadable active.json or one pointing to a missing version falls back to the newest version")
    void listPackages_invalidActiveJson_fallsBackToNewestVersion() {
        when(template.exists("/Packages/Nouryon")).thenReturn(true);
        mockDirectories("/Packages/Nouryon", "v1", "v2");
        mockDirectories("/Packages/Nouryon/v1", "inbound");
        mockDirectories("/Packages/Nouryon/v2", "inbound");
        mockTypeWithPackage("/Packages/Nouryon/v1/inbound",
                packageJson("nouryon", "inbound", "2024-06-19T12:00:00Z", "analist_a"));
        mockTypeWithPackage("/Packages/Nouryon/v2/inbound",
                packageJson("nouryon", "inbound", "2024-07-20T12:00:00Z", "analist_b"));

        mockActiveJson("not json");
        assertEquals("v2", service.listPackages("Nouryon").get(0).activeVersion());

        mockActiveJson("""
                { "inbound": { "version": "v9" }, "outbound": { "version": " " } }
                """);
        MappingPackageOverviewDto dto = service.listPackages("Nouryon").get(0);
        assertEquals("v2", dto.activeVersion());
        assertEquals("v2", dto.latestVersion());
    }
}
