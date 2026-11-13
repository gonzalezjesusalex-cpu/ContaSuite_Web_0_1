# CS-INTEGRATION-RECOVERY-001 — integración ejecutada, aceptación operativa parcial

11/11/2026. Proyecto original `ContaSuite_Web_0_1`. Se corrigieron los cinco defectos reproducidos y se ejecutó la aplicación integrada con PostgreSQL nuevo y datos sintéticos. **ContaSuite v1.0 y el Lote 4 no se declaran terminados ni autorizados para producción.**

## Respaldo y alcance

Antes de editar: `../RESPALDOS/CS_INTEGRATION_RECOVERY_20261111/before.zip`, 303 archivos de código/documentación/scripts/compilación anterior, verificados contra `baseline.json` por SHA-256. No incluye configuración privada, bases ni documentos empresariales. `changes.json`, `final.json` e `integration.diff` en esa carpeta documentan el inventario final exacto y diferencias; `docs/CS_INTEGRATION_RECOVERY_FILES.md` enumera cada ruta.

Se inspeccionaron AGENTS.md, CONTINUAR_EN_CODEX.md e informes/contratos de Lotes 1–4. El repositorio no tiene historial Git utilizable. Se conservaron las implementaciones existentes, sin sustituir módulos. Nuevas restricciones explícitas del usuario autorizaron compilación, empaquetado y ejecución sintética en esta tarea. No se leyeron .env, secretos, KEY ni documentos originales; no se accedió a infraestructura SMB/SAT ni bases del despacho. Los CER/XML/contraseñas de pruebas son generados para el laboratorio.

## Correcciones implementadas

1. **Verificaciones:** `fiscal_verification_decisions` es historial aditivo e inmutable desde las APIs; conserva empresa, obligación, periodo, revisión fiscal, documento, versión, actor y fecha. La tabla anterior sigue como proyección actual compatible con el contrato fiscal. Una repetición de la decisión actual es idempotente; volver a una decisión anterior tras otra revisión crea una corrección nueva auditada. Se bloquea la fila fiscal y se comprueban revisiones documental/fiscal; se lee y verifica SHA-256 del contenido autorizado antes de verificar. Cambiar revisión/versión suspende la vigencia, conserva historial y cumplimiento declarado. GET `/api/integral/obligations/{id}/verifications` autoriza por empresa. La migración conserva sólo decisiones antiguas que aún existen: no reconstruye las ya sobrescritas.
2. **Arranque:** lifespan sólo inspecciona esquema, recupera estados de trabajos interrumpidos y prepara directorios de ejecución; no aplica migraciones, create_all ni sembrado automático. Esquema incompatible provoca error seguro y ningún intento de reparación. `schema_admin.py` exige conexión/data explícitas, dotenv deshabilitado y diferencia instalación nueva de actualización con respaldo suministrado. Valida tablas/columnas, afinidades de tipos, nulabilidad, PK/FK y constraints únicos; no certifica todos los CHECK, índices de rendimiento ni tamaños de campos de instalaciones históricas.
3. **Trabajador:** `--mode alerts`, `index` o `both`; indexación es el modo histórico por defecto y `--evaluate-alerts` ahora es alias de sólo alertas. Modo alertas no construye indexador/proveedor documental. Reloj/zona America/Mexico_City, reserva condicional transaccional, bloqueo advisory PostgreSQL, rollback y reintento; recuperación evalúa condición actual sin inventar avisos diarios omitidos. No se activó trabajador contra configuración existente.
4. **Alertas:** autorización empresarial y permisos de metadatos se aplican en SQL antes de contar/paginar. Orden generated_at descendente e ID estable; filtros empresa, estado, fuente y prioridad; total y conteos del conjunto filtrado completo. Frontend consulta páginas de 50, sin cargar indiscriminadamente todas las alertas. Evidencias usan la fuente fiscal existente y condición revisionada; resolver/reabrir no cambia obligaciones ni certificados.
5. **Calendario:** mes en cuadrícula real, semana por días, próximos como lista, navegación anterior/siguiente, filtros, procedencia y enlaces. Reutiliza editor y reglas existentes, sin cálculos legales ni mutación automática de cumplimiento. CSS adaptable y estados visuales urgentes; filtros móviles ampliados tras QA.
6. **Dependencia documental:** alertas `evidence_review` y contador de Empresas se habilitan sólo con historial versionado disponible y decisiones comprobables. Se suspenden ante cambio material y se conservan estados mientras no cambie la condición. No se creó otro sistema de evidencias. No certifica disponibilidad remota continua: una desconexión no cambia silenciosamente cumplimiento. Los conflictos UUID y la conciliación documental integral siguen pendientes.

