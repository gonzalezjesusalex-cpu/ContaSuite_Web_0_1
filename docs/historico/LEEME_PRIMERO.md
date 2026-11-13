# ContaSuite Web 0.1

Primera base funcional del sistema híbrido para el despacho. Frontend React + TypeScript + Tailwind, API FastAPI, PostgreSQL y agente local Windows. Fecha: 9 de noviembre de 2026.

## Abrir rápidamente en Windows

1. Extrae TODO el ZIP en una carpeta local (por ejemplo `C:\ContaSuiteWeb`). No ejecutes dentro del ZIP.
2. Instala **Python 3.12 de 64 bits**, incluyendo el lanzador `py`. El lanzador elige Python 3.12 o 3.11 de 64 bits; no utiliza 3.15 aunque sea la versión predeterminada.
3. Para probar sin PostgreSQL, abre **INICIAR_PRUEBA.bat**. En el primer arranque requiere Internet para instalar las dependencias de Python.
4. Se abrirá el navegador en `http://127.0.0.1:8000`. Copia la clave de acceso que muestra la consola y pégala en la pantalla de acceso.
5. Encontrarás **tres empresas DEMO**, con tareas y obligaciones ficticias. Puedes editarlas, eliminarlas o crear nuevas empresas.
6. Conserva abierta la consola mientras usas ContaSuite. Para detenerla: Ctrl+C.

El frontend ya está compilado en `frontend/dist`. No necesitas instalar Node.js para ejecutar esta entrega. Después de instalar las dependencias, la interfaz no depende de Google Fonts ni del CDN de Tailwind.

## Usar PostgreSQL

Para una instalación nueva con la arquitectura principal, instala Docker Desktop con Docker Compose, inicia Docker Desktop y abre **INICIAR_CONTASUITE.bat**. El script genera credenciales aleatorias, inicia PostgreSQL 17 y espera a que responda antes de abrir la API.

Los scripts respetan la configuración de `.env` que ya exista. `INICIAR_PRUEBA.bat` no cambia una instalación PostgreSQL existente y `INICIAR_CONTASUITE.bat` no migra una instalación de prueba. Para usar un PostgreSQL propio, configura `DATABASE_URL` y arráncalo por tu cuenta; el lanzador incluido espera Docker para el modo PostgreSQL. Puedes iniciar manualmente la API con el comando indicado en `docs/ARQUITECTURA.md`.

SQLite y PostgreSQL son instalaciones independientes. Cambiar la URL no copia registros. Esta versión no incluye migrador entre las dos bases.

## Funciones implementadas

| Área | Estado en 0.1 |
|---|---|
| Inicio | Logo original de ContaSuite 0.6, saludo según la hora del equipo y nombre configurable |
| Empresas | Registro en tres pasos, edición, búsqueda, filtros, paginación y exportación CSV |
| Empresas de prueba | Tres registros marcados DEMO; se crean una sola vez en el primer arranque |
| Eliminar empresa | Desde su expediente; exige escribir el RFC de confirmación |
| Dashboard | Indicadores calculados con registros reales; periodo configurable |
| Obligaciones | Alta, edición, estado, periodo, fecha límite y referencia de acuse |
| Tareas | Alta, edición, prioridad, responsable, fecha límite y finalización |
| Expediente | Adjuntar, descargar y eliminar PDF, XML y CER; límite de 25 MB |
| Agente local | Conexión real, cola de trabajos y análisis de carpetas de sólo lectura |
| Preferencias | Nombre del usuario, temas claro, oscuro y alto contraste |
| Recibos | Motor original integrado: individual, varios meses, lotes, PDF, folios, historial, ZIP y PDF combinado |
| Recopila | Motor original integrado: carga, coincidencias, revisión y generación de recopiladores, sobrantes y separadores |
| Otros módulos | Navegación y propuestas de Stitch renderizadas en React; motores aún no conectados |

