# ContaSuite Web — informe de estado para revisión de Claude

Fecha de corte: 12 de noviembre de 2026. Este documento resume el trabajo de la conversación y los informes actuales del repositorio. No contiene contraseñas, tokens, documentos empresariales ni configuración privada. No sustituye las matrices y evidencias originales.

## 1. Conclusión principal

Existe una aplicación integrada y funcional en laboratorio, con módulos empresariales, fiscales, documentales y de automatización. Se completaron correcciones importantes de identidad documental, historial, alertas, calendario y preparación Windows. Se implementó y probó una importación piloto de carpetas locales **exclusivamente con datos sintéticos**.

**ContaSuite v1.0 y el Lote 4 no están aprobados para operación definitiva.** Faltan criterios de aceptación operativa, visual y documental. No se inició el Lote 5 ni se desplegó al despacho en estas intervenciones.

El bloqueo inmediato reportado por el usuario al abrir el puerto 8000 está identificado: el lanzador utiliza una base de esquema anterior; el backend rechaza arrancar porque faltan tablas. No se migró ni modificó esa base para solucionar el acceso. Se arrancó el piloto separado en http://127.0.0.1:8060 y su health respondió correctamente en la última comprobación. Esto no garantiza que el proceso siga activo tras cerrar sesión o reiniciar Windows.

## 2. Proyecto y arquitectura

- Carpeta de trabajo: `C:\Users\Usuario\Documents\ChatGPT\ContaSuite Web\ContaSuite_Web_0_1`.
- Backend: FastAPI, SQLAlchemy, autenticación por sesiones personales, CSRF, permisos empresariales y auditoría.
- Frontend: React, TypeScript y Vite; diseño existente de Stitch, temas claro/oscuro/alto contraste y preferencias de movimiento reducido.
- PostgreSQL en laboratorios aislados; SQLite en buena parte de las pruebas unitarias.
- CS-Storage: catálogo, orígenes, ubicaciones, versiones, SHA-256, vínculos empresariales por rol, indexador y revisión documental.
- Trabajador existente para indexación y evaluación opcional de alertas; no se añadió un servicio externo para esa evaluación.
- Arranque ordinario: verifica compatibilidad del esquema; **no migra ni siembra empresas automáticamente**. El aprovisionamiento requiere comando explícito del operador.

No hay historial Git utilizable según la inspección de integración documentada. La trazabilidad de cambios se apoya en ZIP previos, manifiestos SHA-256, inventarios y diffs. Conservar modificaciones ajenas a cada tarea es una condición del proyecto.

## 3. Capacidades existentes y límites

| Área | Estado que se puede sostener |
|---|---|
| Empresas y expedientes | Catálogo, directorio, filtros, navegación y archivo empresarial independiente de actividad fiscal |
| Lote 1: lectura fiscal | fiscal_records canónico para nuevas operaciones; obligations conservado como histórico separado; denominadores y periodos explícitos, sin sumar ambos modelos como si fueran lo mismo |
| Cumplimiento | Separación entre declaración, verificación del despacho y pago; vincular un documento no confirma cumplimiento |
| Lote 2 | Empresas y navegación combinada integradas; archivadas excluidas por defecto donde corresponde, con consulta explícita |
| Lote 3 | Clasificación y revisión ampliadas; bloqueos de historial/UUID corregidos dentro del alcance ensayado; reconocimiento de todos los formatos y aceptación integral pendientes |
| Certificados | CER públicos, renovaciones, historial, relación anterior/renovación y selección actual explícita autorizada; fechas X.509 no significan vigencia SAT |
| Alertas | Pendiente, reconocida, pospuesta, resuelta y obsoleta; acciones auditadas, historial, deduplicación, reapertura por cambios materiales y conservación de aplazamientos |
| Calendario | Mes, semana y próximos; fechas manuales, procedencia, edición e historial; reglas versionadas explícitas con validación de contexto, sin inventar cálculos legales |
| Dashboard de Empresas | Resúmenes de alertas, certificados, obligaciones y evidencia bajo permisos/filtros; Inicio mantiene su bienvenida |
| Documentos | Catálogo, versiones, huellas, revisión, vínculos independientes y conflictos; no se fusiona por nombre/RFC/periodo/UUID |
| Automatización previa | Recopila, CFDI, Declara y Recibos integrados mediante adaptadores y motores existentes; no equivalen a una conexión SAT operativa |
| Imprime | Módulo descartado por el usuario; no reactivarlo |
| SMB | Existe proveedor UNC Windows de sólo lectura y antecedentes de pruebas de oficina. En las tareas recientes no se accedió a SMB real; no confundir soporte implementado con aceptación de esta instalación |
| Secretos | No se habilitó revelación de credenciales ni lectura de KEY reales |

