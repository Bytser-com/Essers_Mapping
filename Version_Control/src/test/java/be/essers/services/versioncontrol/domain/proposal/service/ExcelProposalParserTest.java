package be.essers.services.versioncontrol.domain.proposal.service;

import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalRowDto;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class ExcelProposalParserTest {

    private ExcelProposalParser parser;

    @BeforeEach
    void setUp() {
        parser = new ExcelProposalParser();
    }

    private byte[] createWorkbookBytes(String sheetName, String[][] data) throws IOException {
        try (Workbook workbook = new XSSFWorkbook();
             ByteArrayOutputStream baos = new ByteArrayOutputStream()) {
            Sheet sheet = workbook.createSheet(sheetName);
            for (int r = 0; r < data.length; r++) {
                Row row = sheet.createRow(r);
                for (int c = 0; c < data[r].length; c++) {
                    String val = data[r][c];
                    if (val != null) {
                        try {
                            double num = Double.parseDouble(val);
                            row.createCell(c).setCellValue(num);
                        } catch (NumberFormatException e) {
                            row.createCell(c).setCellValue(val);
                        }
                    }
                }
            }
            workbook.write(baos);
            return baos.toByteArray();
        }
    }

    @Test
    @DisplayName("Parses simple single-header sheet with source_field, target_field, score, comment")
    void parse_simpleSheet_success() throws IOException {
        String[][] data = {
                {"source_field", "target_field", "score", "comment"},
                {"OrderNo", "DeliveryNumber", "95", "Direct match"},
                {"CustomerCode", "AccountID", "80.5", "Check prefix"},
                {null, "DefaultFlag", "100", "Fixed value"}
        };

        byte[] bytes = createWorkbookBytes("Mappings", data);
        List<ProposalRowDto> rows = parser.parseProposalRows(new ByteArrayInputStream(bytes));

        assertEquals(3, rows.size());

        assertEquals("OrderNo", rows.get(0).sourceField());
        assertEquals("DeliveryNumber", rows.get(0).targetField());
        assertEquals(95, rows.get(0).score());
        assertEquals("Direct match", rows.get(0).comment());

        assertEquals("CustomerCode", rows.get(1).sourceField());
        assertEquals("AccountID", rows.get(1).targetField());
        assertEquals(80.5, rows.get(1).score());
        assertEquals("Check prefix", rows.get(1).comment());

        assertNull(rows.get(2).sourceField());
        assertEquals("DefaultFlag", rows.get(2).targetField());
        assertEquals(100, rows.get(2).score());
        assertEquals("Fixed value", rows.get(2).comment());
    }

    @Test
    @DisplayName("Parses Nouryon template layout with section header on row 0 and column headers on row 1")
    void parse_nouryonTemplateLayout_success() throws IOException {
        String[][] data = {
                // Row 0: section categories
                {"IDENTIFICATION", null, null, "CONFIDENCE & EVIDENCE", null, null, "TARGET", null, "SOURCE", null, "REVIEWER INPUT"},
                // Row 1: column headers
                {"Mapping ID", "Runtime source group", "Confidence %", "Confidence reason", "Evidence summary", "Target segment path", "Target field name", "Source segment path", "Source field name", "Source full path", "Reviewer comment"},
                // Row 2: first data row (FIXED rule, no source field, fallback to confidence reason)
                {"MP-001", "Outbound", "95", "Fixed target structure", "Evidence 1", "/SHP_OBDLV_SAVE_REPLICA05", "root", null, null, null, null},
                // Row 3: normal mapping row with reviewer comment
                {"MP-002", "Outbound", "90", "Matched name", "Evidence 2", "/SHP_OBDLV_SAVE_REPLICA05/IDOC", "TABNAM", "/DELVRY03/IDOC", "TABNAM", "/DELVRY03/IDOC/TABNAM", "Confirmed by user"}
        };

        byte[] bytes = createWorkbookBytes("Mapping Proposal", data);
        List<ProposalRowDto> rows = parser.parseProposalRows(new ByteArrayInputStream(bytes));

        assertEquals(2, rows.size());

        // Row 0 data
        assertNull(rows.get(0).sourceField());
        assertEquals("root", rows.get(0).targetField());
        assertEquals(95, rows.get(0).score());
        assertEquals("Fixed target structure", rows.get(0).comment()); // fallback to Confidence reason

        // Row 1 data
        assertEquals("TABNAM", rows.get(1).sourceField());
        assertEquals("TABNAM", rows.get(1).targetField());
        assertEquals(90, rows.get(1).score());
        assertEquals("Confirmed by user", rows.get(1).comment()); // reviewer comment takes precedence
    }

    @Test
    @DisplayName("Parses Dutch headers: bronveld, doelveld, zekerheid, opmerking")
    void parse_dutchHeaders_success() throws IOException {
        String[][] data = {
                {"Bronveld (klant)", "Doelveld (H.Essers)", "Zekerheid", "Opmerking"},
                {"Klant/Nummer", "Klantnummer", "92%", "Gevalideerd"}
        };

        byte[] bytes = createWorkbookBytes("Mapping Proposal", data);
        List<ProposalRowDto> rows = parser.parseProposalRows(new ByteArrayInputStream(bytes));

        assertEquals(1, rows.size());
        assertEquals("Klant/Nummer", rows.get(0).sourceField());
        assertEquals("Klantnummer", rows.get(0).targetField());
        assertEquals(92, rows.get(0).score());
        assertEquals("Gevalideerd", rows.get(0).comment());
    }

    @Test
    @DisplayName("Returns empty list for empty stream or blank workbook")
    void parse_emptyStreamOrBlankWorkbook_returnsEmptyList() throws IOException {
        assertTrue(parser.parseProposalRows(null).isEmpty());

        try (Workbook workbook = new XSSFWorkbook();
             ByteArrayOutputStream baos = new ByteArrayOutputStream()) {
            workbook.createSheet("EmptySheet");
            workbook.write(baos);
            List<ProposalRowDto> rows = parser.parseProposalRows(new ByteArrayInputStream(baos.toByteArray()));
            assertTrue(rows.isEmpty());
        }
    }

    @Test
    @DisplayName("Parses real proposal file from shared SFTP directory if available")
    void parse_realProposalFile_success() throws IOException {
        java.nio.file.Path realFile = java.nio.file.Path.of("../data/shared-sftp/Proposals/voorbeeldbedrijf-c/v1/MProposal-VoorbeeldbedrijfC_V1.xlsx");
        if (!java.nio.file.Files.exists(realFile)) {
            realFile = java.nio.file.Path.of("data/shared-sftp/Proposals/voorbeeldbedrijf-c/v1/MProposal-VoorbeeldbedrijfC_V1.xlsx");
        }
        if (java.nio.file.Files.exists(realFile)) {
            try (InputStream in = java.nio.file.Files.newInputStream(realFile)) {
                List<ProposalRowDto> rows = parser.parseProposalRows(in);
                assertEquals(62, rows.size());

                ProposalRowDto row0 = rows.get(0);
                assertNull(row0.sourceField());
                assertEquals("root", row0.targetField());
                assertEquals(95, row0.score());
                assertNotNull(row0.comment());

                ProposalRowDto row1 = rows.get(1);
                assertEquals("TABNAM", row1.sourceField());
                assertEquals("TABNAM", row1.targetField());
                assertEquals(95, row1.score());
                assertEquals("Same control field name.", row1.comment());
            }
        }
    }
}
