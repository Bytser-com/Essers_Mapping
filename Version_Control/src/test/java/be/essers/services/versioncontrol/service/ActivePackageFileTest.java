package be.essers.services.versioncontrol.service;

import be.essers.services.versioncontrol.domain.dto.ActivePackageInfo;
import be.essers.services.versioncontrol.exception.StorageException;
import org.apache.sshd.sftp.client.SftpClient;
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
import tools.jackson.databind.ObjectMapper;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ActivePackageFileTest {

    private static final String COMPANY = "/Packages/nouryon";
    private static final String PATH = "/Packages/nouryon/active.json";
    private static final String TEMP_PATH = "/Packages/nouryon/.active.json.tmp";

    @Mock
    private SftpRemoteFileTemplate template;

    private ActivePackageFile activePackages;

    @BeforeEach
    void setUp() {
        activePackages = new ActivePackageFile(template, new SftpFolders(template), new ObjectMapper());
    }

    private void mockFile(String content) {
        when(template.exists(PATH)).thenReturn(true);
        doAnswer(inv -> {
            InputStreamCallback callback = inv.getArgument(1);
            try (InputStream in = new ByteArrayInputStream(content.getBytes(StandardCharsets.UTF_8))) {
                callback.doWithInputStream(in);
            }
            return true;
        }).when(template).get(eq(PATH), any(InputStreamCallback.class));
    }

    @Test
    @DisplayName("read returns an empty map when active.json does not exist")
    void read_missingFile_isEmpty() {
        assertTrue(activePackages.read(COMPANY).isEmpty());
        verify(template, never()).get(any(String.class), any(InputStreamCallback.class));
    }

    @Test
    @DisplayName("read returns an empty map for an empty file")
    void read_emptyFile_isEmpty() {
        mockFile("");

        assertTrue(activePackages.read(COMPANY).isEmpty());
    }

    @Test
    @DisplayName("read lowercases the package types and ignores entries without a version")
    void read_lowercasesTypesAndSkipsEntriesWithoutVersion() {
        mockFile("""
                { "Inbound": { "version": "v2", "updated_by": "analist_a" }, "outbound": { "updated_by": "x" } }
                """);

        Map<String, ActivePackageInfo> active = activePackages.read(COMPANY);

        assertEquals(1, active.size());
        assertEquals("v2", active.get("inbound").version());
        assertEquals("analist_a", active.get("inbound").updatedBy());
    }

    @Test
    @DisplayName("read returns an empty map when the JSON is not an object")
    void read_jsonArray_isEmpty() {
        mockFile("[1, 2]");

        assertTrue(activePackages.read(COMPANY).isEmpty());
    }

    @Test
    @DisplayName("write stores the JSON in a temp file and renames it to active.json")
    @SuppressWarnings("unchecked")
    void write_usesTempFileAndRename() throws IOException {
        Session<SftpClient.DirEntry> session = mock(Session.class);
        byte[][] written = new byte[1][];
        doAnswer(inv -> {
            written[0] = ((InputStream) inv.getArgument(0)).readAllBytes();
            return null;
        }).when(session).write(any(InputStream.class), eq(TEMP_PATH));
        when(template.execute(any())).thenAnswer(inv -> {
            SessionCallback<SftpClient.DirEntry, Object> callback = inv.getArgument(0);
            return callback.doInSession(session);
        });

        activePackages.write(COMPANY, Map.of("inbound", new ActivePackageInfo("v2", "2026-11-27T10:00:00Z", "analist_a")));

        verify(session).rename(TEMP_PATH, PATH);
        verify(session, never()).remove(any());
        Map<String, Map<String, String>> json = new ObjectMapper().readValue(written[0], Map.class);
        assertEquals("v2", json.get("inbound").get("version"));
        assertEquals("2026-11-27T10:00:00Z", json.get("inbound").get("updated_at"));
        assertEquals("analist_a", json.get("inbound").get("updated_by"));
    }

    @Test
    @DisplayName("write throws StorageException when the SFTP server fails")
    void write_serverFails_throwsStorageException() {
        when(template.execute(any())).thenThrow(new IllegalStateException("SFTP down"));

        Map<String, ActivePackageInfo> active = Map.of();
        StorageException error = assertThrows(StorageException.class, () -> activePackages.write(COMPANY, active));
        assertTrue(error.getMessage().contains("SFTP down"));
    }
}
