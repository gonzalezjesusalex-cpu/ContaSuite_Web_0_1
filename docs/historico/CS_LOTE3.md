# Estado CS-RELEASE-CLOSURE-001 · 11/11/2026

UUID declarado y SHA-256 se conservan por versión en integral_0003_document_identity. Carga/observación XML detectan conflictos antes de clasificar; no hay fusiones. Se reutilizan revisiones/vínculos, motivo y decisión humana auditada, cola administrativa paginada y suspensión fiscal sin borrar historial. Resolver el vínculo exige verificación fiscal posterior. Clasificación virtual no puede eludir la revisión de identidad. Pruebas sintéticas unitarias, HTTP, PostgreSQL y corrección visual ejecutadas; consultar CS_RELEASE_CLOSURE.md para resultados actuales.

CA-09/11/12/14: historial/versionado, suspensión y lectura/hash ahora probados dentro del alcance XML. CA-03/04/16/19/20: vínculos independientes, conflictos, permisos, cola e idempotencia probados parcialmente. CA-02: asociación dual automática sigue deshabilitada; se conserva revisión humana. Explorador/formularios existentes, interpretación PDF/CER compleja, inventario histórico total, disponibilidad remota y aceptación integral siguen parciales. No convertir estos ensayos en validación SAT o cierre completo del lote.

Los informes anteriores se conservan debajo. Respaldo y reversión actuales: CS_RELEASE_CLOSURE.md e inventario CS_RELEASE_CLOSURE_FILES.md.

---

# Actualización CS-INTEGRATION-RECOVERY-001 · 11/11/2026

El bloqueo de sobrescritura de verificaciones se corrigió con historial aditivo versionado, lectura/hash, proyección actual compatible y migración integral_0002 explícita. Se comprobaron repetición/corrección, cambio de versión, dos revisiones por HTTP, concurrencia PostgreSQL y conservación de historial. La integración de alertas y contador de evidencia utiliza este contrato, sin cambiar el cumplimiento declarado. No se reconstruyen decisiones antiguas ya perdidas.

Lote 3 continúa parcial: identidad UUID, contenido contradictorio, conciliación y asociación dual automática, bandeja integral y QA completa no se declaran resueltos. El resto de este documento es antecedente; matriz actual de integración, respaldo y pruebas en CS_INTEGRATION_RECOVERY.md.

---

# CS-LOTE3-IMPLEMENTATION-001 — avance parcial y parada por integridad

11 de noviembre de 2026. **Lote 3 NO completado. No se declara demo aprobada.**

## Inspección y contratos reales

Se leyeron AGENTS.md, CONTINUAR_EN_CODEX.md y docs/CS_LOTE2.md. Se inspeccionaron clasificador, indexador, servicio, revisión, catálogo, explorador y verificación integral. La carpeta corresponde al proyecto integrado; la ausencia de Git continúa. El esquema de archivado sigue pendiente de aplicación autorizada; no se consultó ninguna base para verificar estado operativo.

