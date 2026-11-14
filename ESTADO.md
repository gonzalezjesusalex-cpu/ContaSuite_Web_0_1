# Estado de ContaSuite Web

Actualizado: 13/11/2026. Versión `1.0.0-rc.1`. **v1.0 no está aprobada**: falta la aceptación en el equipo definitivo (Prioridad 5 de [PLAN_FINALIZACION.md](PLAN_FINALIZACION.md)).

## Instancias conocidas

Datos tomados de los informes de cada iteración; no se abrió su configuración privada. Ninguna se toca sin autorización explícita del usuario.

| Puerto | Instancia | Base | Datos / configuración | Estado |
|---:|---|---|---|---|
| 8000 | Instalación antigua (visita/v0.x) | Base antigua, esquema incompatible con RC1 | `.env` y `data/` de esta carpeta | Congelada. **Decisión (14/11/2026, punto 28): archivar intacta, no migrar.** Copia verificada con SHA-256 en `..\archivo\base-8000-20261114\` (fuera del repositorio); los originales siguen aquí hasta autorizar su retiro. |
| 8062 | Piloto «primera carpeta» | PostgreSQL privado, clúster bajo `.qa/pilot-first` | `.qa/pilot-first` (incluye `access.json`, `private.json`, dumps) | 1 empresa, 25.271 documentos importados; 18 excluidos; conflictos UUID y asociaciones ambiguas en revisión. Segunda carpeta **no** importada. |
| 8072 | Instalación local de pruebas (instalador RC1) | PostgreSQL privado `contasuite_local_*` | Carpeta de instalación `Pruebas-20261112-174658` (fuera de este repositorio) | Agente conectado. Importación PRISMA **pausada** (new=1197, duplicates=3); no reanudar sin instrucción. |
| 8060 | Piloto sintético | `contasuite_pilot_synthetic_001` | `.qa/` | Sólo datos generados. |
| 8056 / 8044 | Laboratorios de recuperación y v0.4 | Clústeres sintéticos | `.qa/` | Históricos; sólo datos ficticios. |

## Módulos vigentes

- **Inicio**: logo, saludo por hora, nombre configurado en su línea, «Bienvenido a ContaSuite» / «Tu espacio de trabajo contable.».
- **Empresas**: catálogo, expedientes, dashboard integral (primera pestaña), tareas, obligaciones, documentos, credenciales/certificados públicos, importar y conciliar. El módulo experimental de Empresas de escritorio no se integra.
- **CS-Storage**: núcleo documental, Centro Documental, indexador con lease/checkpoint, clasificación con revisión humana, fuentes locales y SMB (UNC de sólo lectura con la identidad Windows; ver `docs/SMB.md`).
- **Cuentas**: alta del primer administrador con `APP_TOKEN` (después deja de servir), scrypt, sesiones HttpOnly con CSRF, expiración por inactividad, HTTPS fuera de loopback. Colaboradores con lectura/escritura por empresa; Recopila, CFDI, Declara, Recibos, agentes, revisión global y administración requieren administrador.
- **Recopila, CFDI (antes Organizador), Declara, Recibos**: motores originales integrados por adaptadores web; trabajan con copias subidas, nunca modifican originales.
- **Importador**: XLSX con diagnósticos; confirmación definitiva de Excel real bloqueada.
- **Imprime**: descartado; no se muestra ni se integra.

## Lo que NO está activo

Conexión/descarga SAT automática, OCR, validación fiscal externa, revelación de secretos de credenciales, custodia de llaves privadas FIEL. Las fechas de un CER público no validan autenticidad ni revocación. La presencia de documentos no acredita cumplimiento.

## Validación más reciente

- **Bloque 1 del Prompt Maestro (registro desde la Constancia de Situación Fiscal con OCR local; 14/11/2026, migración `cs_0012`)**: backend 298 aprobadas, 1 omitida (antes 290), con 8 pruebas nuevas en `test_csf.py` sobre constancias sintéticas (moral con texto; física escaneada entre otros documentos, leída con RapidOCR); 14 `node --test` y 18/18 E2E; build, ESLint, Prettier y Ruff sin hallazgos. Revisión visual con servidor sintético: tarjeta de carga, campos «De la constancia» y en ámbar los de OCR, paso 2 con regímenes, obligaciones sugeridas y domicilio, actualización con tabla de cambios, expediente con la constancia adjunta (sólo sus páginas) y su fecha; sin desbordamiento a 360 px. Sin verificar: constancias reales (no se abrieron los archivos de `ARCHIVOS PRUEBA`), escaneos de mala calidad, PostgreSQL y el paquete de `ENTREGAS` regenerado con el OCR.
- **Bloque 2 del Prompt Maestro (roles, permisos y contador responsable; 14/11/2026, migraciones `cs_0007`–`cs_0011`, detalle en [docs/BLOQUE_2_ROLES.md](docs/BLOQUE_2_ROLES.md))**: backend 290 aprobadas, 1 omitida (antes 265); 14 pruebas `node --test` y 18/18 E2E (incluido contraste AA en los tres temas); build, ESLint, Prettier y Ruff sin hallazgos. Revisión visual con servidor sintético: expediente como administrador, contador (oscuro) y auxiliar (alto contraste), diálogo de responsable, historial, directorio y cuentas; sin desbordamiento a 360 px. Sin verificar: migraciones en PostgreSQL (no hay servidor de pruebas fuera de `.qa/`), lector de pantalla y las instancias reales, que necesitan la actualización con respaldo (`schema_admin.py --apply --backup`) antes de usar este código.
- Backend: 251 aprobadas, 1 omitida (privilegio de enlaces simbólicos en Windows) — 14/11/2026, comando único `cd backend && python -m pytest -q` sin `.env` real (incluye las suites aisladas de los lotes y el agente real).
- Frontend: compilación correcta, chunk principal 349 kB tras la carga diferida (antes 595 kB); 14 pruebas `node --test` y E2E Playwright de humo aprobadas — 14/11/2026.
- Cancelación de borradores verificada en navegador real (Edge, E2E `frontend/e2e/drafts.spec.ts`): enlace del menú, Atrás, cambio de sección, cierre de diálogo por Escape/Cerrar/clic fuera y recarga; cancelar conserva página y valores, aceptar descarta sin volver a preguntar. Contraste WCAG AA (axe-core, E2E `frontend/e2e/contrast.spec.ts`): 0 hallazgos en login y 19 pantallas en claro, oscuro y alto contraste (no cubre estados hover, diálogos abiertos ni lector de pantalla). Teclado (E2E `frontend/e2e/keyboard.spec.ts`): enlace para saltar al contenido, foco visible y nunca en elementos ocultos en 5 pantallas, pestañas con Enter/Espacio, foco atrapado en diálogos y devuelto al cerrar, inicio de sesión sin ratón. Punto 24 sin lector de pantalla (requiere prueba humana).
- Rendimiento RC1 del dashboard con 25.271 documentos: ~2,5 s y 92 consultas en PostgreSQL. Tras el punto 5 (13/11/2026, SQLite sintético, mismos 25.271 documentos): 40 consultas (antes 84 en SQLite), ~390 ms (antes ~486 ms), sin tope de 50.000 documentos. Pendiente medir en PostgreSQL.

## Linters (línea base 13/11/2026; ESLint y Ruff en 0 desde el 14/11/2026)

Comandos: `.venv\Scripts\python -m ruff check .` y `npm --prefix frontend run lint`. Formato: `ruff format --check .` y `npm --prefix frontend run format:check`.

- **ruff check: 0 hallazgos (14/11/2026; antes 225).** Mecánico: importaciones múltiples separadas y 78 importaciones sin uso retiradas, conservando con su motivo las que registran endpoints o tablas. Manual: nombres ambiguos, variables sin uso (sin tocar `_guard`, que mantiene el límite de memoria del extractor), `zip` con `strict` explícito, `raise ... from None` en errores de cara al usuario, lambdas como funciones. Excepciones declaradas: E402 en `main.py`/`integral_api.py` (routers tras crear la app; evita ciclos) y `except` amplios intencionados con justificación. Los motores originales siguen excluidos.
- **ESLint: 0 problemas (14/11/2026).** Corregidos los 3 errores de `Recopila.tsx` (importación y parámetro sin uso, `any` sustituido por un tipo del resumen) y `load` de `Credentials.tsx` con `useCallback`; los avisos de `ui.tsx` y `Companies.tsx:65` se resolvieron antes. Excepciones comentadas, sin cambio de comportamiento: `setParams`/`setContext` (cambian de identidad con cada URL en React Router 7 y crearían un bucle) y la vista previa de Recibos (depende de cada campo de `Item`, no del objeto).

Las correcciones que cambian comportamiento (dependencias de hooks, excepciones) se tratan una a una con su prueba.

## Dependencias (auditoría 14/11/2026)

Locks: `backend/requirements.lock.txt` (producción, perfil PostgreSQL) y `backend/requirements-dev.lock.txt` (añade pytest, ruff y sus dependencias). Comandos: `pip-audit -r backend/requirements.lock.txt --no-deps --disable-pip` (pip-audit en un entorno aparte) y `npm --prefix frontend audit`.

- **Python: 0 vulnerabilidades conocidas** en producción y desarrollo tras actualizar `fastapi` 0.121.1 → 0.162.7, `starlette` 0.49.3 → 1.10.0 (ahora fijado explícitamente), `python-multipart` 0.0.20 → 0.0.33, `cryptography` 46.0.3 → 50.0.2, `python-dotenv` 1.2.1 → 1.2.4 y `pytest` 9.0.0 → 9.2.0. Antes: 19 avisos en producción (entre ellos `StaticFiles` de Starlette en Windows) y 1 en pytest. `fastapi` añade `opentelemetry-api` (sólo API; sin SDK ni exportador no envía nada).
- **OCR local (Bloque 1, 14/11/2026):** `rapidocr` 3.10.0 + `onnxruntime` 1.32.0 y sus dependencias (OpenCV headless, numpy, shapely, pyclipper, omegaconf, requests…) en el lock de producción; `pip-audit` 0. Modelos incluidos en el paquete, sin uso de red. Verificado en una copia del runtime privado: CSF sintética escaneada leída completa en ~8 s (3 páginas). Peso: +270 MB instalado, +99 MB comprimido.
- **npm producción: 0.** Desarrollo: 7 moderadas en `typescript-eslint` → `minimatch` (DoS, sólo herramienta de lint), sin corregir.
- Pruebas: `httpx2` 2.16.0 (sucesor de `httpx` para `starlette.testclient`, mismo autor) sólo en desarrollo; elimina el aviso de obsolescencia. `httpx` sigue en producción para el supervisor local.

## Instalación definitiva (Fase 5, 14/11/2026)

Este equipo se usará como servidor definitivo. Sin permisos de administrador en la sesión de desarrollo: los pasos de sistema los ejecuta el usuario siguiendo [docs/INSTALACION_DEFINITIVA.md](docs/INSTALACION_DEFINITIVA.md).

- Paquete `..\ENTREGAS\ContaSuite_v1.0_RC1_20261114.zip` (+ `.sha256`): runtime Python 3.12 construido desde el lock de producción, frontend actual; sin datos ni secretos. Ensayado sin administrador: verificación de hashes, instalación en carpetas nuevas, arranque y `/api/health` 200 con cabeceras de seguridad; plan de servicio generado (registro real: WinError 5 sin administrador). Vigente (tras puntos 13, 18 y 19): SHA-256 `17f627d8…`. El runtime se construye en `..\ENTREGAS\_build\` (no en la carpeta temporal: un antivirus o una limpieza borró allí sus ejecutables) y `package_release.py` rechaza un runtime sin sus binarios esenciales.
- `scripts/verify_installation.py`: comprobación de sólo lectura de servicio, recuperación, loopback, firewall, ACL y HTTPS.
- Respaldos programados (punto 27): pospuestos hasta tener destino externo.
- Punto 19 hecho (14/11/2026): la aplicación rechaza SQLite salvo `CS_TEST_SQLITE=1` (pruebas, E2E, `INICIAR_PRUEBA.bat`); el paquete se regeneró con esta regla.
- Punto 18 hecho (14/11/2026): Recopila avisa antes de generar si un PDF no se puede leer (el motor original lo omitía en silencio; se resuelve en el adaptador, el motor no cambia); los trabajos de fondo de Recopila, Declara y CFDI y el agente registran el traceback; `integral_api` ya no tiene `except: pass`. Los `except` amplios intencionados llevan su justificación. Quedan 10 en scripts de laboratorio/piloto/visita (se tratan con Ruff) y los del motor `recopila_engine.py`, que no se modifica.

## Pendientes

Ver [PLAN_FINALIZACION.md](PLAN_FINALIZACION.md). Resumen:

1. Defectos: `/api/state` sin límite, crecimiento de `SecurityEvent`, trabajos del agente atascados, doble ruta del agente, dashboard lento, puertos incoherentes.
2. Orden: separar datos del código, migraciones unificadas, lanzadores.
3. Calidad: formato, linters, bundle, pruebas frontend, dependencias.
4. Infraestructura y aceptación: SCM, HTTPS/LAN, respaldo externo programado, decisión sobre la base 8000, aceptación con usuarios.

Los informes de iteraciones anteriores están en `docs/historico/` (sólo consulta).
