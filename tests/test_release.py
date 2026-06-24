import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import release


class ReleaseTests(unittest.TestCase):
    def test_sha256_is_uppercase(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.bin"
            path.write_bytes(b"VoiceFlow")
            self.assertEqual(
                release.sha256(path),
                "D87A29B9C3FD799B3EDFCBA2D6ED408E6FB7C2864AB62C87A971D7E5D65DF670",
            )

    def test_find_inno_setup_uses_configured_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ISCC.exe"
            path.write_bytes(b"")
            with patch.dict(os.environ, {"VOICEFLOW_ISCC": str(path)}, clear=False), patch("release.shutil.which", return_value=None):
                self.assertEqual(release.find_inno_setup(), str(path))

    def test_sign_is_optional_without_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(release.sign(Path("VoiceFlow.exe")))

    def test_find_inno_setup_supports_user_local_install(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Programs" / "Inno Setup 6" / "ISCC.exe"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"")
            with patch.dict(os.environ, {"LOCALAPPDATA": directory}, clear=True), patch("release.shutil.which", return_value=None):
                self.assertEqual(release.find_inno_setup(), str(path))


if __name__ == "__main__":
    unittest.main()
