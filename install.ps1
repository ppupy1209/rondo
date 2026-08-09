[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") {
    throw "install.ps1 is for Windows. Use install.sh on macOS or Linux."
}

$RondoRoot = Join-Path $env:LOCALAPPDATA "Rondo"
$Bin = Join-Path $RondoRoot "bin"
New-Item -ItemType Directory -Force -Path $Bin | Out-Null

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

$LocalRepo = if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "bin\rondo"))) { $PSScriptRoot } else { $null }
if ($LocalRepo) {
    $Repo = $LocalRepo
} else {
    $Repo = Join-Path $RondoRoot "app"
    $Temp = Join-Path $env:TEMP "rondo-install-$PID"
    $Archive = "$Temp.zip"
    Remove-Item -Recurse -Force $Temp, $Archive -ErrorAction SilentlyContinue
    Write-Host "Downloading Rondo..."
    Invoke-WebRequest "https://github.com/ppupy1209/rondo/archive/refs/heads/main.zip" -OutFile $Archive
    Expand-Archive $Archive -DestinationPath $Temp -Force
    $Source = Get-ChildItem $Temp -Directory | Select-Object -First 1
    if (-not $Source) { throw "Downloaded Rondo archive is invalid." }
    Remove-Item -Recurse -Force $Repo -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path (Split-Path $Repo) | Out-Null
    Move-Item $Source.FullName $Repo
    Remove-Item -Recurse -Force $Temp, $Archive -ErrorAction SilentlyContinue
}

$Zellij = Get-Command zellij.exe -ErrorAction SilentlyContinue
if (-not $Zellij -and -not (Test-Path (Join-Path $Bin "zellij.exe"))) {
    Write-Host "Installing Zellij..."
    $architecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    if ($architecture -notin @("Arm64", "X64")) { throw "Unsupported Windows architecture: $architecture" }
    # Zellij currently publishes an x64 Windows build. Windows on Arm can run it
    # through the operating system's x64 emulation.
    $target = "x86_64"
    $release = Invoke-RestMethod "https://api.github.com/repos/zellij-org/zellij/releases/latest"
    $asset = $release.assets | Where-Object { $_.name -eq "zellij-$target-pc-windows-msvc.zip" } | Select-Object -First 1
    if (-not $asset) { throw "The latest Zellij release has no Windows $target build." }
    $zip = Join-Path $env:TEMP "zellij-$PID.zip"
    $extract = Join-Path $env:TEMP "zellij-$PID"
    Invoke-WebRequest $asset.browser_download_url -OutFile $zip
    Expand-Archive $zip -DestinationPath $extract -Force
    $binary = Get-ChildItem $extract -Filter zellij.exe -Recurse | Select-Object -First 1
    if (-not $binary) { throw "Downloaded Zellij archive is invalid." }
    Copy-Item $binary.FullName (Join-Path $Bin "zellij.exe") -Force
    Remove-Item -Recurse -Force $extract, $zip -ErrorAction SilentlyContinue
}

function Write-PythonLauncher([string]$Name, [string]$Script) {
    $target = Join-Path $Bin "$Name.cmd"
    $source = Join-Path $Repo "bin\$Script"
    $content = "@echo off`r`nchcp 65001 >nul`r`n`"$Python`" `"$source`" %*`r`n"
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
    $content = "@echo off`r`nchcp 65001 >nul`r`n`"$Python`" `"$source`" $Agent %*`r`n"
    [IO.File]::WriteAllText($target, $content, [Text.UTF8Encoding]::new($false))
}

Write-AgentLauncher "claude-session" "claude"
Write-AgentLauncher "codex-session" "codex"

@{
    "agy-session" = "agy"; "kimi-session" = "kimi"; "grok-session" = "grok"
}.GetEnumerator() | ForEach-Object {
    $content = "@echo off`r`ncall $($_.Value) %*`r`n"
    [IO.File]::WriteAllText((Join-Path $Bin "$($_.Key).cmd"), $content, [Text.UTF8Encoding]::new($false))
}

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
Write-Host "  rondo setup"
Write-Host "  rondo"
