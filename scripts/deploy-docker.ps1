param(
    [switch]$Down
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $projectRoot "agent\.env"
$composePath = Join-Path $projectRoot "docker-compose.yml"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker was not found. Install and start Docker Desktop, then retry."
}

if (-not (Test-Path $configPath)) {
    throw "Missing agent/.env. Copy agent/Common/Configs/.env.example and fill in the model credentials."
}

$config = @{}
Get-Content $configPath | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#")) {
        $pair = $line.Split("=", 2)
        if ($pair.Count -eq 2) {
            $config[$pair[0].Trim()] = $pair[1].Trim()
        }
    }
}

foreach ($key in @(
    "INTERVIEW_GUIDE_OPENAI_BASE_URL",
    "INTERVIEW_GUIDE_OPENAI_MODEL",
    "INTERVIEW_GUIDE_OPENAI_API_KEY",
    "INTERVIEW_GUIDE_EMBEDDING_BASE_URL",
    "INTERVIEW_GUIDE_EMBEDDING_MODEL",
    "INTERVIEW_GUIDE_EMBEDDING_API_KEY",
    "POSTGRES_PASSWORD"
)) {
    if (-not $config.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($config[$key]) -or $config[$key] -eq "replace-me") {
        throw "agent/.env does not contain a configured value for ${key}."
    }
    Set-Item -Path "Env:$key" -Value $config[$key]
}

if ($Down) {
    docker compose --project-directory $projectRoot -f $composePath down
    exit $LASTEXITCODE
}

docker compose --project-directory $projectRoot -f $composePath up --build --detach --remove-orphans
if ($LASTEXITCODE -ne 0) {
    throw "Docker deployment failed. Run docker compose -f docker-compose.yml logs to inspect logs."
}

docker compose --project-directory $projectRoot -f $composePath ps
Write-Host "Deployment complete: http://localhost (frontend), http://localhost:15672 (RabbitMQ)."