## 4. Recuperación de integración y cierre documental

Se corrigió la sobrescritura de verificaciones mediante historial aditivo de decisiones, con versión documental, revisión fiscal, actor y fecha. La proyección actual se conserva por compatibilidad. No se afirma recuperar decisiones históricas ya perdidas antes de disponer de ese historial.

La verificación exige permisos, asociación empresarial y comprobación de contenido/hash. Un conflicto de identidad o cambio de versión puede suspender su validez actual sin borrar la decisión anterior ni cambiar el cumplimiento declarado o el pago.

Se añadió identidad CFDI por versión en `document_cfdi_identities`: UUID declarado normalizado, huella y condición de revisión. Cargas/observaciones XML detectan contradicciones antes de clasificar. Mismo UUID con bytes diferentes requiere revisión; igualdad de UUID no autoriza fusionar documentos. Timbres múltiples o UUID inválidos también requieren revisión.

La cola de conciliación usa las revisiones existentes, con permisos de administrador y paginación. Las correcciones humanas conservan motivo, actor, fecha y vínculos anteriores/elegidos. La reapertura explícita crea otra revisión y conserva el rechazo anterior. Resolver una asociación no restaura por sí solo una verificación fiscal suspendida.

Se probaron bloqueos/idempotencia con conexiones PostgreSQL concurrentes. El bloqueo global documental es conservador; su rendimiento bajo carga sostenida y multiinstancia sigue pendiente.

## 5. Stitch y QA visual

Se localizaron referencias originales en `design_references/stitch_contasuite_enterprise_fiscal_platform (2).zip`: 12 HTML, 12 capturas y DESIGN.md. Se compararon referencias disponibles y se ajustaron componentes compartidos sin sustituir reglas de negocio.

Se conservaron tipografía, jerarquía, paleta, navegación, tarjetas, controles, temas y movimiento reducido. Se añadieron nombre accesible de modal y salto al contenido. Se observaron pantallas reales de Inicio, Empresas, conciliación, revisión y calendario, con comprobaciones parciales de teclado/móvil/temas.

No existe referencia dedicada para todas las pantallas nuevas. No se afirma fidelidad píxel a píxel, accesibilidad completa ni aceptación exhaustiva de todos los flujos. La cancelación de borrador mediante diálogo nativo no se pudo verificar fiablemente en la automatización; las guardas compartidas permanecen integradas.

## 6. Windows, instalador y LAN

Se amplió el empaquetado existente con Python 3.12 privado y dependencias mediante allowlist, aislamiento de entorno y manifiestos. Se probaron instalación limpia, actualización en directorio nuevo, retiro reversible por renombrado, respaldo/restauración y ejecución sin Python en PATH. PostgreSQL debe aprovisionarse aparte.

Se preparó host de servicio Windows con estados, arranque/parada controlada, logs rotativos y manejo de errores. La ejecución oculta y la parada se ensayaron; **no se registró ni validó realmente bajo SCM**: la sonda de creación devolvió WinError 5. Faltan controles SCM, cuenta/ACL efectivas, recuperación tras fallo y reinicio del equipo.

TLS/LAN está preparado mediante configuración de ejemplo, hosts explícitos y proxy de confianza limitado. Se probaron rechazos de Host/Origin no permitidos en HTTP. No se validaron certificado definitivo, firewall, HTTPS operativo ni otro cliente autorizado. No se debilitó PowerShell ni se modificó la red real.

Paquete conservado: `..\ENTREGAS\CS_RELEASE_CLOSURE_20261111.zip`, SHA-256 `05d1c0d71e3150422205db01c6659e9af38106ee1ffd1af7c5f6ac9bbbc02c25`.

**Ese ZIP corresponde al cierre anterior: no contiene la importación piloto posterior.** El código y frontend actuales sí incluyen el piloto; no se generó un nuevo instalador para esa tarea.

