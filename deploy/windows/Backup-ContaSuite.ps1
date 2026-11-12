param(
    [Parameter(Mandatory=$true)][string]$PgBin,
    [Parameter(Mandatory=$true)][string]$Database,
    [Parameter(Mandatory=$true)][string]$Destination,
    [Parameter(Mandatory=$true)][string]$DataDirectory,
    [switch]$WritersStopped
)
$ErrorActionPreference='Stop'
# PGHOST/PGPORT/PGUSER y PGPASSFILE los aprovisiona la cuenta del servicio.
if (-not $WritersStopped) { throw 'Detener API/indexador antes del respaldo conjunto de base y archivos.' }
if (-not $env:PGHOST -or -not $env:PGUSER) { throw 'Proporciona conexión explícita; no se lee .env.' }
if (-not [IO.Path]::IsPathRooted($Destination) -or -not [IO.Path]::IsPathRooted($DataDirectory)) { throw 'Usa rutas absolutas.' }
$out=Join-Path $Destination ('contasuite-'+(Get-Date -Format 'yyyyMMdd-HHmmss-ffff'))
New-Item -ItemType Directory -Path $out -ErrorAction Stop | Out-Null
& (Join-Path $PgBin 'pg_dump.exe') -Fc --file (Join-Path $out 'database.dump') --dbname $Database
if ($LASTEXITCODE -ne 0) { throw 'Falló pg_dump; respaldo incompleto, no se borra.' }
Copy-Item -LiteralPath $DataDirectory -Destination (Join-Path $out 'data') -Recurse
$files=Get-ChildItem -LiteralPath $out -File -Recurse
$manifest=@{}
foreach ($file in $files) { $manifest[$file.FullName.Substring($out.Length+1)]=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash }
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'sha256.json') -Encoding UTF8
Write-Output "Respaldo conservado en $out. Restaurar en otra base y comprobar antes de aprobarlo."
