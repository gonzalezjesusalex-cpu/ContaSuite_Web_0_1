# Operación de ContaSuite

Resumen operativo. Los procedimientos detallados del paquete RC1 siguen en `docs/INSTALL_RC1.md` (servidor), `docs/INSTALL_RELEASE_WINDOWS.md` (paquete versionado), `docs/LOCAL_INSTALLER.txt` (instalación local de pruebas) y `docs/SMB.md` (fuentes de red).

Reglas comunes: nunca restaurar ni instalar encima de una base o carpeta de datos existente; nunca escribir secretos en argumentos, scripts o registros; respaldar y ensayar la restauración antes de cualquier actualización.

## Instalar

### Servidor (servicio Windows + HTTPS en LAN)

1. Verificar el SHA-256 del paquete y extraer en una carpeta nueva (p. ej. `C:\ContaSuite\versions\RC1`). Datos en carpeta separada (p. ej. `C:\ProgramData\ContaSuite\data`).
2. PostgreSQL: base nueva, propietario sin superusuario, sólo loopback, SCRAM. No reutilizar bases existentes.
3. `INSTALL.cmd --mode Install --destination <código> --data-dir <datos>` con `DATABASE_URL`, `APP_TOKEN` y `AGENT_TOKEN` aprovisionados en el entorno privado. Rechaza esquemas existentes.
4. Configuración del servicio cifrada con DPAPI de máquina: `runtime\python.exe -B app\scripts\secure_config.py --create <private>\service.json`. Es específica de esa PC.
5. Registro del servicio con `scripts/service_admin.py` (`--port 8062`, revisar plan y después `--apply`) en el servidor autorizado. Iniciar con `sc.exe start ContaSuiteApi` y comprobar `/api/health`.
6. HTTPS: Nginx con `deploy/windows/nginx-lan.conf.example`, upstream `127.0.0.1:8062`, certificado de la CA del despacho, firewall 443 sólo desde la subred aprobada. No abrir 5432 ni 8062.

### Equipo local de pruebas

Instalador `INSTALAR_CONTASUITE.cmd` del paquete local: Python/PostgreSQL privados, base nueva, puerto sugerido 8072, sin servicio ni LAN. Detalle en `docs/LOCAL_INSTALLER.txt`.

### Base nueva desde el código fuente

```bash
python scripts/schema_admin.py --data-dir <carpeta-datos-nueva> --new --apply
```

Requiere `DATABASE_URL` explícita en el entorno del proceso (no lee `.env`). `--new` rechaza una base que ya tenga empresas. Sin `--apply` sólo verifica compatibilidad.

### Diagnosticar el esquema de cualquier base

```bash
python scripts/schema_admin.py --data-dir <carpeta-datos> --status
```

Sólo lectura. Muestra la revisión Alembic actual, la revisión `head` y si el esquema es compatible. Todo el esquema está en una sola cadena Alembic (`backend/migrations/versions`): `cs_storage_0001`–`0005` y la línea base unificada `cs_0006_unified_baseline`, que incorpora las antiguas cadenas `*_migrations/` (congeladas; los cambios nuevos van en `0007` y siguientes). Una base preparada antes de la unificación aparece como `cs_storage_0005 ... update pending`: sigue arrancando, y se registra en `head` con la actualización normal (respaldo + `--apply --backup`). No ejecutar `alembic current` a mano desde `backend/`: `env.py` cargaría el `.env` de la carpeta.

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

## Migrar una instancia a otro equipo

Inventariar versión/esquema/conteos, detener escritores con autorización, respaldo conjunto, transferencia protegida, verificación de hashes, restauración en base nueva, comparación de empresas/documentos/versiones/vínculos/revisiones, reprovisionar secretos y raíces. DPAPI no es portable. Nunca sobre la base antigua ni sobre el piloto.