Las empresas con recibos emitidos se conservan para proteger su historial; su eliminación se bloquea.

Al eliminar una empresa sin recibos se borran sus tareas, obligaciones, trabajos y documentos adjuntos en ContaSuite. **No se borran ni modifican los archivos de su carpeta original de Windows.** La bitácora conserva el evento de eliminación. Espera a que termine cualquier análisis local antes de borrar la empresa.

Los datos DEMO proceden de los ejemplos de Stitch. No son contribuyentes verificados ni datos reales del despacho. Si eliminas las tres empresas, no reaparecen al reiniciar. En una base vacía puedes volver a cargar el ejemplo desde Empresas.

## Conectar el agente local

1. Inicia la aplicación una vez; se creará `agent/config.json`.
2. Edita `allowed_roots` en ese archivo para indicar únicamente las carpetas que deseas analizar. Ejemplo JSON: `["D:\\Empresas", "\\\\servidor\\expedientes"]`. Las rutas deben existir y ser accesibles por el usuario de Windows.
3. Abre **INICIAR_AGENTE.bat**, sin cerrar la consola del servidor.
4. En la empresa, captura una carpeta contenida dentro de las rutas autorizadas.
5. Abre el expediente y pulsa **Analizar carpeta**. El resultado aparecerá al actualizar los datos (cada 10 segundos).

El agente envía nombres, rutas relativas y tamaños de PDF/XML/CER/KEY. No lee ni envía el contenido de llaves privadas, no mueve archivos y no ejecuta comandos recibidos de la web. El escaneo se limita a 3,000 archivos compatibles, 30,000 archivos inspeccionados o 60 segundos; un resultado parcial se identifica como tal. No clasifica todavía constancias ni valida certificados.

## Archivos y respaldo

- `data/contasuite.db`: base SQLite del modo de prueba.
- `data/documents/`: documentos adjuntados a ContaSuite en ambos modos.
- Volumen Docker `contasuite_pg`: base PostgreSQL del modo principal.
- `.env`: configuración y claves de esta instalación; conserva una copia privada.
- `agent/config.json`: configuración privada del agente.

Para respaldar el modo de prueba, detén aplicación y agente y copia `data`, `.env` y `agent/config.json`. Para PostgreSQL usa `pg_dump` y respalda también `data/documents`. No uses `docker compose down -v` si deseas conservar la base.

## Límites de esta primera entrega

Esta versión está preparada para pruebas locales en un solo despacho, con una clave de instalación. Aún no incluye usuarios, roles, recuperación de contraseña, acceso público, TLS, multiempresa con aislamiento por despacho ni servicio Windows instalado. La arquitectura permite separarlos después; no publiques esta API tal cual en Internet.

No hay conexión SAT, validación 69-B, generación DIOT, descarga de CFDI, interpretación de certificados, OCR, impresión ni ejecución de los motores anteriores. Las pantallas de automatización están identificadas como propuestas de diseño con controles deshabilitados. No se ha recibido el código de esos motores en este ZIP.

La documentación técnica, análisis de las 12 pantallas y el plan para integrar los motores están en `docs/ARQUITECTURA.md`. La validación ejecutada y sus límites están en `docs/VALIDACION.md`.

## Corrección de instalación 0.1.1

El arranque selecciona Python 3.12/3.11 de 64 bits, conserva entornos incompatibles en una carpeta .venv-anterior y separa dependencias SQLite/PostgreSQL. Un fallo de pip muestra su causa original. Instala Python 3.12 si sólo tienes 3.15; no necesitas desinstalarlo. Extrae esta versión en otra carpeta para una prueba nueva o reemplaza los archivos de código conservando `.env`, `data` y `agent/config.json`.

## Ajuste de navegación

Se retiraron del menú y de las rutas visibles los paneles Renombrador de cotizaciones y Relacionador documental.


## Integración de Recibos · primera etapa

