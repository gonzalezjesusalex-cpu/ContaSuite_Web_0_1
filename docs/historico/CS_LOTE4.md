# Actualización de cierre CS-RELEASE-CLOSURE-001 · 11/11/2026

Se regresionaron certificados, alertas, calendario y archivo con el nuevo contrato de identidad. Conflictos UUID/versiones suspenden verificación y alimentan las revisiones/alertas existentes sin alterar cumplimiento declarado. Formularios comparten ajustes Stitch y accesibilidad. CA4-02/08 avanzan en XML versionado; no equivalen a conciliación completa de todo formato. CA4-13/14/23 tienen comprobaciones visuales adicionales; aceptación exhaustiva pendiente. CA4-24 incorpora nuevas pruebas PostgreSQL/HTTP/concurrencia; SCM y TLS/LAN siguen bloqueados/no comprobados.

La matriz anterior sigue como antecedente; matriz final de aceptación, respaldo, inventario, pruebas y límites actuales en CS_RELEASE_CLOSURE.md y CS_RELEASE_CLOSURE_FILES.md. Lote 4 y ContaSuite v1.0 no se declaran terminados.

---

# Estado vigente CS-INTEGRATION-RECOVERY-001 · 11/11/2026

Se continúa el código existente. Cinco defectos corregidos; historial de evidencia integrado, alertas independientes/paginadas, cuadrícula real y contador de evidencia. Aplicación original compilada y ejecutada con PostgreSQL nuevo sintético. **Lote 4 no completamente validado.** Los informes anteriores se conservan como historia.

Respaldo previo verificable: ../RESPALDOS/CS_INTEGRATION_RECOVERY_20261111/before.zip y baseline.json. Inventario exacto actual: CS_INTEGRATION_RECOVERY_FILES.md, changes.json/final.json/integration.diff junto al respaldo. Implementación, pruebas fallidas/repetidas, migraciones, recuperación y riesgos: CS_INTEGRATION_RECOVERY.md.

Migraciones company_archive_0001, lote4_lifecycle_0001, lote4_schedule_0002 e integral_0002 aplicadas sólo en PostgreSQL sintético nuevo y copias sintéticas restauradas. Ninguna migración empresarial ejecutada. Concurrencia real comprobada entre conexiones (8 evaluadores, 6 verificaciones, 2 selecciones). Los pendientes documentales UUID/conciliación siguen abiertos; el historial de verificación y las alertas manuales versionadas sí tienen contrato comprobado.

## Matriz CA4-01 a CA4-24 vigente

| Caso | Estado | Evidencia y límites |
|---|---|---|
| CA4-01 | Parcial | Parser público regresionado en pytest; aceptación criptográfica integral pendiente |
| CA4-02 | Parcial / dependencia | Conciliación documental/UUID del Lote 3 pendiente |
| CA4-03 | Parcial | Renovaciones y selección explícita; conciliación híbrida pendiente |
| CA4-04 | Parcial | Parser conservado, clasificación documental integral pendiente |
| CA4-05 | Regresionado | Temporal X.509 separado de SAT; no se infiere revocación |
| CA4-06 | Probado backend/PG | Renovación y selección concurrente: éxito/409; QA visual de certificado pendiente |
| CA4-07 | Probado en unidad | Umbrales 30/15/7 y vencimiento con reloj sintético |
| CA4-08 | Parcial integrado | Obligaciones/certificados/evidencia versionada; incidencias UUID pendientes |
| CA4-09 | Probado unidad/HTTP | Acciones e historial; evidencia resuelta/reabierta/obsoleta por HTTP |
| CA4-10 | Probado unidad/PG | Posposición, cambio material, recuperación y rollback; 8 conexiones concurrentes |
| CA4-11 | Probado backend | 1205 alertas; autorización previa a paginación, totales completos; UI paginada |
| CA4-12 | Probado parcial | Historial conservado, decisiones inmutables y revisión HTTP; QA UI exhaustiva pendiente |
| CA4-13 | Probado visual parcial | Cuadrícula mensual y semana real observadas; lista próximos conservada |
| CA4-14 | Probado HTTP/UI parcial | Edición manual guardada en navegador, revisión e historial; creación DOM exhaustiva pendiente |
| CA4-15 | Probado backend/HTTP | Versiones conservadas y contexto validado; la fuente legal requiere revisión humana |
| CA4-16 | Parcial | Procedencia manual/regla visible; cobertura X.509 y disponibilidad remota pendiente |
| CA4-17 | Parcial | Enlaces a expediente/sección; navegación exacta por ID no completa |
| CA4-18 | Probado unidad/HTTP | Calendario y resolución de evidencia no alteran cumplimiento declarado |
| CA4-19 | Probado unidad/HTTP | Permisos, revocación de sesión, CSRF y aislamiento empresarial |
| CA4-20 | Probado backend/HTTP | Archivo excluido por defecto y consulta explícita; UI exhaustiva pendiente |
| CA4-21 | Parcial | Lectura indexada sin proveedores en alertas; SMB real excluido; mocks regresionados |
| CA4-22 | Regresionado | KEY/secretos bloqueados; sin revelación habilitada ni claves reales leídas |
| CA4-23 | Probado HTTP/UI parcial | Resumen de Empresas con evidencia 0/1, sin indicadores nuevos en Inicio |
| CA4-24 | Parcial amplio | 168+1 pytest, 48 aisladas, 8 frontend, 7 clasificador, HTTP/PG/UI; operación real pendiente |

