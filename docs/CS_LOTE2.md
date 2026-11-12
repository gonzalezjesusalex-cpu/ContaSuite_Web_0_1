# CS-IMPLEMENT — Lote 2: Empresas y navegación combinada

Fecha: 11 de noviembre de 2026. Código preparado en `ContaSuite_Web_0_1`; sin compilación, activación de esquema ni despliegue.

## Preparación y respaldo

Se leyeron AGENTS.md, CONTINUAR_EN_CODEX.md y el informe de integración del Lote 1. Se comprobó la presencia de fiscal_read, los consumidores y el ejecutor de regresión. Antes de editar se respaldaron las fuentes existentes y sus huellas SHA-256 en:

`../RESPALDOS/CS_LOTE2_20261111_144333/antes_lote2.zip`

`baseline.json` conserva las huellas anteriores; `changes.json`, los archivos intervenidos; `final.json`, las huellas posteriores; `lote2.diff`, las diferencias. Se verificó el ZIP antes y después. No se copiaron datos ni configuración privada.

Para recuperar el código, preservar primero cualquier trabajo posterior y restaurar **solo** los archivos modificados enumerados en changes.json desde el ZIP, respetando sus rutas relativas. Verificar las huellas anteriores con baseline.json. Los añadidos se pueden retirar únicamente tras comprobar sus huellas posteriores y preservar modificaciones posteriores. No superponer carpetas completas ni tocar `.env`, `data/`, bases, `agent/config.json` o `frontend/dist`. No se ejecutó recuperación ni migración. Si el esquema se activara posteriormente, recuperar código no equivale a revertir datos: conservar las tablas/eventos y revisar compatibilidad; la reversión destructiva está deshabilitada.

## Decisiones implementadas

- Archivado separado de `integral_company_activity`: esa tabla expresa actividad fiscal/operativa y permanece intacta.
- Nuevas tablas explícitas `company_archive_states` y `company_archive_events`, en metadata independiente de Base. Estado actual con revisión optimista y eventos con actor, empresa, fecha, acción y antes/después. No se borran empresas, documentos, obligaciones, permisos ni relaciones.
- Archivar/restaurar requiere administrador, igual que la administración empresarial existente. Lectura de expediente/historial conserva permisos por empresa. Archivar no cambia concesiones.
- `DELETE /api/companies/{id}` conserva autenticación administrativa y responde 409 sin borrar datos. El botón de eliminación se sustituyó por archivar/restaurar.
- RFC normalizado antes de validar: se eliminan espacios y se convierten letras a mayúsculas. Altas/ediciones comprueban duplicados normalizados excluyendo el propio ID. PostgreSQL serializa esa comprobación mediante bloqueo transaccional por RFC; la restricción única existente sigue siendo defensa final. Duplicados históricos se señalan, sin fusionarlos ni modificarlos.
- Directorio reutilizado: búsqueda por nombre/RFC/nombre comercial, contador, estado fiscal compartido, activas/archivadas/todas y orden estable por nombre/RFC/contador con desempate por ID. Tabla, formularios y paginación existentes conservados. Adjuntos directos provienen de los documentos visibles de bootstrap; no representan completitud documental ni clasificación consolidada.
- Respuestas de carga/error/vacío diferenciadas. No se inventa un estado de archivo cuando falta esquema.
- Expediente organizado en Resumen, Obligaciones, Documentos, FIEL/CSD y Actividad. Las vistas anteriores siguen accesibles como subvistas, incluyendo históricos fiscales, explorador, credenciales, CER, tareas, declaraciones y bitácora administrativa. Se conserva la distinción entre vigencia temporal y validación SAT pendiente.
- Selector autorizado con archivadas excluidas por defecto, inclusión explícita y conservación de la empresa archivada actualmente abierta. Cambio de empresa remonta el expediente por ID; los borradores empresariales se separan por usuario y empresa.
- Se conservan sección compatible, periodo y filtros del directorio. Al cambiar de empresa no se trasladan subformularios, IDs documentales ni evidencias. Enlaces a Dashboard y Control conservan periodo; Dashboard admite contexto empresarial explícito.
- Router de datos de React Router para bloquear navegación pendiente. Guardas de formularios/diálogos, cambios de sección, selector, cierre y salida del navegador piden confirmación antes de descartar cambios. Guardar un formulario no limpia otros borradores. Las pruebas de estas reglas no sustituyen QA real del router en navegador.

## Capturas en archivadas

Permitidas con permisos normales. Aviso visible al abrir expediente/editar empresa. Confirmación previa al guardar en los flujos cubiertos. Guardar no restaura la empresa. El backend fiscal no introduce bloqueos de escritura por archivado.

| Flujo existente | Cobertura de advertencia de este lote |
|---|---|
| Edición de datos empresariales | Aviso visible y confirmación en PUT de empresa |
| Nueva celda fiscal, edición fiscal y aplicabilidad | Confirmación antes de PUT; captura explícita por empresa archivada permitida |
| Tareas y obligaciones anteriores mediante API compartida | Confirmación en POST/PUT cuando la empresa está archivada |
| Cambio rápido de estado de tarea/obligación | Misma confirmación en la operación compartida |
| Documentos: cargas, clasificación, vínculos y análisis | Fuera de la advertencia específica de captura; componentes preservados, sin consolidación documental |
| Credenciales, certificados y asignación de uso CER | Fuera de la advertencia específica de captura; operaciones sensibles conservan sus bloqueos |
| Opiniones y seguimiento CFDI manual | Fuera de la advertencia específica de captura; no se afirma cobertura completa |
| Recopila, CFDI, Declara, Recibos, importador, agente | Fuera del alcance de nuevas advertencias; módulos conservados |
| Clientes directos de API | Autorización backend vigente; las confirmaciones son interacción de la interfaz, no una nueva condición de autorización |

