# ContaSuite Importador y Conciliador de Empresas v0.1

## Diagnóstico y compatibilidad

Se reutiliza `Company` en `models.py`: ID estable, RFC único, razón social, régimen y responsable. No se crea otro padrón ni se modifican empresas al analizar. El sistema existente usa SQLAlchemy; la instalación local sigue configurada con SQLite, aunque admite PostgreSQL. No se cambió la conexión. PostgreSQL se verificó mediante DDL, sin instancia real.

Obligaciones expone `/api/fiscal-control` y tiene catálogo/períodos/registro/evidencias y staging específico aún sin activar. Credenciales expone `/api/credentials` y conserva una bóveda y vistas previas redactadas. Sus migraciones siguen independientes y pendientes; este importador no las ejecuta. Los contratos `fiscal_import.py` y `credential_import.py` permanecen intactos: el nuevo lector binario añade una capa de lectura/identidad común, no otro servicio de persistencia fiscal ni otra bóveda.

CS-Storage relaciona documentos mediante `Document.company_id`, `DocumentCompanyLink` y versiones/ubicaciones. El análisis documental nuevo sólo consulta ese inventario local; no usa el proveedor SMB ni el lector de archivos remotos. Las futuras asociaciones definitivas deberán pasar por la revisión versionada existente de CS-Storage, en vez de insertar vínculos paralelos. Su implementación está deliberadamente bloqueada.

La autenticación, CSRF, sesiones nominales y auditoría HTTP son las existentes. Un permiso adicional de importación por empresa se combina con el ámbito de la cuenta. Las sesiones de análisis son privadas del usuario que las creó, incluso frente a otro administrador. Inicio no se modificó.

## Archivos

Nuevos:

- `backend/app/company_xlsx.py`: lector en memoria y adaptadores de obligaciones/metadatos.
- `backend/app/company_reconcile.py`: normalización, conciliación y sugerencias documentales puras.
- `backend/app/company_import_models.py`: metadata independiente de staging, decisiones y procedencia.
- `backend/app/company_import_api.py`: análisis sintético, decisiones, reporte, confirmación bloqueada y retención.
- `backend/import_migrations/001_reconciliation.py`: migración explícita de estructuras faltantes.
- `backend/tests/test_company_import.py`: libros/empresas/documentos ficticios y pruebas de permisos.
- `frontend/src/modules/CompanyImporter.tsx` y `company-importer.css`: asistente de cuatro pasos y estilos acotados.
- Este documento.

Modificados: `backend/app/main.py` (registro del router), `backend/requirements-base.txt` (openpyxl), `frontend/src/modules/Companies.tsx` (pestaña adicional) y `CONTINUAR_EN_CODEX.md` (continuidad). Los archivos de Obligaciones, Credenciales, Alertas y CS-Storage no se modificaron.

## Lectura XLSX

Se añadió `openpyxl==3.1.5` por su soporte de XLSX, fechas, cadenas compartidas y hojas sin depender de posiciones fijas de columnas. La lectura usa BytesIO, `read_only=True`, `data_only=False` y `keep_links=False`. No guarda el archivo ni utiliza multipart, para evitar el spooling de cargas a archivos temporales. Sólo se reciben flujos binarios acotados; el nombre original se muestra en el navegador y no se persiste en el backend.

Límites: 8 MB comprimidos, 40 MB descomprimidos, 16 MB por entrada ZIP, 2.000 entradas, ratio máximo 300, 24 hojas, 100 columnas, 10.000 filas inspeccionadas en total y 3.000 registros candidatos. Se rechazan ZIP cifrados, entradas duplicadas, rutas ascendentes, macros VBA, objetos incrustados, ActiveX y relaciones externas. La dependencia defusedxml ya existente protege la lectura XML. No se evalúan fórmulas ni se usan sus resultados cacheados; se omiten y reportan por conteo. Las advertencias del parser se convierten en error genérico para evitar emitir valores de celdas.

Busca encabezados en las primeras 25 filas y reconoce equivalencias: Empresa/Razón social/Contribuyente, RFC/R.F.C., Régimen/Regímen fiscal, Contador/Responsable, ISR/I.S.R., IVA/I.V.A., ISN y demás categorías. Encabezados duplicados se marcan para revisión. Las columnas desconocidas se descartan. Las equivalencias y el registro `ADAPTERS` permiten añadir adaptaciones desde código confiable sin cambiar la lógica principal de lectura; no se permite que clientes declaren columnas sensibles como públicas.

Fuente Obligaciones: conserva valores permitidos y procedencia hoja/fila/período; distingue fechas Excel, texto de fecha no verificado, fecha de texto inválida, NA, blanco, responsable/nota y CON PAGO/SIN PAGO. Ningún valor se registra como presentado, vencido o validado ante autoridad. Una fecha escrita como texto requiere revisión aun cuando su formato sea reconocible. La detección textual es deliberadamente limitada; no interpreta todos los calendarios y variantes regionales.