Pendientes: servicio Windows registrado, LAN/TLS/firewall, carga sostenida/multiinstancia, conciliación UUID, navegación DOM con cancelación fiable, accesibilidad/temas y aceptación integral de certificados. El paquete CMD/Python se ensayó; PowerShell bloqueado por política sin alterarla. No equivale a instalación en el servidor del despacho, aprobación de demo ni cierre de ContaSuite v1.0.

---

# CS-LOTE4-FINALIZATION-001 — funciones pendientes implementadas, validación integral pendiente

Fecha: 11 de noviembre de 2026. Esta sección es el estado vigente. Los informes anteriores se conservan debajo como antecedentes. No se declara Lote 4 completamente validado ni demo aprobada.

## Inspección y preparación

Se inspeccionaron el informe previo/matriz e inventario, lote4_lifecycle, certificados/alertas/calendario, trabajador de indexación, permisos y regresiones. Se confirmó backend/lote4_migrations/001_lifecycle.py con revisión lote4_lifecycle_0001, preparada y no ejecutada. Se preserva el contrato fiscal de Lote 1, archivo empresarial independiente de Lote 2 y bloqueo de evidencias de Lote 3.

Antes de editar se creó y verificó ../RESPALDOS/CS_LOTE4_FINALIZATION_20261111/before.zip, con baseline.json. No se incluyeron secretos, configuración privada ni documentos reales.

## Formularios y contratos de lectura

CalendarManagement reutiliza las APIs de escritura anteriores. Permite crear/editar fechas manuales, consultar y crear versiones de reglas, seleccionar empresa autorizada, concepto y periodo registrados, usar una versión explícita de regla o procedencia manual, indicar motivo/fuente y consultar historial de fechas/reglas (últimas 200 acciones, sin borrar las restantes). Edición por revisión optimista. Las versiones antiguas se conservan y la UI solo permite iniciar la siguiente desde la última.

La nueva lectura /api/integral/calendar/management/{empresa} filtra fechas, reglas e historial por empresa autorizada y devuelve catálogo/periodos compartidos existentes. Fechas: permiso empresarial de escritura; reglas: administrador y aplicabilidad confirmada. El backend valida periodicidad del concepto/periodo tanto en fecha como regla. Una regla revisada es una instrucción explícita de fecha fija y contexto con actor/fuente; no es una fórmula ni una certificación automática de derecho fiscal.

Validación de campos nativos y función pura calendarPayload usada por el formulario: fecha civil real, título, motivo y fuente. Sin conversión UTC de una fecha civil. Confirmación previa para capturas en archivadas; nunca restaura. Guardas existentes de formularios/diálogos y navegación conservadas; al cambiar empresa se confirma descarte y se remonta el editor. Carga, errores backend, confirmación de guardado e historial visibles. Calendario vuelve a consultar tras mutaciones para mostrar la fecha recién guardada. Se conservan ventanas y filtros previos.

Limitación: para nuevas fechas se elige un periodo ya registrado; no se crean periodos fiscales implícitamente. Si faltan periodos/esquemas la UI informa el error o lista vacía; no inventa fechas ni altera obligaciones.

## Evaluación periódica

alert_schedule.tick se integra en el trabajador existente backend/app/storage/worker.py mediante opción **explícita** --evaluate-alerts, intervalo configurable --alert-interval (900 segundos por defecto, mínimo 60). No se activa automáticamente en lanzadores ni HTTP. No se inició ningún trabajador. Este trabajador también tiene funciones de indexación: no ejecutarlo contra configuración existente sin revisión/autorización del entorno.

Nueva programación en tabla alert_evaluation_schedule, singleton id=1. UPDATE condicional de next_due reserva el intervalo dentro de la misma transacción que evalúa y guarda last_success. Si el proveedor falla, rollback de toda la transacción y la evaluación sigue pendiente. Dos intentos por el mismo corte no vuelven a evaluar después del primer commit; el control efectivo entre conexiones depende de las garantías del motor y queda pendiente de ensayo concurrente real. La evaluación comparte además el bloqueo advisory transaccional PostgreSQL del lifecycle. No se validó ese bloqueo en un servidor.

