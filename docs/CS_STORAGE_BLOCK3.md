# CS-Storage v0.1 — bloque 3

Indexación local independiente y clasificación determinista integradas en el Centro Documental existente. Se conserva el diseño de Stitch y sus tres temas. No se compiló, empaquetó ni actualizó `frontend/dist`; tampoco se modificaron `.env`, `data/`, `agent/config.json` o la base real.

## Archivos

| Archivo | Responsabilidad |
|---|---|
| `backend/app/storage/indexer.py` | Cola persistida, exclusión global de trabajadores, leases, checkpoints, inventario, versiones, duplicados e incidencias. |
| `backend/app/storage/worker.py` | Proceso independiente de FastAPI; consume trabajos con sondeo o `--once`. |
| `backend/app/storage/classifier.py` | Reglas RFC v1 para XML CFDI y PDF con texto; evidencia acotada, roles y periodo XML. |
| `backend/app/storage/classify_process.py` | Extracción aislada con límite de memoria del proceso. |
| `backend/app/storage/review.py` | Propuestas, confirmación, corrección, rechazo, responsable, control de revisión y duplicados visibles según permisos. |
| `backend/app/storage/service.py` | Integra revisiones y protege observaciones del trabajador con su lease; las versiones externas nuevas requieren nueva clasificación. |
| `backend/app/storage/catalog.py` | Oculta versiones posteriores pendientes de revisión a actores sin administración global. |
| `backend/app/storage/router.py` | Solicitud/historial de análisis, consulta/análisis/resolución RFC y posibles duplicados, con autenticación existente. |
| `frontend/src/modules/StorageJobs.tsx` | Solicitud e historial de análisis locales dentro de Documentos. |
| `frontend/src/modules/StorageReview.tsx` | Evidencia RFC, propuestas, edición de empresa/rol, decisiones y coincidencias de contenido. |
| `frontend/src/modules/Documents.tsx`, `types.ts`, `styles.css` | Integración de los paneles y estilos con los controles compartidos. |
| `scripts/storage_demo.py` | Demo sintética reproducible, exclusivamente en una carpeta nueva y desechable. |
| `backend/tests/test_storage_indexer.py` | 14 pruebas nuevas del bloque. |

Se reutilizan las tablas creadas por la revisión Alembic 0002. Este bloque no cambia el esquema ni modifica las migraciones históricas.

## Indexación y reanudación

La API encola un origen ya registrado, identificado por ID. No recibe rutas físicas ni identidades del cliente. El trabajador obtiene su raíz y exclusiones de la configuración privada y vuelve a validarlas contra `CS_STORAGE_ALLOWED_ROOTS`. Las fuentes internas y SMB no se admiten como trabajos locales.

Sólo hay un trabajador con lease activo en toda la cola. La reclamación se serializa mediante una fila existente de `storage_sources`, con actualización transaccional, tanto en SQLite como en el dialecto PostgreSQL. El lease dura 120 segundos, se renueva al avanzar y se comprueba antes de guardar observaciones, clasificación y checkpoint. Un propietario obsoleto no puede finalizar el trabajo de otro. No depende de un bloqueo de archivo ni del proceso FastAPI.

Cada archivo terminado guarda su digest de clave, resultado y contadores en `StorageIndexJob.checkpoint`. Después de una interrupción se vuelve a enumerar el origen y se omiten las entradas ya terminadas de ese trabajo. Una interrupción entre la observación y el checkpoint puede repetir la lectura; las huellas, revisión actual y decisiones registradas impiden duplicar versiones o deshacer decisiones humanas. El proceso debe recuperar el lease vencido; no hace falta subir otra vez los documentos.

El análisis incremental vuelve a comprobar SHA-256, incluso si tamaño y fecha no cambiaron. Sólo un cambio de contenido crea una versión. Para archivos sin cambios se omite la extracción cuando ya existe una clasificación válida para el mismo catálogo de RFC. Si cambia ese catálogo, se revisan las propuestas y decisiones automáticas; las resoluciones humanas de la misma versión se conservan.

Los duplicados son candidatos con la misma huella en documentos distintos y versiones actuales. No se fusionan contenidos, empresas, documentos ni permisos. El detalle sólo lista candidatos accesibles para el actor.

