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
$Token = [guid]::NewGuid().ToString('N').Substring(0, 10)
$Temp = Join-Path $env:TEMP "rondo-entry-$Token"
$Workspace = Join-Path $Temp "anywhere-$Token"
$Config = Join-Path $Temp "config"
$Cache = Join-Path $Temp "cache"
$Bin = Join-Path $Temp "bin"
$Fake = Join-Path $Root "tests\fixtures\fake_agent.py"
New-Item -ItemType Directory -Force -Path $Workspace,$Config,$Cache,$Bin | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Config "rondo") | Out-Null
[IO.File]::WriteAllText((Join-Path $Config "rondo\panels"), "codex`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $Config "rondo\language"), "en`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $Config "rondo\approval"), "workspace`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $Config "rondo\audience"), "default`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $Config "rondo\relay"), "auto`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $Bin "codex.cmd"), "@echo off`r`nexit /b 0`r`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText(
    (Join-Path $Bin "codex-session.cmd"),
    "@echo off`r`n`"$Python`" `"$Fake`"`r`n",
    [Text.UTF8Encoding]::new($false)
)
[IO.File]::WriteAllText(
    (Join-Path $Bin "rondo-status.cmd"),
    "@echo off`r`necho STATUS_READY`r`nping -n 31 127.0.0.1 ^>nul`r`n",
    [Text.UTF8Encoding]::new($false)
)

function Invoke-Zellij([string[]]$Arguments, [int]$TimeoutSeconds = 5) {
    $Suffix = [guid]::NewGuid().ToString('N')
    $Stdout = Join-Path $Temp "zellij-$Suffix.out"
    $Stderr = Join-Path $Temp "zellij-$Suffix.err"
    $Command = $null
    try {
        $Command = Start-Process -FilePath $Zellij -ArgumentList $Arguments -PassThru -WindowStyle Hidden -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr
        if (-not $Command.WaitForExit($TimeoutSeconds * 1000)) {
            Stop-Process -Id $Command.Id -Force -ErrorAction SilentlyContinue
            throw "Zellij command timed out: $($Arguments -join ' ')"
        }
        $Output = ""
        $ErrorText = ""
        if (Test-Path -LiteralPath $Stdout) {
            $Content = Get-Content -LiteralPath $Stdout -Raw
            if ($null -ne $Content) { $Output = [string]$Content }
        }
        if (Test-Path -LiteralPath $Stderr) {
            $Content = Get-Content -LiteralPath $Stderr -Raw
            if ($null -ne $Content) { $ErrorText = [string]$Content }
        }
        if ($ErrorText.Trim()) { throw $ErrorText.Trim() }
        return $Output
    } finally {
        if ($Command -and -not $Command.HasExited) {
            Stop-Process -Id $Command.Id -Force -ErrorAction SilentlyContinue
        }
        Remove-Item -LiteralPath $Stdout,$Stderr -Force -ErrorAction SilentlyContinue
    }
}

function Session-Names {
    return @((Invoke-Zellij -Arguments @("list-sessions", "-n")) -split "`r?`n" | ForEach-Object {
        if ($_ -match '^(\S+)') { $Matches[1] }
    })
}

function Wait-AgentPane([string]$Name) {
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    $last = "session did not start"
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $panes = (Invoke-Zellij -Arguments @("-s", $Name, "action", "list-panes", "--json")) | ConvertFrom-Json
            $agent = $panes | Where-Object {
                $_.tab_name -eq "agents" -and $_.title -eq "codex" -and -not $_.exited
            } | Select-Object -First 1
            if ($agent) {
                $screen = Invoke-Zellij -Arguments @("-s", $Name, "action", "dump-screen", "--pane-id", ([string]$agent.id))
                if ($screen.Contains("FAKE_AGENT_READY")) {
                    if (-not $agent.is_focused) { throw "agents pane is not focused" }
                    $tabs = (Invoke-Zellij -Arguments @("-s", $Name, "action", "list-tabs", "--state", "--json")) | ConvertFrom-Json
                    if (-not ($tabs | Where-Object { $_.name -eq "agents" })) {
                        throw "agents tab was not created"
                    }
                    return
                }
                $last = $screen
            }
        } catch { $last = $_.Exception.Message }
        Start-Sleep -Milliseconds 250
    }
    throw "Windows Rondo entry timed out: $last"
}