Tras inactividad se evalúa la condición actual una vez, sin recrear retrospectivamente avisos por cada día omitido. Se recuperan posposiciones vencidas y cambios de umbral/condición con los contratos previos. Se conservan reconocimiento, resolución y aplazamiento mientras la condición no cambie materialmente. Reaparición de condición obsoleta y vencimiento de aplazamiento se mantienen como transiciones explícitas de historial. Los certificados usan 30/15/7 y vencimiento, solo sobre selección actual explícita.

Zona explícita America/Mexico_City. tick acepta reloj y proveedor simulados; candidates admite stamp opcional compatible con los consumidores previos. evaluate admite commit=False y día de corte para que trabajador y programación sean atómicos. El refresh administrativo ahora toma el mismo bloqueo antes de obtener candidatos, evitando calcularlos fuera de esa sección crítica. Fallos del trabajador se registran con mensaje genérico, sin volcar configuración o secretos. Sin esquema nuevo la programación devuelve unavailable y no migra nada.

## Dashboard de Empresas

Resumen backend lote4_summary sobre IDs empresariales ya autorizados por el Dashboard y los registros fiscales de su periodo/filtros. Incluye alertas pendientes persistidas de esos orígenes, certificados actuales próximos/vencidos, obligaciones próximas (15 días y fecha confirmada) y vencidas confirmadas. Los certificados se filtran además por permiso metadata de bóveda. Las obligaciones no se suman con celdas implícitas sin fecha; sus denominadores fiscales se conservan en el servicio compartido.

El alcance visible distingue obligaciones del periodo seleccionado, certificados actuales al corte y alertas persistidas (pueden requerir evaluación). Se excluyen archivadas por defecto; el filtro explícito se transmite al backend y al contrato fiscal. No se suspenden alertas ni se restauran empresas por ese filtro. Si no hay esquema lifecycle, el resumen informa indisponibilidad; no sustituye datos faltantes por cero. Evidencias pendientes es null con explicación del bloqueo, no un contador ficticio.

Se reutilizan Kpi, tarjetas y estructura Stitch dentro de Empresas. Inicio permanece sin indicadores fiscales operativos.

## Migraciones pendientes, ninguna ejecutada

- company_archive_0001, de Lote 2.
- lote4_lifecycle_0001, extensión previa del ciclo de vida.
- **lote4_schedule_0002**, nueva migración explícita backend/lote4_migrations/002_schedule.py: crea solo tabla de programación e inicializa singleton. No está en arranque automático. Requiere lifecycle_0001, esquema fiscal/bóveda/base compatibles y respaldo/restauración ensayada antes de aplicación futura.

Si tablas previas existen pero son incompatibles, create_all no las repara; revisar tipos, constraints e índices antes de activar. Recuperación por código no equivale a eliminar datos. Downgrade destructivo deshabilitado.

## Pruebas actuales y límites

- **43 backend aprobadas**: 38 regresiones de cierre/Lotes 1–4 y 5 nuevas. Se ensayan reloj/proveedor, una reserva por intervalo, ocho días de inactividad, rollback de reserva ante fallo, umbrales 30/15/7/vencimiento, revisión obsoleta de fecha y resumen empresarial con archivo. No son pruebas de transacciones realmente simultáneas.
- **8 frontend de lógica pura aprobadas**: 5 regresiones de navegación/descartes/archivadas y 3 del payload real del formulario (fecha civil, campos inválidos, versión/fuente). No son pruebas DOM, interacción visual ni accesibilidad del navegador.
- **7 clasificador documental aprobadas**, regresión del avance parcial de Lote 3.
- **TypeScript sin emisión aprobado**. Se corrigió un error inicial de inferencia UUID del nuevo formulario antes de la ejecución final; no hay fallos finales.

Backend exclusivamente con SQLite en memoria y metadata sintética; dotenv bloqueado, tokens ficticios, raíces vacías, red/procesos externos bloqueados. No se ejecutaron funciones de migración ni app.main. Node interpreta las pruebas TypeScript sin generar artefactos. Registros de ejecución en backend.json, frontend.json, classifier.json y typescript.json junto al respaldo; son ejecuciones actuales.

No ejecutado: QA HTTP, visual, PostgreSQL, transacciones paralelas reales, pruebas completas de temporizador/indexador funcionando, ni servicios externos. No se reutilizó el laboratorio PostgreSQL histórico sin revalidar aislamiento/configuración. No se declara interfaz verificada por TypeScript.

## Matriz CA4 vigente

