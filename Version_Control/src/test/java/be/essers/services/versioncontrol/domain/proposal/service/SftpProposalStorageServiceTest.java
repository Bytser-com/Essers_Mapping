package be.essers.services.versioncontrol.domain.proposal.service;

import be.essers.services.versioncontrol.domain.proposal.api.dto.CompanyProposalOverviewDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDataDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDetailsDto;
import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalRowDto;
import be.essers.services.versioncontrol.infrastructure.sftp.SftpProperties;
import be.essers.services.versioncontrol.shared.exception.EntityNotFoundException;
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
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.attribute.FileTime;
import java.time.Instant;
import java.util.Base64;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class SftpProposalStorageServiceTest {

    @Mock
    private SftpRemoteFileTemplate template;

    private SftpProperties properties;
    private ObjectMapper objectMapper;
    private SftpProposalStorageService service;

    @BeforeEach
    void setUp() {
        properties = new SftpProperties("localhost", 22, "sftpuser", "sftppass", null, null, "/Proposals", true);
        objectMapper = new ObjectMapper();
        service = new SftpProposalStorageService(template, properties, objectMapper);
    }

    private SftpClient.DirEntry createEntry(String name, boolean isDir) {
        SftpClient.Attributes attrs = new SftpClient.Attributes();
        attrs.setType(isDir ? SftpConstants.SSH_FILEXFER_TYPE_DIRECTORY : SftpConstants.SSH_FILEXFER_TYPE_REGULAR);
        attrs.setPermissions(isDir ? 0040755 : 0100644);
        attrs.setModifyTime(FileTime.from(Instant.parse("2026-11-10T12:00:00Z")));
        return new SftpClient.DirEntry(name, name, attrs);
    }

    @Test
    @DisplayName("listProposals for company returns latest version and metadata")
    void listProposals_forCompany_returnsLatestVersionWithMetadata() {
        String company = "VanRoey";
        String companyPath = "/Proposals/VanRoey";

        when(template.exists(companyPath)).thenReturn(true);

        SftpClient.DirEntry v1 = createEntry("v1", true);
        SftpClient.DirEntry v2 = createEntry("v2", true);
        SftpClient.DirEntry v3 = createEntry("v3", true);
        when(template.list(companyPath)).thenReturn(new SftpClient.DirEntry[]{v1, v2, v3});

        String v3Path = "/Proposals/VanRoey/v3";
        SftpClient.DirEntry excelFile = createEntry("mappingproposal.xlsx", false);
        SftpClient.DirEntry metaFile = createEntry("metadata.json", false);
        when(template.list(v3Path)).thenReturn(new SftpClient.DirEntry[]{excelFile, metaFile});

        String metaJson = """
                {
                  "company": "VanRoey",
                  "version": "v3",
                  "filename": "mappingproposal.xlsx",
                  "createdDate": "2026-11-10T14:30:00Z",
                  "createdBy": "Jane Doe",
                  "description": "Warehouse update",
                  "status": "READY_FOR_REVIEW",
                  "ai_status": null
                }
                """;

        doAnswer(invocation -> {
            InputStreamCallback callback = invocation.getArgument(1);
            try (InputStream in = new ByteArrayInputStream(metaJson.getBytes(StandardCharsets.UTF_8))) {
                callback.doWithInputStream(in);
            }
            return true;
        }).when(template).get(eq("/Proposals/VanRoey/v3/metadata.json"), any(InputStreamCallback.class));

        List<CompanyProposalOverviewDto> results = service.listProposals(company);

        assertEquals(1, results.size());
        CompanyProposalOverviewDto dto = results.get(0);
        assertEquals("VanRoey", dto.company());
        assertEquals("v3", dto.latestVersion());
        assertEquals("mappingproposal.xlsx", dto.filename());
        assertEquals("/Proposals/VanRoey/v3/mappingproposal.xlsx", dto.fullPath());
        assertEquals("2026-11-10T14:30:00Z", dto.createdDate());
        assertEquals("Jane Doe", dto.createdBy());
        assertEquals("Warehouse update", dto.description());
        assertEquals("READY_FOR_REVIEW", dto.status());
        assertNull(dto.aiStatus());
    }

    @Test
    @DisplayName("listProposals supports proposal.json fallback with Python fields")
    void listProposals_supportsProposalJsonFallback() {
        String company = "Ostavel";
        String companyPath = "/Proposals/Ostavel";

        when(template.exists(companyPath)).thenReturn(true);

        SftpClient.DirEntry v1 = createEntry("v1", true);
        when(template.list(companyPath)).thenReturn(new SftpClient.DirEntry[]{v1});

        String v1Path = "/Proposals/Ostavel/v1";
        SftpClient.DirEntry excelFile = createEntry("MProposal-Ostavel_V1.xlsx", false);
        SftpClient.DirEntry proposalFile = createEntry("proposal.json", false);
        when(template.list(v1Path)).thenReturn(new SftpClient.DirEntry[]{excelFile, proposalFile});

        String proposalJson = """
                {
                  "customer": "Ostavel",
                  "uploaded_at": "2026-10-30T13:30:00+01:00",
                  "status": "AI_GENERATING",
                  "ai_status": "RUNNING"
                }
                """;

        doAnswer(invocation -> {
            InputStreamCallback callback = invocation.getArgument(1);
            try (InputStream in = new ByteArrayInputStream(proposalJson.getBytes(StandardCharsets.UTF_8))) {
                callback.doWithInputStream(in);
            }
            return true;
        }).when(template).get(eq("/Proposals/Ostavel/v1/proposal.json"), any(InputStreamCallback.class));

        List<CompanyProposalOverviewDto> results = service.listProposals(company);

        assertEquals(1, results.size());
        CompanyProposalOverviewDto dto = results.get(0);
        assertEquals("Ostavel", dto.company());
        assertEquals("v1", dto.latestVersion());
        assertEquals("MProposal-Ostavel_V1.xlsx", dto.filename());
        assertEquals("2026-10-30T13:30:00+01:00", dto.createdDate());
        assertEquals("AI_GENERATING", dto.status());
        assertEquals("RUNNING", dto.aiStatus());
    }

    @Test
    @DisplayName("listProposals falls back to file modify time when metadata.json is absent")
    void listProposals_fallbackWhenMetadataMissing() {
        String company = "VanRoey";
        String companyPath = "/Proposals/VanRoey";

        when(template.exists(companyPath)).thenReturn(true);

        SftpClient.DirEntry v1 = createEntry("v1", true);
        when(template.list(companyPath)).thenReturn(new SftpClient.DirEntry[]{v1});

        String v1Path = "/Proposals/VanRoey/v1";
        SftpClient.DirEntry excelFile = createEntry("proposal.xlsx", false);
        when(template.list(v1Path)).thenReturn(new SftpClient.DirEntry[]{excelFile});

        List<CompanyProposalOverviewDto> results = service.listProposals(company);

        assertEquals(1, results.size());
        CompanyProposalOverviewDto dto = results.get(0);
        assertEquals("VanRoey", dto.company());
        assertEquals("v1", dto.latestVersion());
        assertEquals("proposal.xlsx", dto.filename());
        assertEquals("2026-11-10T12:00:00Z", dto.createdDate());
        assertNull(dto.createdBy());
    }

    // Puts a version folder with an Excel file and a proposal.json with the given content on the mocked SFTP
    private void mockVersionWithProposalJson(String versionPath, String proposalJson) {
        SftpClient.DirEntry excel = createEntry("proposal.xlsx", false);
        SftpClient.DirEntry json = createEntry("proposal.json", false);
        when(template.list(versionPath)).thenReturn(new SftpClient.DirEntry[]{excel, json});
        doAnswer(invocation -> {
            InputStreamCallback callback = invocation.getArgument(1);
            try (InputStream in = new ByteArrayInputStream(proposalJson.getBytes(StandardCharsets.UTF_8))) {
                callback.doWithInputStream(in);
            }
            return true;
        }).when(template).get(eq(versionPath + "/proposal.json"), any(InputStreamCallback.class));
    }

    private String proposalJson(String uploadedAt, String status) {
        return "{\"uploaded_at\": \"" + uploadedAt + "\", \"status\": \"" + status + "\"}";
    }

    private void mockCompanies(String... companies) {
        when(template.exists("/Proposals")).thenReturn(true);
        SftpClient.DirEntry[] entries = new SftpClient.DirEntry[companies.length];
        for (int i = 0; i < companies.length; i++) {
            entries[i] = createEntry(companies[i], true);
        }
        when(template.list("/Proposals")).thenReturn(entries);
    }

    private void mockVersions(String company, String... versions) {
        SftpClient.DirEntry[] entries = new SftpClient.DirEntry[versions.length];
        for (int i = 0; i < versions.length; i++) {
            entries[i] = createEntry(versions[i], true);
        }
        when(template.list("/Proposals/" + company)).thenReturn(entries);
    }

    @Test
    @DisplayName("TC-57-02 listProposals without company returns all companies with their latest version")
    void listProposals_allCompanies_returnsLatestVersionForEach() {
        mockCompanies("VanRoey", "Google");

        // VanRoey has v1 and v10 -> v10 is latest
        mockVersions("VanRoey", "v1", "v10");
        mockVersionWithProposalJson("/Proposals/VanRoey/v10", proposalJson("2026-11-10T10:00:00+01:00", "READY_FOR_REVIEW"));

        // Google has v2 -> v2 is latest
        mockVersions("Google", "v2");
        mockVersionWithProposalJson("/Proposals/Google/v2", proposalJson("2026-11-09T10:00:00+01:00", "IN_REVIEW"));

        List<CompanyProposalOverviewDto> results = service.listProposals(null);

        assertEquals(2, results.size());
        assertEquals("VanRoey", results.get(0).company());
        assertEquals("v10", results.get(0).latestVersion());
        assertEquals("Google", results.get(1).company());
        assertEquals("v2", results.get(1).latestVersion());
    }

    @Test
    @DisplayName("TC-57-03 the newest upload is first, also when the timezones differ")
    void listProposals_allCompanies_newestUploadFirst() {
        mockCompanies("KlantA", "KlantB", "KlantC", "KlantD");
        mockVersions("KlantA", "v1");
        mockVersionWithProposalJson("/Proposals/KlantA/v1", proposalJson("2026-10-20T10:00:00+02:00", "READY_FOR_REVIEW"));
        mockVersions("KlantB", "v1");
        mockVersionWithProposalJson("/Proposals/KlantB/v1", proposalJson("2026-10-22T10:00:00+02:00", "READY_FOR_REVIEW"));
        mockVersions("KlantC", "v1");
        mockVersionWithProposalJson("/Proposals/KlantC/v1", proposalJson("2026-10-21T10:00:00+02:00", "READY_FOR_REVIEW"));
        // 09:30 UTC = 11:30 in Brussels, so newer than KlantB
        mockVersions("KlantD", "v1");
        mockVersionWithProposalJson("/Proposals/KlantD/v1", proposalJson("2026-10-22T09:30:00Z", "READY_FOR_REVIEW"));

        List<CompanyProposalOverviewDto> results = service.listProposals(null);

        assertEquals(List.of("KlantD", "KlantB", "KlantC", "KlantA"),
                results.stream().map(CompanyProposalOverviewDto::company).toList());
    }

    @Test
    @DisplayName("TC-57-01 a proposal with missing or invalid data is skipped, the others are shown")
    void listProposals_allCompanies_skipsInvalidProposals() {
        mockCompanies("KlantB", "BadJson", "UnknownStatus", "NoUploadTime", "NoProposalJson");

        mockVersions("KlantB", "v1");
        mockVersionWithProposalJson("/Proposals/KlantB/v1", proposalJson("2026-10-22T10:00:00+02:00", "READY_FOR_REVIEW"));

        mockVersions("BadJson", "v1");
        mockVersionWithProposalJson("/Proposals/BadJson/v1", "INVALID_JSON_@@@");

        mockVersions("UnknownStatus", "v1");
        mockVersionWithProposalJson("/Proposals/UnknownStatus/v1", proposalJson("2026-10-22T10:00:00+02:00", "DONE"));

        mockVersions("NoUploadTime", "v1");
        mockVersionWithProposalJson("/Proposals/NoUploadTime/v1", "{\"status\": \"READY_FOR_REVIEW\"}");

        mockVersions("NoProposalJson", "v1");
        when(template.list("/Proposals/NoProposalJson/v1"))
                .thenReturn(new SftpClient.DirEntry[]{createEntry("proposal.xlsx", false)});

        List<CompanyProposalOverviewDto> results = service.listProposals(null);

        assertEquals(1, results.size());
        assertEquals("KlantB", results.get(0).company());
    }

    @Test
    @DisplayName("TC-57-01 when the newest version is broken, the newest valid version is shown")
    void listProposals_allCompanies_brokenNewestVersionFallsBackToPreviousVersion() {
        mockCompanies("KlantA");
        mockVersions("KlantA", "v1", "v2");
        mockVersionWithProposalJson("/Proposals/KlantA/v1", proposalJson("2026-10-20T10:00:00+02:00", "IN_REVIEW"));
        mockVersionWithProposalJson("/Proposals/KlantA/v2", "INVALID_JSON_@@@");

        List<CompanyProposalOverviewDto> results = service.listProposals(null);

        assertEquals(1, results.size());
        assertEquals("v1", results.get(0).latestVersion());
        assertEquals("IN_REVIEW", results.get(0).status());
    }

    @Test
    @DisplayName("listProposals with non-existent company throws EntityNotFoundException")
    void listProposals_companyNotFound_throwsEntityNotFound() {
        when(template.exists("/Proposals/UnknownCompany")).thenReturn(false);
        when(template.list("/Proposals")).thenReturn(new SftpClient.DirEntry[0]);

        assertThrows(EntityNotFoundException.class, () -> service.listProposals("UnknownCompany"));
    }

    @Test
    @DisplayName("listProposals with path traversal throws IllegalArgumentException")
    void listProposals_pathTraversal_throwsIllegalArgumentException() {
        assertThrows(IllegalArgumentException.class, () -> service.listProposals("../etc"));
        assertThrows(IllegalArgumentException.class, () -> service.listProposals("VanRoey/sub"));
    }

    @Test
    @DisplayName("getProposalFile returns file content encoded as Base64 with metadata")
    void getProposalFile_success() {
        String company = "VanRoey";
        String version = "v3";
        String versionPath = "/Proposals/VanRoey/v3";

        when(template.exists("/Proposals/VanRoey")).thenReturn(true);
        when(template.exists("/Proposals/VanRoey/v3")).thenReturn(true);

        SftpClient.DirEntry excelEntry = createEntry("mappingproposal.xlsx", false);
        SftpClient.DirEntry metaEntry = createEntry("metadata.json", false);
        when(template.list(versionPath)).thenReturn(new SftpClient.DirEntry[]{excelEntry, metaEntry});

        String metaJson = """
                {
                  "company": "VanRoey",
                  "version": "v3",
                  "filename": "mappingproposal.xlsx",
                  "createdDate": "2026-11-10T14:30:00Z",
                  "createdBy": "Jane Doe",
                  "description": "Warehouse update"
                }
                """;

        doAnswer(invocation -> {
            InputStreamCallback callback = invocation.getArgument(1);
            try (InputStream in = new ByteArrayInputStream(metaJson.getBytes(StandardCharsets.UTF_8))) {
                callback.doWithInputStream(in);
            }
            return true;
        }).when(template).get(eq("/Proposals/VanRoey/v3/metadata.json"), any(InputStreamCallback.class));

        byte[] fakeExcelBytes = "FAKE_EXCEL_DATA_CONTENT".getBytes(StandardCharsets.UTF_8);
        doAnswer(invocation -> {
            InputStreamCallback callback = invocation.getArgument(1);
            try (InputStream in = new ByteArrayInputStream(fakeExcelBytes)) {
                callback.doWithInputStream(in);
            }
            return true;
        }).when(template).get(eq("/Proposals/VanRoey/v3/mappingproposal.xlsx"), any(InputStreamCallback.class));

        ProposalFileDetailsDto result = service.getProposalFile(company, version);

        assertNotNull(result);
        assertEquals("VanRoey", result.company());
        assertEquals("v3", result.version());
        assertEquals("mappingproposal.xlsx", result.filename());
        assertEquals("/Proposals/VanRoey/v3/mappingproposal.xlsx", result.fullPath());
        assertEquals("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", result.contentType());
        assertEquals(fakeExcelBytes.length, result.sizeBytes());
        assertEquals("2026-11-10T14:30:00Z", result.createdDate());
        assertEquals("Jane Doe", result.createdBy());
        assertEquals("Warehouse update", result.description());
        assertEquals(Base64.getEncoder().encodeToString(fakeExcelBytes), result.fileContentBase64());
    }

    @Test
    @DisplayName("getProposalFile throws EntityNotFoundException when company or version does not exist")
    void getProposalFile_notFound_throwsEntityNotFound() {
        when(template.exists("/Proposals/VanRoey")).thenReturn(false);
        when(template.list("/Proposals")).thenReturn(new SftpClient.DirEntry[0]);

        assertThrows(EntityNotFoundException.class, () -> service.getProposalFile("VanRoey", "v1"));
    }

    @Test
    @DisplayName("getProposalFile resolves company and version case-insensitively")
    void getProposalFile_caseInsensitiveResolution() {
        when(template.exists("/Proposals/vanroey")).thenReturn(false);
        SftpClient.DirEntry vanRoeyDir = createEntry("VanRoey", true);
        when(template.list("/Proposals")).thenReturn(new SftpClient.DirEntry[]{vanRoeyDir});

        when(template.exists("/Proposals/VanRoey/v3")).thenReturn(false);
        SftpClient.DirEntry v3Dir = createEntry("V3", true);
        when(template.list("/Proposals/VanRoey")).thenReturn(new SftpClient.DirEntry[]{v3Dir});

        SftpClient.DirEntry excel = createEntry("test.xls", false);
        when(template.list("/Proposals/VanRoey/V3")).thenReturn(new SftpClient.DirEntry[]{excel});

        doAnswer(invocation -> {
            InputStreamCallback callback = invocation.getArgument(1);
            try (InputStream in = new ByteArrayInputStream("XLS_CONTENT".getBytes(StandardCharsets.UTF_8))) {
                callback.doWithInputStream(in);
            }
            return true;
        }).when(template).get(eq("/Proposals/VanRoey/V3/test.xls"), any(InputStreamCallback.class));

        ProposalFileDetailsDto result = service.getProposalFile("vanroey", "v3");

        assertEquals("VanRoey", result.company());
        assertEquals("V3", result.version());
        assertEquals("test.xls", result.filename());
        assertEquals("application/vnd.ms-excel", result.contentType());
    }

    @Test
    @DisplayName("listAllProposals returns empty list when rootPath does not exist")
    void listAllProposals_rootNotExists_returnsEmptyList() {
        when(template.exists("/Proposals")).thenReturn(false);

        List<CompanyProposalOverviewDto> list = service.listProposals(null);

        assertTrue(list.isEmpty());
    }

    @Test
    @DisplayName("listAllProposals ignores non-directory entries in root")
    void listAllProposals_ignoresNonDirectoryEntriesInRoot() {
        when(template.exists("/Proposals")).thenReturn(true);
        SftpClient.DirEntry fileInRoot = createEntry("readme.txt", false);
        SftpClient.DirEntry dotDir = createEntry(".", true);
        when(template.list("/Proposals")).thenReturn(new SftpClient.DirEntry[]{fileInRoot, dotDir});

        List<CompanyProposalOverviewDto> list = service.listProposals(null);

        assertTrue(list.isEmpty());
    }

    @Test
    @DisplayName("listProposals for company with no versions throws EntityNotFoundException")
    void listProposals_companyWithNoVersions_throwsEntityNotFound() {
        when(template.exists("/Proposals/EmptyCompany")).thenReturn(true);
        when(template.list("/Proposals/EmptyCompany")).thenReturn(new SftpClient.DirEntry[0]);

        assertThrows(EntityNotFoundException.class, () -> service.listProposals("EmptyCompany"));
    }

    @Test
    @DisplayName("getProposalFile throws EntityNotFoundException when no Excel file exists in version folder")
    void getProposalFile_noExcelInVersion_throwsEntityNotFound() {
        when(template.exists("/Proposals/VanRoey")).thenReturn(true);
        when(template.exists("/Proposals/VanRoey/v1")).thenReturn(true);

        SftpClient.DirEntry txtFile = createEntry("notes.txt", false);
        when(template.list("/Proposals/VanRoey/v1")).thenReturn(new SftpClient.DirEntry[]{txtFile});

        assertThrows(EntityNotFoundException.class, () -> service.getProposalFile("VanRoey", "v1"));
    }

    @Test
    @DisplayName("getProposalFile throws StorageException when SFTP read fails")
    void getProposalFile_sftpReadFails_throwsStorageException() {
        when(template.exists("/Proposals/VanRoey")).thenReturn(true);
        when(template.exists("/Proposals/VanRoey/v1")).thenReturn(true);

        SftpClient.DirEntry excel = createEntry("plan.xlsx", false);
        when(template.list("/Proposals/VanRoey/v1")).thenReturn(new SftpClient.DirEntry[]{excel});

        when(template.get(eq("/Proposals/VanRoey/v1/plan.xlsx"), any(InputStreamCallback.class))).thenReturn(false);

        assertThrows(be.essers.services.versioncontrol.shared.exception.StorageException.class,
                () -> service.getProposalFile("VanRoey", "v1"));
    }

    @Test
    @DisplayName("Handles corrupted metadata.json gracefully by logging warning and falling back")
    void readMetadata_corruptedJson_fallsBackGracefully() {
        when(template.exists("/Proposals/VanRoey")).thenReturn(true);
        SftpClient.DirEntry v1 = createEntry("v1", true);
        when(template.list("/Proposals/VanRoey")).thenReturn(new SftpClient.DirEntry[]{v1});

        SftpClient.DirEntry excel = createEntry("plan.xlsx", false);
        SftpClient.DirEntry meta = createEntry("metadata.json", false);
        when(template.list("/Proposals/VanRoey/v1")).thenReturn(new SftpClient.DirEntry[]{excel, meta});

        doAnswer(invocation -> {
            InputStreamCallback callback = invocation.getArgument(1);
            try (InputStream in = new ByteArrayInputStream("INVALID_JSON_@@@".getBytes(StandardCharsets.UTF_8))) {
                callback.doWithInputStream(in);
            }
            return true;
        }).when(template).get(eq("/Proposals/VanRoey/v1/metadata.json"), any(InputStreamCallback.class));

        List<CompanyProposalOverviewDto> result = service.listProposals("VanRoey");

        assertEquals(1, result.size());
        assertEquals("plan.xlsx", result.get(0).filename());
        assertNull(result.get(0).createdBy());
    }

    @Test
    @DisplayName("getProposalFile throws IllegalArgumentException for empty parameters or path traversal")
    void getProposalFile_invalidParams_throwsException() {
        assertThrows(IllegalArgumentException.class, () -> service.getProposalFile("", "v1"));
        assertThrows(IllegalArgumentException.class, () -> service.getProposalFile("VanRoey", ""));
        assertThrows(IllegalArgumentException.class, () -> service.getProposalFile("../etc", "v1"));
        assertThrows(IllegalArgumentException.class, () -> service.getProposalFile("VanRoey", "../etc"));
    }

    @Test
    @DisplayName("readMetadata falls back to template.exists when versionEntries is null")
    void readMetadata_fallsBackToTemplateExistsWhenVersionEntriesNull() {
        when(template.exists("/Proposals/VanRoey")).thenReturn(true);
        SftpClient.DirEntry v1 = createEntry("v1", true);
        when(template.list("/Proposals/VanRoey")).thenReturn(new SftpClient.DirEntry[]{v1});

        when(template.list("/Proposals/VanRoey/v1")).thenReturn(null);
        when(template.exists("/Proposals/VanRoey/v1/metadata.json")).thenReturn(true);

        String metaJson = """
                {
                  "company": "VanRoey",
                  "version": "v1",
                  "filename": "mappingproposal.xlsx",
                  "status": "APPROVED"
                }
                """;

        doAnswer(invocation -> {
            InputStreamCallback callback = invocation.getArgument(1);
            try (InputStream in = new ByteArrayInputStream(metaJson.getBytes(StandardCharsets.UTF_8))) {
                callback.doWithInputStream(in);
            }
            return true;
        }).when(template).get(eq("/Proposals/VanRoey/v1/metadata.json"), any(InputStreamCallback.class));

        List<CompanyProposalOverviewDto> results = service.listProposals("VanRoey");
        assertEquals(1, results.size());
        assertEquals("APPROVED", results.get(0).status());
    }

    @Test
    @DisplayName("listProposals handles general exception with StorageException")
    void listProposals_generalException_throwsStorageException() {
        when(template.exists("/Proposals")).thenThrow(new RuntimeException("Connection failed"));
        assertThrows(be.essers.services.versioncontrol.shared.exception.StorageException.class,
                () -> service.listProposals(null));
    }

    @Test
    @DisplayName("getProposalFileData returns parsed Excel rows and file metadata")
    void getProposalFileData_success() throws Exception {
        String company = "VanRoey";
        String version = "v3";
        String versionPath = "/Proposals/VanRoey/v3";

        when(template.exists("/Proposals/VanRoey")).thenReturn(true);
        when(template.exists("/Proposals/VanRoey/v3")).thenReturn(true);

        SftpClient.DirEntry excelEntry = createEntry("mappingproposal.xlsx", false);
        SftpClient.DirEntry metaEntry = createEntry("metadata.json", false);
        when(template.list(versionPath)).thenReturn(new SftpClient.DirEntry[]{excelEntry, metaEntry});

        String metaJson = """
                {
                  "company": "VanRoey",
                  "version": "v3",
                  "filename": "mappingproposal.xlsx",
                  "uploaded_at": "2026-10-20T16:45:00+02:00",
                  "updated_at": "2026-11-11T23:03:02+00:00",
                  "upload_user": "Jane Doe",
                  "status": "READY_FOR_REVIEW"
                }
                """;

        doAnswer(invocation -> {
            InputStreamCallback callback = invocation.getArgument(1);
            try (InputStream in = new ByteArrayInputStream(metaJson.getBytes(StandardCharsets.UTF_8))) {
                callback.doWithInputStream(in);
            }
            return true;
        }).when(template).get(eq("/Proposals/VanRoey/v3/metadata.json"), any(InputStreamCallback.class));

        // Create Excel in memory with Apache POI
        byte[] excelBytes;
        try (org.apache.poi.xssf.usermodel.XSSFWorkbook wb = new org.apache.poi.xssf.usermodel.XSSFWorkbook();
             java.io.ByteArrayOutputStream baos = new java.io.ByteArrayOutputStream()) {
            org.apache.poi.ss.usermodel.Sheet sheet = wb.createSheet("Mapping Proposal");
            org.apache.poi.ss.usermodel.Row r0 = sheet.createRow(0);
            r0.createCell(0).setCellValue("source_field");
            r0.createCell(1).setCellValue("target_field");
            r0.createCell(2).setCellValue("score");
            r0.createCell(3).setCellValue("comment");

            org.apache.poi.ss.usermodel.Row r1 = sheet.createRow(1);
            r1.createCell(0).setCellValue("OrderNo");
            r1.createCell(1).setCellValue("DeliveryNumber");
            r1.createCell(2).setCellValue(95);
            r1.createCell(3).setCellValue("Direct semantic match");

            org.apache.poi.ss.usermodel.Row r2 = sheet.createRow(2);
            r2.createCell(0).setCellValue("CustomerRef");
            r2.createCell(1).setCellValue("AccountRef");
            r2.createCell(2).setCellValue(70.5);
            r2.createCell(3).setCellValue("Review required");

            wb.write(baos);
            excelBytes = baos.toByteArray();
        }

        doAnswer(invocation -> {
            InputStreamCallback callback = invocation.getArgument(1);
            try (InputStream in = new ByteArrayInputStream(excelBytes)) {
                callback.doWithInputStream(in);
            }
            return true;
        }).when(template).get(eq("/Proposals/VanRoey/v3/mappingproposal.xlsx"), any(InputStreamCallback.class));

        ProposalFileDataDto result = service.getProposalFileData(company, version);

        assertNotNull(result);
        assertEquals("v3", result.version());
        assertEquals("VanRoey", result.comapnyname());
        assertEquals("VanRoey", result.companyname());
        assertEquals("2026-10-20", result.uploadDate());
        assertEquals("16:45:00", result.uploadTime());
        assertEquals("2026-11-11", result.updatedDate());
        assertEquals("23:03:02", result.updatedTime());
        assertEquals("Jane Doe", result.uploadUser());
        assertEquals("READY_FOR_REVIEW", result.status());
        assertNotNull(result.rows());
        assertEquals(2, result.rows().size());

        ProposalRowDto row1 = result.rows().get(0);
        assertEquals("OrderNo", row1.sourceField());
        assertEquals("DeliveryNumber", row1.targetField());
        assertEquals(95, row1.score());
        assertEquals("Direct semantic match", row1.comment());

        ProposalRowDto row2 = result.rows().get(1);
        assertEquals("CustomerRef", row2.sourceField());
        assertEquals("AccountRef", row2.targetField());
        assertEquals(70.5, row2.score());
        assertEquals("Review required", row2.comment());
    }

    @Test
    @DisplayName("getProposalFileData throws EntityNotFoundException when company does not exist")
    void getProposalFileData_companyNotFound_throwsEntityNotFound() {
        when(template.exists("/Proposals/NonExisting")).thenReturn(false);
        when(template.list("/Proposals")).thenReturn(new SftpClient.DirEntry[0]);

        assertThrows(EntityNotFoundException.class,
                () -> service.getProposalFileData("NonExisting", "v1"));
    }

    @Test
    @DisplayName("getProposalFileData throws IllegalArgumentException for empty or invalid parameters")
    void getProposalFileData_invalidParams_throwsException() {
        assertThrows(IllegalArgumentException.class, () -> service.getProposalFileData("", "v1"));
        assertThrows(IllegalArgumentException.class, () -> service.getProposalFileData("VanRoey", ""));
        assertThrows(IllegalArgumentException.class, () -> service.getProposalFileData("../etc", "v1"));
        assertThrows(IllegalArgumentException.class, () -> service.getProposalFileData("VanRoey", "../etc"));
    }

    @Test
    @DisplayName("getProposalFileData throws StorageException when SFTP read fails")
    void getProposalFileData_sftpReadFails_throwsStorageException() {
        when(template.exists("/Proposals/VanRoey")).thenReturn(true);
        when(template.exists("/Proposals/VanRoey/v1")).thenReturn(true);

        SftpClient.DirEntry excelEntry = createEntry("plan.xlsx", false);
        when(template.list("/Proposals/VanRoey/v1")).thenReturn(new SftpClient.DirEntry[]{excelEntry});

        when(template.get(eq("/Proposals/VanRoey/v1/plan.xlsx"), any(InputStreamCallback.class)))
                .thenReturn(false);

        assertThrows(be.essers.services.versioncontrol.shared.exception.StorageException.class,
                () -> service.getProposalFileData("VanRoey", "v1"));
    }
}
