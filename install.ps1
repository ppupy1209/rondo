[CmdletBinding()]
param(
    [ValidatePattern('^v?\d+\.\d+\.\d+$')]
    [string]$Version = "",
    [switch]$ForceRemote
)

$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") {
    throw "install.ps1 is for Windows. Use install.sh on macOS or Linux."
}

$RondoRoot = Join-Path $env:LOCALAPPDATA "Rondo"
$Bin = Join-Path $RondoRoot "bin"
$ZellijVersion = "0.44.3"
New-Item -ItemType Directory -Force -Path $Bin | Out-Null

function Test-ReparsePoint([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    return [bool]((Get-Item -LiteralPath $Path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)
}

function Get-ManagedVersion([string]$Path) {
    if (Test-ReparsePoint $Path) { throw "Refusing a linked Rondo installation: $Path" }
    $marker = Join-Path $Path ".rondo-release.json"
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf) -or (Test-ReparsePoint $marker)) {
        throw "Refusing to replace an unmanaged Rondo directory: $Path"
    }
    try { $value = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json } catch {
        throw "Invalid Rondo release marker: $Path"
    }
    if ($value.schema -ne 1 -or [string]$value.version -notmatch '^\d+\.\d+\.\d+$') {
        throw "Invalid Rondo release marker: $Path"
    }
    return [string]$value.version
}

function Confirm-Checksum([string]$Checksums, [string]$Artifact, [string]$Name) {
    $entries = @()
    foreach ($line in Get-Content -LiteralPath $Checksums) {
        if ($line -match '^([0-9a-fA-F]{64})\s+\*?(.+?)\s*$' -and $Matches[2] -eq $Name) {
            $entries += $Matches[1].ToLowerInvariant()
        }
    }
    if ($entries.Count -ne 1) { throw "Checksum entry is missing or ambiguous: $Name" }
    $actual = (Get-FileHash -LiteralPath $Artifact -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $entries[0]) { throw "Checksum mismatch: $Name" }
}

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Find-Python {
    foreach ($name in @("python.exe", "python3.exe", "py.exe")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $command) { continue }
        $arguments = if ($name -eq "py.exe") { @("-3", "-c", "import sys; assert sys.version_info >= (3, 10); print(sys.executable)") } else { @("-c", "import sys; assert sys.version_info >= (3, 10); print(sys.executable)") }
        try {
            $executable = (& $command.Source @arguments 2>$null | Select-Object -Last 1).Trim()
            if ($LASTEXITCODE -eq 0 -and $executable) { return $executable }
        } catch {}
    }
    $installed = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
    if ($installed) { return $installed.FullName }
    return $null
}

$Python = Find-Python
if (-not $Python) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw "Python 3.10+ is missing and WinGet is unavailable. Install 'App Installer' from Microsoft Store, then run this command again."
    }
    Write-Host "Installing Python 3..."
    winget install --id Python.Python.3.13 -e --source winget --scope user --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "Python installation failed." }
    Refresh-Path
    $Python = Find-Python
    if (-not $Python) { throw "Python was installed but is not available yet. Open a new PowerShell window and run the installer again." }
}

