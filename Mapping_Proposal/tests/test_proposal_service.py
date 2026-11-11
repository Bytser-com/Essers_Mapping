import unittest
from unittest.mock import patch

from services import proposal_service

from io import BytesIO
from openpyxl import Workbook

HEADERS = ["Mapping ID", "Source full path", "Target field name", "Confidence %", "Confidence reason"]
HEADERS_DIFFERENT_ORDER = ["Mapping ID", "Confidence %", "Target field name", "Source full path", "Confidence reason"]

def make_excel(rows, headers=HEADERS, sheet_name="Mapping Proposal"):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(["Titel"])        
    ws.append(headers)              
    for row in rows:
        ws.append(row)          
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer

class ProposalServiceTests(unittest.TestCase):

    @patch("services.proposal_service.sftp_storage")
    def test_picks_highest_version(self, mock_storage):
        # Arrange
        mock_storage.list_dir.return_value = ["MProposal-Brunos_V1.xlsx", "MProposal-Brunos_V2.xlsx"]
        mock_storage.load.side_effect = lambda path: path
        mock_storage.get_modified_time.return_value = "2026-10-30T10:00:00"

        # Act
        result, version, uploaded, edited = proposal_service.get_proposal_file("brunos")

        # Assert
        self.assertEqual(version, 2)
        self.assertEqual(result, "brunos/MProposal-Brunos_V2.xlsx")

    @patch("services.proposal_service.sftp_storage")
    def test_compares_versions_as_numbers(self, mock_storage):
        # Arrange
        mock_storage.list_dir.return_value = ["MProposal-Brunos_V9.xlsx", "MProposal-Brunos_V10.xlsx"]
        mock_storage.load.side_effect = lambda path: path
        mock_storage.get_modified_time.return_value = "2026-10-30T10:00:00"
    
        # Act
        result, version, uploaded, edited = proposal_service.get_proposal_file("brunos")
    
        # Assert
        self.assertEqual(version, 10)
        self.assertEqual(result, "brunos/MProposal-Brunos_V10.xlsx")

    @patch("services.proposal_service.sftp_storage")
    def test_prefers_edited_file(self, mock_storage):
        # Arrange
        mock_storage.list_dir.return_value = ["MProposal-Brunos_V1.xlsx", "MProposal-Brunos_V1_edited.xlsx"]
        mock_storage.load.side_effect = lambda path: path
        mock_storage.get_modified_time.return_value = "2026-10-30T10:00:00"
    
        # Act
        result, version, uploaded, edited = proposal_service.get_proposal_file("brunos")
    
        # Assert
        self.assertTrue(edited)
        self.assertEqual(result, "brunos/MProposal-Brunos_V1_edited.xlsx")

    @patch("services.proposal_service.sftp_storage")
    def test_prefers_higher_version_over_edited_file(self, mock_storage):
        # Arrange
        mock_storage.list_dir.return_value = ["MProposal-Brunos_V2.xlsx", "MProposal-Brunos_V1_edited.xlsx"]
        mock_storage.load.side_effect = lambda path: path
        mock_storage.get_modified_time.return_value = "2026-10-30T10:00:00"
        
        # Act
        result, version, uploaded, edited = proposal_service.get_proposal_file("brunos")
        
        # Assert
        self.assertFalse(edited)
        self.assertEqual(result, "brunos/MProposal-Brunos_V2.xlsx")

    @patch("services.proposal_service.sftp_storage")
    def test_not_edited_when_only_original(self, mock_storage):
        # Arrange
        mock_storage.list_dir.return_value = ["MProposal-Brunos_V1.xlsx"]
        mock_storage.load.side_effect = lambda path: path
        mock_storage.get_modified_time.return_value = "2026-10-30T10:00:00"
        
        # Act
        result, version, uploaded, edited = proposal_service.get_proposal_file("brunos")
        
        # Assert
        self.assertFalse(edited)
        self.assertEqual(result, "brunos/MProposal-Brunos_V1.xlsx")

    @patch("services.proposal_service.sftp_storage")
    def test_ignores_files_without_mproposal_prefix(self, mock_storage):
        # Arrange
        mock_storage.list_dir.return_value = ["MProposal-Brunos_V1.xlsx", "proposal-Brunos_V2.xlsx", "-MProposal-Brunos_V2.xlsx"]
        mock_storage.load.side_effect = lambda path: path
        mock_storage.get_modified_time.return_value = "2026-10-30T10:00:00"
            
        # Act
        result, version, uploaded, edited = proposal_service.get_proposal_file("brunos")
            
        # Assert
        self.assertEqual(result, "brunos/MProposal-Brunos_V1.xlsx")

    @patch("services.proposal_service.sftp_storage")
    def test_ignores_files_that_are_not_xlsx(self, mock_storage):
        # Arrange
        mock_storage.list_dir.return_value = ["MProposal-Brunos_V1.xlsx", "MProposal-Brunos_V2.json"]
        mock_storage.load.side_effect = lambda path: path
        mock_storage.get_modified_time.return_value = "2026-10-30T10:00:00"
                
        # Act
        result, version, uploaded, edited = proposal_service.get_proposal_file("brunos")
                
        # Assert
        self.assertEqual(result, "brunos/MProposal-Brunos_V1.xlsx")
    

    @patch("services.proposal_service.sftp_storage")
    def test_returns_none_for_empty_folder(self, mock_storage):
        # Arrange
        mock_storage.list_dir.return_value = []
        mock_storage.load.side_effect = lambda path: path
        mock_storage.get_modified_time.return_value = "2026-10-30T10:00:00"

        # Act
        result, version, uploaded, edited = proposal_service.get_proposal_file("brunos")

        # Assert
        self.assertIsNone(result)
        self.assertIsNone(version)
        self.assertIsNone(uploaded)
        self.assertIsNone(edited)

    @patch("services.proposal_service.sftp_storage")
    def test_returns_none_when_folder_does_not_exist(self, mock_storage):
        # Arrange
        mock_storage.list_dir.side_effect = FileNotFoundError
        mock_storage.load.side_effect = lambda path: path
        mock_storage.get_modified_time.return_value = "2026-10-30T10:00:00"
    
        # Act
        result, version, uploaded, edited = proposal_service.get_proposal_file("brunos")
    
        # Assert
        self.assertIsNone(result)
        self.assertIsNone(version)
        self.assertIsNone(uploaded)
        self.assertIsNone(edited)

    @patch("services.proposal_service.get_proposal_file")
    def test_reads_mapping_fields(self, mock_get_file):
        # Arrange
        excel = make_excel([
            ["MP-001", "Klant/Nummer", "Klantnummer", 92, "Exact match"]
        ])
        mock_get_file.return_value = (excel, 1, "2026-10-30T10:00:00", False)

        # Act
        mappings, version, uploaded, edited = proposal_service.get_list_from_excel("brunos")

        # Assert
        self.assertEqual(mappings[0], {"id": "MP-001", "bronveld": "Klant/Nummer", "doelveld": "Klantnummer", "zekerheid": 92, "opmerking": "Exact match"})

    @patch("services.proposal_service.get_proposal_file")
    def test_reads_mapping_fields_if_fields_are_in_a_different_order(self, mock_get_file):
        # Arrange
        excel = make_excel([
            ["MP-001", 92, "Klantnummer", "Klant/Nummer", "Exact match"]
        ], HEADERS_DIFFERENT_ORDER)
        mock_get_file.return_value = (excel, 1, "2026-10-30T10:00:00", False)
    
        # Act
        mappings, version, uploaded, edited = proposal_service.get_list_from_excel("brunos")
    
        # Assert
        self.assertEqual(mappings[0], {"id": "MP-001", "bronveld": "Klant/Nummer", "doelveld": "Klantnummer", "zekerheid": 92, "opmerking": "Exact match"})
    
  
    @patch("services.proposal_service.get_proposal_file")
    def test_skips_rows_without_mapping_id(self, mock_get_file):
        # Arrange
        excel = make_excel([
            ["MP-001", "Klant/Nummer", "Klantnummer", 92, "Exact match"],
            [None, None, None, None, None]
        ])
        mock_get_file.return_value = (excel, 1, "2026-10-30T10:00:00", False)
    
        # Act
        mappings, version, uploaded, edited = proposal_service.get_list_from_excel("brunos")
    
        # Assert
        self.assertEqual(len(mappings), 1)
    
    @patch("services.proposal_service.get_proposal_file")
    def test_empty_source_is_none(self, mock_get_file):
        # Arrange
        excel = make_excel([
            ["MP-001", None, "Klantnummer", None, "Geen bronveld gevonden in het bestand van de klant"],
        ])
        mock_get_file.return_value = (excel, 1, "2026-10-30T10:00:00", False)
        
        # Act
        mappings, version, uploaded, edited = proposal_service.get_list_from_excel("brunos")
        
        # Assert
        self.assertIsNone(mappings[0]["bronveld"])
        self.assertIsNone(mappings[0]["zekerheid"])

    @patch("services.proposal_service.get_proposal_file")
    def test_returns_none_when_no_file(self, mock_get_file):
        # Arrange
        mock_get_file.return_value = (None, None, None, None)
            
        # Act
        mappings, version, uploaded, edited = proposal_service.get_list_from_excel("brunos")
            
        # Assert
        self.assertIsNone(mappings)
        self.assertIsNone(version)
        self.assertIsNone(uploaded)
        self.assertIsNone(edited)
    
    @patch("services.proposal_service.get_proposal_file")
    def test_returns_none_without_mapping_proposal_sheet(self, mock_get_file):
        # Arrange
        excel = make_excel([
            ["MP-001", "Klant/Nummer", "Klantnummer", 92, "Exact match"],
        ], sheet_name="blad1")
        mock_get_file.return_value = (excel, 1, "2026-10-30T10:00:00", False)
       
        # Act
        mappings, version, uploaded, edited = proposal_service.get_list_from_excel("brunos")
       
        # Assert
        self.assertIsNone(mappings)
        self.assertIsNone(version)
        self.assertIsNone(uploaded)
        self.assertIsNone(edited)
        
        
        