| Caso | Estado | Evidencia / pendiente |
|---|---|---|
| CA4-01 | Parcial | Registro público existente; falta ensayo criptográfico de aceptación |
| CA4-02 | Bloqueado | Detección/conciliación documental incompleta, Lote 3 |
| CA4-03 | Parcial | Identidad y renovaciones probadas; conciliación híbrida pendiente |
| CA4-04 | Parcial | Parser conservado; clasificación integral confiable pendiente |
| CA4-05 | Parcial | Temporal y SAT separados; sin validación SAT inferida |
| CA4-06 | Aprobado en unidad | Renovación/selección explícita conservadas; QA visual pendiente |
| CA4-07 | Aprobado en unidad | test_certificate_thresholds_with_clock |
| CA4-08 | Bloqueado parcial | Obligaciones/certificados integrados; evidencias/incidencias Lote 3 pendientes |
| CA4-09 | Aprobado en unidad | Ciclo de acciones y auditoría regresionado |
| CA4-10 | Aprobado en unidad | Cambios materiales, posposición/reaparición y días omitidos |
| CA4-11 | Parcial | Resumen backend filtrado nuevo; paginación completa del centro de alertas pendiente |
| CA4-12 | Aprobado en unidad | Historial y procedencia conservados |
| CA4-13 | Parcial | Ventanas/filtros existentes y formulario integrados; cuadrícula/QA pendiente |
| CA4-14 | Parcial | UI y API manual nuevas; tests de payload y backend, no DOM |
| CA4-15 | Parcial | Gestión visual de versiones y validación contextual; fuente legal requiere revisión humana |
| CA4-16 | Parcial | Procedencia/manual/regla visible; cobertura completa X.509 pendiente |
| CA4-17 | Parcial | Enlaces a sección y periodo, no navegación exacta completa a ID |
| CA4-18 | Aprobado en unidad | Calendario no cambia cumplimiento |
| CA4-19 | Parcial | Permisos backend/empresa y regresiones; revocación HTTP nueva pendiente |
| CA4-20 | Parcial | Archivo filtrado en resumen/consultas, capturas confirmadas; QA pendiente |
| CA4-21 | Parcial | Lectura indexada sin proveedores; simulación integral SMB pendiente |
| CA4-22 | Parcial | Sin referencias/lecturas KEY/secretos nuevas; regresiones previas |
| CA4-23 | Parcial | Kpi y backend integrados en Empresas; QA visual pendiente |
| CA4-24 | Parcial | 43+8+7 pruebas, reserva/rollback/reloj; concurrencia real y PostgreSQL pendientes |

## Dependencias, riesgos y recuperación

Lote 3 sigue sin historial íntegro de verificación fiscal, versión/disponibilidad comprobada y conciliación UUID. No se creó evidencia paralela ni se tomó asociación documental como cumplimiento. Esos contadores/alertas permanecen bloqueados explícitamente.

Riesgos pendientes: PostgreSQL y concurrencia real; activación futura de esquema/trabajador; validación DOM de formularios y guardas; listado/historial grande y paginación; conciliación documental/certificados no terminada; integración de alertas con archivos actualmente desconectados no ensayada. Historial de gestión se limita a 200 acciones visibles sin eliminar las anteriores. Fuentes/periodos administrativos requieren revisión humana; no hay reglas legales automáticas nuevas.

Respaldo verificado ../RESPALDOS/CS_LOTE4_FINALIZATION_20261111/before.zip. baseline.json tiene huellas previas; final.json/changes.json inventario exacto y huellas posteriores; finalization.diff diferencias revisables. Para revertir código: preservar cambios posteriores, restaurar SOLO modificados desde el ZIP manteniendo rutas y verificar huellas. Retirar añadidos únicamente después de comprobar huellas finales y conservar trabajos posteriores. No superponer carpetas ni eliminar tablas/eventos. Si esquema se activa en el futuro, conservarlo y revisar compatibilidad antes de volver al código anterior.

No acceso a datos reales, secretos, KEY, SMB/SAT, ni cambios frontend/dist. No se inició aplicación/trabajador, no hubo migraciones, build ni despliegue. Lote 5 no iniciado. Lote 4 no completamente validado; demo no aprobada.

---

## Informes históricos (antecedentes, no estado vigente)

# CS-LOTE4-CLOSURE-001 — avance de cierre, NO completado

11 de noviembre de 2026. Las funciones siguientes están preparadas en código, no activadas por migración ni desplegadas. El informe anterior se conserva abajo como antecedente; sus resultados no son la validación actual.

## Auditoría y decisiones

Se revisaron las reglas del proyecto, el informe CA4, certificados/alertas existentes, calendario, contratos fiscales y regresiones empresariales. El Lote 3 sigue sin historial íntegro de verificación y sin contrato completo de versión/disponibilidad/UUID. No se integraron nuevas alertas de evidencias ni se creó otro sistema de evidencias. El generador compatible excluye documentation_review; la presentación histórica previa no se certifica como el nuevo contrato.

