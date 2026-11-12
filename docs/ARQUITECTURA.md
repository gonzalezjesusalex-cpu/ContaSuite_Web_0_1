# Arquitectura y análisis de ContaSuite Web 0.1

## Estructura implementada

| Directorio | Responsabilidad |
|---|---|
| `frontend/src/components` | Componentes compartidos: campos, tarjetas, indicadores, modales, logo |
| `frontend/src/modules` | Empresas, expediente, registro, tareas/obligaciones y propuestas de automatización |
| `frontend/src/designs` | Árboles de elementos convertidos de Stitch, cargados por módulo |
| `frontend/src/api.ts` | Cliente HTTP, acceso, descargas autenticadas y exportación CSV |
| `frontend/src/types.ts` | Contratos TypeScript de los registros |
| `frontend/dist` | Aplicación compilada lista para servir desde FastAPI |
| `backend/app/models.py` | Modelos SQLAlchemy y relaciones |
| `backend/app/schemas.py` | Validación de entrada con Pydantic |
| `backend/app/database.py` | Sesiones SQLAlchemy y configuración de persistencia |
| `backend/app/main.py` | API, autenticación de instalación, operaciones y servicio del frontend |
| `backend/tests` | Pruebas de API y verificación real del agente por HTTP |
| `agent/agent.py` | Trabajador local de sólo lectura con rutas autorizadas |
| `agent/adapters.py` | Contrato para motores Python puros, sin dependencias de GUI |
| `scripts` | Arranque, desarrollo y conversión de diseños |
| `design-source` | ZIP original descomprimido: HTML, capturas y DESIGN.md |

La separación principal se realiza entre la interfaz, las operaciones de datos y los motores locales. Esta versión mantiene los endpoints de Empresas en un archivo pequeño para facilitar la ejecución; al ampliar módulos se separarán en routers y servicios por dominio. El código fuente y la compilación se entregan juntos.

## Comunicación híbrida

El navegador consulta una única API. En Windows, FastAPI sirve tanto `/api` como los archivos compilados de React; las rutas del navegador se resuelven con React Router. No se necesita CORS para el uso normal.

En desarrollo, Vite dirige `/api` a FastAPI y el lanzador `scripts/dev.mjs` mantiene ambos procesos. En el futuro el navegador y FastAPI podrán alojarse en un servidor HTTPS mientras el agente continúa en Windows.

El agente inicia conexiones salientes autenticadas, informa sus capacidades, reclama trabajos de una cola SQL y publica resultados. No abre puertos locales. La API selecciona la ruta de la empresa y el agente comprueba que pertenece a una carpeta autorizada. No se aceptan nombres de módulos Python, comandos shell ni código arbitrario desde la API.

La cola usa una actualización condicional para reclamar un trabajo una sola vez. Los resultados sólo se admiten para el agente asignado y un trabajo en ejecución. El trabajador reintenta enviar un resultado ante fallos transitorios sin repetir el escaneo. En 0.1 no hay recuperación automática de trabajos interrumpidos por un cierre abrupto; se incorporarán leases, reintentos persistentes y cancelación en la siguiente etapa.

## Modelo de datos

| Entidad | Campos principales | Relación |
|---|---|---|
| Empresa | RFC único, razón social, tipo, régimen, contador, contacto, ruta, notas, is_demo | Raíz del expediente |
| Tarea | título, responsable, categoría, prioridad, fecha, estado | Empresa |
| Obligación | título, periodo AAAA-MM, fecha, estado, referencia | Empresa |
| Documento | nombre original, tipo interno, tamaño, nombre de almacenamiento | Empresa |
| Evento | acción, empresa, fecha | Bitácora interna |
| Agente | identificador, capacidades, última comunicación | Equipo Windows |
| Trabajo | tipo, agente, empresa, estado, parámetros, resultado | Cola de procesamiento |
| Configuración | clave, valor | Marca de inicialización DEMO |

No se calcula cumplimiento legal. El dashboard indica pendientes internos según tareas y obligaciones registradas: vencidos → crítico; abiertos → requiere revisión; sin abiertos → sin pendientes. La opinión 32-D permanece sin consultar. Los vencimientos se capturan manualmente.

La inicialización 0.1 usa `metadata.create_all` para crear una base nueva. No es un sistema de migraciones ni actualiza estructuras de bases anteriores: antes de cambios de esquema se incorporará Alembic con revisiones versionadas. No se incluyen importadores de datos de los programas de escritorio todavía.

## Análisis de las 12 pantallas del ZIP

| Pantalla Stitch | Implementación / decisión |
|---|---|
| Inicio | Reconstrucción React: shell compartido, logo local y saludo dinámico sin dashboard |
| Empresas / Centro de control fiscal | Dashboard, directorio, filtros, periodos y resumen real de trabajo |
| Expediente Distribuidora Bajío | Expediente dinámico por ID; documentos, obligaciones, tareas, historial y análisis local |
| Registro de empresas | Formulario React en tres pasos con borrador y validaciones |
| Tareas y vencimientos | Registros editables con fecha, responsable, prioridad, estado y filtros |
| Recopilador | Motor original integrado: análisis, revisión y generación de PDF |
| Organizador | Motor original integrado: análisis de rutas, copias SHA-256 y ZIP/CSV; movimiento local pendiente |
| Renombrador de cotizaciones | Diseño convertido; OCR y renombrado pendientes |
| Relacionador documental | Diseño convertido; coincidencias y paquetes pendientes |
| Generador de recibos | Diseño convertido; motor PDF individual y masivo pendiente |
| Declara | Motor original separado de la GUI: PDF, revisión, copias renombradas, control mensual e historial; sesión SAT por agente pendiente |
| Centro de impresión | Retirado por solicitud del usuario; no se integrará |
| Configuración | Preferencias funcionales, estado de servicios y propuesta original consultable |

