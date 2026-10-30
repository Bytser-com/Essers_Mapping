import unittest
from unittest.mock import patch

from services import sftp_storage


class SftpStorageTests(unittest.TestCase):

    @patch.dict("os.environ", {"SFTP_ROOT": "/proposals"})
    def test_full_path_adds_root(self):
        self.assertEqual(sftp_storage._full_path("brunos"), "/proposals/brunos")

    @patch.dict("os.environ", {"SFTP_ROOT": "/proposals"})
    def test_full_path_strips_leading_slash(self):
        self.assertEqual(sftp_storage._full_path("/brunos"), "/proposals/brunos")