Se mantiene vault_certificates y vault_alerts. Se añaden extensiones por sus identificadores, nunca copias de certificados/alertas ni referencias a secretos. No se abrieron almacenes, contraseñas ni KEY.

## Implementado en esta intervención

- Selección explícita de certificado actual por empresa y clase fiel/csd, con revisión. Requiere identidad pública por huella y clasificación conocida. La elección no depende de fechas y no implica vigencia SAT.
- Renovación anterior/nueva dentro de la misma empresa/clase; rechazo de autorreferencia, ciclos, huella idéntica y reasignación de antecedente. Certificados anteriores conservados. Selección repetida no incrementa revisión ni vuelve a crear relación.
- Consulta de selección y renovaciones; panel de selección dentro del centro existente. Auditoría de actor, empresa, instante, antes/después y motivo. No se cambió el registro público previo ni se incorporaron rutas KEY.
- Estados pending, acknowledged, snoozed, resolved y obsolete sobre vault_alerts. Acciones autorizadas con revisión, motivo e historial append-only; posposición exige fecha futura en el día civil de México. No cambian obligaciones/certificados.
- Evaluación explícita reutiliza candidates: umbrales 30/15/7; certificados seleccionados como actuales, sin elegir automáticamente históricos. Identidad existente source/reference/kind; huella material de condición; reevaluación idéntica conserva reconocimiento/posposición/resolución. Cambio material reabre; una condición ausente pasa a obsoleta; reaparición y aplazamiento vencido reabren. Historial no eliminado. Fuentes de evidencia pendientes no se evalúan como desaparecidas.
- UI de alertas admite estados y acciones y excluye archivadas por defecto con inclusión expresa. Aún usa confirmaciones/prompts del navegador, pendientes de sustituir por un diálogo completo con pruebas de accesibilidad. No se afirma terminado el diseño visual de esas acciones.
- Fechas manuales nuevas/editables mediante API /integral/calendar/manual/{id}; guardado con revisión, empresa inmutable, concepto y periodo existentes, periodicidad compatible y auditoría completa. Se permiten sin regla; una configuración explícitamente no aplicable rechaza el contexto. El estado fiscal nunca se modifica.
- Reglas como instrucciones explícitas de fecha fija para empresa/concepto/periodo. Versiones inmutables, administrador verificador y referencia de fuente obligatoria. No se incorporó ninguna regla legal predefinida ni fórmula de vencimiento. Usar una regla exige coincidencia exacta de fecha/contexto y aplicabilidad confirmada. Es una revisión interna, no certificación de legalidad.
- Calendario conserva filtros/ventanas y agrega fechas manuales/reglas con procedencia y versión. Se agregó filtro manual en la interfaz. La interfaz de alta/edición de fechas y administración de reglas aún no está construida; estas operaciones están disponibles por API.
- Concesiones empresariales y actividad fiscal no se alteran. Las operaciones nuevas de certificados/alertas exigen permiso específico de bóveda más escritura por empresa. Reglas requieren administrador; fechas manuales escritura por empresa. La captura en archivadas no restaura; selección y acciones de alertas piden confirmación en interfaz. La API de fechas manuales no incluye interacción visual de advertencia todavía.

## Migración preparada, no ejecutada

backend/lote4_migrations/001_lifecycle.py, revisión lote4_lifecycle_0001. Tablas aditivas: certificate_current_selection, certificate_renewals, alert_lifecycle, lote4_action_history, calendar_verified_rules, calendar_manual_dates. Metadata independiente de Base y del arranque; no se convierte historial existente. Downgrade destructivo prohibido.

Requiere esquema base, fiscal, bóveda y empresas compatible; archivo company_archive_0001 para evaluar correctamente exclusión. Las guardas responden 503 si faltan tablas/columnas. Revisar equivalencia de tipos/FK/índices antes de una futura aplicación: create_all no repara tablas existentes.

Cambio justificado de contrato: refresh anterior de alertas reseteaba estados a open. Ahora exige la extensión y devuelve 503 mientras no exista; evita destruir decisiones nuevas mediante el contrato viejo. GET mantiene alertas históricas y añade revisión/posposición. Interfaz conserva opción de abiertas anteriores. No se migran los estados open ni se inventa historial retrospectivo. Cuando se evalúa una alerta antigua, se registra el primer evento de transición conocido.

PostgreSQL: las operaciones de cierre toman bloqueo advisory transaccional común para serializar cambios de relaciones y acciones; no se ha validado contra PostgreSQL. Revisión optimista adicional en selección, alertas y fechas. Errores de integridad en endpoints hacen rollback y responden 409. Falta ensayo real de concurrencia.

## Pruebas ejecutadas ahora

