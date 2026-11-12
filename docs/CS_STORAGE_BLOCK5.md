# CS-Storage — bloque 5, dashboard y preparación de visita

Se cerraron los cinco bloques solicitados para la versión local de CS-Storage. El usuario autorizó además compilar el frontend sin instalador e incluir el dashboard y vigencias públicas FIEL pendientes. El servidor real no se contactó; se conservan `.env`, la base, `data/` y `agent/config.json` de la instalación.

## Archivos y cambios

| Archivo | Función |
|---|---|
| `backend/migrations/versions/0004_connector.py`, `models.py` | Revisión de configuración, frecuencia, próximo análisis, resultado de comprobación y señal persistida del trabajador. Migración aditiva; no reescribe históricos. |
| `backend/app/storage/connector.py`, `router.py` | Administración de orígenes, raíces autorizadas, comprobación local real, exclusiones, borradores Windows, estadísticas e historial. |
| `backend/app/storage/indexer.py`, `worker.py` | Planificación persistente y heartbeat; bloqueo global y reutilización de un trabajo activo para evitar duplicados. |
| `backend/app/storage/dashboard.py` | Conteos por empresa, lectura verificada de CER públicos, RFC/fechas y seguimiento temporal FIEL/CSD. |
| `backend/app/storage/catalog.py` | Correlación SQL explícita para reutilizar correctamente el ámbito de permisos en consultas agregadas. |
| `frontend/src/modules/StorageConnector.tsx` | Configuración de almacenamiento en Stitch, sin secretos de red ni conexiones ficticias. |
| `frontend/src/modules/CompanyDashboard.tsx`, `Companies.tsx`, `Dossier.tsx`, `Documents.tsx` | Dashboard en la primera pestaña y expediente, estado temporal de CER y declaración de uso FIEL/CSD. |
| `frontend/src/App.tsx`, `StorageJobs.tsx`, `styles.css` | Integración con Configuración, estados, tablas acotadas y adaptación a temas/móvil. |
| `scripts/run_windows.py`, `scripts/dev.mjs`, `INICIAR_INDEXADOR.bat` | Arranque del trabajador después de la API y parada conjunta, manteniendo procesos independientes. |
| `scripts/setup_windows.py` | Instalaciones nuevas sin empresas DEMO automáticas; conserva configuraciones existentes. |
| `scripts/storage_demo.py` | Demo aislada ampliada con CER sintéticos y vencimientos operativos. |
| `scripts/visit_check.py`, `VERIFICAR_VISITA.bat` | Preflight sin migrar, sondear PostgreSQL/UNC ni mostrar secretos. |
| `scripts/stamp_build.py`, `CONSTRUIR_FRONTEND.bat` | Manifiesto SHA-256 de compilación tras comprobar las características necesarias. No genera instalador ni paquete. |
| `backend/tests/test_connector_dashboard.py`, `test_visit_readiness.py`, `test_storage_migrations.py` | Pruebas del bloque, dashboard, diagnóstico y actualización del esquema conservando datos. |

## Configuración y programación

Sólo administradores acceden a `/api/storage/connector/options`, `/connector/sources` y sus operaciones de alta, edición y `probe`. Un colaborador no recibe las rutas o campos privados de configuración. Los payloads rechazan contraseñas y propiedades no declaradas.

Las carpetas locales deben existir dentro de `CS_STORAGE_ALLOWED_ROOTS`. La API no permite autorizar cualquier disco desde el navegador. Puede seleccionarse una raíz o una subcarpeta física bajo ella. Se prohíben solapamientos con repositorios internos, UNC y enlaces/reparse points como antes. La comprobación abre el listado de la raíz: es una prueba real de disponibilidad de listado, no una afirmación de que todos los archivos internos sean legibles ni una prueba de escritura.

El tipo y la raíz del origen son inmutables para proteger el historial. Las configuraciones llevan revisión; se rechazan cambios obsoletos y cambios con análisis en cola/en curso. No se eliminan fuentes ni documentos. Puede desactivarse una fuente existente aunque su raíz se haya retirado de la lista de autorizadas, sin acceder a esa ruta. Las exclusiones se aplican tanto al inventario como a lecturas directas.

Frecuencia: manual (`0`) o de 5 a 10,080 minutos. El trabajador revisa las fuentes locales activas y vencidas bajo un mutex de base de datos. Encola sólo si no existe trabajo activo y guarda la próxima fecha en la misma transacción. No recupera ilimitadamente todas las ejecuciones omitidas después de una parada: programa una ejecución y continúa a partir de la hora actual. Reiniciar conserva la programación. No depende de un timer de FastAPI ni del navegador.

La señal del trabajador está en `storage_worker_state`; se considera reciente durante 180 segundos. El panel muestra la última señal, última comprobación, último análisis, documentos actuales indexados e incidencias. Los estados de comprobación son observaciones fechadas, no monitorización continua del sistema de archivos. Un heartbeat reciente tampoco certifica la accesibilidad de cada carpeta.

