# ContaSuite Web v0.4 — Integración y Pruebas Locales

## Resultado y límites de aceptación

Entorno de desarrollo funcional con PostgreSQL real aislado, migraciones aplicadas sólo allí y escenarios sintéticos persistidos. Backend, frontend y flujos HTTP autenticados funcionan. La instalación del despacho, puerto 8000, `.env`, `data/`, agente y SMB no se modificaron.

**QA visual parcial:** se abrió y verificó la pantalla de acceso en el navegador. La revisión visual de las pantallas autenticadas, los tres temas y tamaños móviles está pendiente de configurar/iniciar la sesión personal de laboratorio. Se solicitó al usuario ese paso para no mostrar contraseñas en chat, consola ni logs. No se afirma haber revisado visualmente esas pantallas ni que v0.4 haya cumplido aún todos los criterios de aceptación.

## Diagnóstico

La aplicación usa React/TypeScript/Vite, FastAPI, SQLAlchemy y sesiones HttpOnly con CSRF. El lanzador original utiliza 8000/4173, lee la instalación existente y puede iniciar el indexador. Reutilizarlo para las pruebas habría mezclado entornos, por lo que no se usó ni se detuvo.

Obligaciones, Credenciales, Importador e Integral tienen migraciones explícitas fuera de la cadena automática de CS-Storage. Se revisaron sus dependencias: Empresas/documentos/cuentas deben existir antes de las tablas complementarias. Las comprobaciones anteriores de PostgreSQL eran sólo DDL; esta iteración verificó su creación y operación en una instancia PostgreSQL real.

