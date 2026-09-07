$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\shared.ps1"
Import-DevEnvFile

$root = Get-LerosRepoRoot
$dockerDesktop = 'E:\DevEnv\Docker\app\Docker Desktop.exe'
$dockerExe = Get-DockerExe
$runtimeState = Initialize-DevRuntimeState

if (Get-Process leros -ErrorAction SilentlyContinue) {
    Write-Host '[Leros] Backend is already running.' -ForegroundColor Yellow
    Write-Host '[Leros] If you changed backend code, run deployments\dev\restart-backend.cmd' -ForegroundColor Yellow
    Read-Host 'Press Enter to exit'
    exit 0
}

if (Test-Path $dockerDesktop) {
    Start-Process -FilePath $dockerDesktop | Out-Null
}

Wait-DockerReady

Write-Host '[Leros] Starting Postgres and NATS...' -ForegroundColor Cyan
& $dockerExe compose -f "$root\deployments\dev\docker-compose.dev.yml" up -d postgresql nats
if ($LASTEXITCODE -ne 0) {
    throw 'Docker dependencies failed to start.'
}

Wait-DevPostgresReady -DockerExe $dockerExe
Wait-DevNatsReady -DockerExe $dockerExe
if (Test-DevDatabaseHasDuplicateUserOrgUin -DockerExe $dockerExe) {
    Write-Host '[Leros] Detected duplicate user-org UINs in the local development database.' -ForegroundColor Yellow
    Write-Host '[Leros] The current backend migration requires UIN to be unique.' -ForegroundColor Yellow
    $reset = Read-Host 'Reset local PostgreSQL/NATS volumes and recreate development data? (y/N)'
    if ($reset -match '^(y|yes)$') {
        & $dockerExe compose -f "$root\deployments\dev\docker-compose.dev.yml" down -v
        if ($LASTEXITCODE -ne 0) {
            throw 'Failed to reset local development data volumes.'
        }

        & $dockerExe compose -f "$root\deployments\dev\docker-compose.dev.yml" up -d postgresql nats
        if ($LASTEXITCODE -ne 0) {
            throw 'Failed to recreate local development dependencies.'
        }

        Wait-DevPostgresReady -DockerExe $dockerExe
        Wait-DevNatsReady -DockerExe $dockerExe
        Write-Host '[Leros] Local development data reset completed.' -ForegroundColor Green
    }
    else {
        throw 'Local database contains duplicate user-org UINs. Reset was cancelled.'
    }
}

Ensure-LatestBackendBinary -RepoRoot $root

Write-Host "[Leros] Using API server port $($runtimeState.serverPort) and worker port $($runtimeState.workerPort)." -ForegroundColor Cyan
Prepare-DevRuntimeConfigs -RepoRoot $root -RuntimeState $runtimeState

Start-DevBackendWindows -RuntimeState $runtimeState
Start-DevFrontendWindow

Write-Host ''
Write-Host '[Leros] Dev environment is ready.' -ForegroundColor Green
Write-Host "[Leros] Frontend: http://localhost:3005" -ForegroundColor Green
Write-Host "[Leros] API server: http://localhost:$($runtimeState.serverPort)" -ForegroundColor Green
Write-Host "[Leros] Worker: http://localhost:$($runtimeState.workerPort)" -ForegroundColor Green
Write-Host '[Leros] Frontend auto refreshes. For backend changes, run deployments\dev\restart-backend.cmd' -ForegroundColor Green
Read-Host 'Press Enter to exit'