Fuente Metadatos fiscales: conserva únicamente identidad, régimen, responsable y fechas de certificado reconocidas. No devuelve ni persiste contraseñas, usuarios fiscales, IDSE, SIPARE, INFONAVIT, registro patronal, correos, tokens, claves ni valores desconocidos. Los campos sensibles se descartan antes de formar propuestas. No hay persistencia ni importación de secretos, tampoco cifrados. Los secretos sólo pueden existir transitoriamente en el archivo ficticio analizado en memoria; no se promete borrado criptográfico de objetos Python.

Las hojas exponen un índice, período y diagnósticos, sin títulos arbitrarios; la procedencia del archivo es su SHA-256 y tipo. Esto evita incorporar nombres de archivo/hoja potencialmente sensibles a respuestas y auditoría. No se conserva el libro original completo. Valores no sensibles reconocidos permanecen en la propuesta hasta su eliminación/caducidad.

## Conciliación de empresas

Normaliza RFC por mayúsculas/espacios y razón social por acentos, puntuación y espacios. Reutiliza la validación de formato/fecha de RFC de CS-Storage; los RFC genéricos no se aceptan como identidad inequívoca. Un patrón correcto no prueba existencia ni validez ante SAT.

Estados: exact_rfc, possible_name, new_company, missing_rfc, identity_conflict, source_duplicate y manual_review. Los nombres alternativos se usan como candidatos. La similitud de nombre usa SequenceMatcher con umbral 0,78; es una ayuda, no una identidad. RFC coincidente con nombre muy distinto genera conflicto. Todo inicia pendiente, incluso coincidencias inequívocas.

Los duplicados de origen se detectan por RFC o nombre normalizado y período. La misma empresa en meses distintos no se considera repetida. Proponer vinculación guarda también una propuesta de nombre alternativo con procedencia; no modifica nombres validados ni escribe todavía en el catálogo de alias definitivo. Un RFC inválido no se reproduce en las respuestas y no permite proponer alta.

## Modelo de staging y migración

| Tabla | Finalidad |
|---|---|
| reconcile_sessions | Propietario, fuente, hash, resumen, idempotencia, fecha y caducidad |
| reconcile_rows | Propuestas/redacción, conflictos, procedencia y revisión concurrente |
| reconcile_decisions | Acción elegida, usuario, empresa destino, fecha y revisión |
| company_import_aliases | Alias definitivos futuros por empresa, con procedencia; sin activación automática |
| company_import_permissions | Permiso adicional de importación por cuenta/empresa |
| reconcile_history | Auditoría agregada de creación, decisiones, confirmación bloqueada y eliminación |

Las fuentes no son nuevas copias persistidas de archivos: `source` y SHA-256 en la sesión las identifican. Las propuestas contienen los conflictos y asociaciones documentales; no se crean tablas duplicadas por cada tipo de archivo. No hay otro catálogo empresarial, almacenamiento documental, tabla de obligaciones o bóveda.

La clave de idempotencia incorpora propietario, adaptador, huella de archivo/inventario, catálogo autorizado, alias y versión del motor. Repetir el mismo análisis vigente devuelve la misma sesión y conserva decisiones; un cambio del padrón/alias genera una sesión distinta. Las revisiones de decisiones rechazan ediciones concurrentes. El reporte final sólo incluye conteos y acciones, sin datos de filas.

La metadata es independiente del Base y de Alembic de CS-Storage. Sin esquema, los endpoints responden 503 sin crear tablas. La migración sólo se ensayó sobre bases temporales. `downgrade` sólo permite retirar tablas vacías para evitar perder historial. No se ejecutó ninguna migración real.

## Retención y acceso

Las sesiones caducan en 24 horas: después no se pueden leer ni editar. El propietario puede eliminar su vista previa; un administrador puede purgar sesiones caducadas mediante servicio explícito. No se habilitó un planificador automático en esta iteración. Debe programarse esa purga antes de activar un piloto operativo: caducar bloquea acceso pero no borra físicamente por sí mismo.

La purga elimina propuestas, decisiones y sesión; conserva auditoría de conteos sin nombres/RFC/secretos. Ningún archivo fuente fue guardado. La eliminación SQL no garantiza borrado físico de páginas, WAL, snapshots o backups: el operador debe aplicar cifrado de almacenamiento y retención de respaldos adecuados. No se ejecutan VACUUM ni tareas destructivas contra bases reales.

Los colaboradores requieren concesión explícita en company_import_permissions y acceso vigente a la empresa. Las sugerencias se calculan sólo contra su ámbito; RFC enmascarado en consultas no administrativas. Se revalidan permisos al consultar o decidir. Una empresa fuera del ámbito no puede ser elegida por manipulación de IDs. Las propuestas nuevas requieren administrador. La administración visual de concesiones queda pendiente; ninguna concesión real se creó.

## Endpoints

Prefijo `/api/company-imports`, autenticación obligatoria y sin caché mediante la política HTTP existente:

