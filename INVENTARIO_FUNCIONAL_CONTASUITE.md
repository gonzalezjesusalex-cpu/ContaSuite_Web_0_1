# Inventario funcional de ContaSuite Web

Fecha: 13/11/2026 · Versión analizada: `1.0.0-rc.1` (rama `main`, último commit `b406706`, con la Fase 0 punto 10 —baseline Alembic `0006`— en curso y sin confirmar).
Documento de consulta para planear versiones. **No** sustituye a [PLAN_FINALIZACION.md](PLAN_FINALIZACION.md) (que manda) ni declara v1.0 aprobada.

**Método.** Lectura estática de `backend/app` (incluido `storage/`), `frontend/src`, `agent/`, pruebas y documentos vivos; extracción automática de rutas y tablas por AST; cruce de endpoints usados por el frontend. Ejecución de la suite backend aislada (SQLite temporal, `PYTHON_DOTENV_DISABLED=1`). No se abrieron `.env`, `data/`, `.qa/`, `agent/config.json` ni credenciales; no se tocaron instancias (8000/8062/8072) ni datos.

## Escala de clasificación

| Etiqueta | Significado |
|---|---|
| **IMPLEMENTADA Y PROBADA** | Código en backend y/o frontend con pruebas automatizadas que cubren el flujo principal y que pasan. |
| **IMPLEMENTADA SIN VALIDACIÓN** | Funciona en código, pero sin prueba automatizada específica (o sólo cubierta en frontend sin prueba, o sólo validada manualmente en informes históricos). |
| **PARCIAL** | Parte del flujo existe; un paso clave está bloqueado deliberadamente, falta UI o depende de captura manual. |
| **PROTOTIPO** | Pantalla o dato de demostración (Stitch, semilla DEMO), código muerto o flujo experimental/piloto no destinado a producción. |
| **NO IMPLEMENTADA** | Sólo mencionada en la UI, en textos o en planes. |

## Resumen ejecutivo

