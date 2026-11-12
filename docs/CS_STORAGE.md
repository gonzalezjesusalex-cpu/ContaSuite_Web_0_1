# CS-Storage v0.1 — bloques 1 a 5 y versión de visita

El bloque 1 implementa el núcleo documental y las migraciones. El bloque 2 conecta el Centro Documental dentro de Empresas y expone endpoints restringidos al administrador de la instalación. El bloque 3 incorpora el trabajador independiente, indexación incremental y clasificación RFC con decisiones auditadas. El bloque 4 incorpora cuentas, sesiones revocables, permisos y auditoría; reemplaza el acceso compartido tras el alta del primer administrador. Consulta `docs/CS_STORAGE_BLOCK2.md`, `docs/CS_STORAGE_BLOCK3.md` y `docs/CS_STORAGE_BLOCK4.md` para cada etapa. El cierre del bloque 5 y el dashboard/CER están documentados en `docs/CS_STORAGE_BLOCK5.md`. El usuario autorizó la compilación del frontend para la visita: está actualizada y verificada; no se generó instalador ni paquete. SMB remoto permanece pendiente y no se contactó al despacho. La guía operativa es `LISTO_PARA_VISITA.md`. Las pruebas se ejecutan con información sintética en bases y carpetas temporales; no se ha migrado la base real de esta instalación durante el desarrollo.

## Componentes y archivos

| Archivo | Responsabilidad |
|---|---|
| `backend/app/models.py` | Amplía `Document` y define orígenes, versiones, ubicaciones, vínculos, trabajos, revisiones y eventos. Reutiliza `Company`; no crea otro catálogo de empresas ni una tabla ficticia de usuarios. |
| `backend/app/storage/providers.py` | Contratos separados de lectura y escritura, metadatos y errores con códigos públicos. |
| `backend/app/storage/paths.py` | Claves relativas, formatos permitidos, raíces autorizadas y rechazo de enlaces/reparse points. |
| `backend/app/storage/local.py` | Proveedor externo de sólo lectura; recorrido acotado, exclusiones, metadatos y lectura por identificador relativo. |
| `backend/app/storage/internal.py` | Repositorio privado; staging, publicación atómica sin reemplazo, límites y huellas SHA-256. |
| `backend/app/storage/settings.py` | Configuración explícita y raíces externas inicialmente vacías. |
| `backend/app/storage/service.py` | Registro de orígenes, cargas/versiones internas, observación individual de archivos externos, lecturas verificadas, límites por empresa y eventos. |
| `backend/app/storage/schemas.py` | Respuestas públicas que no contienen rutas físicas, claves del proveedor ni secretos. |
| `backend/app/storage/smb.py` | Proveedor pendiente: no conecta, no enumera UNC y nunca devuelve un éxito ficticio. |
| `backend/alembic.ini`, `backend/migrations/env.py` | Ejecución versionada de migraciones en una conexión explícita. |
| `backend/migrations/versions/0001_legacy_documents.py` | Valida/adopta las tablas actuales; crea Empresas/Documentos en bases nuevas. |
| `backend/migrations/versions/0002_storage_core.py` | Amplía Documentos, crea las tablas documentales y registra los adjuntos anteriores sin abrir sus archivos. |
| `backend/migrations/schema_v01.py` | Instantánea del esquema de la revisión 0002. No modificarla al añadir futuras revisiones. |
| `backend/app/storage/migrate.py` | Punto de entrada de las migraciones; admite un engine temporal de prueba. |
| `backend/app/main.py` | Ejecuta migraciones al arrancar y protege los documentos con historial de borrados por rutas antiguas. Registra el router documental autenticado. |
| `backend/requirements-base.txt` | Alembic 1.20.1 y defusedxml 0.7.1; aplican tanto a SQLite como al perfil PostgreSQL. |
| `.env.example` | Variables nuevas documentadas; el archivo `.env` existente no se modifica. |
| `backend/tests/test_storage_core.py`, `test_storage_migrations.py` | Pruebas de proveedores, servicio, aislamiento, integridad y migraciones. |
| `backend/tests/test_api.py` | Limpia también la revisión Alembic al recrear su base temporal; nunca apunta a la base real. |