El ZIP incluye 12 HTML, 12 capturas PNG y una guía de diseño. No contiene un proyecto React, código backend, motores Python ni base de datos.

Se conservaron el azul de acción `#004AC6`/`#2563EB`, la barra lateral `#213145`, el lienzo `#F8F9FF`, las superficies blancas, Inter y la estructura compacta. Fuentes e iconos se empaquetan localmente. Los módulos funcionales se reorganizan alrededor de datos reales; las propuestas pendientes conservan las clases y estructura de Stitch mediante un renderer de elementos React (sin iframe ni inyección de HTML). La conversión elimina scripts, eventos y referencias remotas de imágenes.

Se incorporó el paquete original de iconos de ContaSuite 0.6 aportado posteriormente. El logo de ContaSuite y los iconos de Recopilador, CFDI, Recibos, Impresión y Declaraciones se copian sin modificar en PNG, con variantes claro/oscuro y resoluciones 64, 128 y 192. La barra lateral usa la variante oscura por su superficie; inicio y encabezados siguen el tema de la aplicación. El icono de Declaraciones se usa en la pestaña del expediente. Los módulos sin recurso equivalente conservan su icono funcional actual.

## Integración de los programas anteriores

Cada motor debe separarse de Tkinter/PySide y exponerse como lógica independiente, conservando los algoritmos existentes y sus casos especiales. La GUI anterior puede seguir funcionando mientras el mismo motor obtiene un adaptador nuevo.

| Motor anterior | Adaptación prevista | Validación para conservar comportamiento |
|---|---|---|
| Recopilador | Entrada de empresa, rutas y filtros; resultados tipados | Comparar archivos y contenido de salida con casos del escritorio |
| Organizador de declaraciones | Análisis, plan de nombres y aplicación separada | RFC, complementarias, duplicados y mes completo |
| Organizador CFDI | XML/PDF, empresa, periodo y jerarquía de destino | Emparejamiento y rutas propuestas antes de mover |
| Renombrador de cotizaciones | OCR local, extracción y plan de nombres | Documentos digitales/escaneados y nombres ya existentes |
| Relacionador documental | Clasificación, coincidencias y armado de expedientes | Conceptos múltiples y pólizas sin CFDI |
| Limpiador de conceptos | Función pura de limpieza | Mantener conceptos originales sin alterar significado |
| Recibos | Datos → PDF independiente o lote de PDFs | Formato existente, importe en letras y fecha manual |
| Impresión | PDF + impresora + opciones → cola del agente | Individual/masiva, Carta, orden y manejo de errores |

El archivo `agent/adapters.py` define `analyze(source, options)` y `execute(plan, destination)`. El análisis devuelve un plan sin modificar archivos; la ejecución se incorporará por motor con autorización y auditoría. Por ahora sólo está registrado el tipo de trabajo `scan_folder`; los motores anteriores no se ejecutan.

## Desarrollo

Requisitos de desarrollo: Python 3.12, Node.js 22.12+ o 24 LTS y la base elegida.

Desde la raíz, crea `.venv`, instala `backend/requirements-dev.txt`, configura `.env` y ejecuta `npm ci` en `frontend`. `npm run dev` desde `frontend` inicia API y Vite. Si utilizas otra instalación Python, pasa la ruta por `CONTA_PYTHON`.

Para iniciar sólo la API desde la raíz:

```powershell
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Para compilar el frontend: `CONSTRUIR_FRONTEND.bat`, o `npm run build` dentro de `frontend`. El lockfile de npm fija las versiones instaladas. Las dependencias backend están fijadas en `requirements.txt`.

OpenAPI: `http://127.0.0.1:8000/docs`. Los endpoints de aplicación requieren `Bearer APP_TOKEN`; los del agente usan un token distinto. Las claves se generan en el primer inicio y no se distribuyen en el ZIP. No cambies los tokens mientras un proceso ya está iniciado: reinicia API y agente después de actualizar su configuración.

## Siguientes etapas

1. Recibir los ZIP actuales de los motores y preparar sus pruebas de regresión.
2. Incorporar Alembic, paginación de API y separación de routers por dominio.
3. Integrar el análisis documental y la lectura de certificados en el agente.
4. Adaptar primero el organizador de declaraciones y el renombrador OCR.
5. Añadir generación PDF y cola de impresión.
6. Preparar autenticación de usuarios, roles, aislamiento por despacho, HTTPS y almacenamiento de documentos para servidor antes del uso remoto real.

Referencias oficiales consultadas para la base técnica: FastAPI SQL databases (`https://fastapi.tiangolo.com/tutorial/sql-databases/`) y Vite build (`https://vite.dev/guide/build`).
