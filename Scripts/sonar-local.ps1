param(
    [string]$ScannerPath = 'sonar-scanner',
    [string]$ProjectKey = 'Essers_Mapping_Local',
    [string]$ServerUrl = 'http://127.0.0.1:9001'
)

$ErrorActionPreference = 'Stop'
$server = [Uri]$ServerUrl
if (-not $server.IsLoopback -or $server.Scheme -notin @('http', 'https') -or $server.UserInfo) {
    throw 'Use a local SonarQube server. This script must not overwrite the shared project.'
}
if (-not $env:SONAR_TOKEN) {
    throw 'Set SONAR_TOKEN to a token from your local SonarQube instance.'
}

$repository = Split-Path -Parent $PSScriptRoot
Push-Location $repository
try {
    & $ScannerPath "-Dsonar.host.url=$ServerUrl" "-Dsonar.projectKey=$ProjectKey" '-Dsonar.qualitygate.wait=true'
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
