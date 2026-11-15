# Operación de ContaSuite

Resumen operativo. Los procedimientos detallados del paquete RC1 siguen en `docs/INSTALL_RC1.md` (servidor), `docs/INSTALL_RELEASE_WINDOWS.md` (paquete versionado), `docs/LOCAL_INSTALLER.txt` (instalación local de pruebas) y `docs/SMB.md` (fuentes de red).

Reglas comunes: nunca restaurar ni instalar encima de una base o carpeta de datos existente; nunca escribir secretos en argumentos, scripts o registros; respaldar y ensayar la restauración antes de cualquier actualización.

`DATABASE_URL` es obligatoria en cualquier modo: sin ella, o con las credenciales de ejemplo (`contasuite:contasuite` o la contraseña `CAMBIAR` de `.env.example`), la API no arranca. No existe conexión por defecto. Debe ser PostgreSQL: SQLite se rechaza salvo que el proceso declare `CS_TEST_SQLITE=1`, reservado a pruebas (suite, E2E, `INICIAR_PRUEBA.bat`).

## Instalar

### Servidor (servicio Windows + HTTPS en LAN)

Para este equipo como servidor definitivo, seguir paso a paso [docs/INSTALACION_DEFINITIVA.md](docs/INSTALACION_DEFINITIVA.md) y comprobar cada fase con `scripts/verify_installation.py` (sin administrador). Resumen general:

1. Verificar el SHA-256 del paquete y extraer en una carpeta nueva (p. ej. `C:\ContaSuite\versions\RC1`). Datos en carpeta separada (p. ej. `C:\ProgramData\ContaSuite\data`).
2. PostgreSQL: base nueva, propietario sin superusuario, sólo loopback, SCRAM. No reutilizar bases existentes.
3. `INSTALL.cmd --mode Install --destination <código> --data-dir <datos>` con `DATABASE_URL`, `APP_TOKEN` y `AGENT_TOKEN` aprovisionados en el entorno privado. Rechaza esquemas existentes.
4. Configuración del servicio cifrada con DPAPI de máquina: `runtime\python.exe -B app\scripts\secure_config.py --create <private>\service.json`. Es específica de esa PC.
5. Registro del servicio con `scripts/service_admin.py` (`--port 8062`, revisar plan y después `--apply`) en el servidor autorizado. Iniciar con `sc.exe start ContaSuiteApi` y comprobar `/api/health`.
6. HTTPS: Nginx con `deploy/windows/nginx-lan.conf.example`, upstream `127.0.0.1:8062`, certificado de la CA del despacho, firewall 443 sólo desde la subred aprobada. No abrir 5432 ni 8062.

### Equipo local de pruebas

Instalador `INSTALAR_CONTASUITE.cmd` del paquete local: Python/PostgreSQL privados, base nueva, puerto sugerido 8072, sin servicio ni LAN. Detalle en `docs/LOCAL_INSTALLER.txt`.

### Prueba manual con datos sintéticos