Abre **Generador de recibos** en la barra lateral. También puedes usar **Emitir recibo** desde el expediente de una empresa para precargarla.

- **Individual:** escribe el nombre del cliente (aunque no esté registrado como empresa), mes/ejercicio cobrado, importe y fecha de emisión. Puedes elegir una empresa o cliente guardado entre las sugerencias. En «Emitir también para otros meses» puedes emitir un recibo separado por mes.
- **En masa:** agrega filas, edita, duplica o quita antes de generar. Guarda o cancela la edición activa antes de emitir el lote. Selecciona una fila para previsualizarla.
- **Vista previa:** usa el PDF real con el membrete de la aplicación 0.6. Ajustar hoja muestra la página completa; el zoom no modifica el PDF. El importe en letra se calcula automáticamente dentro del documento.
- **Generar:** asigna un consecutivo anual según el año de emisión (2026-0001, etc.). La vista previa no consume folios. Cada recibo conserva su PDF original y queda asociado a la empresa y al periodo cobrado.
- **Duplicados:** avisa si ya existe un recibo para la misma empresa/mes/ejercicio o el lote repite un periodo. Sólo una confirmación explícita permite emitir otro.
- **Descargas:** PDF individual; para varios, ZIP de los PDF individuales o PDF combinado. Los PDF se generan en el servidor y no contienen encabezados/pies agregados por el navegador.
- **Historial:** busca nombre, folio, fecha, periodo AAAA-MM o importe. Filtra por empresa y ejercicio cobrado. Puedes abrir, descargar o combinar una selección sin generar folios nuevos.
- **Configuración:** nombre de quien recibe y lugar de emisión. Se aplica a futuras emisiones. El membrete original ya viene incluido.

Los folios web comienzan con su propio consecutivo. **Esta etapa no importa el historial ni los folios de la aplicación de escritorio.** No mezcles ambos sistemas para emitir documentos con una numeración compartida sin migrar primero sus registros.

### Actualizar una instalación existente

Detén ContaSuite. Respalda la carpeta `data` y la base de datos (SQLite: el archivo indicado en DATABASE_URL; PostgreSQL: un respaldo de la base). Copia los archivos del paquete conservando tu `.env`, `data`, `agent/config.json` y base existentes. Inicia con el mismo BAT que utilizabas. Las tablas nuevas de Recibos se crean automáticamente; se conserva el catálogo web actual y no se importa el módulo experimental de Empresas del escritorio. El primer inicio instala las dependencias nuevas de PDF; el frontend ya está compilado.

Respalda juntos la base de datos y `data/receipts`. Esta carpeta contiene los PDF originales; el historial usa sus referencias. La generación del lote revierte archivos, registros y consecutivos si falla antes de completar la emisión. El lote se limita a 300 recibos por operación.

### Alcance de la verificación

Pruebas de API y persistencia ejecutadas en SQLite, incluyendo generación real del PDF, archivos originales, exportaciones, duplicados, folios concurrentes y reversión ante fallo. Compilación de TypeScript y frontend verificada. Revisión en navegador de captura, vista previa, emisión y duplicados. PostgreSQL usa un contador atómico y bloqueo transaccional, pero no se ha probado contra una instancia real en esta entrega. La impresión Windows se integrará con el módulo Imprime.


## Recibos · clientes libres y concepto personalizado

- **Cliente / contribuyente** acepta escritura libre. Puedes emitir sin crear una empresa y sin guardar el cliente.
- **Guardar cliente** conserva el nombre en un catálogo exclusivo de Recibos para próximas emisiones. Los nombres equivalentes con diferencias de espacios o mayúsculas no se duplican.
- **Clientes**, en el encabezado del módulo, muestra ese catálogo y permite eliminar un cliente previa confirmación. Sólo se retira de las sugerencias: sus recibos, nombre histórico, conceptos, folios y PDF se conservan. Las empresas existentes siguen administrándose desde Empresas.
- **Concepto de pago** permite hasta 500 caracteres. Aparece en la vista previa, PDF e historial y puede ser distinto en cada fila del lote. El texto personalizado sustituye por completo la frase de servicios contables; escribe el periodo dentro del concepto si deseas incluirlo. Si lo dejas vacío se usa la frase anterior con el mes y ejercicio seleccionados.
- El periodo cobrado sigue disponible para ordenar y consultar el historial, aunque el concepto sea personalizado.

