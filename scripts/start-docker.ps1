<#
.SYNOPSIS
Start Docker Desktop reliably on Windows, working around its stale-socket startup crash.

.DESCRIPTION
Docker Desktop 4.73 on Windows keeps several AF_UNIX sockets as reparse-point files
under %LOCALAPPDATA%. When it exits uncleanly (force-kill, crash, power loss, a Windows
update restart) those files are left behind. On the next start Docker tries to remove
and recreate each one, the remove fails, and the whole backend aborts:

    starting services: initializing Secrets Engine: listening on
    unix://<HOME>\AppData\Local\docker-secrets-engine\engine.sock: remove ...:
    The file cannot be accessed by the system.

The dialog offers only "Quit" or "Reset to factory defaults", and a factory reset does
NOT help, because it never touches these paths. Observed on at least two different
sockets here (the Inference manager's `dockerInference` and the Secrets Engine's
`engine.sock`), so turning off any single feature is not a general fix.

A leftover file cannot be deleted, renamed, or cleared — not even with every Docker
process stopped and WSL shut down. The directory entry itself is unusable, not merely
locked. The one operation that works is renaming the *parent directory* aside, which is
what this script does before launching. Docker then recreates a clean directory.

Note on detection: `fsutil reparsepoint query` fails with "Error 1920" for these files
whether they are stale leftovers OR live sockets of a healthy running Docker, so it
cannot be used to tell the two apart. This script relies on a rule that is actually
sound instead: if the daemon is not responding, any socket file still sitting in these
directories is by definition a leftover, and is moved aside.

Run this instead of launching Docker Desktop from the Start menu.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts/start-docker.ps1
#>
[CmdletBinding()]
param(
    [int]$TimeoutSeconds = 300,
    # Clear stale sockets without launching Docker.
    [switch]$CleanOnly
)

$ErrorActionPreference = 'Stop'

# Directories holding Docker's unix-socket files. If a future release crashes on a
# socket elsewhere, the error dialog names the path — add its directory here.
$socketDirs = @(
    (Join-Path $env:LOCALAPPDATA 'Docker\run'),
    (Join-Path $env:LOCALAPPDATA 'docker-secrets-engine')
)

function Test-DaemonUp {
    $null = & docker version --format '{{.Server.Version}}' 2>&1
    return $LASTEXITCODE -eq 0
}

if (-not $CleanOnly -and (Test-DaemonUp)) {
    $v = & docker version --format '{{.Server.Version}}' 2>&1
    Write-Host "Docker daemon is already up (server $v)." -ForegroundColor Green
    return
}

# The daemon is down, so anything left in these directories is a leftover.
Write-Host 'Daemon is down — clearing stale sockets before launch.'
$procs = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -like '*docker*' })
if ($procs.Count -gt 0) {
    Write-Host "Stopping $($procs.Count) lingering Docker process(es)..."
    $procs | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
}

$moved = 0
foreach ($dir in $socketDirs) {
    if (-not (Test-Path -LiteralPath $dir)) { continue }
    $files = @(Get-ChildItem -Force -LiteralPath $dir -ErrorAction SilentlyContinue)
    if ($files.Count -eq 0) { continue }
    $aside = "$dir.stale-$(Get-Date -Format yyyyMMddHHmmss)"
    Rename-Item -LiteralPath $dir -NewName (Split-Path $aside -Leaf)
    Write-Host "  $(Split-Path $dir -Leaf): moved $($files.Count) leftover socket(s) aside" -ForegroundColor Green
    $moved++
}
if ($moved -eq 0) { Write-Host '  nothing to clear.' }

# Moved-aside directories can never be deleted (the same unusable entries), so they
# accumulate. They hold a few zero-byte files each; mention it rather than attempting
# a removal that cannot succeed.
$stale = @(Get-ChildItem $env:LOCALAPPDATA -Directory -Filter '*.stale-*' -ErrorAction SilentlyContinue) +
         @(Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Docker') -Directory -Filter '*.stale-*' -ErrorAction SilentlyContinue)
if ($stale.Count -ge 6) {
    Write-Host "Note: $($stale.Count) stale socket dirs under %LOCALAPPDATA% (harmless; only" -ForegroundColor DarkGray
    Write-Host "      'chkdsk C: /F', which needs a reboot, can actually remove them)." -ForegroundColor DarkGray
}

if ($CleanOnly) { return }

$exe = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
if (-not (Test-Path $exe)) { throw "Docker Desktop not found at $exe" }
Write-Host 'Starting Docker Desktop...'
Start-Process $exe

Write-Host "Waiting for the daemon (up to ${TimeoutSeconds}s; a cold WSL boot is slow)..."
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 5
    if (Test-DaemonUp) {
        $v = & docker version --format '{{.Server.Version}}' 2>&1
        Write-Host "Docker daemon is up (server $v)." -ForegroundColor Green
        return
    }
}

Write-Warning "Daemon did not respond within ${TimeoutSeconds}s."
Write-Warning 'If an error dialog names a socket path not listed in $socketDirs, add its directory to this script.'
exit 1