`INICIAR_PRUEBA_MANUAL.bat` prepara el `.venv` si hace falta y abre una instancia aparte de todas las reales: SQLite de prueba en `%LOCALAPPDATA%\ContaSuite\prueba-manual` (no lee el `.env` ni `data\` de esta carpeta, que son de la instancia 8000 archivada), API en el primer puerto libre de 8090–8099 y agente local vinculado con su icono. La consola muestra la clave para crear el primer administrador y la carpeta de ejemplo que se autoriza en Configuración › Agentes locales. `INICIAR_PRUEBA_MANUAL.bat --reset` conserva la prueba anterior renombrada y empieza otra.

### Verificar las migraciones en PostgreSQL

```bash
python scripts/verify_postgres.py --bin <carpeta bin de PostgreSQL> --work <carpeta nueva vacía>
```

Crea un clúster propio y desechable (nunca toca una instancia real): instalación nueva, actualización desde `cs_0006` con datos (rechazada sin respaldo, idempotente), restauración del respaldo y la aplicación sobre PostgreSQL con el agente vinculado.

### Base nueva desde el código fuente

```bash
python scripts/schema_admin.py --data-dir <carpeta-datos-nueva> --new --apply
```

Requiere `DATABASE_URL` explícita en el entorno del proceso (no lee `.env`). `--new` rechaza una base que ya tenga empresas. Sin `--apply` sólo verifica compatibilidad.

### Diagnosticar el esquema de cualquier base

```bash
python scripts/schema_admin.py --data-dir <carpeta-datos> --status
```

Sólo lectura. Muestra la revisión Alembic actual, la revisión `head` y si el esquema es compatible. Todo el esquema está en una sola cadena Alembic (`backend/migrations/versions`): `cs_storage_0001`–`0005` y la línea base unificada `cs_0006_unified_baseline`, que incorpora las antiguas cadenas `*_migrations/` (congeladas; los cambios nuevos van en `0007` y siguientes). `cs_0007_user_role` añade el rol de usuario (`admin`, `contador`, `auxiliar`; Bloque 2): las cuentas administradoras pasan a `admin` y las demás a `auxiliar` con sus mismos permisos por empresa; `cs_0008_user_company_actions` crea la tabla vacía de acciones por empresa de los auxiliares. `cs_0009_run_created_by` añade el autor (`created_by`) a las ejecuciones de Recopila, CFDI y Declara y a los recibos; las anteriores quedan sin autor y, si no tienen empresa, sólo las ve la administración. `cs_0010_audit_actor` añade al historial de empresa el autor y los valores anterior y nuevo de cada cambio. `cs_0011_company_responsible` añade el responsable por usuario (`accountant_id`) y copia el texto libre anterior a `accountant_legacy`; no asigna a nadie: la conciliación por nombre la revisa y confirma el administrador. `cs_0012_company_csf` añade los datos de la Constancia de Situación Fiscal (idCIF, CURP, domicilio fiscal, inicio de operaciones, estatus en el padrón, fecha de emisión) y la tabla `company_regimes` con todos los regímenes vigentes; las empresas existentes quedan con esos datos vacíos. Desde esta revisión, una base anterior (`cs_storage_0005` o `cs_0006_unified_baseline`) aparece como `update pending` e **incompatible** (`user_accounts.role:missing`) y la aplicación no arranca con ella hasta aplicar la actualización normal (respaldo + `--apply --backup`). No ejecutar `alembic current` a mano desde `backend/`: `env.py` cargaría el `.env` de la carpeta.

## Actualizar

1. Detener la instancia y cualquier escritor externo (agente, indexador).
2. Respaldar (sección siguiente) y ensayar la restauración en una base nueva.
3. Paquete: `INSTALL.cmd --mode Update --destination <nueva-versión> --data-dir <datos> --backup <dump-verificado> --writers-stopped`. Conserva el código anterior.
4. Esquema desde fuente: `python scripts/schema_admin.py --data-dir <datos> --backup <dump-verificado> --apply`. Exige un respaldo no vacío.
5. Arrancar: el inicio sólo verifica esquema; si es incompatible se detiene sin repararlo.

No hacer downgrade destructivo. Retiro: `--mode Uninstall` conserva datos y renombra el código.

## Respaldar

```bash
python scripts/backup_postgres.py --pg-bin <bin-postgres> --database <base> --destination <carpeta-nueva> --data-dir <datos> --writers-stopped
```

Genera dump, copia de `data` y `sha256.json`. No copia originales SMB ni secretos: la configuración protegida y el material del gestor de secretos se respaldan aparte.

Programado: `scripts/maintenance_backup.py --config <private>\backup.json` (claves `pg_bin`, `database`, `destination` externa, `data_dir`, `service`, `retention` ≥ 2) desde el Programador de tareas bajo una identidad dedicada, en ventana sin trabajo. Deja `backup.status.json` sin secretos para monitorización.

## Restaurar

```bash
python scripts/restore_postgres.py --backup <carpeta> --verify-only
python scripts/restore_postgres.py --backup <carpeta> --pg-bin <bin-postgres> --database contasuite_restore_FECHA --data-dir <carpeta-nueva>
```

Rechaza bases o carpetas existentes. Comprobar conteos e historial antes de apuntar la aplicación a la base restaurada. La verificación SHA no sustituye el ensayo de restauración.

## Eventos de seguridad

`security_events` registra escrituras, accesos denegados/errores y lecturas que entregan contenido (descargas, archivos, PDF, ZIP, registro de auditoría); las lecturas correctas de consultas y sondeo no se registran. Retención: `CS_SECURITY_EVENT_RETENTION_DAYS` (365 por defecto, mínimo 90, `0` desactiva). El trabajador de alertas purga una vez al día en lotes y deja el evento `security_events_purged`. Purga manual explícita desde `backend/`, con la conexión de la instancia aprovisionada: `python -m app.security_retention --once`. No afecta `storage_events`, la auditoría ni el historial fiscal/documental.

## Análisis del agente local

**Vinculado al usuario (Bloque 4, desde `cs_0013_agent_links`).**

- **Arranque:** el instalador registra el agente en el inicio de sesión de Windows del usuario que instala (acceso directo «ContaSuite - Agente local» en su carpeta Inicio; `runtime\pythonw.exe`, sin ventana ni servicio) con `agent-session.json` en la carpeta de instalación: URL de la API, puerto local `47865` y orígenes de la app, **sin token**. Registro: `%LOCALAPPDATA%\ContaSuite\agente.log`, sin datos de documentos. El agente ya no corre dentro del servicio.
- **Vinculación:** al iniciar sesión en ContaSuite en ese equipo, el navegador pide al servidor un código de un solo uso (2 minutos) y se lo entrega al agente en `http://127.0.0.1:47865` (sólo responde a los orígenes de la app). El agente lo canjea por una credencial propia que guarda sólo en memoria; el servidor guarda sólo su hash. Al cerrar sesión, expirar (30 minutos de inactividad o 12 horas), revocar la sesión o deshabilitar al usuario, el agente queda desvinculado hasta el siguiente inicio de sesión. Un agente por sesión de Windows; un usuario por agente.
- **Carpetas:** sólo el administrador las define en Configuración › Agentes vinculados (rutas absolutas `C:\…` o UNC). El agente lee sólo bajo esas rutas y sólo para empresas en las que el usuario vinculado tiene `carpeta.analizar`. El servidor rechaza antes de encolar una ruta fuera de ellas, con el motivo.
- **Atribución:** cada análisis guarda usuario, equipo y agente, y queda en el historial de la empresa.
- **Encabezado:** «Agente conectado como …» o el motivo (sin conexión, no detectado en el equipo, sin vincular). Sin agente sólo se deshabilita Analizar carpeta, con su motivo.
- **Administración:** Configuración › Agentes vinculados permite revocar un vínculo o pedir el reinicio del agente (se desvincula y espera el siguiente inicio de sesión).
- **Fallos:** el resultado indica la causa sin datos: fuera de las carpetas autorizadas, no existe en este equipo, sin permiso de lectura de Windows, enlace o unión no permitidos, carpetas de red no habilitadas.
- **Transición:** el token compartido `AGENT_TOKEN` (modo anterior: `agent/config.json` con `token`, `INICIAR_AGENTE.bat`) sólo se acepta con `CS_ALLOW_SHARED_AGENT_TOKEN=1`; las instalaciones nuevas no lo generan. Una instalación existente (p. ej. 8072) sigue con su agente anterior hasta actualizarla con autorización.
- **Pendiente:** icono en la bandeja (requiere autorizar `pystray`); otros usuarios de Windows del mismo equipo necesitan permisos sobre la carpeta de instalación, que hoy sólo tiene el usuario que instaló.

Un análisis reclamado por el agente que no entrega resultado en `CS_AGENT_JOB_TIMEOUT_MINUTES` (15 por defecto, mínimo 5; un valor inválido impide arrancar la API) pasa a «Fallido» con el motivo y queda en la auditoría de la empresa. No se reencola: el administrador lo solicita de nuevo. Un resultado tardío se rechaza. La comprobación ocurre cuando el agente consulta trabajos, al solicitar un análisis y cuando un administrador carga el estado.

## Migrar una instancia a otro equipo

Inventariar versión/esquema/conteos, detener escritores con autorización, respaldo conjunto, transferencia protegida, verificación de hashes, restauración en base nueva, comparación de empresas/documentos/versiones/vínculos/revisiones, reprovisionar secretos y raíces. DPAPI no es portable. Nunca sobre la base antigua ni sobre el piloto.
