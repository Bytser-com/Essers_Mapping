package be.essers.services.versioncontrol.service;

import org.apache.sshd.sftp.client.SftpClient;
import org.apache.sshd.sftp.common.SftpConstants;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class SftpFoldersTest {

    @Mock
    private SftpRemoteFileTemplate template;

    private SftpFolders folders;

    @BeforeEach
    void setUp() {
        folders = new SftpFolders(template);
    }

    private static SftpClient.DirEntry entry(String name, int type) {
        SftpClient.Attributes attrs = new SftpClient.Attributes();
        attrs.setType(type);
        return new SftpClient.DirEntry(name, name, attrs);
    }

    private static SftpClient.DirEntry folder(String name) {
        return entry(name, SftpConstants.SSH_FILEXFER_TYPE_DIRECTORY);
    }

    private static SftpClient.DirEntry file(String name) {
        return entry(name, SftpConstants.SSH_FILEXFER_TYPE_REGULAR);
    }

    @Test
    @DisplayName("path joins the segments with a slash")
    void path_joinsSegments() {
        assertEquals("/Packages", SftpFolders.path("/Packages"));
        assertEquals("/Packages/nouryon/v1/inbound", SftpFolders.path("/Packages", "nouryon", "v1", "inbound"));
        assertEquals("/Packages/nouryon/.active.json.tmp", SftpFolders.path("/Packages/nouryon", ".active.json.tmp"));
    }

    @Test
    @DisplayName("sanitizeSegment trims a name and rejects path traversal")
    void sanitizeSegment_trimsAndRejectsTraversal() {
        assertEquals("nouryon", SftpFolders.sanitizeSegment("  nouryon "));
        assertThrows(IllegalArgumentException.class, () -> SftpFolders.sanitizeSegment("a/b"));
        assertThrows(IllegalArgumentException.class, () -> SftpFolders.sanitizeSegment("a\\b"));
        assertThrows(IllegalArgumentException.class, () -> SftpFolders.sanitizeSegment(".."));
    }

    @Test
    @DisplayName("isDirectory is false for files and entries without attributes")
    void isDirectory_onlyForFolders() {
        assertTrue(SftpFolders.isDirectory(folder("v1")));
        assertFalse(SftpFolders.isDirectory(file("MPackage.json")));
        assertFalse(SftpFolders.isDirectory(new SftpClient.DirEntry("x", "x", null)));
    }

    @Test
    @DisplayName("list returns an empty array for a missing folder")
    void list_missingFolder_isEmpty() {
        when(template.list("/Packages/onbekend")).thenReturn(null);

        assertEquals(0, folders.list("/Packages/onbekend").length);
    }

    @Test
    @DisplayName("subfolders returns only folders, without . and ..")
    void subfolders_onlyRealFolders() {
        when(template.list("/Packages")).thenReturn(new SftpClient.DirEntry[]{
                folder("."), folder(".."), folder("nouryon"), file("readme.txt"), folder("brunos")});

        assertEquals(List.of("nouryon", "brunos"), folders.subfolders("/Packages"));
    }

    @Test
    @DisplayName("findSubfolder returns the exact name when it exists")
    void findSubfolder_exactName() {
        when(template.exists("/Packages/nouryon")).thenReturn(true);

        assertEquals("nouryon", folders.findSubfolder("/Packages", "nouryon"));
    }

    @Test
    @DisplayName("findSubfolder finds a folder case-insensitively, or returns null")
    void findSubfolder_caseInsensitiveOrNull() {
        when(template.list("/Packages")).thenReturn(new SftpClient.DirEntry[]{folder("Nouryon")});

        assertEquals("Nouryon", folders.findSubfolder("/Packages", "NOURYON"));
        assertNull(folders.findSubfolder("/Packages", "brunos"));
    }

    @Test
    @DisplayName("exists asks the SFTP server")
    void exists_delegatesToServer() {
        when(template.exists("/Packages")).thenReturn(true);
        when(template.exists("/Other")).thenReturn(false);

        assertTrue(folders.exists("/Packages"));
        assertFalse(folders.exists("/Other"));
    }
}