$LocalRepo = if (-not $ForceRemote -and $PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "bin\rondo"))) { $PSScriptRoot } else { $null }
if ($LocalRepo) {
    $Repo = $LocalRepo
} else {
    $Repo = Join-Path $RondoRoot "app"
    $Requested = $Version.TrimStart('v')
    $ReleaseUrl = if ($Requested) {
        "https://github.com/ppupy1209/rondo/releases/download/v$Requested"
    } else {
        "https://github.com/ppupy1209/rondo/releases/latest/download"
    }
    $Temp = Join-Path $env:TEMP "rondo-install-$PID-$([guid]::NewGuid().ToString('N'))"
    $Archive = Join-Path $Temp "rondo.zip"
    $Checksums = Join-Path $Temp "SHA256SUMS"
    $Extract = Join-Path $Temp "extracted"
    New-Item -ItemType Directory -Force -Path $Extract | Out-Null
    try {
        Write-Host "Downloading verified Rondo release..."
        Invoke-WebRequest "$ReleaseUrl/rondo.zip" -OutFile $Archive
        Invoke-WebRequest "$ReleaseUrl/SHA256SUMS" -OutFile $Checksums
        Confirm-Checksum $Checksums $Archive "rondo.zip"
        Expand-Archive $Archive -DestinationPath $Extract -Force
        $Sources = @(Get-ChildItem -LiteralPath $Extract -Directory -Force)
        if ($Sources.Count -ne 1 -or (Test-ReparsePoint $Sources[0].FullName)) {
            throw "Downloaded Rondo archive is invalid."
        }
        $Source = $Sources[0]
        $RondoScript = Join-Path $Source.FullName "bin\rondo"
        if (-not (Test-Path -LiteralPath $RondoScript -PathType Leaf) -or (Test-ReparsePoint $RondoScript)) {
            throw "Downloaded Rondo archive is invalid."
        }
        $Detected = ((& $Python $RondoScript --version | Select-Object -Last 1) -replace '^rondo\s+', '').Trim()
        if ($LASTEXITCODE -ne 0 -or $Detected -notmatch '^\d+\.\d+\.\d+$') {
            throw "Downloaded Rondo version is invalid."
        }
        if ($Requested -and $Requested -ne $Detected) {
            throw "Requested Rondo $Requested but archive contains $Detected."
        }

        $Previous = "$Repo.previous"
        $Staging = "$Repo.installing"
        if (Test-Path -LiteralPath $Repo) { $null = Get-ManagedVersion $Repo }
        if (Test-Path -LiteralPath $Previous) {
            $null = Get-ManagedVersion $Previous
        }
        if (Test-Path -LiteralPath $Staging) { throw "An interrupted Rondo installation needs recovery: $Staging" }
        New-Item -ItemType Directory -Force -Path (Split-Path $Repo) | Out-Null
        $HadPrevious = Test-Path -LiteralPath $Repo
        if ($HadPrevious) { Move-Item -LiteralPath $Repo -Destination $Staging }
        try {
            Move-Item -LiteralPath $Source.FullName -Destination $Repo
            $Marker = Join-Path $Repo ".rondo-release.json"
            $TemporaryMarker = "$Marker.tmp"
            $MarkerValue = @{schema=1; version=$Detected; source="github-release"} | ConvertTo-Json -Compress
            [IO.File]::WriteAllText($TemporaryMarker, "$MarkerValue`n", [Text.UTF8Encoding]::new($false))
            Move-Item -LiteralPath $TemporaryMarker -Destination $Marker -Force
        } catch {
            if (Test-Path -LiteralPath $Repo) { Remove-Item -LiteralPath $Repo -Recurse -Force }
            if ($HadPrevious -and (Test-Path -LiteralPath $Staging)) {
                Move-Item -LiteralPath $Staging -Destination $Repo
            }
            throw
        }
        if ($HadPrevious) {
            if (Test-Path -LiteralPath $Previous) {
                Remove-Item -LiteralPath $Previous -Recurse -Force
            }
            Move-Item -LiteralPath $Staging -Destination $Previous
        }
    } finally {
        if (Test-Path -LiteralPath $Temp) { Remove-Item -LiteralPath $Temp -Recurse -Force }
    }
}