## Datos e integridad

`Document` conserva su identificador, nombre y compatibilidad con los adjuntos anteriores. Se permite `company_id = NULL` para documentos pendientes y `storage_name = NULL` para documentos gestionados mediante proveedores. La revisión actual se controla de forma atómica para rechazar escrituras con una versión obsoleta.

Las tablas nuevas son:

- `storage_sources`: orígenes y configuración privada.
- `document_versions`: versiones con número, nombre, tamaño, huella y responsable.
- `document_locations`: ubicaciones por versión, claves relativas privadas y disponibilidad.
- `document_company_links`: relaciones con empresas y roles, sin duplicar empresas.
- `storage_index_jobs`: estados, checkpoints y leases del trabajador independiente del bloque 3.
- `document_classification_reviews`: evidencia, propuestas y decisiones de revisión ligadas a una versión.
- `storage_events`: operaciones del núcleo, actor, resultado y códigos de error sin mensajes del sistema de archivos.

Las huellas no son únicas: dos empresas pueden tener archivos idénticos sin que se fusionen documentos ni permisos. El índice de SHA-256 permite detectar posibles duplicados actuales en el bloque 3, filtrados por permisos. Las versiones anteriores siguen registradas. Una ubicación externa sobrescrita se marca `superseded`; guardar metadatos de una versión anterior no implica conservar sus bytes si sólo existían en una carpeta externa.

Las lecturas del servicio comprueban tamaño y SHA-256 antes de entregar un buffer al consumidor. Si el archivo desaparece o cambia, no se entregan bytes sin verificar; la disponibilidad se actualiza con el error correspondiente y puede recuperarse al reaparecer el contenido esperado. No se borra su historial.

La escritura usa únicamente nombres generados dentro del repositorio privado. Se escribe en staging, se verifica el formato, se sincroniza y se publica mediante un enlace físico atómico sin reemplazo. El sistema de archivos del repositorio debe soportar enlaces físicos dentro del mismo volumen (probado en NTFS). Si la publicación o transacción falla, se retira sólo el objeto creado por esa operación. Una interrupción abrupta del proceso puede dejar un objeto privado huérfano o staging residual: su reconciliación sigue pendiente; no se purgan archivos automáticamente.

## Proveedores y límites

**LocalFolderProvider** sólo accede a raíces locales explícitamente autorizadas. No tiene métodos de escritura. Rechaza claves absolutas, `..`, ADS de Windows, nombres reservados, enlaces simbólicos y puntos de unión, incluso dentro de una raíz autorizada. Las exclusiones se aplican tanto al recorrido como a lecturas directas. En Windows valida la ruta final del handle abierto; en POSIX abre los componentes con descriptores y `O_NOFOLLOW`.

El recorrido tiene por defecto un máximo de 30,000 entradas y 60 segundos. Al llegar al límite informa `scan_limit`; no es un inventario completo y no debe utilizarse para marcar archivos desaparecidos. Los errores de una subcarpeta se registran y se continúa con las demás. No hay concurrencia adicional dentro del proveedor.

**InternalStorageProvider** escribe exclusivamente dentro de `DATA_DIR/cs-storage`, fuera de las rutas estáticas de la aplicación. Los directorios se crean al efectuar una escritura, no al consultar disponibilidad. Los permisos NTFS de la cuenta que ejecute el backend deben limitar también el acceso físico al repositorio; el proveedor no sustituye una ACL del sistema operativo.

