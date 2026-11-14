# Instalación definitiva en este equipo (Fase 5)

Guía para instalar ContaSuite como servidor del despacho en este equipo. Los pasos marcados **[Admin]** se ejecutan en **PowerShell como administrador**; los demás, en una sesión normal. Nada de esta guía toca la instalación antigua del puerto 8000 (archivada en `..\archivo\base-8000-20261114`) ni los datos de `ContaSuite_Web_0_1`.

Después de cada fase, comprobar con (sin administrador; no cambia nada ni muestra secretos):

```powershell
py -3.12 scripts\verify_installation.py [--url https://<dns>]
```

## 0. Decisiones previas (con el responsable de TI del despacho)

| Dato | Ejemplo | Para qué |
|---|---|---|
| Nombre DNS interno | `contasuite.despacho.local` | Dirección que usarán los equipos y certificado TLS |
| Subred de los clientes | `192.168.1.0/24` | Única origen permitido en el firewall |
| Certificado TLS | emitido por la CA del despacho, con SAN del DNS | HTTPS en la LAN (no usar autofirmado como definitivo) |
| Gestor de secretos | el del despacho | Guardar la contraseña de PostgreSQL y la clave de alta |

Sin DNS, subred y certificado se pueden completar los pasos 1–6 (servicio local); el 7 queda pendiente.

Rutas usadas en esta guía:

| Uso | Ruta |
|---|---|
| Paquete extraído (se conserva para actualizar) | `C:\ContaSuite\paquetes\RC1-20261114` |
| Código instalado (versión) | `C:\ContaSuite\versions\RC1-20261114` |
| Datos | `C:\ProgramData\ContaSuite\data` |
| Registros | `C:\ProgramData\ContaSuite\logs` |
| Configuración privada | `C:\ProgramData\ContaSuite\private` |

## 1. PostgreSQL 17 [Admin]

```powershell
winget install --id PostgreSQL.PostgreSQL.17 -e
```

El instalador pide la contraseña del superusuario `postgres`: guardarla en el gestor de secretos. Después:

1. Abrir `C:\Program Files\PostgreSQL\17\data\postgresql.conf` y dejar `listen_addresses = 'localhost'` (el instalador suele dejar `'*'`).
2. En `pg_hba.conf` deben quedar sólo líneas `host ... 127.0.0.1/32 scram-sha-256` y `::1/128 scram-sha-256` (más las `local` si existen). Ninguna con otra red.
3. `Restart-Service postgresql-x64-17`
4. No crear reglas de firewall para 5432.

Crear el rol y la base de ContaSuite (pide la contraseña de `postgres`; la de `contasuite_app` se escribe dos veces con `\password`, sin quedar en el historial):

```powershell
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -h 127.0.0.1 -U postgres
```

```sql
CREATE ROLE contasuite_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
\password contasuite_app
CREATE DATABASE contasuite OWNER contasuite_app ENCODING 'UTF8' TEMPLATE template0;
REVOKE ALL ON DATABASE contasuite FROM PUBLIC;
\q
```

## 2. Verificar y extraer el paquete

El paquete está en `..\ENTREGAS\ContaSuite_v1.0_RC1_20261114.zip` con su `.sha256`. Contiene Python 3.12 privado con las dependencias del lock de producción y el frontend compilado; no contiene datos, `.env` ni credenciales.

```powershell
$zip = 'C:\Users\Jesus Alex Gonzalez\Documents\Apps en desarrollo\ContaSuite Web\ENTREGAS\ContaSuite_v1.0_RC1_20261114.zip'
(Get-FileHash $zip -Algorithm SHA256).Hash.ToLower() -eq (Get-Content ($zip -replace '\.zip$', '.sha256')).Split(' ')[0]
```

Debe imprimir `True`. Luego **[Admin]**:

```powershell
New-Item -ItemType Directory C:\ContaSuite\paquetes, C:\ContaSuite\versions, C:\ProgramData\ContaSuite\data, C:\ProgramData\ContaSuite\logs, C:\ProgramData\ContaSuite\private | Out-Null
Expand-Archive $zip C:\ContaSuite\paquetes\RC1-20261114
# Código: sólo administradores/SYSTEM escriben; usuarios leen (evita que otra cuenta altere lo que ejecuta el servicio).
icacls C:\ContaSuite /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX'
# Datos, registros y configuración privada: sólo administradores/SYSTEM (ProgramData deja escribir a los usuarios).
icacls C:\ProgramData\ContaSuite /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F'
```

## 3. Instalar (aplica el esquema en la base nueva) [Admin]

Los secretos sólo viven en esta sesión; se piden ocultos y se borran al terminar. Los tokens de este paso son de un solo uso: el servicio recibe otros nuevos en el paso 4.

```powershell
$pw = Read-Host 'Contraseña de contasuite_app' -AsSecureString
$plain = [Net.NetworkCredential]::new('', $pw).Password
$env:PYTHON_DOTENV_DISABLED = '1'
$env:DATABASE_URL = 'postgresql+psycopg://contasuite_app:' + [uri]::EscapeDataString($plain) + '@127.0.0.1:5432/contasuite'
function New-Token { $b = New-Object byte[] 36; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); [Convert]::ToBase64String($b) }
$env:APP_TOKEN = New-Token
$env:AGENT_TOKEN = New-Token
& C:\ContaSuite\paquetes\RC1-20261114\INSTALL.cmd --mode Install --destination C:\ContaSuite\versions\RC1-20261114 --data-dir C:\ProgramData\ContaSuite\data --public-url https://<dns>
Remove-Item Env:DATABASE_URL, Env:APP_TOKEN, Env:AGENT_TOKEN; $plain = $null; $pw = $null
```