## 7. Importación piloto local

Acceso: Empresas → Importar y conciliar → Fuente → Desde carpeta local · importar empresas.

La aplicación web ofrece dos carpetas previamente autorizadas en el servidor. No pretende que un selector del navegador conceda acceso arbitrario al disco. Se rechazan rutas UNC, unidades de red mapeadas, enlaces y carpetas superpuestas. Sólo se abre contenido PDF/XML/CER público, con exclusiones obligatorias para llaves, secretos y respaldos, además de límites configurables.

La vista previa muestra inventario, candidatos RFC/fuentes, clasificaciones, duplicados, conflictos e incidencias. La empresa no se deduce del nombre de carpeta: el usuario debe revisar RFC y razón social. Puede editar clasificación y vínculos Emisor/Receptor/Titular.

La confirmación requiere sesión administrativa y acción explícita dentro de ContaSuite. Se vuelve a comprobar el inventario/hash y se guarda en una transacción usando los servicios existentes. Un fallo intermedio revierte el intento. Se asocia por RFC normalizado, sin duplicar empresas; versiones y documentos por origen/ruta no se duplican al repetir sin cambios. Una corrección de reimportación agrega revisión y preserva la anterior.

No se crean obligaciones ni se confirma cumplimiento o pago. Los conflictos UUID quedan pendientes. Los originales no se escriben. Las incidencias de archivos no importados quedan en el análisis guardado; no se inventan documentos fiscales para representar errores.

La API está deshabilitada por defecto. Exige CS_PILOT_ENABLED, CS_PILOT_DATABASE coincidente con PostgreSQL local exclusivo y dos CS_PILOT_ROOTS autorizadas. La base ensayada es `contasuite_pilot_synthetic_001`; no mezclarla con datos reales.

### Resultados sintéticos

- 2 empresas revisadas; 11 archivos físicos generados contando excluidos.
- 8 archivos inventariados no excluidos; 7 contenidos analizados: 4 XML, 2 PDF y 1 CER.
- 6 contenidos clasificados/importados; 1 PDF ilegible no importado.
- 1 archivo de formato no admitido sin abrir; 3 entradas excluidas, incluyendo un directorio.
- 6 documentos, 6 versiones y 6 vínculos empresariales tras reimportación.
- 2 documentos con conflicto UUID pendientes; originales SHA-256 intactos.
- Dos confirmaciones simultáneas produjeron 1 commit y 1 respuesta idempotente.
- Respaldos anterior/posterior restaurados en bases nuevas y contrastados en conteos y filas documentales/auditoría.

**No se han proporcionado ni analizado las dos carpetas empresariales reales en este flujo.** El próximo paso requiere sus rutas y autorización expresa para analizarlas. Esa autorización no sustituye la confirmación de importación posterior dentro de la aplicación.

## 8. Pruebas: interpretar por ejecución, no sumar cifras

| Ejecución | Resultado documentado |
|---|---|
| Cierre de release | 179 backend aprobadas, 1 omitida; 12 afectadas repetidas después de correcciones finales |
| Cierre: adicionales | 48 regresiones aisladas, 8 de lógica frontend, 7 del clasificador, TypeScript/build; 51 comprobaciones HTTP más rechazo de Host; PostgreSQL/restauración/concurrencia y paquete probados |
| Piloto: suite general | 193 aprobadas, 1 omitida, antes de las últimas correcciones específicas |
| Piloto: suite afectada final | 37 aprobadas; incluye 14 específicas del piloto y regresiones de identidad/importador |
| Piloto: HTTP PostgreSQL | 40 comprobaciones iniciales y 15 finales aprobadas |
| Piloto: frontend/recuperación | TypeScript sin emisión, build Vite, confirmación visual sintética y restauraciones aprobados |

Estas suites se solapan. No presentar la suma como cantidad de pruebas únicas. La suite general completa no se repitió después de cada corrección final: se repitieron las afectadas. Hay advertencias preexistentes de reflexión SQLite y deprecación; Vite avisa de chunk principal >500 KB. La omitida está relacionada con privilegios para enlaces simbólicos.

Hubo tentativas fallidas por importación del entorno Python, permisos de temporales y fixtures, documentadas y corregidas/repetidas. Una revisión automática de aprobación falló temporalmente por límite de uso; luego pudo completarse. No son aprobaciones implícitas de producción.