- `storage/classifier.py`: XML con defusedxml, RFC por emisor/receptor; antes un diccionario descartaba silenciosamente identidades repetidas. Clasificación es heurística estructural, no validación XSD ni SAT.
- `storage/review.py`: propuestas vinculadas a versión, resolución humana, relaciones `DocumentCompanyLink` por papel; la clasificación automática requiere administrador y preserva una resolución humana previa para la misma versión. No se ejecutaron pruebas de integración de este flujo en esta intervención.
- `storage/service.py`: versiones y ubicaciones existentes, contenido SHA-256, actualización conservadora de disponibilidad; cambios de bytes crean versión y eliminan vínculos automáticos anteriores. La continuidad depende de ubicación previa; no queda acreditada una política completa contra sustituciones de identidad CFDI.
- `storage/indexer.py`: extracción por proceso aislado, revisión e idempotencia por versión/catálogo; fallos de recorrido no implican eliminación automática. No se ejecutó indexador.
- `storage/catalog.py`: ámbito documental por empresa y clasificación; los documentos con versión nueva pendiente pueden quedar ocultos a usuarios no administradores. Cambiar esa política requiere pruebas de aislamiento antes de habilitar edición offline de versiones nuevas.
- `integral_models.py`: catálogo virtual existente de 16 categorías; se conserva. `virtual_evidence_relations` guarda versión y destino; `fiscal_evidence` solo documento/rol, sin versión exacta. No son equivalentes.
- `integral_api.verify`: la tabla `integral_compliance_verification` tiene PK por registro; al verificar de nuevo ejecuta UPDATE sobre la fila. El evento de auditoría no guarda una instantánea íntegra de los valores sustituidos. La función no acredita lectura del contenido como requisito de verificación.
- `fiscal_read.py`: revisión fiscal y versión documental vigentes son necesarias para contar verificación; no aporta por sí solo historial inmutable ni prueba de disponibilidad.
- `VirtualExplorer.tsx`: explorador por empresa, categorías, búsqueda, filtros y vistas original/organizada existentes; revisión administrativa. No contiene una bandeja unificada que satisfaga todos los tipos de incidencia de este lote.

## Bloqueos y criterio de parada

**Evidencias / CA-12:** la fila actual de verificación se sobrescribe. No se puede afirmar que todas las decisiones anteriores sean recuperables del contrato existente. No se modificó ni sustituyó ese flujo. La preservación histórica exige diseñar y ensayar una extensión aditiva explícita y una transición conservadora; no basta con habilitar una nueva verificación. Nunca se intentó recuperar datos reales.

**Asociación automática dual / UUID:** el clasificador no tiene un contrato persistido de identidad UUID y detección de contenido contradictorio entre documentos. Habilitar nuevas asociaciones automáticas compartidas sin esa comprobación ampliaría exposición de contenido. Se conservaron las propuestas de ambos papeles, pero no se habilitó la asociación automática a múltiples empresas. Ese flujo continúa requiriendo revisión.

Se detuvieron las partes afectadas de 3.1 y las fases dependientes 3.2–3.4; no se presenta el avance como implementación integral. Quedan pendientes parser CER integrado, conflictos UUID, clasificación versionada completa, historial de verificación, comprobación de contenido, bandeja unificada e integración de disponibilidad/permisos/archivado. Ninguno de estos puntos exige acceso a datos reales: deben resolverse y ensayarse con contratos y fixtures sintéticos en la continuación del mismo lote.

## Cambios independientes implementados

1. RFC emisor/receptor y catálogo normalizados exactamente por espacios y mayúsculas. Identidades de catálogo ambiguas impiden asociación automática; no se elige arbitrariamente una empresa.
2. Papeles issuer/receiver conservados y propuestas deduplicadas por empresa/papel.
3. `.key` excluido antes de hacer seek o leer el stream.
4. Resultado explícito `authority_validated=false`; no se afirma validación SAT.
5. Pruebas puras nuevas, sin importar aplicación/configuración/base/proveedores.

No se alteraron relaciones, versiones, documentos, permisos ni verificación existentes. No se habilitó asociación dual automática. No se creó catálogo nuevo.

## Matriz de aceptación

`Parcial` no significa criterio aprobado. Inspección estática no equivale a prueba ejecutada.