38 pruebas backend aprobadas: 32 regresiones de Lotes 1/2/calendario y 6 nuevas de cierre. Ensayo sintético de renovaciones/ciclos/selección, permiso insuficiente, historial, deduplicación, reconocimiento, posposición, resolución, cambio material/reapertura, obsolescencia/reaparición, recuperación de posposición vencida, fechas manuales/editadas, versiones de reglas y contexto incompatible. Se preserva estado fiscal al editar fecha. No se han probado todas las carreras ni todas las combinaciones de permisos nuevos.

7 pruebas puras de clasificación del Lote 3 aprobadas. TypeScript sin emisión aprobado. Ninguna prueba final fallida. Tablas sintéticas en SQLite en memoria mediante metadata de tests; no se ejecutó ninguna función de migración. Dotenv bloqueado, tokens sintéticos, raíces vacías, red/procesos prohibidos. No se inició app.main.

No ejecutado: HTTP real, navegador/QA visual, PostgreSQL, scheduler, desconexión SMB simulada ni pruebas criptográficas nuevas de certificados. El laboratorio PostgreSQL histórico no se reutilizó: no se revalidaron aislamiento/configuración/credenciales sin acceder a esos elementos. No se afirma compatibilidad PostgreSQL probada.

## Matriz CA4 actualizada

| Caso | Estado actual | Evidencia/límite |
|---|---|---|
| CA4-01 | Parcial | Registro público anterior conservado; no ensayo criptográfico nuevo |
| CA4-02 | Bloqueado | Conciliación documental de Lote 3 incompleta |
| CA4-03 | Parcial | Identidad única previa y renovación por huella; conciliación registro/detección pendiente |
| CA4-04 | Parcial | Parser previo conservado; clasificación confiable integral pendiente |
| CA4-05 | Parcial | Selección no cambia estado SAT; prueba criptográfica faltante |
| CA4-06 | Aprobado en unidad | test_renewal_and_explicit_selection; UI sin QA |
| CA4-07 | Parcial | Umbrales configurados en candidates; matriz temporal completa pendiente |
| CA4-08 | Bloqueado | Categorías de evidencia/incidencias del Lote 3 pendientes |
| CA4-09 | Aprobado en unidad | test_alert_states_dedup_snooze_reopen; UI sin QA |
| CA4-10 | Aprobado en unidad | Cambios materiales/reaparición/posposición vencida |
| CA4-11 | Parcial | Filtrado visual; falta contador backend y paginación coherentes de todo el histórico |
| CA4-12 | Aprobado en unidad | Historial append-only con actor/motivo/antes/después |
| CA4-13 | Parcial | Ventanas y filtros conservados; cuadrícula y QA pendientes |
| CA4-14 | Parcial | API manual/editada probada; formulario visual pendiente |
| CA4-15 | Parcial | Versiones inmutables y contexto probados; UI/revisión legal humana pendientes |
| CA4-16 | Parcial | Fechas manuales y regla versionada identificables; cobertura certificado incompleta |
| CA4-17 | Parcial | Enlaces de sección, no apertura exacta garantizada |
| CA4-18 | Aprobado en unidad | Regresiones y edición manual sin alterar fiscal |
| CA4-19 | Parcial | Permisos backend presentes y denegación ensayada; HTTP/revocación nuevos pendientes |
| CA4-20 | Parcial | No restauración, filtros y regresiones; cobertura visual parcial |
| CA4-21 | Parcial | Operaciones de metadatos sin proveedores; desconexión simulada pendiente |
| CA4-22 | Parcial | Ningún secreto/KEY añadido; pruebas anteriores conservadas |
| CA4-23 | Pendiente | Indicadores Dashboard no consolidados con lifecycle |
| CA4-24 | Parcial | 38 regresiones/cierre aprobadas; PostgreSQL/concurrencia/temporizador pendientes |

## Bloqueos y pendientes de cierre

Lote 3: faltan verificación fiscal histórica íntegra, versión documental y disponibilidad comprobada, detección de conflictos UUID y revisión confiable. No se sustituyen por fiscal_evidence sin versión.

Pendientes desacoplados: edición visual de fechas/reglas, temporizador compatible de evaluaciones y recuperación automática tras inactividad, contador backend y paginación, integración del Dashboard, matriz temporal completa de certificados, conciliación híbrida, QA y carreras concurrentes. El motor solo se ejecuta por refresh administrativo explícito; no se presenta como evaluación periódica automática. Los avisos de archivado de la API manual se integrarán con su futura interfaz. No corresponde declarar completado Lote 4.

## Respaldo y recuperación

../RESPALDOS/CS_LOTE4_CLOSURE_20261111/before.zip verificado antes de editar. baseline.json contiene huellas previas; changes.json/final.json inventario exacto y huellas posteriores, closure.diff diferencias. Inventario impreso al final de este informe. Restaurar SOLO archivos modificados desde el ZIP tras preservar trabajo posterior; verificar huellas previas. Retirar añadidos solo si conservan huellas finales y tras conservar cambios posteriores. Nunca superponer carpetas completas ni eliminar tablas/historial. Si se activa el esquema después, la reversión de código requiere revisar compatibilidad y conservar todos los datos: no ejecutar downgrade destructivo.