## 9. Esquemas y migraciones

Entre las revisiones relevantes están company_archive_0001, lote4_lifecycle_0001, lote4_schedule_0002, integral_0002_evidence_history e integral_0003_document_identity, además de las de almacenamiento/fiscal/credenciales/conciliación e integral inicial. Consultar los archivos para los nombres exactos y dependencias.

Se aplicaron explícitamente en bases sintéticas nuevas y copias restauradas. El piloto no requirió una nueva migración: reutiliza las tablas existentes. **No asumir que la base del lanzador 8000 tiene estas revisiones.** El error suministrado acredita tablas faltantes, no autoriza a ejecutar migraciones ni permite inferir por sí solo el tipo o contenido de esa base.

## 10. Respaldos y fuentes para revisión

Todos estos caminos son relativos a la raíz del proyecto, salvo los respaldos/entregas que están en la carpeta superior:

- `AGENTS.md` y `CONTINUAR_EN_CODEX.md`: leer sus secciones vigentes; hay antecedentes debajo con instrucciones históricas sustituidas.
- `docs/CS_LOTE2.md`, `docs/CS_LOTE3.md`, `docs/CS_LOTE4.md`: contratos y matrices; las secciones antiguas no representan necesariamente el estado final.
- `docs/CS_INTEGRATION_RECOVERY.md` y su inventario.
- `docs/CS_RELEASE_CLOSURE.md`, `docs/CS_RELEASE_CLOSURE_FILES.md` y `docs/INSTALL_RELEASE_WINDOWS.md`.
- `docs/CS_PILOT_IMPORT_001.md` y `docs/CS_PILOT_IMPORT_001_FILES.md`.
- Capturas sintéticas: `docs/qa-release` y `docs/qa-pilot`.
- Respaldo release: `..\RESPALDOS\CS_RELEASE_CLOSURE_20261111_225752`.
- Respaldo piloto: `..\RESPALDOS\CS_PILOT_IMPORT_20261111_180638`.
- Dentro del respaldo piloto: before.zip, baseline.json, final.json, changes.json, pilot.diff y results/summary.json con evidencias anonimizadas.

La última intervención del piloto registra 8 archivos modificados, 16 añadidos y 2 assets compilados antiguos sustituidos. Los ZIP previos conservan el build anterior. No copiar `.qa`, bases, entornos, credenciales o datos a una entrega compartida.

## 11. Bloqueos y prioridad sugerida para Claude

1. Auditar coherencia de contratos de identidad, revisiones, verificación fiscal y reimportación; buscar condiciones de carrera y pérdida de historial sin reconstruir módulos.
2. Revisar configuración y estrategia para el arranque del usuario: distinguir laboratorio 8060 de la base antigua 8000. Antes de actualizar esta última, identificarla sin revelar secretos y acordar respaldo/restauración y autorización de migración.
3. Revisar límites de exploración/extracción, aislamiento, exposición de rutas y privacidad del piloto. Los límites temporales se comprueban entre operaciones; no son una garantía de tiempo real estricto.
4. Completar QA de accesibilidad, cancelación de borradores, temas, resoluciones y flujos de certificados; no convertir comprobaciones parciales en aceptación general.
5. Resolver SCM/TLS/LAN/Windows limpio y operación de respaldos sólo con entorno y permisos autorizados.
6. Tras autorización de las dos rutas reales, preparar un piloto nuevo separado de los fixtures; analizar primero, presentar propuestas y esperar confirmación definitiva dentro de ContaSuite.

## 12. Instrucción sugerida para entregar a Claude

> Analiza este informe y los archivos fuente/documentales adjuntos. Distingue implementación, pruebas ejecutadas y aceptación pendiente. Señala riesgos concretos con referencias a archivos y contratos; no supongas que tienes acceso al repositorio por leer rutas locales. No solicites secretos ni documentos reales para una revisión inicial. No propongas reescribir módulos estables, mezclar bases sintéticas con reales, fusionar por UUID ni migrar la base del puerto 8000 sin autorización y recuperación ensayada. Prioriza los defectos demostrables y propone el siguiente paso mínimo y seguro. ContaSuite v1.0 todavía no está aprobada.