El contrato `WindowsSMBProvider` permanece pendiente y sin acceso de red. El formulario guarda servidor, recurso, subcarpeta, cuenta prevista y una **referencia no secreta**; exige estado desactivado y sin programación. No acepta contraseña, no usa `net use`, no crea sesiones Windows ni guarda secretos. La consulta de preparación siempre indica pendiente. Para la visita existe una modalidad funcional con el backend/indexador ejecutados en el servidor y fuentes físicas locales; la operación mediante UNC desde otra máquina requiere completar y validar el adaptador remoto.

## Dashboard y FIEL

`GET /api/storage/dashboard` aplica los mismos permisos del catálogo y acepta un `company_id` opcional. Cuenta documentos mediante relaciones actuales sin duplicarlos por múltiples roles. Sólo analiza certificados de empresas accesibles. El expediente solicita su empresa concreta para no dejar fuera su certificado al aplicar límites globales.

La lectura de cada CER pasa por la verificación SHA-256 y por el parser X.509. Se muestran fechas UTC, días restantes, RFC extraíbles del sujeto, titular y serie pública. No se solicita la clave privada, no se intenta emparejarla, no se contacta al SAT y no se valida cadena de confianza, autenticidad oficial o revocación.

El despacho declara el uso `fiel`, `csd` o `unknown` mediante `PUT /documents/{id}/certificate-usage` o la categoría de carga. Esta etiqueta no se deduce arbitrariamente del nombre. El RFC del CER debe coincidir con el de la empresa y el vínculo debe estar confirmado para que una FIEL cuente como temporalmente comprobable. Sin RFC, vínculo pendiente, archivo no disponible o discordancia, se solicita revisión.

Estados: vigente, vence en 30 días o menos, vencida, aún no vigente, sin FIEL, no disponible o pendiente de verificar RFC/vínculo. Si existen una FIEL anterior vencida y otra renovada vigente, la empresa se evalúa con la vigente; el certificado viejo continúa visible en el detalle. Los CSD y certificados sin uso identificado no se cuentan como FIEL. No se modifica el documento físico al cambiar la etiqueta; se comprueban permiso de escritura de todas las empresas vinculadas y revisión física actual, y se registra el responsable.

Se procesan como máximo los 200 CER más recientes del ámbito. Si se alcanza el límite, la interfaz lo informa y no afirma ausencia/vencimiento definitivo donde podría faltar un certificado. Los conteos y fechas proceden de registros reales o de la demo identificada, nunca de valores simulados para aparentar conexión.

## Compilación y preparación

La compilación autorizada se ejecutó con TypeScript y Vite en modo producción. `frontend/dist/contasuite-build.json` incluye características, revisión de esquema y SHA-256 de los archivos. El preflight detecta archivos cambiados y no confunde un frontend viejo con esta versión.

`VERIFICAR_VISITA.bat` no aplica migraciones ni abre servidores remotos. Comprueba Python, dependencias, claves presentes sin imprimirlas, compilación y lectura de revisión de SQLite con `mode=ro`. Una base nueva/anterior se informa como pendiente; PostgreSQL y SMB se dejan para revisión técnica. No es un certificado de disponibilidad de producción.

La demostración fue servida directamente por FastAPI con los archivos compilados, sin Vite. Se utilizó una base ficticia creada en un directorio nuevo; se iniciaron API y trabajador separados. El lanzador Windows incorpora ese mismo patrón después de la señal de salud de la API; al detenerlo termina su trabajador. Un cierre durante un trabajo conserva el checkpoint y requiere esperar al vencimiento de su lease para recuperarlo, como en el bloque 3.

La guía [LISTO_PARA_VISITA.md](../LISTO_PARA_VISITA.md) define arranque, respaldo previo, demostración, levantamiento y aceptación. No se generó instalador ni ZIP, ni se migró la base original durante el desarrollo.

## Pruebas y alcance

Validación final de la suite: 122 pruebas aprobadas y una omitida (symlink antiguo por privilegios Windows), con la advertencia previa de Starlette/AnyIO. Las pruebas nuevas cubren configuración/revisión/raíces, frecuencia, heartbeat, no duplicación, desactivación, borrador SMB sin red, vigencia/renovación/RFC/permisos y preflight íntegro sin modificaciones ni secretos. La compilación TypeScript/Vite terminó correctamente.

Edge sobre la compilación: login y dashboard, tres CER sintéticos, renovación, cambio FIEL/CSD, señal del trabajador, comprobación local, frecuencia guardada, Windows pendiente, historial, tres temas, móvil sin desbordamiento y acceso a los cuatro módulos como administrador. No hubo errores JavaScript. Los escenarios no modificaron datos originales.

Pendientes de la visita: infraestructura y TLS, permisos/documentos reales, aprobación de frecuencia/exclusiones y restauración, PostgreSQL si se elige ese perfil, y validación de red/SMB. El adaptador SMB remoto y la sesión/descarga automática SAT no están implementados productivamente y no deben anunciarse como activos. OCR masivo, custodia de llaves privadas e impresión continúan fuera del alcance solicitado; impresión se retiró por instrucción del usuario.

Fuentes técnicas: [X.509 de cryptography](https://cryptography.io/en/latest/x509/reference/) para fechas UTC y atributos públicos; [control de acceso de Windows](https://learn.microsoft.com/windows/security/identity-protection/access-control/access-control) para la validación de permisos en la visita. Las pruebas locales no sustituyen esa validación presencial.
