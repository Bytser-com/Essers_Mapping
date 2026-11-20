package be.essers.services.versioncontrol.domain.proposal.service;

import be.essers.services.versioncontrol.infrastructure.sftp.SftpProperties;
import be.essers.services.versioncontrol.shared.exception.EntityNotFoundException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.integration.file.remote.InputStreamCallback;
import org.springframework.integration.file.remote.SessionCallback;
import org.springframework.integration.file.remote.session.Session;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class AiReviewStorageTest {
    @Mock SftpRemoteFileTemplate template;
    @Mock Session<Object> session;

    private final ObjectMapper mapper = new ObjectMapper();
    private SftpProposalStorageService storage;

    @BeforeEach
    void setUp() {
        storage = new SftpProposalStorageService(template,
                new SftpProperties("localhost", 2222, "shareduser", "", null, null, "/Proposals", true), mapper);
    }

    @Test
    void rejectionUpdatesOnlyAiReviewAndDoesNotTouchExcel() throws Exception {
        String metadataPath = "/Proposals/nouryon/v2/inbound/proposal.json";
        when(template.exists("/Proposals/nouryon")).thenReturn(true);
        when(template.exists("/Proposals/nouryon/v2")).thenReturn(true);
        when(template.exists("/Proposals/nouryon/v2/inbound")).thenReturn(true);
        when(template.exists(metadataPath)).thenReturn(true);
        String original = """
                {"customer":"Nouryon","version":"v2","status":"READY_FOR_REVIEW",
                 "filename":"MProposal.xlsx","custom_field":"keep me",
                 "ai_review":{"decision":"ACCEPTED","summary":"old"}}
                """;
        doAnswer(call -> {
            InputStreamCallback callback = call.getArgument(1);
            callback.doWithInputStream(new ByteArrayInputStream(original.getBytes(StandardCharsets.UTF_8)));
            return true;
        }).when(template).get(eq(metadataPath), any(InputStreamCallback.class));
        AtomicReference<String> savedPath = new AtomicReference<>();
        AtomicReference<byte[]> savedContent = new AtomicReference<>();
        when(template.execute(any(SessionCallback.class))).thenAnswer(call -> {
            SessionCallback<Object, ?> callback = call.getArgument(0);
            // Mock Session is only used for the single JSON write.
            doAnswer(write -> {
                ByteArrayOutputStream buffer = new ByteArrayOutputStream();
                ((java.io.InputStream) write.getArgument(0)).transferTo(buffer);
                savedContent.set(buffer.toByteArray());
                savedPath.set(write.getArgument(1));
                return null;
            }).when(session).write(any(java.io.InputStream.class), any(String.class));
            return callback.doInSession(session);
        });

        JsonNode decision = mapper.readTree("""
                {"decision":"REJECTED","summary":"Duplicate CITY","findings":["CITY conflict"],"checked_mappings":96}
                """);
        JsonNode result = storage.saveAiReview("nouryon", "v2", "inbound", decision);
        assertEquals("REJECTED", result.get("decision").asText());
        assertNotNull(result.get("reviewed_at"));
        assertEquals(metadataPath, savedPath.get());
        JsonNode stored = mapper.readTree(savedContent.get());
        assertEquals("READY_FOR_REVIEW", stored.get("status").asText());
        assertEquals("keep me", stored.get("custom_field").asText());
        assertEquals("MProposal.xlsx", stored.get("filename").asText());
        assertEquals("REJECTED", stored.get("ai_review").get("decision").asText());
        assertEquals(1, stored.get("ai_review").get("findings").size());
        verify(session, times(1)).write(any(java.io.InputStream.class), eq(metadataPath));
    }

    @Test
    void rejectsUnfinishedOrInvalidAiResults() throws Exception {
        JsonNode unfinished = mapper.readTree("""
                {"decision":"PENDING","summary":"not done","findings":[],"checked_mappings":96}
                """);
        assertThrows(IllegalArgumentException.class,
                () -> storage.saveAiReview("nouryon", "v2", "inbound", unfinished));
        verifyNoInteractions(template);
    }

    @Test
    void missingProposalMustNotCreateMetadataOrNewVersion() throws Exception {
        when(template.exists("/Proposals/nouryon")).thenReturn(false);
        JsonNode accepted = mapper.readTree("""
                {"decision":"ACCEPTED","summary":"ok","findings":[],"checked_mappings":96}
                """);
        assertThrows(EntityNotFoundException.class,
                () -> storage.saveAiReview("nouryon", "v2", "inbound", accepted));
        verify(template, never()).execute(any(SessionCallback.class));
    }
}
