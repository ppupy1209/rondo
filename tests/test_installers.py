"""Release bootstrap contracts that must not silently become mutable."""
from __future__ import annotations

import base64
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InstallerContractTest(unittest.TestCase):
    def test_powershell_checksum_retries_an_empty_hash_result(self) -> None:
        executable = shutil.which("powershell") or shutil.which("pwsh")
        if not executable:
            self.skipTest("PowerShell is unavailable")

        source = (ROOT / "install.ps1").read_text(encoding="utf-8")
        start = source.index("function Get-Sha256")
        end = source.index("function Get-ManagedVersion", start)
        helper = source[start:end]
        command = f"""\
Import-Module Microsoft.PowerShell.Utility
$script:attempts = 0
function Get-FileHash {{
    param([string]$LiteralPath, [string]$Algorithm)
    $script:attempts++
    if ($script:attempts -eq 1) {{ return $null }}
    return [pscustomobject]@{{ Hash = ("A" * 64) }}
}}
{helper}
$digest = Get-Sha256 "ignored"
if ($digest -ne ("a" * 64) -or $script:attempts -ne 2) {{
    throw "SHA-256 retry contract failed"
}}
"""
        encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
        result = subprocess.run(
            [executable, "-NoProfile", "-EncodedCommand", encoded],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_powershell_bootstrap_param_block_supports_invoke_expression(self) -> None:
        executable = shutil.which("powershell") or shutil.which("pwsh")
        if not executable:
            self.skipTest("PowerShell is unavailable")

        source = (ROOT / "install.ps1").read_text(encoding="utf-8")
        body_marker = '$ErrorActionPreference = "Stop"'
        self.assertIn(body_marker, source)
        param_block = source.split(body_marker, 1)[0]
        command = f"""\
$source = @'
{param_block}
'@
try {{
    Invoke-Expression $source
}} catch {{
    Write-Error $_
    exit 1
}}
"""
        encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
        result = subprocess.run(
            [executable, "-NoProfile", "-EncodedCommand", encoded],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_windows_launchers_add_their_bin_directory_to_path(self) -> None:
        source = (ROOT / "install.ps1").read_text(encoding="utf-8")
        self.assertEqual(source.count('set `"PATH=%~dp0;%PATH%`"'), 2)
        self.assertIn("Run now in this PowerShell", source)
        self.assertIn("close all terminal windows", source)

    def test_readme_install_urls_match_the_cli_version(self) -> None:
        version = subprocess.run(
            [sys.executable, str(ROOT / "bin" / "rondo"), "--version"],
            capture_output=True, text=True, check=True,
        ).stdout.split()[1]
        for name in ("README.md", "README.en.md"):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn(f"/rondo/v{version}/install.sh", source)
            self.assertIn(f"/rondo/v{version}/install.ps1", source)
            self.assertIn(f"-Version v{version}", source)
            self.assertIn("& ([scriptblock]::Create((irm ", source)

    def test_bootstraps_use_versioned_verified_assets(self) -> None:
        shell = (ROOT / "install.sh").read_text(encoding="utf-8")
        powershell = (ROOT / "install.ps1").read_text(encoding="utf-8")
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
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        for asset in ("rondo.tar.gz", "rondo.zip", "SHA256SUMS"):
            self.assertIn(asset, workflow)
        self.assertIn('"v*.*.*"', workflow)
        self.assertIn("test \"$GITHUB_REF_NAME\" = \"v$version\"", workflow)


if __name__ == "__main__":
    unittest.main()