No se ejecutaron migraciones, no se accedió a SMB/SAT, secretos ni datos empresariales reales; no se modificó frontend/dist ni se desplegó. No se inició Lote 5. Sin demo aprobada.

---

## Informe histórico anterior (no representa el estado actualizado)

# CS-LOTE4-IMPLEMENTATION-001 — entrega parcial

Lote 4 no completado. Sin demo aprobada. Fecha: 11 de noviembre de 2026.

## Inspección y dependencias

Se consultaron las reglas del proyecto, reportes de Lotes 2/3 y contratos fiscales, modelos de bóveda, API de certificados, alertas e interfaz integral. El código previo del Lote 1 se contrastó mediante sus consumidores actuales y las regresiones. No se consultó el estado de bases reales.

Reutilizables: fiscal_records, fiscal_periods, due_verified, effective/cutoff del contrato fiscal, vault_certificates, permisos metadata de credential_api.allowed, archivado independiente, router integral y componentes Stitch. El parser existente parse_public_certificate usa cryptography X.509 con límite de tamaño; no se sustituyó. VaultCipher declara cifrado autenticado y provisión externa; se inspeccionó su contrato de código anteriormente, sin abrir almacenes ni claves.

Bloqueos: Lote 3 no garantiza historial íntegro de verificación; detección/conciliación UUID documental y disponibilidad comprobada pendientes. vault_certificates no representa selección actual ni relación de renovación; su identidad única incluye kind, por lo que un cambio de clasificación no acredita conciliación global. vault_alerts carece de actualización, aplazamiento y acciones históricas requeridas; refresh puede reabrir open sin esa semántica. El programador existente es de indexación, no motor central de alertas. No se modificó ni amplió ese trabajador para hacer evaluaciones sin un contrato persistido correcto.

Se aislaron verificación documental, alertas de evidencia/incidencias, renovaciones/selección actual y acciones de alertas. No se inventaron referencias a secretos. Las nuevas capacidades de escritura y seguimiento persistente requieren extensiones explícitas revisadas y ensayadas; no se implementaron ni simularon.

## Código implementado

Calendario **de lectura**: GET /api/integral/calendar. Ventanas mes, semana ISO y próximos 30 días desde un corte seleccionable; filtro empresa/tipo/estado e inclusión expresa de archivadas. Solo fechas límite confirmadas de fiscal_records y vencimientos registrados de vault_certificates. Sin inferencia legal ni lectura de archivos. Identidades estables source+ID; deduplicación; periodos fiscales reales; enlaces a sección y periodo. No se altera cumplimiento. Fechas X.509 convertidas explícitamente al día de México; Date fiscal permanece fecha civil.

Permisos backend: fiscal por empresa y certificados por permiso metadata además del ámbito empresarial. Falta de fuente se declara por sources; esquemas parciales responden mediante guardas existentes. Archivadas excluidas por defecto cuando el esquema está disponible; falta de esquema se declara no evaluable y no se finge persistencia. Inclusión no restaura ni suspende alertas. No hay escrituras nuevas, por lo que no se introducen confirmaciones de captura nuevas.

Interfaz Calendario fiscal reutiliza tabla/tarjeta/filtros Stitch dentro de Empresas. Las tres ventanas se presentan como lista tabular, no cuadrícula mensual/semanal. Incluye selector de día, carga/error/vacío y procedencia. Certificados históricos identificados como tales; no se selecciona automáticamente el más reciente ni se declara SAT validado. Los centros previos de certificados/alertas se conservan sin presentar sus contratos como cumplimiento del nuevo diseño.

## Validación actual

32 pruebas backend aprobadas: 5 de calendario y 27 regresiones fiscales/Empresas (incluyen 17 fiscales). Fixtures existentes aislados, dotenv bloqueado, SQLite en memoria y tablas sintéticas nuevas, raíces vacías, sin migraciones ni app.main. 7 pruebas puras del clasificador Lote 3 aprobadas. TypeScript sin emisión aprobado. No fallos en ejecuciones finales. No pruebas visuales/HTTP/PostgreSQL, ni ensayos nuevos de certificados/alertas, desconexión simulada, posposición, renovación o recuperación tras inactividad. Estas pruebas pendientes no son aprobaciones.

## Matriz CA4

