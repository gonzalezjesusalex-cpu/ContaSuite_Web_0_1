# ContaSuite Web — reglas para agentes

Plan vigente: [PLAN_FINALIZACION.md](PLAN_FINALIZACION.md) (manda sobre cualquier otro documento). Estado e instancias: [ESTADO.md](ESTADO.md). Operación: [OPERACION.md](OPERACION.md). Informes y reglas de iteraciones anteriores: `docs/historico/` (sólo consulta; no sustituyen a este archivo).

## Datos, instancias y secretos

- No tocar sin autorización explícita del usuario: la base/instancia del puerto 8000, el piloto 8062, la instalación local 8072, `.env`, `data/`, `agent/config.json` ni nada dentro de `.qa/`.
- No abrir ni mostrar secretos: `.env`, `access.json`, `private.json`, configuración del agente, dumps.
- No mover ni borrar archivos de datos. Si algo debe moverse, proponer antes la lista exacta.
- No migrar bases reales ni importar la segunda carpeta del piloto. No reanudar la importación PRISMA pausada en 8072.
- No fusionar documentos por UUID, nombre ni RFC: conflictos y asociaciones ambiguas quedan en revisión humana.
- No incluir datos, dumps, `.env`, credenciales, `.qa/` ni documentos empresariales en commits ni entregas.
- No declarar v1.0 aprobada.

## Código y diseño

- Continuar el proyecto existente: no reescribir módulos estables; corregir e integrar sobre el código actual, un módulo a la vez.
- Conservar el diseño Stitch (botones, colores, iconos originales de ContaSuite 0.6, bordes, sombras, espaciados, animaciones). Fuentes: `design-source/`, `frontend/src/designs/`, `frontend/tailwind.config.cjs`; controles compartidos en `frontend/src/components/stitch.ts` y reglas `.stitch-live-module` en `styles.css`.
- Mantener temas claro, oscuro y alto contraste, y respetar `prefers-reduced-motion`.
- Inicio: logo, saludo por hora local, nombre configurado en su propia línea, «Bienvenido a ContaSuite», «Tu espacio de trabajo contable.».
- Nombres visibles: Recopila, CFDI (antes Organizador), Declara y Recibos. Imprime está descartado. Empresas experimental de escritorio no se integra.
- No presentar como activas funciones no implementadas (SAT, OCR, impresión, contadores ficticios de Stitch).
- Motores originales sin cambios: `backend/app/recopila_engine.py`, `backend/app/organizador_engine.py`, `backend/app/declara_engine.py` (extraído con `scripts/extract_declara_engine.py`). Adaptar mediante sus adaptadores web.

## Seguridad

- Nunca aceptar actores, roles ni ámbitos enviados por el cliente fuera de endpoints administrativos autorizados.
- No guardar llaves privadas FIEL ni contraseñas de red. Fechas de un CER no son validación SAT.
- El arranque sólo verifica esquema; nunca migrar ni sembrar al iniciar. Cambios de esquema mediante migración explícita con respaldo.

## Forma de trabajar

- Una fase a la vez y un punto a la vez; cada punto en su propio commit, con las pruebas afectadas ejecutadas y aprobación del usuario antes de seguir.
- Antes de cambiar lógica, ejecutar la línea base de pruebas y anotarla.
- Git no está en el PATH de este equipo: usar el `git.exe` de GitHub Desktop. No hacer push sin autorización.

## Validación

- Backend: `cd backend && python -m pytest -q` (comando único: incluye las suites aisladas `tests/run_*.py` en subprocesos y la prueba `slow` del agente real; `-m "not slow"` la omite). `backend/app/database.py` carga `.env` de la raíz: ejecutar las pruebas sin `.env` real (dotenv deshabilitado y `DATABASE_URL` SQLite temporal), como hace `backend/tests/test_api.py`.
- E2E: `npm --prefix frontend run build` y `npm --prefix frontend run e2e` con `E2E_PYTHON` (servidor sintético propio, ver README).
- Frontend: `npm --prefix frontend ci` y `npm --prefix frontend run build`; sólo tipos: `npm --prefix frontend exec -- tsc --noEmit -p frontend/tsconfig.json`.
