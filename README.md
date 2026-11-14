# ContaSuite Web

Plataforma para un despacho contable mexicano: catálogo de empresas y expedientes, Centro Documental (CS-Storage), control de obligaciones, credenciales/certificados públicos y los módulos Recopila, CFDI, Declara y Recibos.

Versión: `1.0.0-rc.1` (candidata; **no** aprobada para producción). Estado y pendientes: [ESTADO.md](ESTADO.md). Instalar, actualizar y respaldar: [OPERACION.md](OPERACION.md). Plan de cierre de v1.0: [PLAN_FINALIZACION.md](PLAN_FINALIZACION.md). Reglas para quien modifique el código: [AGENTS.md](AGENTS.md).

## Componentes

| Carpeta | Contenido |
|---|---|
| `backend/` | API FastAPI + SQLAlchemy. PostgreSQL en instalaciones; SQLite sólo en pruebas. Migraciones en `migrations/` (Alembic CS-Storage) y en las cadenas `*_migrations/`. |
| `frontend/` | React 19 + TypeScript + Vite, diseño Stitch (temas claro, oscuro y alto contraste). |
| `agent/` | Agente local Windows de sólo lectura para inventariar carpetas. |
| `scripts/` | Administración de esquema, respaldo/restauración, servicio Windows, empaquetado. |
| `deploy/windows/` | Lanzadores, plantilla Nginx y scripts de servicio. |
| `docs/` | Referencia técnica de módulos e instalación RC1. `docs/historico/` guarda informes de iteraciones anteriores. |
| `reference/desktop/` | Fuentes de escritorio originales usadas como referencia de los motores. |

## Desarrollo

Requisitos: Python 3.12 de 64 bits, Node.js (sólo para compilar/desarrollar el frontend).

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r backend/requirements-dev.txt
npm --prefix frontend ci
```

Pruebas:

```bash
cd backend && python -m pytest -q
npm --prefix frontend run build
npm --prefix frontend exec -- tsc --noEmit -p frontend/tsconfig.json
node --test frontend/tests/
```

Prueba E2E de humo (Playwright: primer acceso, sesión, empresas, expediente, subir y descargar documento). Requiere el frontend compilado; levanta su propio servidor sintético (`scripts/e2e_server.py`, SQLite temporal, puerto 8097) y no lee `.env` ni toca datos reales. Usa el Edge instalado; `E2E_PYTHON` indica el Python con `backend/requirements-dev.txt`:

```bash
npm --prefix frontend run build
E2E_PYTHON=.venv/Scripts/python npm --prefix frontend run e2e
```

Servidor de desarrollo: configurar un `.env` propio (ver `.env.example`, nunca uno con datos reales) y ejecutar `npm --prefix frontend run dev` (Vite 4173 + FastAPI). `scripts/dev.mjs` acepta `CONTA_PYTHON` con la ruta del Python preparado.

### Puertos

`CS_PORT` es la única fuente del puerto de la API; `--port` explícito tiene prioridad. Sin `CS_PORT`, cada lanzador usa su valor documentado:

| Lanzador | Puerto por defecto |
|---|---|
| Servicio empaquetado (`service_runtime`, `windows_service`, `service_admin`) | 8062 |
| Desarrollo (`npm run dev`: API y proxy de Vite) | 8090 |
| `INICIAR_CONTASUITE.bat` / `INICIAR_PRUEBA.bat` (instancia antigua de esta carpeta) | 8000, hasta decidir su destino |
| Instalador local de pruebas | 8072 (elegido en el asistente) |

El arranque de la API **no migra ni siembra datos**: sólo verifica que el esquema sea compatible. Una base nueva se prepara con `scripts/schema_admin.py` (ver [OPERACION.md](OPERACION.md)).

## Qué no hay que versionar ni entregar

`.env`, `data/`, `.qa/`, `agent/config.json`, entornos `.venv*`, `node_modules/`, `frontend/dist/`, dumps y cualquier credencial. Ya están en `.gitignore`.
