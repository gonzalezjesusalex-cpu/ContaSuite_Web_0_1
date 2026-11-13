param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$DataDirectory,
    [ValidateSet('api','alerts','index')][string]$Mode='api',
    [int]$Port=8000
)
$ErrorActionPreference='Stop'
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
& $Python -B (Join-Path $root 'scripts/service_runtime.py') --data-dir $DataDirectory --mode $Mode --port $Port
exit $LASTEXITCODE
