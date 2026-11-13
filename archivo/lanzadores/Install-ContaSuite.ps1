param(
    [Parameter(Mandatory=$true)][ValidateSet('Install','Update')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$DataDirectory,
    [string]$VerifiedDatabaseBackup
)
$ErrorActionPreference='Stop'
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not [IO.Path]::IsPathRooted($DataDirectory)) { throw 'DataDirectory debe ser absoluta y externa al paquete.' }
if (-not $env:DATABASE_URL) { throw 'Proporciona DATABASE_URL al proceso; no se lee .env.' }
if ($Mode -eq 'Update' -and -not (Test-Path -LiteralPath $VerifiedDatabaseBackup -PathType Leaf)) { throw 'Actualización requiere respaldo previamente restaurado y comprobado.' }
# Instalar dependencias es un paso explícito del operador, con requirements-recovery.lock.txt.
$argsList=@('-B',(Join-Path $root 'scripts/schema_admin.py'),'--data-dir',$DataDirectory,'--apply')
if ($Mode -eq 'Install') { $argsList+='--new' } else { $argsList+=@('--backup',$VerifiedDatabaseBackup) }
& $Python @argsList
if ($LASTEXITCODE -ne 0) { throw 'Esquema no actualizado; revisar el error antes de arrancar.' }
Write-Output 'Esquema verificado. Arranque separado mediante Start-ContaSuite.ps1.'
