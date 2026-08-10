$ErrorActionPreference = "Stop"

$ZellijCommand = Get-Command zellij.exe -ErrorAction SilentlyContinue
$Zellij = if ($ZellijCommand) { $ZellijCommand.Source } else { Join-Path $env:LOCALAPPDATA "Rondo\bin\zellij.exe" }
if (-not (Test-Path -LiteralPath $Zellij -PathType Leaf)) { throw "zellij.exe is required" }
$Python = (Get-Command python.exe -ErrorAction Stop).Source
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Launcher = Join-Path $env:LOCALAPPDATA "Rondo\bin\rondo.cmd"
if (-not (Test-Path -LiteralPath $Launcher -PathType Leaf)) { throw "installed rondo.cmd is required" }
$Token = [guid]::NewGuid().ToString('N').Substring(0, 10)
$Temp = Join-Path $Root "tests\.windows-smoke-$Token"
$Workspace = Join-Path $Temp "project"
$Fake = Join-Path $Temp "fake-codex.cmd"
New-Item -ItemType Directory -Force -Path $Workspace | Out-Null
& git init -q $Workspace
[IO.File]::WriteAllText(
    $Fake,
    "@echo off`r`n`"$Python`" `"$(Join-Path $Root 'tests\fixtures\fake_agent.py')`" %*`r`n",
    [Text.UTF8Encoding]::new($false)
)

function Session-Names {
    return @((& $Zellij list-sessions --short 2>$null) | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Wait-Screen([string]$Name, [string]$Title, [string]$Marker) {
    $deadline = [DateTime]::UtcNow.AddSeconds(35)
    $last = "pane did not register"
    $statePath = Join-Path $Workspace ".rondo\state.json"
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
            $paneId = ""
            if ($Title -eq "Relay") {
                if ($state.relay.status -eq "active") { $paneId = [string]$state.relay.pane_id }
            } else {
                $wanted = $Title.ToLowerInvariant()
                $session = $state.sessions.PSObject.Properties | ForEach-Object { $_.Value } |
                    Where-Object { $_.agent -eq $wanted -and $_.status -eq "active" } | Select-Object -Last 1
                if ($session) { $paneId = [string]$session.pane_id }
            }
            if ($paneId) {
                $last = (& $Python -c "import subprocess,sys; p=subprocess.run([sys.argv[1],'-s',sys.argv[2],'action','dump-screen','--pane-id',sys.argv[3]],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=3); sys.stdout.write(p.stdout)" $Zellij $Name $paneId 2>$null) -join "`n"
                if ($last.Contains($Marker)) { return }
            }
        } catch {
            $sessions = (Session-Names) -join ", "
            $last = "$($_.Exception.Message) (expected=$Name; sessions=$sessions)"
        }
        Start-Sleep -Milliseconds 250
    }
    throw "Rondo Windows smoke timed out waiting for $Marker : $last"
}

$PreviousOverride = $env:RONDO_CODEX_COMMAND
$Process = $null
$Name = (& $Python -c "import sys; sys.path.insert(0, sys.argv[1]); from pathlib import Path; from rondo.core import session_name; print(session_name(Path(sys.argv[2])))" (Join-Path $Root "lib") $Workspace).Trim()
$Failure = $null
try {
    $env:RONDO_CODEX_COMMAND = $Fake
    Push-Location $Workspace
    try { & $Launcher setup --agents codex } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw "non-interactive setup failed" }
    $Process = Start-Process -FilePath $env:COMSPEC -ArgumentList @("/d", "/c", "`"$Launcher`"") -WorkingDirectory $Workspace -PassThru -WindowStyle Hidden
    Wait-Screen $Name "Codex" "FAKE_AGENT_READY"
    $Message = "WINDOWS_VISIBLE_$Token"
    Push-Location $Workspace
    try { & $Launcher message codex $Message } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw "visible delivery command failed" }
    Wait-Screen $Name "Codex" "RECEIVED:$Message"
    Wait-Screen $Name "Relay" $Message
    if (-not (Test-Path -LiteralPath (Join-Path $Workspace ".rondo\context.md") -PathType Leaf)) {
        throw "project context was not created"
    }
    Write-Host "Windows Rondo tabs and visible delivery: OK"
} catch {
    $Failure = $_
} finally {
    if ($Name -and ((Session-Names) -contains $Name)) {
        $cleanupPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "SilentlyContinue"
            & $Zellij delete-session --force $Name 2>$null | Out-Null
        } catch {} finally {
            $ErrorActionPreference = $cleanupPreference
        }
    }
    if ($Process -and -not $Process.HasExited) {
        $Process.WaitForExit(3000) | Out-Null
        if (-not $Process.HasExited) {
            try { $Process.Kill() } catch {}
        }
    }
    $env:RONDO_CODEX_COMMAND = $PreviousOverride
    if (Test-Path -LiteralPath $Temp) {
        for ($attempt = 1; $attempt -le 40; $attempt++) {
            try {
                Remove-Item -LiteralPath $Temp -Recurse -Force
                break
            } catch {
                if ($attempt -eq 40 -and -not $Failure) { $Failure = $_ }
                Start-Sleep -Milliseconds 250
            }
        }
    }
}
if ($Failure) { throw $Failure }
$global:LASTEXITCODE = 0
