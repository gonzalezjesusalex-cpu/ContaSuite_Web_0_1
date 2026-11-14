# Estado de ContaSuite Web

Actualizado: 13/11/2026. Versión `1.0.0-rc.1`. **v1.0 no está aprobada**: falta la aceptación en el equipo definitivo (Prioridad 5 de [PLAN_FINALIZACION.md](PLAN_FINALIZACION.md)).

## Instancias conocidas

Datos tomados de los informes de cada iteración; no se abrió su configuración privada. Ninguna se toca sin autorización explícita del usuario.

| Puerto | Instancia | Base | Datos / configuración | Estado |
|---:|---|---|---|---|
| 8000 | Instalación antigua (visita/v0.x) | Base antigua, esquema incompatible con RC1 | `.env` y `data/` de esta carpeta | Congelada. No iniciar ni migrar. Decisión pendiente (plan, punto 28). |
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

- Backend: 251 aprobadas, 1 omitida (privilegio de enlaces simbólicos en Windows) — 14/11/2026, comando único `cd backend && python -m pytest -q` sin `.env` real (incluye las suites aisladas de los lotes y el agente real).
- Frontend: compilación correcta, chunk principal 349 kB tras la carga diferida (antes 595 kB); 14 pruebas `node --test` y E2E Playwright de humo aprobadas — 14/11/2026.
- Rendimiento RC1 del dashboard con 25.271 documentos: ~2,5 s y 92 consultas en PostgreSQL. Tras el punto 5 (13/11/2026, SQLite sintético, mismos 25.271 documentos): 40 consultas (antes 84 en SQLite), ~390 ms (antes ~486 ms), sin tope de 50.000 documentos. Pendiente medir en PostgreSQL.

## Linters (línea base 13/11/2026, sin corregir)

Comandos: `.venv\Scripts\python -m ruff check .` y `npm --prefix frontend run lint`. Formato: `ruff format --check .` y `npm --prefix frontend run format:check`.

- **ruff check: 225 hallazgos.** 80 importaciones sin uso (F401, sobre todo `app`/`scripts`; algunas pueden registrar modelos por efecto lateral), 62 importaciones múltiples en una línea (E401), 35 `except Exception` amplios (BLE001, plan punto 18), 16 importaciones fuera de cabecera en `app` (E402), 11 nombres ambiguos `l`/`O` (E741), 7 variables sin uso (F841: `integral_dashboard.py` `base_ids`/`today`, `pilot_batch_extract.py` `guard`), 4 `raise` sin `from` (B904), 3 `zip` sin `strict` (B905), 3 lambdas asignadas (E731), 2 variables de bucle sin uso (B007), 1 f-string sin campos (F541), 1 `try/except/pass` (S110).
- **ESLint: 3 errores, 6 advertencias.** `Recopila.tsx`: importación `InputHTMLAttributes` y parámetro `i` sin uso, un `any`. `react-hooks/exhaustive-deps`: `ui.tsx:32` (ref en limpieza de efecto), `Companies.tsx:65` (`tabs`) y `:104` (`setParams`), `Credentials.tsx:467` (`load`), `IntegralDashboard.tsx:144` (`setContext`), `Receipts.tsx:167` (`item`). `rules-of-hooks`: sin infracciones.

Las correcciones que cambian comportamiento (dependencias de hooks, excepciones) se tratan una a una con su prueba.

## Dependencias (auditoría 14/11/2026)

Locks: `backend/requirements.lock.txt` (producción, perfil PostgreSQL) y `backend/requirements-dev.lock.txt` (añade pytest, ruff y sus dependencias). Comandos: `pip-audit -r backend/requirements.lock.txt --no-deps --disable-pip` (pip-audit en un entorno aparte) y `npm --prefix frontend audit`.

- **Python: 0 vulnerabilidades conocidas** en producción y desarrollo tras actualizar `fastapi` 0.121.1 → 0.162.7, `starlette` 0.49.3 → 1.10.0 (ahora fijado explícitamente), `python-multipart` 0.0.20 → 0.0.33, `cryptography` 46.0.3 → 50.0.2, `python-dotenv` 1.2.1 → 1.2.4 y `pytest` 9.0.0 → 9.2.0. Antes: 19 avisos en producción (entre ellos `StaticFiles` de Starlette en Windows) y 1 en pytest. `fastapi` añade `opentelemetry-api` (sólo API; sin SDK ni exportador no envía nada).
- **npm producción: 0.** Desarrollo: 7 moderadas en `typescript-eslint` → `minimatch` (DoS, sólo herramienta de lint), sin corregir.
- Pendiente menor: `starlette.testclient` avisa que `httpx` está obsoleto para pruebas y recomienda `httpx2`; sólo afecta a la suite.

## Pendientes

Ver [PLAN_FINALIZACION.md](PLAN_FINALIZACION.md). Resumen:

1. Defectos: `/api/state` sin límite, crecimiento de `SecurityEvent`, trabajos del agente atascados, doble ruta del agente, dashboard lento, puertos incoherentes.
2. Orden: separar datos del código, migraciones unificadas, lanzadores.
3. Calidad: formato, linters, bundle, pruebas frontend, dependencias.
4. Infraestructura y aceptación: SCM, HTTPS/LAN, respaldo externo programado, decisión sobre la base 8000, aceptación con usuarios.

Los informes de iteraciones anteriores están en `docs/historico/` (sólo consulta).