- `POST /preview/xlsx?source=obligations|fiscal_metadata&synthetic_only=true`: flujo binario XLSX; rechaza el modo no sintético.
- `POST /preview/inventory`: consulta acotada del catálogo local, sin red ni escaneo.
- `GET /{id}`: sesión propia vigente, propuestas filtradas y RFC enmascarado según permisos.
- `PUT /{id}/rows/{number}`: propone vincular, crear, excluir o dejar pendiente, con revisión esperada.
- `GET /{id}/report`: reporte agregado, aplicado=false y secretos importados=0.
- `POST /{id}/confirm`: requiere confirmación explícita y audita el intento; siempre responde 423 en v0.1.
- `DELETE /{id}`: descarta sólo staging propio, sin afectar originales ni empresas.
- `DELETE /maintenance/expired`: purga administrativa explícita de staging caducado.

La declaración de contenido sintético es una barrera de flujo, no un detector infalible de datos reales. No cargar libros reales hasta una autorización posterior y revisión operativa. No hay importación parcial de metadatos definitivos mientras la confirmación siga bloqueada.

## Asociación documental

Consulta como máximo 500 documentos PDF/XML/CER ya registrados; examina nombres, claves relativas, vínculos y período en la base. No abre contenidos, no recorre directorios y no lee KEY. Las rutas/nombres se usan transitoriamente como evidencia y no se exponen en la propuesta documental. Busca RFC explícito, razón social/alias y período AAAA-MM cuando sea inequívoco.

Clasifica inequívoca, probable, sin coincidencia o conflicto. Incluso una coincidencia inequívoca por metadatos exige revisión humana y puede ser incorrecta si la ruta contiene RFC ajeno. Los vínculos existentes que contradicen la sugerencia generan conflicto. Se registra el usuario que toma la decisión, pero no se aplica asociación alguna. El indicador de reindexación incremental permanece deshabilitado; no se añadió otro indexador.

El piloto documental debe realizarse primero en una base de demostración con documentos sintéticos. El endpoint no impide técnicamente que un operador autorizado consulte el inventario real; no se usó contra la instalación real durante el desarrollo.

## Asistente visual

Nueva pestaña Importar y conciliar en Empresas, con cuatro pasos: selección, análisis, conciliación y confirmación. Muestra nombre/tamaño del archivo local, resumen de estados/períodos/hojas, tabla con sugerencias y confianza, buscador, filtro, propuestas manuales, reporte agregado y botón final deshabilitado. Las advertencias del lector identifican hojas sin encabezado, fórmulas omitidas y registros por revisar.

Usa componentes/tokens Stitch existentes, estilos propios acotados, encabezados fijos, desplazamiento horizontal, botones/selectores accesibles por teclado y estados de carga/error/éxito. El progreso es por etapas, sin porcentajes de procesamiento ficticios. No se cambió Inicio ni se rediseñaron módulos existentes.

## Pruebas y limitaciones

Comprobación ampliada: **39 pruebas aprobadas**, incluyendo el importador, Credenciales, Obligaciones y dashboard documental. Existe una advertencia previa deprecada de Starlette/AnyIO. Se verifican múltiples hojas, períodos, equivalencias, fechas/blancos/NA/responsables/pago, RFC, similitud, duplicados por período, alias, archivo corrupto y tamaño, contenido incrustado, idempotencia, confirmación bloqueada, permisos/revocación/propiedad, enmascarado, redacción de secretos, caducidad/purga y propuestas documentales sin I/O remoto. DDL PostgreSQL generado sin servidor. TypeScript se comprueba sin emitir archivos.

Pendientes: QA visual y accesibilidad en navegador; compatibilidad con muestras sanitizadas de formatos reales; celdas combinadas/encabezados complejos y más fechas regionales; corrección manual de datos originales; pantalla de concesiones; ejecución final transaccional y supervisada que revalide padrón/roles/revisiones antes de crear empresas o usar los servicios existentes. La coincidencia aproximada no basta para fusionar. No se deben reutilizar propuestas caducadas o antiguas para escribir directamente.

## Piloto propuesto, todavía no ejecutado

1. Aprobar una base aislada nueva con dos empresas ficticias y aplicar sólo allí la migración preparada. No cambiar `.env` ni usar el servidor real.
2. Preparar XLSX sintéticos con dos meses, RFC repetido en períodos distintos, un duplicado del mismo período, un nombre aproximado, un RFC faltante y columnas de secretos falsos.
3. Analizar cada fuente dos veces: comprobar que conserva el mismo ID, que no aparecen secretos/fórmulas y que no cambia el número de empresas.
4. Proponer vínculos/exclusiones con cuentas de ámbitos distintos; comprobar revisión concurrente, auditoría y rechazo de acceso ajeno.
5. Preparar documentos sintéticos en CS-Storage de esa base y revisar sugerencias sin activar SMB ni escribir en originales.
6. Revisar resumen, verificar que confirmación sigue bloqueada y eliminar/purgar staging. Autorizar cualquier siguiente etapa por separado.

No se compilaron fuentes, no se desplegó, no se importaron libros reales y no se modificaron datos/configuraciones existentes. La pestaña nueva no aparecerá en la entrega compilada actual hasta una futura compilación expresamente autorizada.