| Caso | Estado | Evidencia y límite |
|---|---|---|
| 01 | Pendiente | Registro previo existe; sin implementación/ensayo nuevo |
| 02 | Bloqueado | Conciliación documental incompleta |
| 03 | Pendiente | Identidad/conciliación de certificados por completar |
| 04 | Parcial | Parser X.509 previo inspeccionado, sin prueba nueva |
| 05 | Parcial | Calendario declara SAT undetermined; certificados no ensayados |
| 06 | Pendiente | Renovación/actual sin representación |
| 07 | Pendiente | No motor 30/15/7 nuevo; calendario usa umbrales sin cambiar alertas |
| 08 | Bloqueado | Evidencias/incidencias del Lote 3 incompletas |
| 09 | Pendiente | Acciones/historial sin implementar |
| 10 | Pendiente | Reapertura material sin implementar |
| 11 | Parcial | count del calendario sobre eventos filtrados; no contador central de alertas |
| 12 | Pendiente | Historial de alertas no ampliado |
| 13 | Parcial | Ventanas backend probadas; UI tabular sin cuadrícula ni QA |
| 14 | Pendiente | Sin fechas manuales nuevas |
| 15 | Pendiente | No reglas automáticas; no se infieren fechas legales |
| 16 | Parcial | Procedencia fiscal probada; certificados sin ensayo nuevo |
| 17 | Parcial | Enlaces a empresa/sección/periodo, no apertura garantizada de ID exacto |
| 18 | Aprobado en unidad | test_calendar_read_does_not_change_fiscal |
| 19 | Parcial | test_calendar_scope y regresiones; certificados/HTTP pendientes |
| 20 | Parcial | test_calendar_archived_and_idempotent; historial previo conservado sin escrituras |
| 21 | Parcial | Nuevo calendario consulta solo metadatos; no ensayo de SMB simulado |
| 22 | Parcial | No nuevas rutas de secretos; regresión de módulos sensibles y prueba KEY del Lote 3 |
| 23 | Pendiente | Calendario integrado en Empresas; resumen Dashboard sin ampliar |
| 24 | Parcial | Idempotencia calendario y regresiones aprobadas; motor de alertas pendiente |

## Migraciones y continuación

Ninguna migración nueva preparada ni ejecutada. company_archive_0001 sigue preparada de Lote 2. Antes de continuar escrituras: diseñar extensiones aditivas para selección/renovación, acciones/historial/posposición de vault_alerts y fechas manuales/reglas versionadas; mantener tablas existentes, definir concurrencia y recuperación, ensayar únicamente memoria/copia sintética. Resolver aparte historial documental antes de alertas de evidencia. No se implementó ningún lote posterior.

## Inventario y reversión

Modificados: backend/app/integral_api.py (registro del endpoint), frontend/src/modules/Companies.tsx (pestaña calendario).
Añadidos: backend/app/fiscal_calendar.py, frontend/src/modules/FiscalCalendar.tsx, backend/tests/run_lote4_isolated.py, docs/CS_LOTE4.md.

Respaldo ../RESPALDOS/CS_LOTE4_20261111/antes_lote4.zip, baseline.json y final.json con huellas, lote4.diff con diferencias. Para recuperar: preservar cambios posteriores, extraer SOLO los dos modificados con sus rutas relativas y comprobar huellas previas; retirar añadidos únicamente tras verificar sus huellas finales y conservar trabajos posteriores. No superponer carpetas ni tocar datos/configuración/documentos.

No acceso a datos reales, .env, credenciales, claves privadas, SMB/SAT; sin migraciones, arranque, firmas, compilación, despliegue ni cambios frontend/dist. No se habilitó revelación ni importación definitiva. Se entrega componente desacoplado y límites explícitos, no un Lote 4 completo.


## Inventario exacto de esta intervención

Modificados:
- backend/app/credential_alerts.py
- backend/app/fiscal_calendar.py
- backend/app/integral_api.py
- frontend/src/modules/Credentials.tsx
- frontend/src/modules/FiscalCalendar.tsx
- docs/CS_LOTE4.md

Añadidos:
- backend/app/lote4_lifecycle.py
- backend/lote4_migrations/001_lifecycle.py
- backend/tests/run_lote4_closure.py
- frontend/src/modules/CertificateLifecycle.tsx


## Inventario exacto FINALIZATION

Modificados:
- backend/app/credential_alerts.py
- backend/app/integral_api.py
- backend/app/integral_dashboard.py
- backend/app/lote4_lifecycle.py
- backend/app/storage/worker.py
- frontend/src/modules/FiscalCalendar.tsx
- frontend/src/modules/IntegralDashboard.tsx
- docs/CS_LOTE4.md

Añadidos:
- backend/app/alert_schedule.py
- backend/app/lote4_summary.py
- backend/tests/run_lote4_finalization.py
- frontend/src/calendarForm.ts
- frontend/src/modules/CalendarManagement.tsx
- frontend/tests/lote4.test.mjs
- backend/lote4_migrations/002_schedule.py
