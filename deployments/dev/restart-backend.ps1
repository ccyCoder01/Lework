$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\shared.ps1"
Import-DevEnvFile

$root = Get-LerosRepoRoot
$runtimeState = Initialize-DevRuntimeState

Stop-DevProcessesByPorts -Ports @([int]$runtimeState.serverPort, [int]$runtimeState.workerPort)

Write-Host '[Leros] Stopping remaining backend processes...' -ForegroundColor Cyan
Get-Process leros -ErrorAction SilentlyContinue | Stop-Process -Force

& "$PSScriptRoot\rebuild-backend.ps1"

$runtimeState = Get-ConfiguredDevRuntimeState
Prepare-DevRuntimeConfigs -RepoRoot $root -RuntimeState $runtimeState

Write-Host '[Leros] Restarting server and worker...' -ForegroundColor Cyan
Start-DevBackendWindows -RuntimeState $runtimeState

Write-Host ''
Write-Host '[Leros] Backend restart completed.' -ForegroundColor Green
Write-Host "[Leros] API server: http://localhost:$($runtimeState.serverPort)" -ForegroundColor Green
Write-Host "[Leros] Worker: http://localhost:$($runtimeState.workerPort)" -ForegroundColor Green
Write-Host '[Leros] Frontend does not need to restart. Just refresh the page.' -ForegroundColor Green
Read-Host 'Press Enter to exit'
