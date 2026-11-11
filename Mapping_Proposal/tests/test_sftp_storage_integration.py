import posixpath
import unittest
from datetime import datetime
from io import BytesIO

from dotenv import load_dotenv

from services import sftp_storage

load_dotenv()

TEST_DIR = "integration-test"
TEST_FILE = "test.txt"
TEST_CONTENT = b"test"


def sftp_available():
    try:
        with sftp_storage._connect():
            return True
    except Exception:
        return False


@unittest.skipUnless(sftp_available(), "Test-SFTP is niet bereikbaar")
class SftpStorageIntegrationTests(unittest.TestCase):

    def setUp(self):
        dir_path = sftp_storage._full_path(TEST_DIR)
        with sftp_storage._connect() as sftp:
            sftp.mkdir(dir_path)
            sftp.putfo(BytesIO(TEST_CONTENT), posixpath.join(dir_path, TEST_FILE))

    def tearDown(self):
        dir_path = sftp_storage._full_path(TEST_DIR)
        with sftp_storage._connect() as sftp:
            sftp.remove(posixpath.join(dir_path, TEST_FILE))
            sftp.rmdir(dir_path)

    def test_list_dir_returns_file_names(self):
        file_names = sftp_storage.list_dir(TEST_DIR)
        self.assertIn(TEST_FILE, file_names)

    def test_load_returns_file_content(self):
        buffer = sftp_storage.load(f"{TEST_DIR}/{TEST_FILE}")
        self.assertEqual(buffer.read(), TEST_CONTENT)

    def test_list_dir_raises_for_missing_folder(self):
        with self.assertRaises(FileNotFoundError):
            sftp_storage.list_dir("bestaat-niet")