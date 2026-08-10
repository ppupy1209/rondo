$ErrorActionPreference = "Stop"

$ZellijCommand = Get-Command zellij.exe -ErrorAction SilentlyContinue
$Zellij = if ($ZellijCommand) {
    $ZellijCommand.Source
} else {
    Join-Path $env:LOCALAPPDATA "Rondo\bin\zellij.exe"
}
if (-not (Test-Path -LiteralPath $Zellij -PathType Leaf)) { throw "zellij.exe is required" }
$Python = (Get-Command python.exe -ErrorAction Stop).Source
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Name = "rondo-win-e2e-$([guid]::NewGuid().ToString('N').Substring(0, 10))"
$Temp = Join-Path $env:TEMP $Name
$Repo = Join-Path $Temp "repo"
$Layout = Join-Path $Temp "layout.kdl"
$Fake = Join-Path $Root "tests\fixtures\fake_agent.py"
New-Item -ItemType Directory -Force -Path $Repo | Out-Null

function Invoke-Zellij([string[]]$Arguments) {
    $output = & $Zellij @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($output -join "`n") }
    return $output
}

function Wait-Screen([string]$Marker) {
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    $last = "session did not start"
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $panes = (Invoke-Zellij @("-s", $Name, "action", "list-panes", "--json")) | ConvertFrom-Json
            $pane = $panes | Where-Object { $_.title -eq "codex" } | Select-Object -First 1
            if ($pane) {
                $last = (Invoke-Zellij @("-s", $Name, "action", "dump-screen", "--pane-id", [string]$pane.id)) -join "`n"
                if ($last.Contains($Marker)) { return $pane }
            }
        } catch { $last = $_.Exception.Message }
        Start-Sleep -Milliseconds 250
    }
    throw "Windows Zellij smoke timed out: $last"
}

$escapedPython = $Python.Replace("\", "\\").Replace('"', '\"')
$escapedFake = $Fake.Replace("\", "\\").Replace('"', '\"')
$escapedRepo = $Repo.Replace("\", "\\").Replace('"', '\"')
$content = @"
layout {
    tab name="agents" focus=true {
        pane name="codex" command="$escapedPython" cwd="$escapedRepo" {
            args "$escapedFake"
        }
    }
}
"@
[IO.File]::WriteAllText($Layout, $content, [Text.UTF8Encoding]::new($false))

$process = $null
try {
    $process = Start-Process -FilePath $Zellij -ArgumentList @("-s", $Name, "-n", $Layout) -PassThru -WindowStyle Hidden
    $pane = Wait-Screen "FAKE_AGENT_READY"
    $token = "WINDOWS_E2E_$([guid]::NewGuid().ToString('N').Substring(0, 8))"
    Invoke-Zellij @("-s", $Name, "action", "paste", "--pane-id", [string]$pane.id, "--", $token) | Out-Null
    Invoke-Zellij @("-s", $Name, "action", "send-keys", "--pane-id", [string]$pane.id, "Enter") | Out-Null
    $null = Wait-Screen "RECEIVED:$token"
    Write-Host "Windows Zellij delivery lifecycle: OK"
} finally {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    & $Zellij delete-session --force $Name 2>$null | Out-Null
    $ErrorActionPreference = $previousPreference
    if ($process -and -not $process.HasExited) {
        $process.WaitForExit(3000) | Out-Null
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    }
    if (Test-Path -LiteralPath $Temp) { Remove-Item -LiteralPath $Temp -Recurse -Force }
}
