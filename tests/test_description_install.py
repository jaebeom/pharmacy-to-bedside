"""rokey_p3_description installs every data directory it ships (CMakeLists install(DIRECTORY ...)). No colcon.

navigation.launch.py falls back to share/rokey_p3_description/config/zones.yaml when zones_file is empty, so a
directory left out of install() is only found through an absolute source path.
"""

import re
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "rokey_p3_description"


class DescriptionInstallTests(unittest.TestCase):
    def test_every_data_directory_is_installed(self):
        cmake = (PACKAGE / "CMakeLists.txt").read_text()
        match = re.search(r"install\(\s*DIRECTORY\s+([^\n]+)\n\s*DESTINATION share/\$\{PROJECT_NAME\}", cmake)
        self.assertIsNotNone(match, "install(DIRECTORY ... DESTINATION share/${PROJECT_NAME}) not found")
        installed = set(match.group(1).split())
        shipped = {path.name for path in PACKAGE.iterdir() if path.is_dir()}
        self.assertEqual(shipped, installed)

    def test_zones_yaml_is_in_an_installed_directory(self):
        self.assertTrue((PACKAGE / "config" / "zones.yaml").is_file())
        self.assertIn("config", (PACKAGE / "CMakeLists.txt").read_text())


if __name__ == "__main__":
    unittest.main()
