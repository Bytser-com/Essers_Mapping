package be.essers.services.versioncontrol.domain.proposal.service;

import be.essers.services.versioncontrol.domain.proposal.api.dto.ProposalRowDto;
import org.apache.poi.ss.usermodel.*;
import org.springframework.stereotype.Component;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@Component
public class ExcelProposalParser {

    public List<ProposalRowDto> parseProposalRows(InputStream inputStream) {
        if (inputStream == null) {
            return Collections.emptyList();
        }

        try (Workbook workbook = WorkbookFactory.create(inputStream)) {
            Sheet sheet = findMappingSheet(workbook);
            if (sheet == null) {
                return Collections.emptyList();
            }
            return extractRows(sheet);
        } catch (Exception e) {
            throw new IllegalArgumentException("Failed to parse proposal Excel file: " + e.getMessage(), e);
        }
    }

    private Sheet findMappingSheet(Workbook workbook) {
        int sheetCount = workbook.getNumberOfSheets();
        if (sheetCount == 0) {
            return null;
        }

        for (int i = 0; i < sheetCount; i++) {
            Sheet s = workbook.getSheetAt(i);
            String name = normalize(s.getSheetName());
            if (name.equals("mappingproposal") || name.equals("mappings") || name.equals("proposal")) {
                return s;
            }
        }

        for (int i = 0; i < sheetCount; i++) {
            Sheet s = workbook.getSheetAt(i);
            String name = normalize(s.getSheetName());
            if (name.contains("mapping") || name.contains("proposal")) {
                return s;
            }
        }

        return workbook.getSheetAt(0);
    }

    private List<ProposalRowDto> extractRows(Sheet sheet) {
        int headerRowIndex = findHeaderRowIndex(sheet);
        Row headerRow = sheet.getRow(headerRowIndex);
        if (headerRow == null) {
            return Collections.emptyList();
        }

        int sourceFieldCol = -1;
        int sourceFullPathCol = -1;
        int targetFieldCol = -1;
        int targetPathCol = -1;
        int scoreCol = -1;
        int commentCol = -1;
        int commentFallbackCol = -1;

        for (Cell cell : headerRow) {
            String val = getCellString(cell);
            if (val == null) {
                continue;
            }
            String norm = normalize(val);
            int idx = cell.getColumnIndex();

            if (norm.equals("sourcefield") || norm.equals("sourcefieldname")
                    || norm.startsWith("bronveld") || norm.contains("bronveld")) {
                sourceFieldCol = idx;
            } else if (norm.contains("sourcefullpath") || norm.contains("sourcesegmentpath") || norm.contains("sourcepath")) {
                sourceFullPathCol = idx;
            } else if (sourceFieldCol == -1 && norm.equals("source")) {
                sourceFieldCol = idx;
            }

            if (norm.equals("targetfield") || norm.equals("targetfieldname")
                    || norm.startsWith("doelveld") || norm.contains("doelveld")) {
                targetFieldCol = idx;
            } else if (norm.contains("targetsegmentpath") || norm.contains("targetpath")) {
                targetPathCol = idx;
            } else if (targetFieldCol == -1 && norm.equals("target")) {
                targetFieldCol = idx;
            }

            if (norm.equals("score") || norm.equals("confidence") || norm.equals("zekerheid")
                    || (norm.startsWith("confidence") && !norm.contains("reason"))
                    || norm.startsWith("zekerheid")) {
                scoreCol = idx;
            }

            if (norm.equals("comment") || norm.equals("reviewercomment") || norm.contains("opmerking")) {
                commentCol = idx;
            } else if (norm.equals("confidencereason") || norm.equals("reason")) {
                commentFallbackCol = idx;
            } else if (commentFallbackCol == -1 && norm.equals("evidencesummary")) {
                commentFallbackCol = idx;
            }
        }

        List<ProposalRowDto> result = new ArrayList<>();
        int lastRowNum = sheet.getLastRowNum();
        for (int r = headerRowIndex + 1; r <= lastRowNum; r++) {
            Row row = sheet.getRow(r);
            if (row == null || isRowEmpty(row)) {
                continue;
            }

            String sourceField = sourceFieldCol >= 0 ? getCellString(row.getCell(sourceFieldCol)) : null;
            if (sourceField == null && sourceFullPathCol >= 0) {
                sourceField = getCellString(row.getCell(sourceFullPathCol));
            }

            String targetField = targetFieldCol >= 0 ? getCellString(row.getCell(targetFieldCol)) : null;
            if (targetField == null && targetPathCol >= 0) {
                targetField = getCellString(row.getCell(targetPathCol));
            }

            Number score = scoreCol >= 0 ? getCellNumber(row.getCell(scoreCol)) : null;

            String comment = commentCol >= 0 ? getCellString(row.getCell(commentCol)) : null;
            if (comment == null && commentFallbackCol >= 0) {
                comment = getCellString(row.getCell(commentFallbackCol));
            }

            if (sourceField != null || targetField != null || score != null || comment != null) {
                result.add(new ProposalRowDto(sourceField, targetField, score, comment));
            }
        }

        return result;
    }