## Migraciones y PostgreSQL

Nueva revisión explícita `backend/integral_migrations/002_evidence_history.py` (`integral_0002`, depende de integral_0001). Downgrade destructivo bloqueado. Orden de instalación: recibos → Alembic CS-Storage → modelos base → fiscal_0001 → vault_0001 → reconciliation → integral_0001 → company_archive_0001 → lote4_lifecycle_0001 → lote4_schedule_0002 → integral_0002. Las ramas históricas usan ejecutores independientes; `schema_admin.py` es el coordinador explícito, no un único grafo Alembic global. No ejecutado sobre datos empresariales.

Se reutilizaron únicamente binarios PostgreSQL 17.11, creando clúster totalmente nuevo `.qa/integration-recovery-20261111-v3/cluster`, rol y credenciales sintéticas SCRAM, escucha loopback y puerto libre. Antes de crear bases se contrastó SHOW data_directory con la ruta autorizada. No se reutilizó el clúster v0.4. Primeras tentativas en sandbox no fueron utilizables; se creó el clúster v3 fuera del aislamiento de procesos del sandbox. Las conexiones requirieron ejecución elevada revisada automáticamente por el entorno.

Base limpia `contasuite_recovery`: todas las revisiones aplicadas y esquema compatible. Restauración en base nueva: conteos de todas las tablas iguales y archivo interno sintético copiado con SHA-256 idéntico. Para probar actualización anterior, se retiró sólo la tabla nueva en la copia sintética restaurada y se aplicó integral_0002 explícitamente; captura de la decisión superviviente comprobada. No se borró historial del origen. Esa retirada es construcción de un fixture anterior, no procedimiento de actualización ni reversión real.

Último ensayo de respaldo estable: escritores de la API sintética detenidos, pg_dump custom `verified-backup-final2.dump`, SHA-256 `5acc24edf87e03b73167c308f2da41c258444c33a76799de4a3f652412d53f5b`. Restaurado en `contasuite_recovery_restore_final2`; resultado `postgres-results-final2.json`. Una tentativa anterior comparando conteos con API activa detectó crecimiento de auditoría y falló; se conservó y se repitió con escritores detenidos. No se presentó esa tentativa como respaldo aprobado. La API fue iniciada después; el sondeo de disponibilidad inicial encontró un timeout, pero el log confirmó startup completo y consultas posteriores correctas.

Concurrencia real entre conexiones PostgreSQL: 8 evaluadores simultáneos → 1 evaluación y 7 not_due; 6 verificaciones simultáneas → 1 decisión y 5 repeticiones idempotentes; 2 selecciones de certificado con revisión 0 → 1 éxito y 1 conflicto 409. También se probó rollback tras fallo del proveedor, reintento, renovación enlazada y suspensión por versión cambiada. No es una prueba de carga prolongada ni de múltiples servidores.

## Validaciones de esta ejecución

| Validación | Resultado real |
|---|---|
| Reproducciones estructurales de los cinco defectos | 5 fallaron sobre baseline; 5 aprobadas después. Son inspecciones AST/texto, complementadas con pruebas funcionales |
| Regresiones aisladas Lotes 1–4 y recuperación | 48 aprobadas, SQLite en memoria, sin red/procesos externos |
| Suite pytest existente adaptada | 168 aprobadas, 1 omitida por privilegios de enlaces simbólicos Windows |
| Lógica frontend | 8 aprobadas |
| Clasificador documental puro | 7 aprobadas |
| TypeScript sin emisión | Aprobado |
| Producción TypeScript + Vite | Aprobada; advertencia de chunk principal superior a 500 kB |
| PostgreSQL limpio, actualización sintética, respaldo/restauración y concurrencia | Aprobados en los alcances descritos arriba |
| HTTP inicial real | 30 comprobaciones aprobadas |
| HTTP integración adicional | 30 comprobaciones aprobadas; evidencia/alerta/dashboard/manual/reglas/archivo/CSRF |
| Navegador | Login, Empresas, Dashboard con PostgreSQL, cuadrículas mensual/semanal, fecha manual y edición guardada con revisión/historial observados |
| Móvil | Cuadrícula a una columna sin desborde; controles corregidos y comprobados a 390 px (selector de vista 277 px en área útil 375 px); captura final conservada |
| Instalación/actualización desde paquete | Aprobadas mediante CMD/Python con base nueva; arranque, sesión, rechazo de reinstalación, respaldo/restauración y actualización ensayados |

