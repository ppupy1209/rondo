"""Release bootstrap contracts that must not silently become mutable."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InstallerContractTest(unittest.TestCase):
    def test_readme_install_urls_match_the_cli_version(self) -> None:
        version = subprocess.run(
            [sys.executable, str(ROOT / "bin" / "rondo"), "--version"],
            capture_output=True, text=True, check=True,
        ).stdout.split()[1]
        for name in ("README.md", "README.en.md"):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn(f"/rondo/v{version}/install.sh", source)
            self.assertIn(f"/rondo/v{version}/install.ps1", source)

    def test_bootstraps_use_versioned_verified_assets(self) -> None:
        shell = (ROOT / "install.sh").read_text()
        powershell = (ROOT / "install.ps1").read_text()
        for source in (shell, powershell):
            self.assertIn("SHA256SUMS", source)
            self.assertIn("0.44.3", source)
            self.assertNotIn("archive/refs/heads/main", source)
            self.assertNotIn("zellij-org/zellij/releases/latest", source)
            self.assertNotIn(".tar.gz.sha256sum", source)
            self.assertNotIn(".zip.sha256sum", source)
        self.assertIn("b6acf83a7739cf5f0f4e9bd47709642d4d98acbbf8c34d4a12c6e706f531da61", shell)
        self.assertIn("45f25febb588d36f499232b3ba80a9edcde3b3a2a85bebb105a82457b0ca6aef", powershell)
        self.assertIn('filter="data"', shell)
        self.assertIn('[ -f "$f" ] && [ ! -L "$f" ] || continue', shell)

    def test_release_job_publishes_both_platform_archives_and_checksums(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()
        for asset in ("rondo.tar.gz", "rondo.zip", "SHA256SUMS"):
            self.assertIn(asset, workflow)
        self.assertIn('"v*.*.*"', workflow)
        self.assertIn("test \"$GITHUB_REF_NAME\" = \"v$version\"", workflow)


if __name__ == "__main__":
    unittest.main()
