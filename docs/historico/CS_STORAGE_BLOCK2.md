# CS-Storage — cierre del bloque 2

El Centro Documental está integrado en el código fuente y validado en modo desarrollo. Se abre en **Empresas → Documentos**, también mediante `/empresas?tab=documentos`, y dentro de **cada expediente → Documentos**. Conserva las pestañas existentes y la navegación principal, además de los controles, colores, iconos, temas y movimiento reducido de Stitch.

No se ejecutó una compilación de producción ni se generó `frontend/dist`, paquete o instalador. El lanzador habitual sirve la versión compilada anterior; para distribuir esta interfaz hará falta una autorización explícita para compilar. Durante las pruebas se utilizaron servidores de desarrollo, documentos sintéticos y una base separada bajo `.qa/storage2`; no se migró la base real ni se conectó al despacho.

## Funciones disponibles

- Explorador con paginación de 25 documentos por página. La API admite páginas de hasta 100.
- Búsqueda por nombre, empresa, RFC del catálogo y periodo capturado. Los símbolos `%` y `_` se buscan literalmente.
- Filtros de empresa, formato, tipo documental, año, mes y origen. En un expediente, la empresa queda fijada también al cargar.
- Cargas al repositorio privado con empresa opcional, categoría, tipo y periodo. Sin empresa, el documento entra en la bandeja sin clasificar.
- PDF y XML con comprobación de formato. CER con comprobación X.509 de un certificado público, sin claves ni datos anexos. No se lee su vigencia ni se solicita FIEL o contraseña.
- Detalle con metadatos públicos, origen, disponibilidad de la última comprobación, versiones y SHA-256. No se muestran rutas físicas, claves de proveedor, UNC ni configuración privada.
- Comprobación explícita del contenido sin modificar archivos originales.
- Vista previa de PDF mediante el lector del navegador y XML como texto literal. La interfaz limita la vista previa de XML a 1 MB; el documento completo sigue siendo descargable dentro del límite de carga.
- Descarga del documento actual o una versión histórica, con su nombre original y contenido verificado antes de enviar HTTP 200. No se guarda un archivo si la respuesta llega vacía.
- Bandeja sin clasificar para consultar documentos pendientes. La detección RFC y las decisiones de confirmar/corregir/rechazar se incorporarán en el bloque 3; no hay botones que aparenten esa funcionalidad.

El tipo y el periodo de las nuevas cargas se capturan manualmente. No se infieren de una fecha de carga ni del nombre del archivo. La búsqueda por RFC en este bloque usa las empresas vinculadas, no extrae aún emisor o receptor del XML.

## Archivos y cambios

| Archivo | Cambio |
|---|---|
| `backend/app/security.py` | Extrae y reutiliza la validación actual de APP_TOKEN sin duplicarla ni importar la aplicación desde el servicio. |
| `backend/app/storage/router.py` | Opciones, catálogo, carga, detalle, comprobación y contenido; todos requieren autenticación de instalación. |
| `backend/app/storage/catalog.py` | Consultas paginadas, permisos por empresa en el núcleo, respuestas públicas y verificación/adopción de adjuntos anteriores. |
| `backend/app/storage/service.py` | Integra el catálogo, valida metadatos de carga y conserva el nombre propio de cada versión en la descarga. |
| `backend/app/storage/schemas.py` | Tipos públicos de catálogo, empresas, ubicaciones, versiones y contenido verificado. |
| `backend/app/storage/internal.py` y `paths.py` | Permiten CER únicamente tras validar un certificado público. Rechazan DER privado, PEM privado y certificados con bytes anexos. |
| `backend/app/main.py` | Registra el router; muestra sólo metadatos mínimos en el estado y unifica las descargas antiguas con el servicio verificado. Valida también las cargas del endpoint anterior. |
| `backend/requirements-base.txt` | Añade `cryptography==46.0.3` para la validación del certificado público; se instaló desde wheels, sin compilación local. |
| `frontend/src/modules/Documents.tsx` | Explorador, filtros, carga, detalle, versiones, disponibilidad y vista previa con controles compartidos de Stitch. |
| `frontend/src/modules/Companies.tsx` | Añade la pestaña Documentos y el acceso por URL. |
| `frontend/src/modules/Dossier.tsx` | Integra el mismo explorador limitado a una empresa en lugar del listado anterior. Conserva el resto del expediente. |
| `frontend/src/api.ts` | Permite cancelar consultas mediante AbortSignal. |
| `frontend/src/types.ts` | Añade los tipos públicos de CS-Storage y admite documentos sin empresa. |
| `frontend/src/styles.css` | Estilos complementarios del explorador, detalle, carga, XML y vista móvil; usa las variables y controles existentes. |
| `backend/tests/test_storage_catalog.py` | Once pruebas nuevas de API/catálogo, identidad, versiones, compatibilidad, formatos y contenido. |
| `backend/tests/test_api.py`, `test_storage_core.py` | Actualizan las expectativas de descarga anterior: ahora verifica y registra historial. El borrado por rutas antiguas sigue bloqueado cuando existe historial; ya no debe esperarse su eliminación en cascada después de descargar. |
| `AGENTS.md`, `CONTINUAR_EN_CODEX.md`, `docs/CS_STORAGE.md` | Estado real, restricciones de compilación y siguiente bloque. |

