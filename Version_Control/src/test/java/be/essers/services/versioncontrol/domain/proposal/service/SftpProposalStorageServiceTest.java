package be.essers.services.versioncontrol.domain.proposal.service;

import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalFileDto;
import be.essers.services.versioncontrol.infrastructure.sftp.SftpProperties;
import be.essers.services.versioncontrol.shared.exception.EntityNotFoundException;
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
class SftpProposalStorageServiceTest {

    @Mock
    private SftpRemoteFileTemplate template;

    private SftpProperties properties;
    private SftpProposalStorageService service;

    @BeforeEach
    void setUp() {
        properties = new SftpProperties("localhost", 22, "sftpuser", "sftppass", null, null, "/Proposals", true);
        service = new SftpProposalStorageService(template, properties);
    }

    private SftpClient.DirEntry createEntry(String name, boolean isDir) {
        SftpClient.Attributes attrs = new SftpClient.Attributes();
        attrs.setType(isDir ? SftpConstants.SSH_FILEXFER_TYPE_DIRECTORY : SftpConstants.SSH_FILEXFER_TYPE_REGULAR);
        attrs.setPermissions(isDir ? 0040755 : 0100644);
        return new SftpClient.DirEntry(name, name, attrs);
    }

    @Test
    @DisplayName("listProposals for specific company returns files in company folder")
    void listProposals_forCompany_returnsFiles() {
        String company = "VanRoey";
        String companyPath = "/Proposals/VanRoey";

        when(template.exists(companyPath)).thenReturn(true);

        SftpClient.DirEntry file1 = createEntry("proposal_vanroey_1.json", false);
        SftpClient.DirEntry dotDir = createEntry(".", true);
        SftpClient.DirEntry subDir = createEntry("archive", true);

        when(template.list(companyPath)).thenReturn(new SftpClient.DirEntry[]{file1, dotDir, subDir});

        List<ProposalFileDto> results = service.listProposals(company);

        assertEquals(1, results.size());
        assertEquals("VanRoey", results.get(0).company());
        assertEquals("proposal_vanroey_1.json", results.get(0).filename());
        assertEquals("/Proposals/VanRoey/proposal_vanroey_1.json", results.get(0).fullPath());
    }

    @Test
    @DisplayName("listProposals for non-existent company throws EntityNotFoundException")
    void listProposals_companyNotFound_throwsEntityNotFound() {
        when(template.exists("/Proposals/NonExisting")).thenReturn(false);

        assertThrows(EntityNotFoundException.class, () -> service.listProposals("NonExisting"));
    }

    @Test
    @DisplayName("listProposals with path traversal characters throws IllegalArgumentException")
    void listProposals_pathTraversal_throwsIllegalArgumentException() {
        assertThrows(IllegalArgumentException.class, () -> service.listProposals("../etc"));
        assertThrows(IllegalArgumentException.class, () -> service.listProposals("VanRoey/sub"));
    }

    @Test
    @DisplayName("listProposals without company parameter returns files from all company folders")
    void listProposals_noCompany_returnsAllCompanyFiles() {
        when(template.exists("/Proposals")).thenReturn(true);

        SftpClient.DirEntry compVanRoey = createEntry("VanRoey", true);
        SftpClient.DirEntry compGoogle = createEntry("Google", true);
        SftpClient.DirEntry dotDir = createEntry(".", true);

        when(template.list("/Proposals")).thenReturn(new SftpClient.DirEntry[]{compVanRoey, compGoogle, dotDir});

        SftpClient.DirEntry fileVanRoey = createEntry("vanroey_map.xml", false);
        when(template.list("/Proposals/VanRoey")).thenReturn(new SftpClient.DirEntry[]{fileVanRoey});

        SftpClient.DirEntry fileGoogle = createEntry("google_map.json", false);
        when(template.list("/Proposals/Google")).thenReturn(new SftpClient.DirEntry[]{fileGoogle});

        List<ProposalFileDto> results = service.listProposals(null);

        assertEquals(2, results.size());
        assertTrue(results.stream().anyMatch(f -> "VanRoey".equals(f.company()) && "vanroey_map.xml".equals(f.filename())));
        assertTrue(results.stream().anyMatch(f -> "Google".equals(f.company()) && "google_map.json".equals(f.filename())));
    }

    @Test
    @DisplayName("listProposalFilenames returns only filename strings")
    void listProposalFilenames_returnsFilenames() {
        when(template.exists("/Proposals/VanRoey")).thenReturn(true);
        SftpClient.DirEntry file1 = createEntry("file_a.txt", false);
        SftpClient.DirEntry file2 = createEntry("file_b.txt", false);
        when(template.list("/Proposals/VanRoey")).thenReturn(new SftpClient.DirEntry[]{file1, file2});

        List<String> filenames = service.listProposalFilenames("VanRoey");

        assertEquals(List.of("file_a.txt", "file_b.txt"), filenames);
    }
}