Un inventario completo y sin errores puede marcar ubicaciones ausentes como `missing`, conservando el documento y su historial. Las exclusiones no cuentan como desapariciones. Si hay un error de acceso, enlace, lectura, formato o límite de recorrido, se conserva una terminación `completed_with_errors` y **no se infieren desapariciones de ese recorrido**. Las ubicaciones afectadas por errores concretos se actualizan como denegadas, modificadas o no disponibles. Los códigos se registran en auditoría; no se guardan mensajes del sistema operativo en respuestas públicas.

Los originales externos nunca se renombran, copian dentro de su carpeta, modifican o borran. Las versiones conservan metadatos y huellas: si el origen reemplaza un archivo, la versión anterior no implica que sus bytes hayan sido archivados.

## Reglas RFC v1

- XML: lectura segura, sin DTD ni entidades. Sólo un `Comprobante` en el namespace CFDI 3/4, con un emisor y receptor reconocibles y válidos por estructura/fecha, puede vincular automáticamente. Distingue `issuer` y `receiver`; los RFC genéricos no identifican empresas. El periodo se toma de `Fecha`, si es válido entre 2000 y 2100. Otros XML ofrecen sugerencias y requieren revisión.
- PDF: texto seleccionable, hasta 10 páginas y 100,000 caracteres. Un único RFC identificable en todo el contenido examinado, registrado en una sola empresa y con extracción completa, permite vínculo `owner`. Varios RFC, contenido truncado, cifrado o ilegible requieren revisión. Un PDF sin texto queda pendiente; no se hace OCR.
- Nunca se clasifica por el nombre del archivo, la carpeta o la fecha de carga. No se verifica el RFC contra el SAT, su homoclave oficial ni la validez fiscal del documento.
- Si emisor y receptor son empresas distintas registradas, ambos se proponen y se requiere revisión. Una asignación manual previa nunca se sustituye automáticamente.
- Los certificados públicos CER admitidos permanecen disponibles, pero su clasificación es manual. No se interpreta su vigencia. Las llaves privadas y contenedores siguen excluidos.

La evidencia pública contiene RFC, roles y motivos, no texto completo del PDF, claves físicas o rutas. Las propuestas están ligadas a una versión. Confirmar usa los vínculos propuestos; corregir guarda las empresas y roles elegidos; rechazar descarta la propuesta y conserva vínculos confirmados anteriores. Sin vínculos anteriores, el documento queda `rejected` y sale de pendientes. Una resolución obsoleta devuelve 409. Cada decisión registra el actor del servidor y la fecha.

En este bloque, HTTP utiliza `APP_TOKEN` y el actor `installation_admin`. El trabajador se identifica como `cs_storage_indexer`, y conserva `requested_by` en el trabajo. No se presentan estas identidades técnicas como usuarios personales. Los endpoints de análisis/indexación y la evidencia global requieren administración; las concesiones individuales y sesiones corresponden al bloque 4.

## Límites y operación

El proveedor limita el recorrido a 30,000 entradas y 60 segundos, y las lecturas al tamaño configurado. El tiempo de recorrido incluye el trabajo entre entradas: una carpeta grande puede quedar parcial y necesita dividirse en raíces menores o ajustar los límites del servicio. El checkpoint se acota también a ese máximo. No se promete terminar automáticamente un árbol que siempre supera el límite.

La extracción utiliza un subproceso por archivo, hasta 25 segundos y 384 MB de memoria, con Job Object en Windows o `RLIMIT_AS` en POSIX. Admite hasta 25 MB para clasificación y 10,000 empresas en el catálogo enviado al extractor; exceder esos límites deja la clasificación pendiente. La carga/descarga conserva el límite independiente de `CS_STORAGE_MAX_FILE_MB`. Sólo se admite una extracción simultánea por proceso consumidor; el worker tiene además exclusión global en la base. Un despliegue HTTP con múltiples procesos deberá incluirse en la validación del bloque 4.

El límite de 60 segundos del recorrido no es un timeout de acceso del sistema de archivos. No se usa UNC ni una carpeta remota en esta etapa. El worker no purga objetos internos huérfanos ni staging; esa reconciliación sigue pendiente y no elimina archivos automáticamente.

