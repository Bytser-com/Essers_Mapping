import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import app

client = TestClient(app)

MAPPINGS = [
    {"id": "MP-001", "bronveld": "Klant/Nummer", "doelveld": "Klantnummer", "zekerheid": 92, "opmerking": "Exact match"},
]


class ProposalsRouterTests(unittest.TestCase):

    @patch("services.proposal_service.get_list_from_excel")
    def test_returns_proposal_for_existing_company(self, mock_get_list):
        # Arrange
        mock_get_list.return_value = (MAPPINGS, 1, "2026-10-30T10:00:00", False)

        # Act
        response = client.get("/proposals/brunos")
        data = response.json()

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data, {"klant": "brunos", "versie": 1, "status": "Klaar om na te kijken", "geupload": "2026-10-30T10:00:00", "mappings": MAPPINGS})

    @patch("services.proposal_service.get_list_from_excel")
    def test_returns_404_for_unknown_company(self, mock_get_list):
        # Arrange
        mock_get_list.return_value = (None, None, None, None)
    
        # Act
        response = client.get("/proposals/unknown")
    
        # Assert
        self.assertEqual(response.status_code, 404)

    @patch("services.proposal_service.get_list_from_excel")
    def test_status_in_review_when_edited(self, mock_get_list):
        # Arrange
        mock_get_list.return_value = (MAPPINGS, 1, "2026-10-30T10:00:00", True)
       
        # Act
        response = client.get("/proposals/brunos")
        data = response.json()
       
        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["status"],"In review")