Debe terminar con `Installation prepared`. Si falla, no continuar: la carpeta se conserva para diagnóstico.

## 4. Configuración cifrada del servicio [Admin]

```powershell
& C:\ContaSuite\versions\RC1-20261114\runtime\python.exe -B C:\ContaSuite\versions\RC1-20261114\app\scripts\secure_config.py --create C:\ProgramData\ContaSuite\private\service.json
```

Pide (oculto) la misma `DATABASE_URL` del paso 3 —escribirla completa: `postgresql+psycopg://contasuite_app:<contraseña>@127.0.0.1:5432/contasuite`— y el nombre DNS. Cifra con DPAPI de esta máquina y muestra la **clave de alta inicial**: guardarla en el gestor de secretos (sirve una sola vez para crear el primer administrador). El archivo no es portable a otro equipo.

## 5. Registrar el servicio Windows [Admin]

Revisar el plan (no cambia nada) y aplicarlo:

```powershell
$svc = 'C:\ContaSuite\versions\RC1-20261114'
$args5 = '--root', $svc, '--data-dir', 'C:\ProgramData\ContaSuite\data', '--log-dir', 'C:\ProgramData\ContaSuite\logs', '--config-file', 'C:\ProgramData\ContaSuite\private\service.json', '--port', '8062'
& "$svc\runtime\python.exe" -B "$svc\app\scripts\service_admin.py" @args5
& "$svc\runtime\python.exe" -B "$svc\app\scripts\service_admin.py" @args5 --apply
```

Registra `ContaSuiteApi` con inicio automático, cuenta virtual `NT SERVICE\ContaSuiteApi` (sin privilegios) y recuperación 15/30/60 s. No lo inicia. Ya existe la cuenta virtual, así que se dan sus permisos mínimos:

```powershell
icacls C:\ContaSuite\versions\RC1-20261114 /grant 'NT SERVICE\ContaSuiteApi:(OI)(CI)RX'
icacls C:\ProgramData\ContaSuite\data /grant 'NT SERVICE\ContaSuiteApi:(OI)(CI)M'
icacls C:\ProgramData\ContaSuite\logs /grant 'NT SERVICE\ContaSuiteApi:(OI)(CI)M'
icacls C:\ProgramData\ContaSuite\private /grant 'NT SERVICE\ContaSuiteApi:(OI)(CI)R'
sc.exe start ContaSuiteApi
```

## 6. Primer administrador y comprobación local

1. `py -3.12 scripts\verify_installation.py`: servicio, recuperación, API y PostgreSQL sólo en loopback, configuración privada protegida.
2. Abrir `http://127.0.0.1:8062` **en este equipo** (HTTP sólo se admite en loopback). Crear la cuenta administradora personal con la clave de alta del paso 4. Después esa clave deja de servir.
3. Crear las cuentas de los colaboradores con sus empresas (Configuración › Usuarios y permisos).

## 7. HTTPS en la LAN [Admin] — requiere DNS, subred y certificado

1. Descargar Nginx estable para Windows desde `nginx.org` (verificar la firma publicada) y extraerlo en `C:\nginx`.
2. Copiar `C:\ContaSuite\versions\RC1-20261114\app\deploy\windows\nginx-lan.conf.example` como `C:\nginx\conf\nginx.conf` y sustituir DNS, subred y rutas del certificado/clave. Mantener el upstream `127.0.0.1:8062`.
3. Certificado y clave en `C:\nginx\certs`, con ACL sólo para administradores/SYSTEM (`icacls C:\nginx\certs /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F'`).
4. `C:\nginx\nginx.exe -t` debe validar la configuración. Nginx no trae servicio Windows propio: crear una tarea programada «Al iniciar el sistema», cuenta SYSTEM, que ejecute `C:\nginx\nginx.exe` con inicio en `C:\nginx`.
5. Firewall, sólo HTTPS desde la subred de los clientes (el nombre debe empezar por `ContaSuite`):

   ```powershell
   New-NetFirewallRule -DisplayName 'ContaSuite HTTPS LAN' -Direction Inbound -Protocol TCP -LocalPort 443 -RemoteAddress <subred> -Profile Domain,Private -Action Allow
   ```

   Nunca abrir 5432 ni 8062.
6. En cada equipo cliente, sólo si la CA del despacho no es ya de confianza: instalar su certificado **público** en «Entidades de certificación raíz de confianza» tras comprobar la huella por otro canal.
7. `py -3.12 scripts\verify_installation.py --url https://<dns>` en este equipo, y abrir `https://<dns>` desde otro equipo de la subred.

## 8. Aceptación (plan, puntos 25, 26 y 29)

Registrar resultado y fecha de cada prueba en `ESTADO.md`:

- Reiniciar el equipo **sin iniciar sesión** y comprobar `https://<dns>/api/health` desde otro equipo.
- Recuperación: en el Administrador de tareas finalizar el proceso `python.exe` del servicio; SCM debe reiniciarlo en ~15 s.
- Desde otro equipo: inicio de sesión, cookies `Secure`, expiración por inactividad, colaborador sin acceso a empresas ajenas.
- Equipo fuera de la subred: no debe conectar.
- Lista de flujos aprobados y firmada por los usuarios del despacho (punto 29).

## Pendiente fuera de esta guía

- **Respaldos programados (punto 27):** pospuestos hasta tener destino externo; procedimiento en `OPERACION.md` › Respaldar.
- Retirar de `ContaSuite_Web_0_1` los originales de la base 8000 (`data/`, `.env`) requiere autorización aparte (punto 7).
