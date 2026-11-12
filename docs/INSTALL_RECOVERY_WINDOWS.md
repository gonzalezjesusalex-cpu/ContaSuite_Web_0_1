# Instalación reproducible de integración — 11/11/2026

El ZIP de integración es código ejecutable y frontend compilado, sin datos, entornos, contraseñas ni PostgreSQL incluido. No es un instalador MSI firmado ni una aprobación para operación real. No usar los lanzadores históricos para esta actualización: sus textos todavía describen migración automática y preparación de configuración.

## Preparación en una máquina nueva autorizada

1. Verificar SHA-256 del ZIP y `PACKAGE_SHA256.json` de cada archivo extraído. Extraer a una carpeta nueva; no superponer una instalación existente.
2. Instalar Python 3.12 x64 y PostgreSQL 17 desde sus distribuidores oficiales. Crear un entorno Python separado y ejecutar `python -m pip install -r backend/requirements-recovery.lock.txt`. El lock reproduce las 43 distribuciones del entorno probado, incluidas herramientas de QA; no contiene rutas privadas. Descarga de dependencias/instalación en otro equipo pendiente.
3. Aprovisionar PostgreSQL con base nueva, propietario dedicado sin privilegios de superusuario, SCRAM y escucha local. Restringir `pg_hba.conf` a la cuenta/base necesarias. Mantener configuración y datos fuera del directorio versionado. No reutilizar contraseñas del laboratorio. Las credenciales se aprovisionan al entorno de los procesos, no al ZIP ni a argumentos visibles del servicio.
4. Aprovisionar `DATABASE_URL`, `APP_TOKEN` y `AGENT_TOKEN` para esos procesos; las raíces `CS_STORAGE_ALLOWED_ROOTS` y `CS_STORAGE_SMB_ALLOWED_ROOTS` quedan `[]` hasta autorización independiente. Proteger configuración/datos/logs con ACL de la cuenta dedicada. No activar revelación de credenciales ni importación definitiva.
5. Ejecutar `deploy/windows/Install-ContaSuite.ps1 -Mode Install -Python <ruta-absoluta-python> -DataDirectory <ruta-absoluta-datos>`. La instalación rechaza una base con tabla companies. La migración es una operación explícita y separada del arranque.
6. Ejecutar `deploy/windows/Start-ContaSuite.ps1` con las mismas rutas. API en `127.0.0.1:8000`; frontend servido por FastAPI, sin Node en ejecución. Crear administrador personal con el token de instalación; después ese token no sustituye la sesión personal.

## Actualización

En este equipo la política de PowerShell impidió ejecutar los .ps1; no se modificó. La alternativa probada es `deploy\windows\Install-ContaSuite.cmd "python.exe" "datos absolutos" Install`, o `Update "dump verificado"`. `Start-ContaSuite.cmd "python.exe" "datos absolutos" api 8000` inicia la misma API. Para alertas sustituir api por alerts; para indexación por index sólo tras autorizar raíces. Estos lanzadores no cargan .env ni cambian políticas del sistema. El ejecutor Python exige variables explícitas igual que PowerShell.

Detener escritores API/indexador/alertas. Respaldar conjuntamente la base con pg_dump y los archivos de datos. Restaurar el respaldo en otra base y verificar integridad/contenido antes de continuar. Extraer el código nuevo en otra carpeta; conservar el código anterior y la configuración externa. Ejecutar `Install-ContaSuite.ps1 -Mode Update ... -VerifiedDatabaseBackup <dump-verificado>`. El script exige un archivo no vacío; la restauración y su autorización siguen siendo responsabilidad del operador y deben quedar registradas. `create_all` no corrige automáticamente tipos/constraints previos; la comprobación final rechaza incompatibilidades.

Después ejecutar comprobación sin `--apply`: `python -B scripts/schema_admin.py --data-dir <ruta>` con DATABASE_URL explícita. El arranque ordinario verifica columnas/tipos/nulabilidad/PK/FK y no crea ni modifica esquema. Si falla, conservar el respaldo y diagnosticar; no borrar tablas. No se garantiza downgrade de esquema; el historial nuevo debe conservarse al revertir código.

## Servicios y LAN

`service.example.xml` es una plantilla WinSW sin binario descargado ni servicio registrado. La cuenta dedicada debe recibir las variables mediante un mecanismo protegido del administrador. API y alertas son servicios distintos; para alertas usar `service_runtime.py --mode alerts`. Indexación requiere `--mode index` y raíces autorizadas aparte. Un único proceso API: los motores históricos de generación todavía recuperan trabajos al reiniciar y no están certificados para varias réplicas.

Publicar en LAN mediante proxy inverso HTTPS con certificado válido y nombre DNS del despacho; upstream sólo `127.0.0.1:8000`, firewall sin exposición directa de PostgreSQL ni API. El backend confía encabezados de proxy sólo desde loopback. Las sesiones existentes exigen HTTPS fuera de loopback, HttpOnly, SameSite y CSRF; no desactivar estas verificaciones. TLS, firewall, cuenta de servicio y navegación desde otro equipo deben comprobarse en un entorno autorizado antes de operación.

## Respaldos automáticos

`Backup-ContaSuite.ps1` usa PGHOST/PGPORT/PGUSER/PGPASSFILE aprovisionados, pg_dump custom, copia de datos y manifiesto SHA-256. Requiere `-WritersStopped` porque no promete un snapshot atómico con documentos cambiando. Conserva todos los respaldos; no hay purga automática. Para programarlo, configurar una tarea de Windows con cuenta dedicada, ventana de mantenimiento que detenga/reinicie escritores y destino privado externo. El paquete no registra tareas ni guarda contraseñas. Antes de activar el horario, ensayar fallo de disco, restauración de archivos/base, retención y recuperación de la cuenta. La automatización de mantenimiento y sus permisos queda pendiente de validación operativa.

Alternativa probada con la política actual: `python -B scripts/backup_postgres.py --pg-bin <binarios> --database <base> --destination <destino-absoluto> --data-dir <datos-absolutos> --writers-stopped`. Nunca detiene servicios ni elimina respaldos anteriores; el operador coordina la ventana de mantenimiento. Se probó dump/restauración en otra base sintética.

## Reproducción del laboratorio de esta tarea

Los scripts `integration_runtime.py`, `integration_http.py`, `integration_postgres.py`, `integration_http_followup.py` e `integration_package.py` permanecen en el repositorio y trabajan exclusivamente con marcas sintéticas verificadas bajo `.qa/integration-recovery-20261111-v3`. No forman parte del paquete operativo. La preparación inicial se niega a reutilizar un entorno existente; las pruebas que crean bases también rechazan reemplazarlas. Para otro ensayo asignar una ruta y puertos nuevos revisados, nunca apuntar los scripts al entorno empresarial.