La actualización adapta automáticamente las tablas existentes al arrancar. Conserva tu `.env`, datos y base actuales como se explica arriba; respáldalos antes de actualizar. Los PDF emitidos anteriormente no se regeneran ni se modifica su contenido. Verificación: 23 pruebas aprobadas en SQLite, incluida la migración desde el esquema anterior, emisión sin empresa, concepto personalizado y conservación del historial tras eliminar un cliente. También se revisaron los nuevos controles y el PDF en navegador.


## Recibos en masa por varios meses

En **En masa**, captura cliente, concepto, ejercicio, importe y fecha. Activa **Generar por varios meses para este cliente** y marca las casillas de los meses. También puedes seleccionar todos o limpiar la selección. Pulsa **Agregar N recibos al lote**: aparece una fila independiente por mes para ese cliente. El importe capturado se aplica completo a cada recibo, no se divide entre meses. Repite con otros clientes y meses y luego pulsa **Generar lote**. Cada recibo recibe su propio folio.

La selección de meses se conserva para facilitar agregar otros clientes. El mes del desplegable sólo se usa cuando la opción de varios meses está desactivada. Al editar una fila del lote se modifica únicamente ese recibo; no se vuelve a expandir por los meses seleccionados. El lote admite hasta 300 recibos y conserva el aviso de duplicados por cliente y periodo. Un concepto personalizado se repite tal como se captura; si lo dejas vacío, cada PDF utiliza el mes correspondiente en el concepto predeterminado.


## Integración de Recopila y ajustes visuales incluidos en esta entrega

Los cambios del parche ya están aplicados y la interfaz se reconstruyó con autorización del usuario. No necesitas aplicar ningún parche. El proyecto completo está listo para continuar en Codex: consulta `CONTINUAR_EN_CODEX.md` y `AGENTS.md`.

- Inicio: logo, saludo según hora, nombre en línea independiente, «Bienvenido a ContaSuite» y «Tu espacio de trabajo contable».
- Recibos: casillas de varios meses también en el modo en masa; una fila independiente por mes. Botones y tarjetas reutilizan los tokens originales de Stitch, con transiciones, entrada de tarjetas, modales y resultados. Se respeta la preferencia de reducir movimiento.
- Recopila: motor original de escritorio conservado sin cambios en `backend/app/recopila_engine.py`; adaptador API separado y pantalla funcional en React. Carga un ZIP, una carpeta o PDF/XML; analiza, muestra coincidencias/UUID y documentos sobrantes, vista previa y generación del recopilador general, sobrantes, separadores, reportes y recopiladores por mes opcionales. Descarga individual o ZIP del resultado. Historial de hasta 50 análisis recientes y vinculación opcional con empresa. No incluye descarga SAT ni OCR.
- El proceso corre en el servidor de ContaSuite sobre copias de los documentos. Requiere conservar `data/recopila` junto con la base para mantener los análisis y sus resultados. Límite de carga de 100 MB; hasta 1,000 archivos por selección o 5,000 documentos dentro de un ZIP (500 MB descomprimidos).
- Verificación: 26 pruebas de API aprobadas en SQLite, incluidas las nuevas de Recopila; comprobación de tipos sin emitir JavaScript. La revisión visual exacta de las adaptaciones de Stitch sigue pendiente. La compilación de distribución está incluida en esta entrega; los módulos restantes continuarán uno por uno en Codex.