$PreviousConfig = $env:XDG_CONFIG_HOME
$PreviousCache = $env:XDG_CACHE_HOME
$PreviousHistory = $env:RONDO_HISTORY
$PreviousPath = $env:Path
$Known = Session-Names
$Process = $null
$Name = $null
try {
    $env:XDG_CONFIG_HOME = $Config
    $env:XDG_CACHE_HOME = $Cache
    $env:RONDO_HISTORY = "off"
    $env:Path = "$Bin;$(Join-Path $env:LOCALAPPDATA 'Rondo\bin');$PreviousPath"
    $Process = Start-Process -FilePath $Python -ArgumentList @((Join-Path $Root "bin\rondo")) -WorkingDirectory $Workspace -PassThru -WindowStyle Hidden
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while ([DateTime]::UtcNow -lt $deadline) {
        $Name = Session-Names | Where-Object { $_ -notin $Known -and $_ -like "rondo-anywhere-$Token*" } | Select-Object -First 1
        if ($Name) { break }
        Start-Sleep -Milliseconds 250
    }
    if (-not $Name) { throw "Rondo did not create a session for a non-Git directory" }
    Wait-AgentPane $Name
    Write-Host "Windows Rondo anywhere entry: OK"

    # A force-terminated Zellij server can leave a PID marker that still makes
    # list-sessions report the dead session as active. Rondo must remove only
    # that orphaned marker and recreate the same workspace without timing out.
    $Marker = Join-Path $env:TEMP "zellij\contract_version_1\$Name"
    if (-not (Test-Path -LiteralPath $Marker -PathType Leaf)) {
        throw "Windows Zellij server marker was not created"
    }
    $ServerPidText = (Get-Content -LiteralPath $Marker -Raw).Trim()
    if ($ServerPidText -notmatch '^\d+$') { throw "Windows Zellij server marker is invalid" }
    $ServerPid = [int]$ServerPidText
    Stop-Process -Id $ServerPid -Force
    if ($Process -and -not $Process.HasExited) { $Process.WaitForExit(5000) | Out-Null }
    if (-not (Test-Path -LiteralPath $Marker -PathType Leaf)) {
        throw "Windows Zellij did not leave the expected orphaned marker"
    }

    $Process = Start-Process -FilePath $Python -ArgumentList @((Join-Path $Root "bin\rondo")) -WorkingDirectory $Workspace -PassThru -WindowStyle Hidden
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    $CurrentServerPidText = ""
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process.HasExited -and $Process.ExitCode -ne 0) {
            throw "Rondo orphan recovery exited with code $($Process.ExitCode)"
        }
        if (Test-Path -LiteralPath $Marker -PathType Leaf) {
            try { $CurrentServerPidText = (Get-Content -LiteralPath $Marker -Raw).Trim() } catch {
                $CurrentServerPidText = ""
            }
        } else {
            $CurrentServerPidText = ""
        }
        if ($CurrentServerPidText -match '^\d+$' -and $CurrentServerPidText -ne $ServerPidText) { break }
        Start-Sleep -Milliseconds 250
    }
    if ($CurrentServerPidText -notmatch '^\d+$' -or $CurrentServerPidText -eq $ServerPidText) {
        throw "Rondo did not replace the orphaned Windows Zellij session"
    }
    Start-Sleep -Milliseconds 750
    Wait-AgentPane $Name
    Write-Host "Windows Rondo orphaned session recovery: OK"
} finally {
    if ($Name) {
        for ($attempt = 1; $attempt -le 5; $attempt++) {
            try { & $Zellij delete-session --force $Name 2>$null | Out-Null } catch {}
            if ($Name -notin (Session-Names)) { break }
            Start-Sleep -Milliseconds 250
        }
    }
    if ($Process -and -not $Process.HasExited) {
        $Process.WaitForExit(3000) | Out-Null
        if (-not $Process.HasExited) { Stop-Process -Id $Process.Id -Force }
    }
    if ($Name -and $Name -in (Session-Names)) {
        try { & $Zellij delete-session --force $Name 2>$null | Out-Null } catch {}
    }
    $LeakedSession = $Name -and $Name -in (Session-Names)
    $env:XDG_CONFIG_HOME = $PreviousConfig
    $env:XDG_CACHE_HOME = $PreviousCache
    $env:RONDO_HISTORY = $PreviousHistory
    $env:Path = $PreviousPath
    if (Test-Path -LiteralPath $Temp) {
        for ($attempt = 1; $attempt -le 20; $attempt++) {
            try {
                Remove-Item -LiteralPath $Temp -Recurse -Force
                break
            } catch {
                if ($attempt -eq 20) { throw }
                Start-Sleep -Milliseconds 250
            }
        }
    }
    if ($LeakedSession) { throw "Windows Rondo entry smoke leaked session: $Name" }
}

$global:LASTEXITCODE = 0
