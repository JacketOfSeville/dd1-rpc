import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dd1_rpc.__main__ import default_client_id


class ClientIdTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.env_file = Path(tmp.name) / ".env"

    def lookup(self, env):
        with mock.patch.dict(os.environ, env, clear=True):
            return default_client_id(self.env_file)

    def test_none(self):
        self.assertIsNone(self.lookup({}))

    def test_env_file(self):
        self.env_file.write_text('# c\nCLIENT_ID="123"\n', encoding="utf-8")
        self.assertEqual(self.lookup({}), "123")

    def test_environment_wins_over_file(self):
        self.env_file.write_text("CLIENT_ID=123\n", encoding="utf-8")
        self.assertEqual(self.lookup({"CLIENT_ID": "456"}), "456")

    def test_legacy_name(self):
        self.assertEqual(self.lookup({"DD1_RPC_CLIENT_ID": "789"}), "789")


if __name__ == "__main__":
    unittest.main()