Los resultados históricos 43+8+7 y 122/168 de informes anteriores no se suman como nuevas ejecuciones. Los 48 incluyen las regresiones anteriores; no son 48 adicionales a ellas. Pytest ensaya código existente y tiene solapamiento con el ejecutor aislado; no se presenta una cifra combinada artificial.

La suite general inicial falló por permisos de carpeta temporal; la repetición usó carpetas sintéticas del workspace. Después se adaptaron fixtures al aprovisionamiento explícito de esquema, lectura de contenido y selección explícita del certificado actual. Se corrigieron dos expectativas antiguas de eliminación para exigir 409 y verificar conservación empresarial; no se relajó autorización, integridad ni auditoría. Se corrigió además la creación del directorio de datos en un arranque con esquema previamente preparado.

HTTP adicional tuvo tentativas fallidas del ejecutor por falta de espera de startup, ruta errónea de lifecycle y un conteo esperado incorrecto de historial. Se corrigió el ejecutor y se conservaron las revisiones sintéticas generadas; el resultado aprobado final está separado en `http-followup-results.json`. La vigencia fiscal declarada permaneció fulfilled durante resolución/reapertura documental.

QA visual no equivale a certificación completa de accesibilidad o Stitch. Capturas reales en `docs/qa-recovery/`. El intento de comprobar cancelación de navegación con borrador no obtuvo una confirmación fiable de la herramienta; esa rama DOM sigue pendiente aunque las guardas tienen pruebas de lógica pura. No se declara aprobada la navegación con cancelación por haber llegado a otra pestaña.

## Ejecución y paquete Windows

La aplicación original compilada se sirve en **http://127.0.0.1:8056/**, exclusivamente con base/configuración sintéticas. Sesión de administrador de pruebas en el navegador abierto; credenciales de laboratorio en el archivo privado de ese entorno, fuera del paquete. No es una demo paralela: se ejecuta este código fuente y frontend compilado. No usar esos datos/credenciales en producción.

`scripts/package_recovery.py` genera `../ENTREGAS/CS_INTEGRATION_RECOVERY_20261111.zip` mediante allowlist; incluye código, migraciones, frontend, lock de dependencias y scripts Windows. Dos construcciones con las mismas entradas deben tener el mismo SHA-256. Excluye .qa, .env, dependencias, datos y credenciales. Incluye manifiesto de cada archivo. No hay compilador Inno Setup/NSIS/PyInstaller disponible en PATH; se entrega el paquete reproducible y scripts, sin afirmar que exista MSI/EXE firmado.

Ensayo real del paquete: extraído en carpeta nueva, instalación sobre otra base PostgreSQL sintética, nueva instalación sobre base existente rechazada, API iniciada mediante CMD, frontend y sesión personal accesibles, proceso de prueba detenido, respaldo ejecutado por Python y restaurado a otra base, actualización explícita y compatibilidad comprobadas. Se reutilizó el Python preparado; no se instaló el lock desde Internet en otro equipo. `package-results.json` junto al respaldo conserva SHA del ZIP ensayado. El paquete final se ensaya después de incorporar informes/capturas; su hash se contrasta con el archivo .sha256 entregado. También se ejecuta el trabajador CLI en modo alerts/once y se verifica last_success sin trabajos de indexación.

PowerShell bloqueó la ejecución .ps1 por política local: no se alteró esa política. Se probaron alternativas CMD/Python incluidas, sin registrar servicios ni eludir permisos empresariales. Los .ps1 y la plantilla WinSW son entregables pendientes de ejecución autorizada en una política compatible.

Instalación/actualización separadas, arranque sin migraciones, plantilla de servicio local, conexión PostgreSQL explícita, guía HTTPS/LAN y respaldo programable: `docs/INSTALL_RECOVERY_WINDOWS.md`. No se instaló servicio, tarea programada ni proxy, ni se desplegó en servidor del despacho. El horario de respaldos exige una ventana de mantenimiento; no se promete consistencia base/archivos con escritores activos.