No se encontró Docker/PostgreSQL en las rutas disponibles. Se usaron binarios portables PostgreSQL 17.11, descargados desde [EDB](https://productsdl.enterprisedb.com/download-postgresql-binaries), proveedor enlazado por la [página oficial de PostgreSQL para Windows](https://www.postgresql.org/download/windows/). No se instaló un servicio Windows ni se modificó PATH del sistema. Se instaló `psycopg[binary]==3.2.12`, ya declarado en los requisitos del proyecto.

## Aislamiento técnico

| Elemento | Configuración |
|---|---|
| PostgreSQL | 127.0.0.1:55484 |
| Base exclusiva | contasuite_dev_v04 |
| Rol del clúster de laboratorio | contasuite_lab |
| Cluster | `.qa/dev-v04/cluster` |
| Backend | http://127.0.0.1:8044 |
| Frontend Vite | http://127.0.0.1:4184 |
| Datos/fixtures/logs | `.qa/dev-v04/` |
| Usuario administrador de aplicación | devadmin |
| Usuario lector de aplicación | devlector, limitado a empresa ficticia 1 |

Antes de migrar, `local_v04.environment` verifica current_database, current_user, inet_server_port y SHOW data_directory contra constantes/marker del laboratorio. Rechaza clústeres fuera del proyecto, nombres/puertos distintos o marcador no verificable. No acepta una URL de base arbitraria como argumento.

Las variables DATABASE_URL, DATA_DIR, APP_TOKEN, AGENT_TOKEN y SEED_DEMO se fijan para el proceso. CS_STORAGE_ALLOWED_ROOTS y CS_STORAGE_SMB_ALLOWED_ROOTS quedan vacíos. Las variables de bóveda se vacían expresamente: no se activa revelación ni se reutiliza una clave del despacho. Los siguientes arranques incluyen PYTHON_DOTENV_DISABLED=1 para impedir incluso valores de fallback del `.env` original. El arranque inicial ya había sobreescrito explícitamente todas las variables operativas anteriores y no usó raíces reales.

Las contraseñas aleatorias de PostgreSQL/cuentas sólo se conservan cifradas con DPAPI del usuario Windows en `secrets.dpapi`. El proceso las descifra en memoria; nunca se imprimen ni se escriben a `.env` o archivos de configuración. `initdb` recibe su contraseña por una tubería local efímera y configura SCRAM, no trust. La aplicación conserva autenticación normal, control de sesión y permisos. El rol PostgreSQL de laboratorio es el propietario del clúster de pruebas: no es una propuesta de rol productivo.

El indexador y el agente no se inician en este entorno. No hay procesos automáticos contra SMB, SAT, IMSS o INFONAVIT. El laboratorio sólo escucha en loopback.

## Migraciones realizadas en desarrollo

Orden ejecutado:

1. CS-Storage Alembic `cs_storage_0001` → `cs_storage_0004` sobre base nueva.
2. Tablas base de aplicación existentes con `Base.metadata.create_all`.
3. `fiscal_migrations/001_control_obligaciones.py`.
4. `credential_migrations/001_vault.py`.
5. `import_migrations/001_reconciliation.py`.
6. `integral_migrations/001_integral.py`.

Se repitió la migración sin duplicar catálogo ni registros. Antes de repetir, se generó un respaldo PostgreSQL `-Fc` en `.qa/dev-v04/backups`. El respaldo se restauró en una base nueva llamada `contasuite_dev_v04_restore_<marca>` dentro del mismo clúster verificado; se comprobaron el marcador sintético, empresas y obligaciones. No se restauró ni sobrescribió ninguna base existente. El nombre concreto quedó en `restore-report.json`.

La API sigue aplicando su arranque estándar a la conexión recibida. Por eso el lanzador aislado verifica y fija entorno antes de iniciar FastAPI; no se usa el lanzador original para estos ensayos.

## Datos ficticios reproducibles

`scripts/local_v04_seed.py` carga cuatro empresas claramente marcadas PRUEBAS/DEMO, con RFC de ejemplos sintéticos, regímenes General, RESICO, PFAE y RIF histórico. Incluye:

- ISR cumplido y verificado por revisión interna del despacho; otro registro cumplido con fecha y sin evidencia validada.
- Pendiente vencido con fecha verificada, sin revisar y NA.
- Responsables Ana/Luis PRUEBAS, actividad confirmada y empresa histórica inactiva.
- Tres CER públicos X.509 autofirmados de prueba: vigente, próximo y vencido. No son certificados SAT; la clave de firma se genera sólo en memoria y nunca se guarda.
- Documentos XML sintéticos clasificados/sin clasificar y vínculos con obligaciones.
- Opinión manual sin resultado oficial, seguimiento CFDI, tarea y alertas.
- Un XLSX de dos filas ficticias repetidas para probar conciliación y duplicados.

La carga usa un marcador para no duplicar el conjunto. Las pruebas HTTP añaden una empresa ficticia nueva por ejecución: son registros intencionales de prueba, no duplicados del seed. La repetición de un mismo XLSX conserva la sesión por idempotencia.

## Cómo abrir la aplicación ahora

Los servidores de desarrollo quedaron iniciados para esta revisión. No abras otra instancia si el puerto ya responde.

1. Abre **CONFIGURAR_ACCESO_V0_4.bat** en la raíz del proyecto. Elige y repite una contraseña de al menos doce caracteres; no se mostrará en pantalla. Esto sólo cambia `devadmin` en la base aislada y actualiza su valor DPAPI.
2. Abre **http://127.0.0.1:4184/**.
3. Inicia sesión como **devadmin** con la contraseña que elegiste.
4. Entra a **Empresas**. Usa el mes/ejercicio actual de los datos sintéticos.
5. Revisa Dashboard general, Control de obligaciones (Dashboard y Tabla), Credenciales y Certificados, Centro de Alertas, Calendario fiscal, Opiniones, Seguimiento CFDI, Calidad e Importar y conciliar.
6. Abre el expediente de EMPRESA FICTICIA 1 y su Explorador documental. Alterna Organizada/Estructura original. El visor y descargas usan el componente documental existente.
7. En el importador usa únicamente `.qa/dev-v04/fixtures/obligaciones_FICTICIAS.xlsx`; declara que es sintético. La confirmación definitiva sigue bloqueada.

Si los servidores ya no están activos, abre **INICIAR_DESARROLLO_V0_4.bat**, conserva la consola y entra en la URL anterior. Ctrl+C detiene los procesos frontend/backend iniciados por ese lanzador. PostgreSQL portable puede permanecer activo; no es un servicio Windows ni escucha en la red del despacho.

Comandos equivalentes desde la raíz:

```powershell
.\.venv\Scripts\python.exe scripts/local_v04.py password
.\.venv\Scripts\python.exe scripts/local_v04.py run
```

Para reproducir preparación/migración/seed del laboratorio actual (nunca apuntan al `.env` del despacho):

```powershell
.\.venv\Scripts\python.exe scripts/local_v04.py setup
.\.venv\Scripts\python.exe scripts/local_v04.py migrate
.\.venv\Scripts\python.exe scripts/local_v04.py seed
```

`setup` requiere que los binarios descargados o el ZIP oficial estén en `.qa/dev-v04/runtime`. No es un instalador de distribución. Si la identidad técnica no coincide, se detiene. No borres carpetas manualmente con procesos activos. Para detener únicamente este PostgreSQL, tras cerrar el laboratorio puede usarse su `pg_ctl.exe -D .qa/dev-v04/cluster stop -m fast`; verificar siempre esa ruta antes de operar.

## Sincronización y correcciones

- Se agregó el evento local `contasuite-data-changed` después de mutaciones API exitosas. App refresca el estado y Dashboard Integral vuelve a consultar PostgreSQL; no se crean copias estadísticas independientes.
- Se conserva actualización del dashboard al recuperar foco/cada treinta segundos. Ediciones de otra ventana se reflejan por esa consulta periódica; no hay websocket ni caché persistente de indicadores.
- Empresas ahora conserva pestaña y período en la navegación URL. El selector fiscal sigue independiente de las fechas de certificados.
- Se corrigió el seed nominal para usar la fila de identidad `identity`, evitando ofrecer bootstrap cuando ya existen cuentas.
- Se corrigió el arranque PostgreSQL portable: Windows no admite `--pwfile=-`; se usa tubería local. También se evita que pg_ctl deje el lanzador esperando descriptores de salida heredados.
- Se añadió respaldo previo a repetir migraciones del laboratorio y prueba de restauración en otra base nueva.
- No se relajaron permisos ni validaciones para aprobar los flujos.

## Pruebas y resultados

Suite completa: **168 aprobadas, una omitida, una advertencia deprecada Starlette/AnyIO**. Estas pruebas mantienen bases temporales y raíces SMB vacías. No son pruebas contra la base del despacho.

Además, `scripts/local_v04_check.py` ejecutó diez comprobaciones HTTP contra 8044/PostgreSQL real aislado, sin overrides de autenticación:

1. Acceso anónimo rechazado.
2. Login nominal administrativo.
3. Dashboard con empresas persistidas en PostgreSQL.
4. Alta de empresa/obligación, edición, cambio de indicador e historial.
5. Metadatos de certificados y revelación deshabilitada.
6. Alertas persistidas sin duplicación al actualizar dos veces.
7. Clasificación documental/vistas y asociación a obligación sin cambiar estado fiscal.
8. XLSX sintético analizado, duplicado detectado y confirmación bloqueada.
9. Bóveda bloqueada sin proveedor de claves.
10. Login lector, conteos aislados y rechazo de otra empresa/revisión administrativa.

Reporte sin secretos en `.qa/dev-v04/integration-report.json`. TypeScript `--noEmit` aprobado. No fue necesario compilar Vite: el modo desarrollo sirve los módulos nuevos. `frontend/dist` conserva la entrega anterior.

Se comprobaron backend.log, frontend.log, postgres.log, isolation.json y vite.config.mjs contra todos los secretos generados del laboratorio: no contienen sus valores. Los logs HTTP registran rutas/estados, no cuerpos de login ni contraseñas. Los datos fiscales ficticios del laboratorio no se mezclan con producción.

## Revisión visual y pendientes

Confirmado visualmente: pantalla de acceso local operativa y sin superposición en la resolución disponible. No se ha verificado Inicio tras autenticación, tablas, modales, temas o móvil. La sesión del administrador debe iniciarla el usuario con su contraseña elegida; no se mostró una contraseña en chat/logs para automatizar ese paso.

Pendientes para aceptar completamente v0.4: revisión visual de las doce pantallas solicitadas; pruebas de teclado/móvil y temas; verificación visual de edición/actualización de indicadores; interfaces administrativas avanzadas ya documentadas en v0.3. Las pruebas HTTP no sustituyen QA visual. Revelación/copias de secretos, importación definitiva, OCR, conexiones externas y escaneos SMB reales permanecen deshabilitados.

## Archivos de esta iteración

Nuevos: `scripts/local_v04.py`, `local_v04_seed.py`, `local_v04_check.py`, `local_v04_restore_check.py`, `INICIAR_DESARROLLO_V0_4.bat`, `CONFIGURAR_ACCESO_V0_4.bat`, este documento. Artefactos de ejecución sólo en `.qa/dev-v04` (excluido por gitignore).

Modificados: `frontend/src/api.ts`, `frontend/src/App.tsx`, `frontend/src/modules/Companies.tsx`, `frontend/src/modules/IntegralDashboard.tsx` y `CONTINUAR_EN_CODEX.md`. No se cambiaron modelos productivos ni las migraciones anteriores.

## Plan de piloto real posterior

- [x] PostgreSQL de pruebas aislado e identidad verificada.
- [x] Migraciones aplicadas allí; respaldo/restauración ensayados.
- [x] Cuentas, CSRF y permisos probados por HTTP real.
- [x] Preview XLSX, duplicados y bloqueo de aplicación definitiva.
- [x] Dashboard sincronizado con registros persistidos.
- [x] CER sintéticos asociados y alertas verificadas.
- [x] Clasificación virtual no altera documentos ni estado fiscal.
- [x] Auditoría y revisión de logs sin secretos generados.
- [ ] QA visual completa y aceptación del usuario.
- [ ] Autorización separada de muestras reales mínimas y cuentas responsables.
- [ ] Excel de obligaciones sanitizado, metadatos fiscales sin secretos y CER públicos aprobados.
- [ ] Inventario real acotado, de lectura; nunca un escaneo general como primer piloto.
- [ ] Verificar recuperación, retención de staging y permisos con el entorno piloto antes de cada operación.

No ejecutar la importación real hasta completar esos pendientes. La base del laboratorio contiene exclusivamente datos ficticios y no debe convertirse en producción mediante cambio de URL o copia de carpetas.