Desde el bloque 2, el flujo admite PDF, XML y certificados públicos CER, con un máximo predeterminado de 25 MB por archivo. Comprueba la firma inicial de PDF y XML sin DTD, entidades ni recursos externos. No certifica que un PDF sea fiscalmente válido ni incorpora OCR. Excluye `.key`, `.pem`, `.pfx`, `.p12`, archivos comprimidos y otros formatos no admitidos. Los CER se validan mediante un lector X.509 y sólo admiten un certificado público; se rechazan claves privadas y datos anexos. El dashboard de visita interpreta fechas UTC y RFC de CER públicos, con uso FIEL/CSD declarado. No valida autenticidad, revocación o acceso SAT y no implementa custodia de llaves privadas.

**WindowsSMBProvider** devuelve `pending_configuration` / `smb_not_configured`. No recibe contraseñas, no inicia conexiones ni representa una implementación productiva. El contrato comparte disponibilidad, enumeración, metadatos y lectura con el proveedor local. El bloque 5 guarda la preparación del servidor y referencia no secreta de identidad como borrador desactivado. La operación remota, cuenta/permisos, desconexiones y reintentos requieren completar y validar el adaptador en el entorno del cliente; no se habilitan por guardar el borrador. El modo operativo disponible usa carpetas físicas locales con API/indexador en el servidor Windows.

## Configuración y ejecución

Se conservan `DATABASE_URL`, `DATA_DIR`, `APP_TOKEN` y `AGENT_TOKEN` existentes. Variables nuevas:

| Variable | Predeterminado | Uso |
|---|---|---|
| `CS_STORAGE_ALLOWED_ROOTS` | `[]` | Array JSON de raíces absolutas autorizadas para fuentes locales. Ninguna carpeta externa queda autorizada implícitamente. |
| `CS_STORAGE_MAX_FILE_MB` | `25` | Límite por archivo, entre 1 y 100 MB. |

Ejemplo de configuración local ficticia, todavía sin modificar `.env`:

```dotenv
CS_STORAGE_ALLOWED_ROOTS=["C:/ContaSuite-Demo/servidor"]
CS_STORAGE_MAX_FILE_MB=25
```

No utilizar la carpeta privada interna o la de adjuntos anteriores como fuente externa; el servicio rechaza ese solapamiento. El constructor `StorageSettings` permite límites pequeños y rutas temporales en las pruebas.

Desde la raíz del proyecto, preparar el entorno existente:

```powershell
.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
```

Las migraciones se ejecutan al arrancar FastAPI, antes de crear las restantes tablas existentes. Antes de arrancar una instalación con datos, respaldar su base y `data/`. También pueden ejecutarse explícitamente, desde `backend`, contra la base que indique `DATABASE_URL`:

```powershell
../.venv/Scripts/python.exe -m app.storage.migrate
```

Ese comando sí modifica el esquema de la base configurada: no ejecutarlo contra una instalación real sin el respaldo. Durante este desarrollo sólo se llamó `upgrade_storage` con engines temporales de prueba. No se requiere conexión al despacho ni se cambia SQLite a PostgreSQL automáticamente.

Las revisiones son ascendentes e idempotentes. No implementan un downgrade destructivo: restaurar una copia verificada para revertir. La migración SQLite usa una transacción real y reconstruye Documentos conservando filas e índices. Si detecta dependencias entrantes ajenas al esquema original, se detiene y revierte, en lugar de arriesgar datos al reconstruir la tabla. Las revisiones no importan modelos vivos para generar su esquema: 0002 usa su instantánea versionada y 0003 declara el esquema aditivo de identidad de forma explícita.

Los adjuntos anteriores se registran con los mismos identificadores y nombres, una versión inicial sin SHA-256 y una ubicación `unchecked`. La migración no abre ni comprueba archivos, y no afirma que estén disponibles. El servicio verifica y registra esas huellas en el primer acceso al contenido, sin mover los archivos. La ruta de descarga anterior también utiliza el mismo servicio verificado desde el bloque 2. Los documentos con historial y sus empresas quedan protegidos contra borrado desde las rutas antiguas. Los adjuntos creados por el endpoint anterior se validan por contenido y se incorporan al historial al comprobarlos o descargarlos; conservan el mismo identificador y archivo físico.