## Aceptación de Lotes 1–5

| Lote | Comprobado ahora | Estado y pendiente |
|---|---|---|
| 1 | Modelo canónico, períodos/denominadores, histórico separado, revisión fiscal/documental y HTTP | Regresionado; aceptación funcional completa del despacho pendiente |
| 2 | Empresas, permisos/revocación, RFC duplicado, archivo/restauración y conservación HTTP | Regresionado; QA visual exhaustiva de todos los filtros/guardas pendiente |
| 3 | Historial inmutable, contenido SHA-256, versión/revisión, idempotencia, HTTP y contención real | Bloqueo de sobrescritura corregido; UUID/conciliación, asociación dual automática y bandeja unificada pendientes; no se habilitan de manera insegura |
| 4 | Certificados/renovaciones, alertas, programación, evidencia, reglas/manual, cuadrículas y resumen; PostgreSQL/HTTP/UI parcial | Matriz CA4 actualizada en CS_LOTE4.md; varios criterios siguen parciales |
| 5 | Infraestructura de entrega/paquete ensayable en esta recuperación | No hay especificación ni matriz funcional de Lote 5 verificada en el repositorio; no se inventó un módulo ni se declara aprobado |

## Riesgos, bloqueos y operación real

- No resueltos por esta tarea: contrato de identidad UUID y contenido contradictorio, conciliación documental completa, asociación dual automática y bandeja de incidencias integral. Exigen diseño/revisión del alcance fiscal/documental y pruebas dedicadas, no habilitar asociación por coincidencia parcial. No afectan a la verificación manual versionada ahora comprobada.
- No recuperables mediante esta migración: decisiones históricas que la implementación anterior ya sobrescribió; sólo un respaldo anterior podría acreditarlas. No se leyeron respaldos reales.
- No comprobados: servicio Windows registrado/recuperación tras reinicio del equipo, instalación offline en otro PC, TLS/LAN/firewall, carga sostenida, multiinstancia API, toda la navegación con cancelación, revisión visual exhaustiva de certificados/incidencias y todos los temas con teclado/lector de pantalla. No hay SAT, OCR ni revelación de secretos habilitados por estos cambios.
- Una verificación refleja lectura autorizada y hash en ese momento, no autenticidad SAT ni disponibilidad remota futura. Las alertas de evidencia suspenden validez por revisión/versión; no acceden a SMB para comprobar disponibilidad periódicamente.
- El servicio exige todos los esquemas integrados. Una instalación antigua parcial debe actualizarse explícitamente y probarse en copia; arrancar no la repara. Un archivo de respaldo existente no prueba por sí mismo que sea restaurable: conservar evidencia de ensayo y autorización antes de una actualización real.
- Paginación offset con orden estable no es un snapshot entre páginas: nuevas alertas pueden mover posiciones mientras se navega. Los totales reflejan cada consulta, sin filtrar después de truncar.

**Preparación operativa: parcial.** Hay código integrado ejecutable y evidencia sintética reproducible, pero no autorización ni validación suficiente para migrar/operar en la infraestructura empresarial. No se declara finalizada ContaSuite v1.0.

## Recuperación

Detener procesos de prueba que se hayan creado para esta tarea identificándolos por PID/comando y ruta del clúster; no detener por nombre global. Antes de revertir código guardar cambios posteriores. Comparar cada archivo con `final.json`; restaurar sólo modificados desde before.zip y comprobar su SHA-256 en baseline.json. Conservar los archivos añadidos aparte antes de retirarlos y no tocar archivos posteriores que no coincidan. La compilación anterior también está en el respaldo; restaurarla junto con el código compatible. No extraer el ZIP sobre data/configuración ni eliminar tablas/historial.

La única migración nueva es aditiva y no permite downgrade destructivo. Volver a código antiguo puede volver a sobrescribir verificaciones: conservar tabla/historial y revisar compatibilidad antes de ejecutar una versión anterior. Los dumps/archivos sintéticos permanecen bajo .qa; el respaldo de código no es un respaldo de datos reales. Para futuras bases reales seguir el procedimiento de dump + archivos + restauración ensayada, con autorización separada.
