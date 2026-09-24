$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
docker info | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop with Linux containers first.' }
if (-not (Test-Path '.env')) {
    docker run --rm --mount "type=bind,source=$PSScriptRoot,target=/work" -w /work python:3.12-slim python scripts/setup.py
    if ($LASTEXITCODE -ne 0) { throw 'Secret generation failed.' }
}
docker compose up -d --build --wait
if ($LASTEXITCODE -ne 0) { throw 'Startup failed. Run docker compose logs.' }
Write-Host 'Open http://localhost:8080 and sign in using APP_TOKEN from .env'