El backend debe haber iniciado o ejecutado las migraciones antes de arrancar el trabajador. Desde `backend`, con el mismo entorno/configuración de la API:

```powershell
../.venv/Scripts/python.exe -m app.storage.worker --once
# O permanecer consumiendo la cola:
../.venv/Scripts/python.exe -m app.storage.worker
```

En Empresas → Documentos → Análisis de carpetas locales se selecciona un origen registrado y se solicita el análisis. La interfaz consulta los trabajos activos cada cinco segundos; también permite actualizar manualmente. Si no hay trabajador, el estado permanece en cola: no se muestra progreso ficticio. Se pueden detener los trabajadores con Ctrl+C; los trabajos interrumpidos se recuperan al vencer el lease. Todavía no hay análisis programado ni formulario para registrar fuentes: la configuración y frecuencia corresponden al bloque 5. El registro local mediante `StorageService.register_local` ya existe desde el bloque 1.

Endpoints nuevos, todos bajo `/api/storage` y autenticados:

| Método y ruta | Uso |
|---|---|
| `GET /index-jobs` | Últimos 30 trabajos, contadores y estado; no expone checkpoints ni rutas. |
| `POST /index-jobs` | Encolar `{source_id}`; devuelve el trabajo activo del origen si ya existe uno. |
| `GET /documents/{id}/reviews` | Evidencia, propuestas e historial de hasta 50 revisiones. |
| `POST /documents/{id}/classify` | Analizar contenido de una carga interna o documento accesible, con extractor aislado. |
| `POST /documents/{id}/reviews/{review_id}` | `{revision, action, links}`; acciones `confirm`, `correct`, `reject`. |
| `GET /documents/{id}/duplicates` | Hasta 20 candidatos accesibles con igual huella actual. |

## Demo y pruebas

Desde la raíz del proyecto, especificando siempre una carpeta **inexistente**:

```powershell
.venv/Scripts/python.exe scripts/storage_demo.py --output .qa/storage-demo-nueva
```

El script rechaza reutilizar una carpeta. Genera empresas y RFC ficticios, XML/PDF, rutas anidadas, nombres contradictorios, duplicados, archivos sin RFC, exclusiones y una llave ficticia que no se procesa. Ejecuta tres escenarios: inicial; modificación/desaparición; acceso denegado simulado. Sólo modifica/borra los fixtures creados dentro de ese directorio desechable. Escribe una base aislada, `report.json` y `environment.json`; no cambia `.env` ni usa la base real. La simulación de denegación no cambia ACL del equipo ni pretende ser un permiso del servidor Windows.

`environment.json` contiene `DATABASE_URL`, `DATA_DIR` y `CS_STORAGE_ALLOWED_ROOTS` de la demo para reutilizarlos en procesos locales separados. Esos valores se aplican sólo al entorno de prueba; nunca reemplazar con ellos la configuración del despacho. `.qa/` está excluido de las entregas.

Validación: 84 pruebas aprobadas, una omitida por privilegios de symlink de Windows y una advertencia previa de Starlette/AnyIO. Las 14 nuevas cubren reglas XML/PDF, asociación/ambigüedad, metadatos idénticos con bytes cambiados, lectura sola, historial, duplicados y aislamiento, desapariciones/exclusiones/límites, acceso denegado, reanudación y propietario vencido, conservación de decisiones humanas, cambios del catálogo y ejecución real del CLI como proceso separado. TypeScript `--noEmit` correcto.

Revisión en Edge con Vite y FastAPI de desarrollo sobre una base ficticia: confirmar/corregir/rechazar, extracción solicitada desde interfaz, cola y trabajador independiente hasta completarse, tres temas, vista móvil sin desbordamiento horizontal y sin errores de JavaScript. No se generó compilación. PostgreSQL conserva la cobertura DDL previa; no se probó contra un servidor PostgreSQL real ni contra SMB.

## Siguiente bloque

Bloque 4: cuentas/sesiones nominativas, permisos integrales y auditoría con validación de seguridad. Después, bloque 5: configuración del futuro conector Windows, orígenes y frecuencia. La conexión real al despacho y sus permisos se validarán presencialmente. Dashboard y vigencia FIEL permanecen fuera de este bloque.