Desde el bloque 2, `/api/state` incluye metadatos públicos mínimos de los documentos anteriores y nuevos, sin claves físicas. `/api/documents/{id}/download` delega en la misma verificación de CS-Storage; no constituye una vía alternativa para descargar contenido modificado.

## Identidad y permisos: bloque 4

El núcleo exige un `StorageActor` construido por código confiable del servidor. Desde el bloque 4 procede de la sesión personal; no se aceptan identidad ni concesiones en payloads ordinarios. Las cuentas usan contraseñas scrypt y cookies HttpOnly/CSRF con revocación y caducidad. La clave APP_TOKEN sólo conserva la transición anterior al alta del primer administrador; después deja de autorizar.

Los colaboradores tienen lectura o escritura por empresa en Empresas, tareas, obligaciones y documentos, incluidas las rutas anteriores. La revisión global, orígenes, usuarios, auditoría, agentes y motores con historial global requieren administración. Se filtran resultados y rutas antes de enviarlos al navegador. Consultar `docs/CS_STORAGE_BLOCK4.md` para la matriz, migración 0003, uso, recuperación local y límites de despliegue.

## Pruebas y próximos bloques

Desde `backend`:

```powershell
../.venv/Scripts/python.exe -m pytest -q
```

Las pruebas nuevas cubren migraciones repetidas sobre una base anterior y una vacía, conservación de archivos e identificadores, rollback con dependencias inesperadas, proveedores, exclusiones, errores de lectura simulados, un punto de unión real en Windows, límites, versiones, colisiones, integridad, archivos desaparecidos y recuperados, metadatos públicos, permisos y compatibilidad de la API anterior. Las eliminaciones y modificaciones de los escenarios se realizan sólo en fixtures temporales desechables.

Resultado final del bloque 1: **59 pruebas aprobadas y una omitida**, con 18 pruebas nuevas de CS-Storage. La omitida es la prueba anterior del agente que exige el privilegio de enlaces simbólicos; la prueba nueva con un punto de unión Windows sí se ejecutó. Se mantiene una advertencia existente de obsolescencia de Starlette/AnyIO. No se compiló ni empaquetó la aplicación. También se comprobó que una ruta UNC se rechaza antes de cualquier sondeo de archivos/red.

La compatibilidad estructural con PostgreSQL se comprueba generando DDL con su dialecto. **No se ha ejecutado aún una migración contra un PostgreSQL real**, ni local ni del despacho; no confundir esa comprobación estructural con una prueba de integración del servidor.

Estado por bloques:

1. Bloque 2 completado: Centro Documental en Empresas, listados paginados, filtros, cargas, vista previa y descarga por el servicio; verificación del flujo de adjuntos anterior. Detalles en `docs/CS_STORAGE_BLOCK2.md`.
2. Bloque 3 completado: worker independiente con lease/checkpoint, clasificación RFC, resoluciones auditadas y demo aislada reproducible. Validación: 84 pruebas aprobadas y una omitida, TypeScript sin emisión y revisión en Edge. Detalles en `docs/CS_STORAGE_BLOCK3.md`.
3. Bloque 4 completado: cuentas, sesiones individuales revocables, permisos y auditoría. Validación: 107 pruebas aprobadas y una omitida; 23 nuevas, TypeScript y Edge. Detalles en `docs/CS_STORAGE_BLOCK4.md`.
4. Bloque 5 completado para configuración y fuentes locales: panel, programación, diagnóstico y borradores Windows. Dashboard/CER y compilación autorizada de visita incluidos. Validación final: 122 pruebas aprobadas y una omitida, compilación/Edge y programación real en demo. SMB productivo y servidor del despacho siguen pendientes de validación presencial; consultar `docs/CS_STORAGE_BLOCK5.md`.

El dashboard de Empresas y seguimiento temporal de CER públicos FIEL/CSD están integrados en la primera pestaña y el expediente. Inicio mantiene su bienvenida y se conservan Stitch y los cuatro módulos. No se activan acceso SAT, OCR ni custodia de claves privadas.