    private int findHeaderRowIndex(Sheet sheet) {
        int maxRow = Math.min(10, sheet.getLastRowNum());
        for (int r = 0; r <= maxRow; r++) {
            Row row = sheet.getRow(r);
            if (row == null) {
                continue;
            }
            for (Cell cell : row) {
                String val = getCellString(cell);
                if (val == null) {
                    continue;
                }
                String norm = normalize(val);
                if (norm.contains("sourcefield") || norm.contains("targetfield")
                        || norm.equals("mappingid") || norm.contains("bronveld")
                        || norm.contains("doelveld") || norm.equals("score") || norm.equals("comment")) {
                    return r;
                }
            }
        }
        return 0;
    }

    private boolean isRowEmpty(Row row) {
        for (Cell cell : row) {
            if (cell != null && cell.getCellType() != CellType.BLANK) {
                String val = getCellString(cell);
                if (val != null && !val.isBlank()) {
                    return false;
                }
            }
        }
        return true;
    }

    private String getCellString(Cell cell) {
        if (cell == null) {
            return null;
        }
        CellType type = cell.getCellType();
        if (type == CellType.FORMULA) {
            type = cell.getCachedFormulaResultType();
        }
        switch (type) {
            case STRING:
                String s = cell.getStringCellValue();
                return (s != null && !s.isBlank()) ? s.trim() : null;
            case NUMERIC:
                if (DateUtil.isCellDateFormatted(cell)) {
                    return cell.getLocalDateTimeCellValue().toString();
                }
                double num = cell.getNumericCellValue();
                if (num == Math.floor(num) && !Double.isInfinite(num)) {
                    return String.valueOf((long) num);
                }
                return String.valueOf(num);
            case BOOLEAN:
                return String.valueOf(cell.getBooleanCellValue());
            default:
                return null;
        }
    }

    private Number getCellNumber(Cell cell) {
        if (cell == null) {
            return null;
        }
        CellType type = cell.getCellType();
        if (type == CellType.FORMULA) {
            type = cell.getCachedFormulaResultType();
        }
        switch (type) {
            case NUMERIC:
                double num = cell.getNumericCellValue();
                if (num == Math.floor(num) && !Double.isInfinite(num)) {
                    return (int) num;
                }
                return num;
            case STRING:
                String s = cell.getStringCellValue();
                if (s == null || s.isBlank()) {
                    return null;
                }
                String clean = s.replace("%", "").trim();
                try {
                    double parsed = Double.parseDouble(clean);
                    if (parsed == Math.floor(parsed) && !Double.isInfinite(parsed)) {
                        return (int) parsed;
                    }
                    return parsed;
                } catch (NumberFormatException ignored) {
                    return null;
                }
            default:
                return null;
        }
    }

    private String normalize(String value) {
        if (value == null) {
            return "";
        }
        return value.toLowerCase()
                .replaceAll("[^a-z0-9]", "");
    }
}