Las guardas de salida observan cambios en formularios/diálogos montados; no certifican detección de toda interacción programática, selector de archivos o editor externo. Se incluyó recuperación de borrador empresarial como cambio pendiente. La cobertura de esos componentes requiere QA posterior.

## Esquema preparado, NO ejecutado

`backend/company_migrations/001_archive.py`, revisión `company_archive_0001`, crea solo las tablas de archivado. No está en la cadena Alembic ni en el arranque. Requiere tabla companies existente. No transforma históricos, ni usa almacenamiento del navegador como sustituto de persistencia.

**Antes de activarlo:** respaldo consistente y restauración aislada comprobada; revisar tablas/columnas/FK, permisos y concurrencia PostgreSQL; aplicar posteriormente con conexión explícita y autorización. Si existe una tabla incompatible, `create_all` no la repara: revisar equivalencia previamente. Las guardas actuales comprueban tablas y nombres de columnas, no toda equivalencia de tipos/índices.

**Mientras falte esquema:** directorio con archivado y operaciones/historial de archivo responden 503. Bootstrap añade `archive_available=false` y estado desconocido (`null`), no una persistencia ficticia. Los expedientes existentes mantienen acceso autorizado. El selector puede incluir expresamente empresas de bootstrap; no afirma conocer su estado. El directorio nuevo no estará operativo hasta activar posteriormente la migración. Esta limitación es deliberada y no es aceptación de demo.

Con el esquema disponible, ausencia de fila de estado significa empresa nunca archivada (activa en archivo); las operaciones crean estado/evento explícito. Esto no determina actividad fiscal. Las listas fiscales/globales excluyen archivadas por defecto; consulta explícita de expediente o inclusión expresa las admite. El contrato fiscal y sus denominadores no se recalculan en React.

## Validación ejecutada ahora

- **27 pruebas backend**, incluyendo las **17 regresiones fiscales** del Lote 1. SQLite exclusivamente en memoria; tablas sintéticas mediante metadata de prueba, sin ejecutar migraciones. dotenv bloqueado antes de importar datos; tokens sintéticos, raíces locales/SMB vacías, bóveda vacía, red/procesos bloqueados y almacenamiento temporal junto al respaldo. No se importa ni inicia app.main. La protección del endpoint DELETE se inspecciona por AST sin arrancar FastAPI.
- Cubiertos búsqueda/filtros/orden, RFC normalizado y autoedición, duplicados sin fusión, archivado/restauración, documentos/registros conservados, auditoría, revisión obsoleta, captura en archivada, concesiones y actividad fiscal intactas, ámbitos y principal sin permisos tras revocación, exclusión/inclusión expresa y esquema ausente.
- **5 pruebas frontend de lógica pura** con Node y TypeScript interpretado sin emisión: navegación/contexto sin evidencias trasladadas, aliases de sección, consentimiento para descartar, borradores independientes y avisos de captura en archivadas. No abren navegador, aplicación ni conexiones.
- TypeScript `--noEmit` aprobado con dependencias existentes. No se ejecutó Vite ni se emitieron bundles.
- AST backend válido; comparación del diff contra respaldo y comprobación de que seguridad, importador y bóveda no cambiaron. El test fiscal de protección anterior se adaptó para permitir los cambios empresariales autorizados, manteniendo comparación de escrituras fiscales/tareas y módulos sensibles.

Registros en `backend.json`, `frontend_units.json`, `typescript.json` y `final.json` junto al respaldo. Son resultados nuevos; no se presentan validaciones históricas como actuales.

## Pendientes y riesgos

- QA visual y funcional real: router, confirmación al retroceder, teclado/foco, temas, móvil, selectores, diálogos, archivos y descarga CSV. TypeScript no acredita estas verificaciones.
- HTTP autenticado y revocación de sesión/concesiones en vivo: se probó ámbito de un principal actualizado; no un flujo HTTP completo de revocación.
- Dos transacciones realmente simultáneas, bloqueo PostgreSQL y rendimiento de listas grandes. Se probó conflicto por revisión obsoleta, no una carrera real.
- No se ejecutó la suite histórica completa porque contiene fixtures de migración. No hubo pruebas PostgreSQL, SMB, SAT ni servicios.
- El esquema de archivado no está activado y hay cobertura de advertencias deliberadamente parcial, inventariada arriba.
- Se conservan limitaciones fiscales del Lote 1 (aplicabilidad temporal, condición de pago y verificación concurrente). No se consolidaron documentos/certificados/alertas de otros lotes.

## Archivos

El inventario exacto está en changes.json junto al respaldo. Backend: company_lifecycle, main, schemas, integración fiscal para excluir/incluir archivadas y ejecutores de pruebas. Frontend: Directorio, Expediente, formulario, navegación/guardas, contexto, advertencias, API compartida, tipos, router, componentes de diálogo/actividad y pruebas. Migración nueva independiente y este informe. No se modificaron estilos, diseños Stitch, motores de automatización ni Inicio.

No se modificaron `.env`, `data/`, bases reales o `agent/config.json`. No hubo migraciones, arranque, compilación, despliegue, acceso SMB/SAT ni cambios en `frontend/dist`. Importación definitiva y revelación permanecen bloqueadas. El trabajo se detiene en el Lote 2 para revisión; no se inició el Lote 3 ni se declara aprobada una demo.