| # | Módulo | Ruta UI | Estado global |
|---|---|---|---|
| 0 | Plataforma: cuentas, sesiones y seguridad | `/` (login), Configuración | IMPLEMENTADA Y PROBADA |
| 1 | Inicio | `/` | IMPLEMENTADA SIN VALIDACIÓN (sin prueba de UI) |
| 2 | Empresas (catálogo, alta, expediente, archivo) | `/empresas`, `/empresas/:id` | IMPLEMENTADA Y PROBADA, con restos PROTOTIPO |
| 3 | Dashboard integral (panel, opiniones, seguimiento CFDI, calidad de datos) | `/empresas` (4 primeras pestañas) | IMPLEMENTADA Y PROBADA; opiniones/CFDI = PARCIAL (captura manual) |
| 4 | Control de obligaciones fiscales | `/empresas` · Control de obligaciones; expediente · Obligaciones | IMPLEMENTADA Y PROBADA |
| 5 | Tareas y vencimientos / calendario fiscal | `/tareas` | IMPLEMENTADA Y PROBADA (backend) |
| 6 | Credenciales y certificados + Centro de alertas | `/empresas` y expediente · FIEL/CSD | PARCIAL (revelación bloqueada, sin validación SAT) |
| 7 | CS-Storage / Centro documental | expediente · Documentos; `/empresas` · Documentos; Configuración | IMPLEMENTADA Y PROBADA |
| 8 | Importar y conciliar (+ piloto local y lotes) | `/empresas` · Importar y conciliar | PARCIAL (confirmación definitiva bloqueada) / piloto = PROTOTIPO operativo |
| 9 | Recopila | `/recopilador-cfdi` | IMPLEMENTADA Y PROBADA |
| 10 | CFDI (antes Organizador) | `/organizador-cfdi` | IMPLEMENTADA Y PROBADA |
| 11 | Declara | `/declara` | IMPLEMENTADA Y PROBADA |
| 12 | Recibos | `/recibos` | IMPLEMENTADA Y PROBADA |
| 13 | Agente Windows | indicador superior, expediente · «Analizar carpeta» | PARCIAL (defectos P1 #3 y #4) |
| 14 | Configuración | `/configuracion` | IMPLEMENTADA SIN VALIDACIÓN, con vista Stitch PROTOTIPO |
| — | Imprime / Empresas de escritorio | — | Descartados; no integrar |

---

# Parte 1 · Inventario por módulo

## 0. Plataforma: cuentas, sesiones y seguridad

**Propósito.** Autenticación del despacho, permisos por empresa, auditoría de accesos y protección transversal de la API.

**Pantallas.** `Login.tsx` (alta del primer administrador con `APP_TOKEN` + inicio de sesión); `AccountSecurity.tsx` dentro de Configuración: «Mi cuenta» (cambio de contraseña, cerrar todas las sesiones), «Usuarios y permisos» (alta/edición/revocación, lectura/escritura por empresa), «Auditoría de accesos y operaciones».

| Funcionalidad | Clasificación |
|---|---|
| Bootstrap del primer administrador con `APP_TOKEN` (deja de servir después) | IMPLEMENTADA Y PROBADA |
| Login con scrypt, bloqueo por intentos (`login_throttles`) | IMPLEMENTADA Y PROBADA |
| Sesión HttpOnly + CSRF + expiración por inactividad (30 min) | IMPLEMENTADA Y PROBADA |
| HTTPS obligatorio fuera de loopback; `CS_ALLOWED_HOSTS` (TrustedHost) | IMPLEMENTADA Y PROBADA |
| Usuarios, permisos lectura/escritura por empresa, revocación | IMPLEMENTADA Y PROBADA |
| Auditoría `security_events` por cada petición `/api/*` | IMPLEMENTADA Y PROBADA — con defecto P1 #2 (crecimiento sin límite) |
| Errores 422 sin datos enviados (no filtra contraseñas) | IMPLEMENTADA Y PROBADA |
| Cabeceras de seguridad en HTML (CSP, X-Frame-Options) | NO IMPLEMENTADA (sólo en `/api/`; plan P3 #21) |
| Recuperación de contraseña por correo / MFA | NO IMPLEMENTADA |

**Endpoints.** `/api/auth/status`, `bootstrap`, `login`, `me`, `logout`, `logout-all`, `password`, `users` (GET/POST), `users/{id}` (PUT), `users/{id}/revoke`, `audit`.
**Tablas.** `user_accounts`, `user_company_grants`, `user_sessions`, `login_throttles`, `security_events`, `identity_state`.
**Servicios.** `accounts.py`, `security.py` (`Principal`, `auth`, `admin_auth`, `require_company`), middleware `security_audit` en `main.py`.
**Integraciones.** Reales: ninguna externa. **Pruebas.** `test_accounts.py` (20), `test_api.py` (9), `test_bootstrap.py` (5), `test_visit_readiness.py` (3).
**Dependencias.** Base de todo el sistema; `Principal` se usa en todos los routers.
**Problemas / mejoras.** Retención de `security_events` y no auditar sondeos GET (P1 #2). Credencial por defecto `contasuite:contasuite` en `database.py` (P3 #20). Preferencias (nombre mostrado, tema) sólo en `localStorage`, no por usuario en servidor.

## 1. Inicio

**Propósito.** Pantalla de bienvenida.
**Pantalla.** `Welcome` en `App.tsx`: logo, saludo por hora (mañana/tarde/noche), nombre configurado en su propia línea, «Bienvenido a ContaSuite», «Tu espacio de trabajo contable.».

| Funcionalidad | Clasificación |
|---|---|
| Saludo por hora local y nombre configurado | IMPLEMENTADA SIN VALIDACIÓN (sin prueba de UI) |
| Shell: menú lateral, migas, búsqueda global de empresas, indicador de agente, actualización manual, cambio de tema | IMPLEMENTADA SIN VALIDACIÓN |
| Temas claro / oscuro / alto contraste | IMPLEMENTADA SIN VALIDACIÓN (el botón superior sólo alterna claro/oscuro; alto contraste sólo desde Configuración) |

**Endpoints.** `/api/state` (sondeo cada 10 s, P1 #1), `/api/auth/me`.
**Problemas.** Miga «Workspace Fiscal» fija; versión «ContaSuite v1.0 RC1» escrita en el pie del menú; sondeo de `/api/state` con todos los documentos.

## 2. Empresas (catálogo, alta, expediente, archivo)

**Propósito.** Padrón de contribuyentes del despacho y expediente por empresa.

**Pantallas y pestañas.**
- `/empresas` (`Companies.tsx`, «Centro de Control Fiscal») con **14 pestañas**: Dashboard general, Opiniones de cumplimiento, Seguimiento CFDI, Calidad de datos, Directorio, Importar y conciliar, Credenciales y Certificados, Centro de Alertas, Control de obligaciones, Obligaciones Fiscales, Tareas Operativas, Expedientes Digitales, Documentos, Reportes. Selector de «Periodo activo».
- Directorio: filtros (archivo activo/archivadas/todas, orden, búsqueda, contador, estado interno), paginación de 10, exportación CSV.
- `/empresas/nueva` y `/empresas/:id/editar` (`CompanyForm.tsx`): alta por pasos con resumen.
- `/empresas/:id` (`Dossier.tsx`): 5 secciones (`companyNavigation.ts`) —Resumen, Obligaciones (Cumplimiento / Histórico fiscal), Documentos (Documentos / Explorador documental), FIEL/CSD (Credenciales y Certificados / e.firma y CSD), Actividad (Tareas / Declaraciones / Historial)—, cambio de empresa, archivar/restaurar, «Analizar carpeta» vía agente, accesos a Recopila y Recibos.

| Funcionalidad | Clasificación |
|---|---|
| Alta y edición de empresa, RFC único (409 si se duplica) | IMPLEMENTADA Y PROBADA |
| Directorio con filtros y orden servido por `/api/company-lifecycle` | IMPLEMENTADA Y PROBADA |
| Archivar / restaurar (sin borrar), historial de archivo | IMPLEMENTADA Y PROBADA |
| Eliminación de empresa | Bloqueada a propósito (`forbid_delete`) |
| Expediente con 5 secciones y conservación de filtros/periodo al cambiar de empresa | IMPLEMENTADA Y PROBADA (frontend `lote2.test.mjs`) |
| Protección de borradores sin guardar al navegar (`dirtyForms`, `navigationGuard`) | IMPLEMENTADA Y PROBADA (`lote2.test.mjs`); cancelación de borradores pendiente de verificación manual (plan P4 #24) |
| Aviso al capturar en empresa archivada | IMPLEMENTADA Y PROBADA (`lote2.test.mjs`) |
| Exportar directorio CSV y obligaciones del periodo CSV (pestaña Reportes) | IMPLEMENTADA SIN VALIDACIÓN |
| Pestaña «Expedientes Digitales» (tarjetas por empresa) | IMPLEMENTADA SIN VALIDACIÓN |
| «Bitácora del expediente» (tabla `audit_events`) | IMPLEMENTADA SIN VALIDACIÓN |
| Columna «Opinión 32-D» del directorio | PROTOTIPO (insignia fija «Sin consultar») |
| Carga de «ejemplo DEMO» (`POST /api/demo`) | PROTOTIPO |
| Vista «Resumen Ejecutivo» (KPIs, distribución, carga de trabajo) | PROTOTIPO — código muerto: no figura en la lista de pestañas |
| Pestaña «e.firma y CSD» | PARCIAL (panel `CompanyDashboard` real + texto fijo «Validación SAT pendiente») |
| DIOT | NO IMPLEMENTADA (sólo aviso en Reportes) |

**Endpoints.** `/api/companies` (POST), `/api/companies/{id}` (PUT, DELETE→bloqueado), `/api/company-lifecycle` (GET), `/{id}` (PUT), `/{id}/history`, `/api/demo`, `/api/jobs`, `/api/state`.
**Tablas.** `companies`, `audit_events`, `company_archive_states`, `company_archive_events`, `tasks`, `obligations`.
**Pruebas.** `test_api.py`, `test_rc1_operations.py` (4), `test_accounts.py` (ámbito por empresa); frontend `lote2.test.mjs` (5 casos).
**Dependencias.** Contenedor de los módulos 3–8 y enlaces a Recopila, Recibos y Declara.
**Problemas / mejoras.** 14 pestañas con duplicados: «Control de obligaciones» y «Obligaciones Fiscales» renderizan el mismo `FiscalControl`; «Tareas Operativas» duplica `/tareas` (P4 #22). Conteos de documentos calculados con `state.documents` completo (P1 #1). Reagrupar en Panel, Directorio, Documentos, Obligaciones, Credenciales, Importar.

## 3. Dashboard integral

**Propósito.** Visión consolidada del despacho por periodo: alertas, certificados, documentos, trabajo por responsable, obligaciones; registro manual de opiniones de cumplimiento y revisiones CFDI; calidad de datos.

**Pantallas.** `IntegralDashboard.tsx` en 4 vistas: Dashboard general, Opiniones de cumplimiento, Seguimiento CFDI, Calidad de datos.

| Funcionalidad | Clasificación |
|---|---|
| Panel consolidado por periodo (alertas, certificados, documentos, responsables, obligaciones) | IMPLEMENTADA Y PROBADA — lento (~2,5 s, 92 consultas, tope 50 000 docs; P1 #5) |
| Registro de opinión de cumplimiento (autoridad, fecha, resultado, próxima revisión) | PARCIAL — captura manual; `official_query_performed: false` |
| Registro de revisión CFDI por periodo | PARCIAL — captura manual; `sat_validated: false` |
| Calidad de datos (`integral_quality_issues`) | IMPLEMENTADA Y PROBADA |
| Clasificación virtual por reglas de metadatos (analizar, revisar, decidir) | IMPLEMENTADA Y PROBADA — siempre requiere revisión humana |
| Comparar certificado contra CER público | IMPLEMENTADA Y PROBADA en backend; sin UI |
| Alta de categorías virtuales, actividad de empresa, verificación de obligación e historial | IMPLEMENTADA Y PROBADA en backend; sin UI identificada |

**Endpoints.** `/api/integral/dashboard`, `companies/{cid}/activity|documents|opinions|cfdi`, `classification/analyze|reviews|categories`, `classification/documents/{id}/decision`, `documents/{id}/history`, `obligations/{id}/verify|verifications`, `certificates/{id}/compare`, más los registrados por `fiscal_calendar` y `lote4_lifecycle` (ver módulos 5 y 6).
**Tablas.** `integral_audit`, `integral_cfdi_reviews`, `integral_company_activity`, `integral_compliance_verification`, `integral_opinions`, `integral_quality_issues`, `integral_settings`, `virtual_categories`, `virtual_document_metadata`, `virtual_evidence_relations`, `virtual_rules`.
**Servicios.** `integral_api.py`, `integral_dashboard.py`, `virtual_classifier.py`, `fiscal_read.py`.
**Pruebas.** `test_integral.py` (9).
**Dependencias.** Empresas, Obligaciones, Credenciales, CS-Storage.
**Problemas.** Rendimiento (P1 #5); `except Exception` silencioso en `integral_api.py:65` (P3 #18); etiqueta OpenAPI «Dashboard integral v0.3».

## 4. Control de obligaciones fiscales

**Propósito.** Matriz empresa × obligación × periodo con estado, responsable, evidencia de CS-Storage e historial de cambios.

**Pantallas.** `FiscalControl.tsx` («Control de obligaciones»: avance por obligación, distribución por régimen, seguimiento por responsable, vencimientos verificados, evidencias de CS-Storage); `FiscalSummary.tsx` (resumen e histórico fiscal por empresa); `fiscalRead.ts` (lectura y estado interno compartido).

| Funcionalidad | Clasificación |
|---|---|
| Matriz por periodo y edición de celda con historial | IMPLEMENTADA Y PROBADA |
| Vinculación de evidencias documentales | IMPLEMENTADA Y PROBADA |
| Estado interno de empresa (Sin pendientes / Requiere revisión / Crítico) | IMPLEMENTADA Y PROBADA (lectura) |
| Aplicabilidad por empresa y alta de obligaciones en catálogo | IMPLEMENTADA Y PROBADA en backend; sin UI de edición identificada |
| Importación de obligaciones desde Excel (`fiscal_import.py`, `fiscal_import_*`) | PARCIAL — sólo vista previa vía Importador; aplicación definitiva bloqueada |
| Cálculo automático de vencimientos según reglas SAT | NO IMPLEMENTADA (sólo fechas verificadas manualmente) |

**Endpoints.** `/api/fiscal-control` (GET), `cell` (PUT), `history/{record_id}`, `applicability` (PUT), `catalog` (POST).
**Tablas.** `fiscal_catalog`, `fiscal_applicability`, `fiscal_periods`, `fiscal_records`, `fiscal_evidence`, `fiscal_history`, `fiscal_import_batches`, `fiscal_import_rows`, `fiscal_verification_decisions`.
**Pruebas.** `test_fiscal_control.py` (5), parte de `test_integral.py`.
**Dependencias.** Empresas, usuarios (responsables), CS-Storage (evidencias).

## 5. Tareas y vencimientos / calendario fiscal

**Propósito.** Tareas operativas del despacho y calendario de fechas registradas (manuales o por regla verificada).

**Pantallas.** `/tareas` (`TasksAndDeadlines.tsx`): vista Tareas (`Records.tsx`, alta/edición/completar) y vista Calendario (`FiscalCalendar.tsx` + `CalendarManagement.tsx`: «Fechas manuales y reglas revisadas»).

| Funcionalidad | Clasificación |
|---|---|
| Tareas: alta, edición, completar, filtro | IMPLEMENTADA Y PROBADA (backend) |
| Obligaciones heredadas (`/api/obligations`, tabla `obligations`) | IMPLEMENTADA SIN VALIDACIÓN — sin UI propia; reemplazadas por Control de obligaciones |
| Calendario de fechas registradas | IMPLEMENTADA Y PROBADA |
| Fechas manuales con fecha civil y reglas versionadas con fuente | IMPLEMENTADA Y PROBADA (backend + `lote4.test.mjs`) |
| Recordatorios por correo / notificaciones | NO IMPLEMENTADA |

**Endpoints.** `/api/tasks`, `/api/tasks/{id}`, `/api/obligations`, `/api/obligations/{id}`, `/api/integral/calendar`, `/api/integral/calendar/management/{cid}`, `calendar/manual/{id}`, `calendar/rules/{id}/versions`, `lifecycle/{cid}/history`.
**Tablas.** `tasks`, `obligations`, `calendar_manual_dates`, `calendar_verified_rules`, `lote4_action_history`, `fiscal_records`.
**Pruebas.** `test_integral.py`, `test_api.py`; frontend `lote4.test.mjs` (3 casos).
**Problemas.** Dos modelos de «obligación» conviven (`obligations` heredada vs. `fiscal_records`); unificar en v1.1.

## 6. Credenciales y certificados + Centro de alertas

**Propósito.** Bóveda cifrada de accesos por empresa, certificados públicos (CER) con vigencia y alertas de vencimiento.

**Pantallas.** `Credentials.tsx`: «Credenciales y Certificados» (accesos disponibles, certificados públicos) y «Centro de Alertas»; `CertificateLifecycle.tsx` («Certificado actual y renovaciones»); `CompanyDashboard.tsx` («Expedientes y vigencia FIEL»).

| Funcionalidad | Clasificación |
|---|---|
| Guardar/editar/archivar secreto cifrado con control de revisión | IMPLEMENTADA Y PROBADA — requiere `CONTA_VAULT_KEYRING`; sin él responde 423 |
| Revelar secreto | PARCIAL — endpoint existe pero siempre devuelve 423 («deshabilitada hasta reautenticación reciente»); `reveal_enabled=false` |
| Registro de certificado público (CER X.509) con fechas, huella y serie | IMPLEMENTADA Y PROBADA (`authority_validated: false`) |
| Certificado actual y cadena de renovaciones | IMPLEMENTADA Y PROBADA |
| Alertas de vencimiento con umbrales (60/30/15 días), posponer/atender | IMPLEMENTADA Y PROBADA |
| Configuración de umbrales, servicios y permisos de bóveda | IMPLEMENTADA Y PROBADA en backend; sin UI identificada |
| Programación de evaluación de alertas (`alert_schedule.py`) | IMPLEMENTADA SIN VALIDACIÓN |
| Validación ante SAT / revocación | NO IMPLEMENTADA (las fechas del CER no validan) |
| Custodia de llave privada FIEL | Excluida por regla (no implementar) |

**Endpoints.** `/api/credentials/companies/{cid}` (GET), `secrets` (POST), `secrets/{id}/reveal` (POST→423), `secrets/{id}` (DELETE), `certificates` (POST), `certificates/{id}` (PUT), `history`, `permissions` (PUT), `/api/credentials/services`, `/api/credentials/alerts` (GET), `alerts/refresh`, `alerts/settings`; `/api/integral/certificates/{cid}/lifecycle`, `certificates/{cid}/current`, `alerts/{id}/lifecycle`.
**Tablas.** `vault_services`, `vault_grants`, `vault_credentials`, `vault_versions`, `vault_certificates`, `vault_audit`, `vault_alert_settings`, `vault_alerts`, `certificate_current_selection`, `certificate_renewals`, `alert_lifecycle`, `alert_evaluation_schedule`.
**Servicios.** `credential_api.py`, `credential_alerts.py` (se registra por efecto de importación), `credential_crypto.py`, `credential_import.py`, `lote4_lifecycle.py`, `lote4_summary.py`, `alert_query.py`.
**Pruebas.** `test_credentials.py` (10), `test_integral.py`.
**Dependencias.** Empresas, CS-Storage (CER como documento), usuarios.

## 7. CS-Storage / Centro documental

**Propósito.** Núcleo documental: subir, versionar, deduplicar, verificar integridad, clasificar con revisión humana, indexar fuentes locales y SMB de sólo lectura.

**Pantallas.** `Documents.tsx` (lista, detalle, vista previa, verificación, duplicados), `StorageReview.tsx` (revisión de clasificación), `StorageJobs.tsx` (trabajos de indexación), `DocumentReconciliation.tsx` («Conciliación documental»), `VirtualExplorer.tsx` («Explorador documental virtual»), `CompanyDashboard.tsx`, y en Configuración `StorageConnector.tsx` («Almacenamiento documental»: orígenes, prueba, últimos análisis).

| Funcionalidad | Clasificación |
|---|---|
| Subida de PDF/XML/CER validando contenido (máx. 25 MB); rechazo de llaves privadas | IMPLEMENTADA Y PROBADA |
| Versiones, ubicaciones, vínculos documento↔empresa, deduplicación por hash | IMPLEMENTADA Y PROBADA |
| Verificación de integridad y descarga/vista de contenido | IMPLEMENTADA Y PROBADA |
| Clasificación determinista (XML CFDI 3.3/4.0, RFC) con revisión humana y reapertura | IMPLEMENTADA Y PROBADA |
| Identidad CFDI (UUID) sin fusión automática; conflictos a revisión | IMPLEMENTADA Y PROBADA (`document_identity.py`) |
| Indexador con lease/checkpoint y trabajador | IMPLEMENTADA Y PROBADA |
| Fuente local y SMB (UNC de sólo lectura con identidad Windows) | IMPLEMENTADA Y PROBADA (SMB real sólo en Windows; 1 prueba omitida por privilegio de enlaces) |
| Conciliación documental y uso de certificado | IMPLEMENTADA Y PROBADA |
| Eliminación de documento | PARCIAL — sólo documentos heredados sin historial; gestionados → 409 |
| OCR / extracción de PDF | NO IMPLEMENTADA (`isolated_analyzer_required`) |

**Endpoints.** `/api/storage/dashboard`, `options`, `documents` (GET/POST), `documents/{id}` y `/verify`, `/content`, `/duplicates`, `/classify`, `/reviews`, `/reviews/{rid}`, `/reviews/{rid}/reopen`, `/certificate-usage`, `index-jobs` (GET/POST), `reconciliation`, `connector/options`, `connector/sources` (GET/POST/PUT), `connector/sources/{id}/probe`; heredados `/api/companies/{id}/documents`, `/api/documents/{id}/download`, `/api/documents/{id}` (DELETE).
**Tablas.** `documents`, `document_versions`, `document_locations`, `document_company_links`, `document_classification_reviews`, `document_cfdi_identities`, `storage_sources`, `storage_index_jobs`, `storage_worker_state`, `storage_events`.
**Servicios.** `storage/service.py`, `catalog.py`, `classifier.py`, `classify_process.py`, `indexer.py`, `worker.py`, `local.py`, `smb.py`, `connector.py`, `review.py`, `paths.py` (bloqueo de enlaces/junctions/nombres reservados), `internal.py`, `providers.py`, `settings.py`, `dashboard.py`, `migrate.py`.
**Pruebas.** `test_storage_core.py` (15), `test_storage_catalog.py` (11), `test_storage_indexer.py` (15), `test_storage_smb.py` (5), `test_storage_migrations.py` (5), `test_connector_dashboard.py` (10), `test_document_identity.py` (10).
**Dependencias.** Empresas y usuarios; alimenta Obligaciones (evidencias), Credenciales (CER), Dashboard integral e Importador.
**Problemas.** `/api/state` envía todos los documentos (P1 #1). Configuración de raíces vía `.env` (`CS_STORAGE_ALLOWED_ROOTS`, `CS_STORAGE_SMB_ALLOWED_ROOTS`).

## 8. Importar y conciliar (+ piloto local y análisis por lotes)

**Propósito.** Llevar información existente del despacho (Excel de obligaciones/metadatos fiscales, inventario documental, carpetas autorizadas) a propuestas revisables sin aplicar cambios automáticamente.

**Pantallas.** `CompanyImporter.tsx` («Importar y conciliar»), `PilotImport.tsx` («Importar empresas»: seleccionar carpetas autorizadas, resultado del piloto), `BatchPilot.tsx` («Primera carpeta · análisis por lotes»).

| Funcionalidad | Clasificación |
|---|---|
| Vista previa XLSX (obligaciones / metadatos fiscales) con diagnósticos, ≤8 MB | IMPLEMENTADA Y PROBADA |
| Propuestas de conciliación por inventario documental (≤500 docs) | IMPLEMENTADA Y PROBADA |
| Decisiones por fila (vincular, proponer alta, excluir, pendiente) auditadas | IMPLEMENTADA Y PROBADA |
| Informe de sesión, descarte y purga de sesiones expiradas | IMPLEMENTADA Y PROBADA (purga sin UI) |
| Confirmación definitiva (aplicar a empresas) | PARCIAL — bloqueada a propósito (423, `confirmation_enabled=false`) |
| Importación piloto desde carpetas autorizadas (`CS_LOCAL_IMPORT_*`) | PROTOTIPO operativo — probado; activo sólo con banderas de entorno |
| Análisis por lotes de la primera carpeta (`CS_BATCH_DATABASE`) | PROTOTIPO — sólo lectura de resultados |

**Endpoints.** `/api/company-imports/preview/xlsx`, `preview/inventory`, `{id}`, `{id}/rows/{n}`, `{id}/confirm` (→423), `{id}/report`, `{id}` (DELETE), `maintenance/expired`; `/api/pilot-imports` (`options`, lista, `preview`, `{id}`, `rows/{n}`, `confirm`); `/api/pilot-batches`, `{id}/rows`.
**Tablas.** `reconcile_sessions`, `reconcile_rows`, `reconcile_decisions`, `reconcile_history`, `company_import_aliases`, `company_import_permissions`; las del piloto usan base propia configurable.
**Servicios.** `company_import_api.py`, `company_xlsx.py`, `company_reconcile.py`, `pilot_import.py`, `pilot_scan.py`, `pilot_extract.py`, `pilot_batch.py`, `pilot_batch_extract.py`.
**Pruebas.** `test_company_import.py` (11), `test_xlsx_diagnostics.py` (5), `test_pilot_import.py` (14), `test_local_import.py` (4), `test_pilot_batch.py` (4).
**Dependencias.** Empresas, CS-Storage, usuarios.
**Restricciones vigentes.** No importar la segunda carpeta; no reanudar PRISMA en 8072; no fusionar por UUID/nombre/RFC.

## 9. Recopila

**Propósito.** Relacionar pólizas con sus comprobantes y preparar los PDF del recopilador. Motor original `recopila_engine.py` sin cambios; adaptador `recopila.py`.
**Pantalla.** `Recopila.tsx`: carga de entrada, «Revisión de pólizas», «Detalle de la póliza», «Archivos de salida», «Vista previa», descarga ZIP. Sólo administradores.

| Funcionalidad | Clasificación |
|---|---|
| Carga y análisis de entrada (copias subidas, originales intactos) | IMPLEMENTADA Y PROBADA |
| Generación de salidas, vista de archivo y descarga ZIP | IMPLEMENTADA Y PROBADA |
| Recuperación tras reinicio (marca `error` en `analyzing/generating`) | IMPLEMENTADA Y PROBADA |
| Ejecución directa sobre carpetas del servidor | NO IMPLEMENTADA (sólo copias subidas) |

**Endpoints.** `/api/recopila/runs` (GET/POST), `{id}`, `{id}/generate`, `{id}/file`, `{id}/zip`. **Tabla.** `recopila_runs`. **Pruebas.** `test_recopila.py` (3) — cobertura más baja de los motores.
**Problemas.** `except Exception` silenciosos en `recopila_engine.py` (263, 275) (P3 #18); el motor no se modifica, registrar el error en el adaptador.

## 10. CFDI (antes Organizador)

**Propósito.** Organizar Emitidos, Recibidos y reportes Excel por rutas de origen, RFC y ejercicio, fiel a `Organizar_CFDI.bat`. Motor `organizador_engine.py` sin cambios.
**Pantalla.** `Organizador.tsx`: análisis, «Meses», «Tipos y formatos», «Auditoría de archivos», «Detalle del archivo», generar y descargar. Sólo administradores.

| Funcionalidad | Clasificación |
|---|---|
| Análisis → plan → ejecución sobre copias verificadas | IMPLEMENTADA Y PROBADA |
| Auditoría por archivo y descarga | IMPLEMENTADA Y PROBADA |
| Clasificación por contenido XML | Excluida por diseño (sólo rutas del BAT) |
| Descarga masiva de CFDI del SAT | NO IMPLEMENTADA |

**Endpoints.** `/api/organizador/runs` (GET/POST), `{id}`, `{id}/generate`, `{id}/download`. **Tabla.** `organizador_runs`. **Pruebas.** `test_organizador.py` (6).

## 11. Declara

**Propósito.** Analizar declaraciones y acuses en PDF, revisar sus nombres propuestos y llevar el control mensual documental por empresa. Motor extraído de Declara v0.2.6 (`declara_engine.py`, regenerable con `scripts/extract_declara_engine.py`).
**Pantalla.** `Declara.tsx`: «Control mensual documental», «Revisión de declaraciones y acuses», «Detalle y resolución», vista previa por archivo, generación y descarga. Acceso desde expediente · Actividad · Declaraciones.

| Funcionalidad | Clasificación |
|---|---|
| Análisis de PDF y plan revisable de nombres | IMPLEMENTADA Y PROBADA |
| Resolución manual de casos y generación de copias renombradas | IMPLEMENTADA Y PROBADA |
| Vista previa y descarga | IMPLEMENTADA Y PROBADA |
| Sesión SAT remota / presentación de declaraciones | NO IMPLEMENTADA (excluida) |

**Endpoints.** `/api/declara/runs` (GET/POST), `{id}`, `{id}/resolve`, `{id}/generate`, `{id}/file/{index}`, `{id}/download`. **Tabla.** `declara_runs`. **Pruebas.** `test_declara.py` (10).

## 12. Recibos

**Propósito.** Emitir recibos de servicios contables con folio y PDF (membrete `assets/membrete.png`), conservar historial. Motor `receipt_engine.py`.
**Pantalla.** `Receipts.tsx`: «Lote de emisión», «Recibos emitidos», «Documentos listos», «Vista previa», catálogo de clientes, configuración, aviso de duplicados.

| Funcionalidad | Clasificación |
|---|---|
| Emisión con folio consecutivo (`receipt_counters`) y PDF | IMPLEMENTADA Y PROBADA |
| Clientes de recibos (alta/baja), configuración | IMPLEMENTADA Y PROBADA |
| Detección de duplicados | IMPLEMENTADA Y PROBADA |
| Historial y descarga de PDF | IMPLEMENTADA Y PROBADA |
| Exportación (`POST /api/receipts/export`) y vista previa de servidor | IMPLEMENTADA Y PROBADA en backend; sin llamada desde la UI |
| Envío por correo / timbrado CFDI de ingresos | NO IMPLEMENTADA |

**Endpoints.** `/api/receipts` (GET/POST), `{id}/pdf`, `clients` (GET/POST/DELETE), `settings` (GET/PUT), `preview`, `duplicates`, `export`. **Tablas.** `receipts`, `receipt_counters`, `receipt_clients`, `settings`. **Servicios.** `receipts.py`, `receipt_engine.py`, `receipt_migration.py`. **Pruebas.** `test_receipts.py` (9).

## 13. Agente Windows

**Propósito.** Proceso local que lista nombres y tamaños de PDF/XML/CER en carpetas autorizadas y reporta al servidor.
**UI.** Indicador «Agente conectado/desconectado» en la barra superior; «Analizar carpeta» y «Análisis recientes» en el expediente; lista de agentes en Configuración.

| Funcionalidad | Clasificación |
|---|---|
| Heartbeat y capacidades (`scan_folder`), token `AGENT_TOKEN` | IMPLEMENTADA Y PROBADA |
| Reclamación atómica de trabajos y entrega de resultado (≤2 MB) | IMPLEMENTADA Y PROBADA — sin expiración de `running` (P1 #3) |
| Inventario seguro `safe_inventory` con `SECRET_PATTERNS` (ruta `run()`) | IMPLEMENTADA Y PROBADA |
| Ruta antigua `main()`/`scan_folder` que incluye `.key` | Defecto P1 #4 (debe delegar en `run()`) |
| Servicio Windows registrado en SCM | PARCIAL (WinError 5; P5 #25) |
| Importar al catálogo a partir del análisis del agente | NO IMPLEMENTADA (el análisis no importa por sí solo) |

**Endpoints.** `/api/jobs`, `/api/agent/heartbeat`, `/api/agent/{id}/claim`, `/api/agent/jobs/{id}/result`. **Tablas.** `agents`, `jobs`. **Código.** `agent/agent.py`, `agent/adapters.py`, `scripts/managed_agent.py`, `windows_service.py`, `service_admin.py`. **Pruebas.** `test_managed_windows_agent.py` (3), `test_api.py`, `scripts/test_agent_package.py`.

## 14. Configuración

**Pantalla.** `/configuracion`: «Preferencias del despacho» (nombre mostrado, apariencia claro/oscuro/alto contraste — guardado en el navegador), «Estado de servicios» (base de datos, API, Consulta SAT y OCR «Pendiente de integrar», agentes locales), `StorageConnector` (sólo admin), `AccountSecurity`, y un desplegable «Ver propuesta visual original de Stitch».

| Funcionalidad | Clasificación |
|---|---|
| Preferencias locales (nombre, tema) | IMPLEMENTADA SIN VALIDACIÓN |
| Estado de servicios | IMPLEMENTADA SIN VALIDACIÓN (la API se muestra «Conectada» de forma fija) |
| Vista Stitch de Configuración (`designs/configuracion.json`) | PROTOTIPO — datos de ejemplo; retirar (P4 #23) |

## 15. Infraestructura y operación (no visible en la UI)

| Elemento | Clasificación |
|---|---|
| Verificación de esquema al arrancar (`schema_compatibility.py`), sin migrar ni sembrar | IMPLEMENTADA Y PROBADA |
| Migraciones: Alembic 0001–0005 + 6 cadenas propias (`company_`, `credential_`, `fiscal_`, `import_`, `integral_`, `lote4_migrations`) vía `scripts/schema_admin.py` | IMPLEMENTADA Y PROBADA; unificación en curso (`0006_unified_baseline`, sin confirmar) |
| Respaldo/restauración PostgreSQL (`backup_postgres.py`, `restore_postgres.py`, `maintenance_backup.py`) | IMPLEMENTADA SIN VALIDACIÓN automatizada; respaldo externo programado pendiente (P5 #27) |
| Instalador local y paquete de versión (`install_release.py`, `package_*`, `local_install.py`) | IMPLEMENTADA (prueba en `test_release_runtime.py`, `scripts/test_local_installer.py`) |
| HTTPS en LAN, servicio Windows, aceptación de usuarios | NO IMPLEMENTADA en equipo definitivo (Prioridad 5) |

---

## 5 bis. Elementos visuales con datos de demostración (consolidado)

| Elemento | Ubicación | Acción sugerida |
|---|---|---|
| Semilla DEMO: 3 empresas ficticias con tareas y «Declaración mensual · DEMO» | `main.py` `seed_examples` + `POST /api/demo`; botón «Cargar ejemplo DEMO» en directorio vacío | Ocultar en producción o mover a herramienta de laboratorio |
| Insignias «DEMO» / «EMPRESA DEMO» (`is_demo`) | Directorio y expediente | Mantener mientras exista la semilla |
| Columna «Opinión 32-D: Sin consultar» fija | Directorio de empresas | Alimentar desde `integral_opinions` o retirar |
| Vista «Resumen Ejecutivo» (KPIs, carga de trabajo) inalcanzable | `Companies.tsx` | Eliminar o reintegrar en el Dashboard general |
| Vista previa Stitch de Configuración | `/configuracion` (desplegable) | Retirar (P4 #23) |
| JSON Stitch no enrutados: `recibos`, `recopilador-cfdi`, `organizador-cfdi`, `relacionador`, `renombrador` (~245 KB) | `frontend/src/designs/` vía `import.meta.glob` (chunks diferidos) | Mover a `design-source/`; relacionador y renombrador no son módulos vigentes |
| «Workspace Fiscal», «ContaSuite v1.0 RC1», marcador de nombre de ejemplo en Configuración | `App.tsx` | Tomar versión de `/api/health`; textos configurables |

## 7 bis. Integraciones reales y simuladas (consolidado)

| Integración | Estado |
|---|---|
| PostgreSQL (producción) / SQLite (pruebas) | Real. Bloqueos advisory sólo efectivos en PostgreSQL (P3 #19). |
| Sistema de archivos local con validación de rutas | Real |
| Recursos SMB (UNC sólo lectura, identidad Windows) | Real, sólo Windows |
| Agente Windows (HTTP con token) | Real |
| Cifrado de bóveda (`CONTA_VAULT_KEYRING`) | Real; revelación deshabilitada |
| Lectura X.509 de CER, XLSX, XML CFDI | Real (análisis local, sin consulta externa) |
| Generación de PDF (Recibos) y ZIP (Recopila, CFDI, Declara) | Real |
| SAT: opinión 32-D, validación CFDI, vigencia/revocación de certificados, descarga masiva | **Simulada por captura manual** (`official_query_performed`, `sat_validated`, `authority_validated` = `false`) o no implementada |
| OCR / extracción de PDF | No implementada |
| Correo, notificaciones, DIOT, timbrado | No implementadas |

## 8. Pruebas automatizadas disponibles y resultados

**Backend** (`cd backend && python -m pytest -q`, aislado): 27 archivos `test_*.py`, 211 funciones de prueba (más casos parametrizados). Scripts aislados adicionales fuera de pytest: `run_lote1_isolated.py`, `run_lote2_isolated.py`, `run_lote3_classifier.py`, `run_lote4_*`, `run_recovery_isolated.py`, `verify_live_agent.py` (requieren PostgreSQL/Windows; P3 #16).

Resultado de esta ejecución (13/11/2026, árbol de trabajo actual incluida la `0006` sin confirmar): **220 aprobadas, 1 omitida, 0 fallidas** en 137 s. Omitida: `test_api.py:126` (Windows no permite crear enlaces simbólicos sin privilegios). 185 advertencias, en su mayoría `SAWarning` de `schema_compatibility.py:31-32` por el índice de expresión `uq_fiscal_catalog_name` (no reflejable en SQLite; conviene revisar que la verificación de esquema no lo ignore en PostgreSQL).

| Archivo | Pruebas | Módulo |
|---|---:|---|
| test_accounts.py | 20 | Cuentas |
| test_api.py | 9 | Núcleo / empresas / agente |
| test_bootstrap.py | 5 | Arranque |
| test_company_import.py | 11 | Importar y conciliar |
| test_connector_dashboard.py | 10 | CS-Storage conector |
| test_credentials.py | 10 | Credenciales |
| test_declara.py | 10 | Declara |
| test_document_identity.py | 10 | Identidad CFDI |
| test_fiscal_control.py | 5 | Obligaciones |
| test_integral.py | 9 | Dashboard integral / calendario / ciclo de vida |
| test_local_import.py | 4 | Importación local |
| test_managed_windows_agent.py | 3 | Agente |
| test_organizador.py | 6 | CFDI |
| test_pilot_batch.py | 4 | Lotes |
| test_pilot_import.py | 14 | Piloto |
| test_rc1_operations.py | 4 | Operación RC1 |
| test_receipts.py | 9 | Recibos |
| test_recopila.py | 3 | Recopila |
| test_release_runtime.py | 2 | Versión/instalador |
| test_storage_catalog.py | 11 | CS-Storage |
| test_storage_core.py | 15 | CS-Storage |
| test_storage_indexer.py | 15 | CS-Storage |
| test_storage_migrations.py | 5 | Migraciones |
| test_storage_smb.py | 5 | SMB |
| test_unified_baseline.py | 4 | Baseline Alembic (en curso, sin confirmar) |
| test_visit_readiness.py | 3 | Preparación de instalación |
| test_xlsx_diagnostics.py | 5 | Importador XLSX |

**Frontend.** `frontend/tests/lote2.test.mjs` (5 casos: navegación de expediente, borradores, archivo) y `lote4.test.mjs` (3 casos: fechas manuales y reglas). Sin E2E. **No se pudieron ejecutar** ni la compilación (`npm run build`) ni estas pruebas: este equipo no tiene Node.js. Última compilación correcta conocida: RC1, 12/11/2026 (advertencia de chunk >500 KB).

**Huecos de cobertura.** UI completa (sin E2E: P3 #15), Inicio y Configuración, respaldo/restauración, exportaciones CSV, Recopila (sólo 3 pruebas), rendimiento del dashboard con volumen real.

## 9. Mapa de dependencias entre módulos

```
Cuentas/seguridad ──► todos los routers (Principal, ámbito por empresa)
Empresas ──► Dashboard integral, Obligaciones, Tareas, Credenciales, CS-Storage, Importador, Recibos (?empresa=), Recopila (?empresa=), Declara (?empresa=)
CS-Storage ──► Obligaciones (evidencias) · Credenciales (CER) · Dashboard integral (documentos, calidad) · Importador (inventario) · Explorador virtual
Obligaciones (fiscal_records) ──► Calendario · Dashboard integral · Estado interno de empresas · Alertas (lote4)
Credenciales ──► Alertas · Ciclo de vida de certificados · Dashboard integral
Agente Windows ──► Empresas (carpeta) · /api/state (indicador)
Recopila, CFDI, Declara, Recibos ──► independientes entre sí; sólo requieren cuentas (admin) y, opcionalmente, empresa
```

## 10. Problemas conocidos y mejoras recomendadas (consolidado)

Los de Prioridad 1–5 del plan siguen vigentes; se listan con lo detectado en este inventario.

| # | Problema | Origen | Módulo |
|---|---|---|---|
| 1 | `/api/state` devuelve todos los documentos y se consulta cada 10 s | Plan P1 #1 (confirmado en `App.tsx:31`) | Plataforma |
| 2 | `security_events` sin retención | Plan P1 #2 | Cuentas |
| 3 | Trabajos de agente atascados en `running` | Plan P1 #3 (confirmado en `main.py` `claim`) | Agente |
| 4 | Doble ruta del agente; `SUPPORTED` incluye `.key` | Plan P1 #4 (confirmado `agent/agent.py:13`) | Agente |
| 5 | Dashboard integral lento | Plan P1 #5 | Dashboard |
| 6 | Puertos incoherentes 8000/8062 | Plan P1 #6 | Operación |
| 7 | 14 pestañas con duplicados y código muerto «Resumen Ejecutivo» | Plan P4 #22 + inventario | Empresas |
| 8 | Endpoints sin UI: comparar certificado, categorías virtuales, aplicabilidad/catálogo fiscal, umbrales de alertas, permisos/servicios de bóveda, verificación de obligaciones, export de recibos, purga de sesiones de importación | Inventario | Varios |
| 9 | Dos modelos de obligación (`obligations` heredada vs. `fiscal_records`) | Inventario | Tareas/Obligaciones |
| 10 | Columna 32-D fija aunque existen opiniones registradas | Inventario | Empresas/Dashboard |
| 11 | JSON de Stitch no enrutados dentro de `src/` | Inventario | Frontend |
| 12 | `credential_alerts` se registra por efecto secundario de importación | Inventario | Credenciales |
| 13 | Botón de tema superior no ofrece alto contraste | Inventario | Shell |
| 14 | Formato/linters, bundle >500 KB sin `React.lazy`, `except Exception` silenciosos | Plan P3 #12–14, #18 | Calidad |
| 15 | Sin E2E; Node.js ausente en este equipo | Plan P3 #15 + inventario | Pruebas |

---

# Parte 2 · Propuestas para versiones futuras

Principio común: cada versión continúa el código existente, conserva el diseño Stitch y los motores originales, y no presenta como activa ninguna integración no implementada. Las propuestas son de planeación; requieren aprobación antes de iniciarse y no forman parte de la estabilización v1.0.

## v1.1 — Consolidación posterior a la aceptación (UX y deuda inmediata)

Objetivo: que lo que ya existe sea completo y coherente, sin nuevas integraciones externas.

| Propuesta | Componentes reutilizables |
|---|---|
| Empresas en 5–6 secciones; retirar «Resumen Ejecutivo», duplicados y vista Stitch | `Companies.tsx`, `IntegralDashboard.tsx`, `companyNavigation.ts`, `lote2.test.mjs` |
| Columna 32-D alimentada por la última opinión registrada | `integral_opinions`, `/api/integral/dashboard` |
| UI de administración para lo que ya tiene backend: aplicabilidad y catálogo fiscal, umbrales de alertas, servicios/permisos de bóveda, categorías virtuales, comparar certificado | `fiscal_control.py`, `credential_alerts.py`, `credential_api.py`, `integral_api.py`, `components/stitch.ts` |
| Unificar `obligations` heredada en `fiscal_records` (migración explícita con respaldo) | `fiscal_control.py`, `Records.tsx`, baseline Alembic 0006 |
| Preferencias de usuario en servidor (nombre, tema) | `user_accounts`, `AccountSecurity.tsx` |
| E2E Playwright base (login, empresas, expediente, documento) | `.qa/smoke.cjs` como referencia (sin datos), `frontend/tests` |

## v1.2 — Importación definitiva y operación documental

Objetivo: cerrar los flujos que hoy terminan en «vista previa».

| Propuesta | Componentes reutilizables |
|---|---|
| Habilitar la confirmación del Importador (alta/vínculo de empresas, alias, obligaciones desde Excel) con respaldo previo y reversión por sesión | `company_import_api.py` (sesiones, decisiones, auditoría ya existentes), `company_xlsx.py`, `fiscal_import.py`, `reconcile_*` |
| Importar al catálogo documental desde el análisis del agente, con revisión humana | `agent/agent.py` (`safe_inventory`), `jobs`, `storage/indexer.py`, `review.py` |
| Promover el piloto local a flujo soportado (sin banderas de entorno) tras resolver conflictos UUID en revisión | `pilot_import.py`, `pilot_scan.py`, `document_identity.py`, `PilotImport.tsx` |
| Exportaciones: ZIP de recibos desde la UI, informe de sesión de importación | `POST /api/receipts/export`, `/company-imports/{id}/report` |
| Programar evaluación de alertas y purga de sesiones expiradas desde el mantenimiento | `alert_schedule.py`, `maintenance/expired`, `scripts/maintenance_backup.py` |

## v1.3 — Notificaciones, reportes y productividad del despacho

| Propuesta | Componentes reutilizables |
|---|---|
| Notificaciones internas y por correo (vencimientos, certificados, tareas) — opt-in, sin datos sensibles en el cuerpo | `vault_alerts`, `alert_lifecycle`, `calendar_*`, `tasks` |
| Reportes por periodo (cumplimiento interno, carga por responsable, documentos por empresa) en CSV/PDF | `fiscal_read.py`, `exportFiscal`, `receipt_engine.py` (generación PDF) |
| Bitácora unificada por empresa (fusionar `audit_events`, `integral_audit`, `vault_audit`, `lote4_action_history` en una vista) | `Dossier.tsx` · Historial, tablas de auditoría existentes |
| Recibos: envío por correo y plantillas por cliente | `receipts.py`, `receipt_clients`, `settings` |
| Tablero por responsable / carga de trabajo (retomar lo útil de «Resumen Ejecutivo» con datos reales) | `IntegralDashboard.tsx`, `user_accounts` |

## v1.5 — Análisis documental asistido (sin consulta SAT)

| Propuesta | Componentes reutilizables |
|---|---|
| Analizador aislado de PDF (proceso separado con límites) para extraer texto de acuses y declaraciones; OCR opcional | Contrato `virtual_classifier.analyze_public` (`isolated_analyzer_required`), `storage/classify_process.py` |
| Declara integrado con CS-Storage: tomar PDF del catálogo en lugar de subirlos y vincular acuses a `fiscal_records` como evidencia | `declara.py`, `fiscal_evidence`, `document_company_links` |
| CFDI/Recopila sobre documentos del catálogo (sin re-subir), conservando originales | `organizador.py`, `recopila.py`, `storage/service.py` |
| Reglas de clasificación virtual editables y métricas de precisión con revisión humana | `virtual_rules`, `virtual_categories`, `VirtualExplorer.tsx`, `StorageReview.tsx` |
| Conciliación CFDI: emitidos/recibidos vs. obligaciones del periodo (interna) | `document_cfdi_identities`, `storage/classifier.py`, `integral_cfdi_reviews` |

## v2.0 — Integraciones externas y plataforma

Requiere decisiones de seguridad y legales previas; nada de esto debe aparecer como activo antes de existir.

| Propuesta | Componentes reutilizables | Condiciones |
|---|---|---|
| Consulta/descarga SAT (CFDI masiva, opinión 32-D, validación CFDI y estado de certificados) | Campos `official_query_performed`, `sat_validated`, `authority_validated` ya modelados; `integral_opinions`, `integral_cfdi_reviews`, `vault_certificates` | Sin custodia de llave privada FIEL en servidor; firma en el equipo del usuario (agente) |
| Revelación de secretos con reautenticación reciente y proveedor de claves (DPAPI/HSM) | `credential_crypto.py`, endpoint `reveal` (hoy 423), `vault_audit` | Revisión de seguridad dedicada |
| Agente Windows como servicio con capacidades ampliadas (firma local, sincronización de carpetas) | `agent/adapters.py` (`Engine` protocol), `jobs`, `windows_service.py` | SCM y recuperación resueltos (P5 #25) |
| DIOT y otros motores fiscales como módulos independientes | Patrón adaptador + motor intacto (`recopila`, `organizador`, `declara`) | Motor validado por separado |
| Multi-despacho / multi-sede, API documentada para terceros, portal de clientes de sólo lectura | `Principal`, `user_company_grants`, `company_archive_*`, OpenAPI de FastAPI | Aislamiento por inquilino y auditoría |
| Despliegue en contenedores / nube privada | `compose.yaml`, `deploy/`, baseline Alembic única | PostgreSQL obligatorio; HTTPS |

## Componentes base que conviene preservar en todas las versiones

- Seguridad: `security.py`, `accounts.py`, `storage/paths.py`, middleware de auditoría (con retención).
- Patrón motor original + adaptador web + `*_runs` con recuperación tras reinicio.
- Control de revisión optimista (`revision`) y auditoría en cada escritura.
- Propuestas revisables con decisiones humanas (Importador, clasificación, identidad CFDI) en lugar de fusiones automáticas.
- Sistema visual Stitch: `components/stitch.ts`, `.stitch-live-module`, `OriginalIcon.tsx`, temas y `prefers-reduced-motion`.