No se añadieron tablas ni se alteró la instantánea de las migraciones del bloque 1. La estructura de empresa, periodos y documentos ya soportaba esta interfaz.

## Endpoints

| Método y ruta | Función |
|---|---|
| `GET /api/storage/options` | Empresas permitidas, orígenes públicos y límites de carga. |
| `GET /api/storage/documents` | Catálogo paginado. Parámetros: `q`, `company_id`, `period`, `year`, `month`, `format`, `document_type`, `source_id`, `pending`, `offset`, `limit`. |
| `POST /api/storage/documents` | Un archivo y sus metadatos; se almacena una copia interna. |
| `GET /api/storage/documents/{id}` | Detalle y versiones sin ubicaciones físicas. |
| `POST /api/storage/documents/{id}/verify` | Verificación actual y primera huella de un adjunto anterior, cuando corresponda. |
| `GET /api/storage/documents/{id}/content` | Descarga verificada; admite `revision` y `preview`. |
| `GET /api/documents/{id}/download` | Compatibilidad con enlaces anteriores, usando la misma verificación del contenido. |

Los tipos documentales admitidos son `unknown`, `cfdi`, `declaration`, `acknowledgement`, `certificate` y `other`. Los periodos admitidos van de `2000-01` a `2100-12`.

## Compatibilidad e integridad

Los adjuntos anteriores conservan el identificador y el archivo físico. La primera comprobación o descarga registra su huella y ubicación comprobada. Si hay una huella registrada, no se reemplaza con la del contenido modificado: la descarga se rechaza por integridad. Los errores no devuelven mensajes del sistema operativo ni rutas internas.

Registrar historial impide que el documento o su empresa se eliminen desde los endpoints antiguos. Esto sustituye la expectativa anterior de borrado en cascada tras una descarga, para conservar las versiones y sus eventos. No se ofrece eliminación de documentos en el nuevo explorador.

Los CER se comprueban como certificados públicos y se conservan con sus bytes originales. No se aceptan claves privadas con extensión `.cer`, archivos `.key`/`.pfx`/`.p12` ni un certificado al que se haya anexado una clave. Esta lectura no constituye validación de vigencia, autenticidad fiscal o custodia de e.firma/CSD.

Las respuestas de descarga usan `no-store`, `nosniff` y disposición de archivo segura. El XML de vista previa se devuelve como texto plano y React lo muestra escapado, sin inyección de HTML. El servicio verifica el contenido completo antes de abrir la respuesta y cierra el buffer al terminar o interrumpirse la transmisión.

## Identidad y límites pendientes

La autenticación sigue siendo **APP_TOKEN del administrador de la instalación**. El actor `installation_admin` se construye en el servidor y no identifica a una persona real. No se aceptan usuarios o permisos enviados por el cliente. Se probaron los límites por empresa con actores restringidos inyectados en pruebas; eso no equivale a disponer ya de sesiones individuales en producción.

Quedan pendientes del bloque 3 el worker independiente, indexación programada e incremental completa, clasificación determinista por RFC, extracción emisor/receptor y resolución de la bandeja. El bloque 4 implementará identidades nominativas y protección integral en los demás módulos. SMB y su panel se completarán en el bloque 5; no se realizó una conexión real al servidor Windows.

## Validación

- Suite completa: **70 aprobadas, una omitida** por el privilegio de enlaces simbólicos de Windows en una prueba anterior. Se mantiene la advertencia previa de Starlette/AnyIO.
- Once pruebas nuevas: búsqueda y filtros, paginación, aislamiento entre empresas, autenticación, descargas/versiones, nombres históricos, adjuntos anteriores, contenido modificado o desaparecido, certificados públicos frente a claves privadas y validación de metadatos.
- TypeScript comprobado mediante `tsc --noEmit`, sin generar archivos de compilación.
- Edge en desarrollo con datos aislados: carga asignada y sin clasificar, filtros de empresa/origen, primera verificación de adjunto anterior, descarga XML comparada byte por byte, bandeja pendiente, contexto fijo de empresa y mensaje de error de descarga persistente.
- Capturas de claro, oscuro y alto contraste, y móvil de 390 px; sin errores JavaScript ni desbordamiento horizontal de página. XML con una etiqueta `script` se mostró literalmente y no se ejecutó.
- PostgreSQL mantiene la comprobación estructural del bloque 1; aún no se probaron estas consultas contra un servidor PostgreSQL real.

El siguiente trabajo es el **bloque 3: indexación y clasificación**. El dashboard/FIEL permanece como trabajo posterior. No compilar ni empaquetar sin autorización explícita del usuario.