$Zellij = Get-Command zellij.exe -ErrorAction SilentlyContinue
if (-not $Zellij -and -not (Test-Path (Join-Path $Bin "zellij.exe"))) {
    Write-Host "Installing Zellij $ZellijVersion (verified)..."
    $architecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    if ($architecture -notin @("Arm64", "X64")) { throw "Unsupported Windows architecture: $architecture" }
    # Zellij currently publishes an x64 Windows build. Windows on Arm can run it
    # through the operating system's x64 emulation.
    $target = "x86_64"
    $asset = "zellij-$target-pc-windows-msvc.zip"
    $expectedDigest = "45f25febb588d36f499232b3ba80a9edcde3b3a2a85bebb105a82457b0ca6aef"
    $base = "https://github.com/zellij-org/zellij/releases/download/v$ZellijVersion"
    $temp = Join-Path $env:TEMP "zellij-$PID-$([guid]::NewGuid().ToString('N'))"
    $zip = Join-Path $temp $asset
    $extract = Join-Path $temp "extracted"
    New-Item -ItemType Directory -Force -Path $extract | Out-Null
    try {
        Invoke-WebRequest "$base/$asset" -OutFile $zip
        $actualDigest = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualDigest -ne $expectedDigest) { throw "Checksum mismatch: $asset" }
        Expand-Archive $zip -DestinationPath $extract -Force
        $binaries = @(Get-ChildItem -LiteralPath $extract -Filter zellij.exe -Recurse -File)
        if ($binaries.Count -ne 1 -or (Test-ReparsePoint $binaries[0].FullName)) {
            throw "Downloaded Zellij archive is invalid."
        }
        Copy-Item -LiteralPath $binaries[0].FullName -Destination (Join-Path $Bin "zellij.exe") -Force
    } finally {
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Recurse -Force }
    }
}

function Write-PythonLauncher([string]$Name, [string]$Script) {
    $target = Join-Path $Bin "$Name.cmd"
    $source = Join-Path $Repo "bin\$Script"
    $content = "@echo off`r`nchcp 65001 >nul`r`nset PYTHONUTF8=1`r`n`"$Python`" `"$source`" %*`r`n"
    [IO.File]::WriteAllText($target, $content, [Text.UTF8Encoding]::new($false))
}

@{
    "rondo" = "rondo"; "ai" = "rondo";
    "ai-status" = "ai-status"; "rondo-status" = "ai-status";
    "rondo-claude-status" = "rondo-claude-status"; "claude-statusline" = "rondo-claude-status";
    "rondo-lens" = "rondo-lens"; "rondo-relay" = "rondo-relay";
    "rondo-agent-session" = "rondo-agent-session"
}.GetEnumerator() | ForEach-Object { Write-PythonLauncher $_.Key $_.Value }

function Write-AgentLauncher([string]$Name, [string]$Agent) {
    $target = Join-Path $Bin "$Name.cmd"
    $source = Join-Path $Repo "bin\rondo-agent-session"
    $content = "@echo off`r`nchcp 65001 >nul`r`nset PYTHONUTF8=1`r`n`"$Python`" `"$source`" $Agent %*`r`n"
    [IO.File]::WriteAllText($target, $content, [Text.UTF8Encoding]::new($false))
}

Write-AgentLauncher "claude-session" "claude"
Write-AgentLauncher "codex-session" "codex"
Write-AgentLauncher "agy-session" "gemini"
Write-AgentLauncher "kimi-session" "kimi"
Write-AgentLauncher "grok-session" "grok"

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (($userPath -split ";") -notcontains $Bin) {
    [Environment]::SetEnvironmentVariable("Path", "$Bin;$userPath", "User")
}
$env:Path = "$Bin;$env:Path"

$ClaudeSettings = Join-Path $HOME ".claude\settings.json"
if (Test-Path $ClaudeSettings) {
    try { $config = Get-Content $ClaudeSettings -Raw | ConvertFrom-Json } catch { $config = $null }
} else {
    $config = [pscustomobject]@{}
}
if ($config -and -not $config.statusLine) {
    $config | Add-Member -NotePropertyName statusLine -NotePropertyValue ([pscustomobject]@{type="command"; command="rondo-claude-status"; refreshInterval=5})
    New-Item -ItemType Directory -Force -Path (Split-Path $ClaudeSettings) | Out-Null
    $config | ConvertTo-Json -Depth 20 | Set-Content $ClaudeSettings -Encoding UTF8
}

Write-Host ""
Write-Host "Rondo installed. Open a new PowerShell window, then run:"
Write-Host "  rondo"
Write-Host "Run 'rondo setup' later to change the saved choices."