| Caso | Estado | Evidencia / pendiente |
|---|---|---|
| CA-01 | Pendiente | Explorador existente inspeccionado; sin prueba UI/ubicaciones |
| CA-02 | Parcial | test_two_registered_roles verifica propuesta dual; automático permanece deshabilitado |
| CA-03 | Pendiente | Papeles probados; autorización independiente documental no probada |
| CA-04 | Parcial | test_ambiguous_identity, test_malformed_no_automatic, test_repeated_role_requires_review; bandeja pendiente |
| CA-05 | Pendiente | Precedencia humana inspeccionada en review.py, sin prueba nueva |
| CA-06 | Pendiente | duplicates existente; agrupación visual/ubicaciones sin implementar |
| CA-07 | Pendiente | No se introducen fusiones; continuidad completa no probada |
| CA-08 | Pendiente | Versiones existentes inspeccionadas, sin ensayo de reevaluación |
| CA-09 | Bloqueado | Falta unificar documento/versión exacta y transición de evidencias |
| CA-10 | Parcial | authority_validated=false probado; integración de decisión fiscal pendiente |
| CA-11 | Bloqueado | Suspensión histórica y revisión pendiente requieren contrato conservador |
| CA-12 | Bloqueado | Verificación actual sobrescribe fila; no se alteró |
| CA-13 | Pendiente | Catálogo existente no se abrió contra servicios; sin prueba offline nueva |
| CA-14 | Bloqueado | Verificación no exige aún lectura comprobada; no se habilitaron cambios nuevos |
| CA-15 | Pendiente | Sin proveedor simulado/ensayo de errores nuevos |
| CA-16 | Parcial | 27 regresiones fiscales/Empresas pasan; no acreditan aislamiento documental del Lote 3 |
| CA-17 | Pendiente | Advertencias documentales no implementadas; esquema de archivo no activado |
| CA-18 | Parcial | No se ejecutan escrituras documentales; conservación nueva sin prueba integral |
| CA-19 | Pendiente | Bandeja unificada no implementada |
| CA-20 | Pendiente | Idempotencia/resolución integral no ensayadas |

## Pruebas ejecutadas ahora

- 7 pruebas puras de clasificación aprobadas: dos papeles como propuesta, una empresa registrada automática, identidad ambigua, XML malformado, exclusión KEY sin acceso, RFC normalizado y papel repetido. Última ejecución posterior a conservar la barrera multiempresa.
- 27 regresiones backend del Lote 2 aprobadas, incluyen las 17 fiscales. Ejecutor aislado existente: SQLite en memoria, dotenv bloqueado, red/procesos bloqueados, sin migraciones. No son pruebas CA completas del Lote 3.
- TypeScript sin emisión aprobado. Ningún archivo frontend cambió.
- No pruebas HTTP, visuales, PostgreSQL, proveedores SMB simulados ni suite histórica con fixtures de migración. Cero pruebas ejecutadas fallidas; los criterios pendientes/bloqueados no se contabilizan como aprobados.

Comandos desde la carpeta del proyecto:

    .venv/Scripts/python.exe -B backend/tests/run_lote3_classifier.py
    .venv/Scripts/python.exe -B backend/tests/run_lote2_isolated.py --snapshot ../RESPALDOS/CS_LOTE2_20261111_144333/antes_lote2.zip
    node frontend/node_modules/typescript/bin/tsc --noEmit -p frontend/tsconfig.json

## Inventario y recuperación

Modificado: `backend/app/storage/classifier.py`.

Añadidos: `backend/tests/run_lote3_classifier.py`, `docs/CS_LOTE3.md`.

Respaldo verificado: `../RESPALDOS/CS_LOTE3_20261111/antes_lote3.zip`; baseline.json contiene huellas. changes.json/final.json y lote3.diff registran diferencias e inventario final.

Recuperación: preservar primero trabajos posteriores; restaurar únicamente classifier.py desde el ZIP y verificar su huella contra baseline.json. Retirar los dos añadidos solo después de comprobar sus huellas finales y conservar cambios posteriores. No superponer directorios ni tocar configuración, datos o documentos. No se ejecutó reversión.

## Migraciones y seguridad

Ninguna migración nueva preparada ni ejecutada. Se requiere una propuesta adicional de historial de verificación y contrato UUID antes de continuar las partes bloqueadas; este informe no presenta una migración improvisada como solución validada.

No se accedió a `.env`, `data/`, secretos, credenciales, llaves privadas ni documentos reales. No se conectó a SMB/SAT/servicios fiscales, no se inició la aplicación, no hubo compilación, despliegue ni modificación de frontend/dist. Lotes 4 y 5 no iniciados. Se entrega avance parcial seguro, no cierre del Lote 3.
