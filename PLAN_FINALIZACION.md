# ContaSuite Web — Plan de finalización v1.0

Fecha del análisis: 13 de noviembre de 2026. Versión analizada: `1.0.0-rc.1`.
Alcance revisado: backend completo (`backend/app`, migraciones, pruebas), frontend (`frontend/src`), agente, lanzadores, `deploy/windows`, scripts de instalación/respaldo y documentos de validación. No se abrieron `.env`, `agent/config.json` ni archivos de credenciales. Las pruebas no se ejecutaron durante el análisis.

## Diagnóstico general

Base sólida: seguridad bien implementada, trazabilidad documental cuidadosa y unas 200 pruebas de backend. Antes de declarar v1.0 hay que corregir 3 defectos reales de rendimiento/operación, ordenar un proyecto muy fragmentado y hacer legible el código.

### Lo que está bien y NO se debe tocar

- Autenticación: scrypt, bloqueo por intentos, cookies HttpOnly, CSRF, expiración por inactividad de 30 min, HTTPS obligatorio fuera de loopback, errores 422 sin datos enviados.
- Validación de rutas: bloqueo de enlaces/junctions/nombres reservados (`backend/app/storage/paths.py`).
- Arranque que sólo verifica esquema; actualizaciones explícitas con respaldo.
- Bloqueos `pg_advisory_xact_lock` en PostgreSQL para evitar duplicados.

---

## 🔴 Prioridad 1 — Defectos a corregir antes de finalizar

> **Estado al 18/11/2026:** los puntos 1 (`document_counts` y sondeo), 2 (`security_retention.py`), 3 (caducidad de trabajos, ahora renovable con el latido) y 4 (agente con una sola ruta) ya están corregidos en el código; el texto de cada uno se conserva como registro. Quedan el 5 (medir en PostgreSQL) y el 6 (revisar `deploy/windows`; `vite.config.ts` y `scripts/dev.mjs` ya usan `CS_PORT`).
>
> **Mejoras del análisis estático (18/11/2026):** 1 recorrido incompleto — hecha; 2 renovación del trabajo con el latido — hecha; 3 resultados fuera de `/api/state` y último trabajo por empresa — hecha; 4 acción `trabajadores.ver` — hecha; 5 árbol virtual en SQL — hecha; 6 aviso del lanzador al cerrar con el agente ocupado — hecha, **sin commit** (`scripts/dev_launcher.py` sin confirmar); 7 documentación — esta actualización. Ninguna requiere migración. Verificado con pruebas sintéticas; sin verificar en PostgreSQL, en el navegador ni con el agente real. No se declara v1.0 aprobada.

1. **`/api/state` devuelve TODOS los documentos y se consulta cada 10 s.**
   - `frontend/src/App.tsx` hace `setInterval(refresh, 10000)`; `backend/app/main.py` (`state`) devuelve `documents` sin límite. Con 25.271 documentos son varios MB por pestaña cada 10 s.
   - El frontend sólo usa `state.documents` para contar (`modules/Companies.tsx`, `modules/Dossier.tsx`).
   - Corrección: sustituir la lista por conteos por empresa (`document_counts: {company_id: n}` + total), subir el intervalo a 30–60 s o refrescar sólo con el evento `contasuite-data-changed`/foco de ventana. Ajustar `types.ts`.
2. **`SecurityEvent` crece sin límite.**
   - El middleware `security_audit` de `main.py` escribe una fila por cada petición `/api/*`, incluido el sondeo de `/state` (~8.600 filas/día por pestaña). No hay purga.
   - Corrección: no auditar lecturas GET de sondeo (o sólo las fallidas/denegadas) y añadir retención configurable (p. ej. 12 meses) ejecutada desde el mantenimiento existente (`scripts/maintenance_backup.py` o el trabajador de alertas).
3. **Trabajos del agente atascados en `running`.**
   - `main.py` (`claim`/`result`): si el agente muere tras reclamar, el trabajo queda `running` para siempre.
   - Corrección: columna/uso de `claimed_at` y expiración (p. ej. 15 min) que lo marque `failed` con mensaje claro, o lo devuelva a `queued` una sola vez.
4. **Agente con dos rutas de código.**
   - `agent/agent.py`: `INICIAR_AGENTE.bat` ejecuta `main()`, que usa `scan_folder` (incluye `.key` en `SUPPORTED`, no aplica exclusiones de secretos). La ruta nueva `run()` usa `safe_inventory` con `SECRET_PATTERNS`.
   - Corrección: que `main()` delegue en `run()`; eliminar `scan_folder` y su `SUPPORTED`. Actualizar `scripts/test_agent_package.py` / pruebas.
5. **Dashboard integral lento y con tope fijo.**
   - `docs/RC1_VALIDATION.md`: ~2,5 s, 92 consultas por lectura, tope de 50.000 documentos (`backend/app/integral_dashboard.py`).
   - Corrección: agregación SQL con `GROUP BY`/`COUNT` y revisar índices en `documents.company_id`, vínculos y revisiones. Objetivo: <10 consultas y <500 ms con 25k documentos.
6. **Puertos incoherentes.**
   - RC1 usa 8062, pero `frontend/vite.config.ts` (proxy), `deploy/windows/Start-ContaSuite.cmd` y `.ps1`, y `scripts/dev.mjs` usan 8000 (base antigua incompatible).
   - Corrección: una sola fuente (`CS_PORT`, valor por defecto 8062) leída por todos.

## 🟠 Prioridad 2 — Ordenar el proyecto

7. **Separar código de datos.** Sacar de la carpeta de código: `.qa/` (contiene dumps de importación real y `access.json`), `data/`, `.env`, `.venv-anterior-*`, `backend/.pytest_cache` (16 MB), `__pycache__`. Estructura propuesta:
   ```
   ContaSuite Web/
     ContaSuite_Web/          ← sólo código fuente (repositorio Git)
     instancias/piloto-8062/  ← datos, .env, respaldos
     instancias/local-8072/
     archivo/qa-historico/    ← contenido actual de .qa
   ```
   ⚠️ Mover, nunca borrar. Las rutas absolutas en configuraciones de instancias existentes deben revisarse antes de mover nada.
8. **Git real.** Repositorio limpio, commit inicial del estado actual, etiqueta `v1.0.0-rc.1`, una rama por fase.
9. **Documentación consolidada.** Tres documentos vivos:
   - `README.md` — qué es y cómo arrancar.
   - `ESTADO.md` — qué está vigente, pendientes, tabla de instancias (puerto, base, carpeta de datos, estado).
   - `OPERACION.md` — instalar, actualizar, respaldar, restaurar.
   El resto a `docs/historico/`. `AGENTS.md` reducido a reglas vigentes (sin capas superpuestas).
10. **Migraciones unificadas.** Hoy: Alembic (`migrations/versions` 0001–0005) + 7 cadenas propias (`company_`, `credential_`, `fiscal_`, `import_`, `integral_`, `lote4_migrations`) aplicadas en orden fijo por `scripts/schema_admin.py` + `create_all`, sin registro de versión. Para v1.0: una sola cadena Alembic con baseline del esquema actual, de modo que `alembic current` diagnostique cualquier base (incluida la del 8000).
11. **Lanzadores.** Reducir los ~12 `.bat`/`.cmd` a: Instalar, Abrir, Detener, Respaldar (+ Administración). Retirar los de v0.4/visita/piloto a `archivo/`.

## 🟡 Prioridad 3 — Calidad de código

12. **Formato.** Frontend: 411 de 975 líneas >160 caracteres (máx. 4.475). Backend: funciones enteras en una línea con `;`. Aplicar Prettier y `ruff format` SIN cambios de lógica, en un commit aislado, con pruebas antes y después.
13. **Linters.** ESLint (`react-hooks`) y `ruff check`.
14. **Bundle.** Sin `React.lazy`; chunk principal >500 KB. Carga diferida por ruta (Declara, Recibos, Recopila, CFDI, Configuración).
15. **Pruebas frontend.** Sólo `frontend/tests/lote2.test.mjs` y `lote4.test.mjs`. Añadir E2E mínimo con Playwright (login, empresas, expediente, subir/descargar documento) partiendo de `.qa/smoke.cjs`.
16. **Suite backend unificada.** Integrar `backend/tests/run_lote*_isolated.py` en pytest con marcadores (`postgres`, `windows`) y un comando único documentado.
17. **Dependencias.** Separar lock de producción y de desarrollo (hoy `requirements-recovery.lock.txt` incluye pytest/httpx). Ejecutar `pip-audit` y `npm audit`.
18. **`except Exception` silenciosos.** 25 casos; revisar especialmente `integral_api.py:65` y `recopila_engine.py` (263, 275) para al menos registrar el error.
19. **PostgreSQL obligatorio en producción.** Los bloqueos advisory no tienen efecto en SQLite; `INICIAR_PRUEBA.bat` arranca SQLite portable. Hacer explícito y forzado que SQLite es sólo para pruebas.
20. **Sin credenciales por defecto.** `backend/app/database.py` usa `contasuite:contasuite` como `DATABASE_URL` por defecto; en modo producción debe fallar si no está definida.
21. **Cabeceras de seguridad en el HTML.** `Content-Security-Policy`, `X-Frame-Options: DENY`, `Referrer-Policy` (hoy sólo se aplican cabeceras a `/api/`).

## 🔵 Prioridad 4 — Experiencia de usuario

22. **Empresas tiene 14 pestañas** (`modules/Companies.tsx`), con duplicados: "Control de obligaciones" y "Obligaciones Fiscales" renderizan el mismo `FiscalControl`; "Tareas Operativas" duplica `/tareas`; "Resumen Ejecutivo" es código muerto. Reagrupar en 5–6 secciones (Panel, Directorio, Documentos, Obligaciones, Credenciales, Importar).
23. **Configuración** aún incluye la vista previa Stitch con datos de ejemplo ("pendiente de integrar"). Retirarla en la versión final.
24. **Accesibilidad.** Completar teclado, contraste en los tres temas y la cancelación de borradores (documentada como no verificada).

## ⚙️ Prioridad 5 — Infraestructura y aceptación (equipo definitivo, con autorización)

25. Servicio Windows registrado en SCM (hoy WinError 5), reinicio y recuperación tras caída.
26. HTTPS en LAN: certificado, DNS, firewall, prueba desde otra PC.
27. Respaldo programado a destino externo + restauración de prueba documentada.
28. Decisión sobre la base del puerto 8000: respaldar y migrar, o archivar.
29. Aceptación con usuarios del despacho: lista firmada de flujos aprobados.

---

## Ruta de ejecución

| Fase | Contenido | Riesgo |
|---|---|---|
| 0. Limpieza | Puntos 7–11 | Nulo (no toca lógica) |
| 1. Formato | Puntos 12–13 | Bajo (mecánico, verificado con pruebas) |
| 2. Defectos | Puntos 1–6, 20–21 | Medio (cada uno con su prueba) |
| 3. Rendimiento y frontend | Puntos 5, 14, 22–23 | Medio |
| 4. Pruebas | Puntos 15–17 | Bajo |
| 5. Aceptación | Puntos 25–29 | Requiere autorización |
| 6. v1.0 | Etiqueta, instalador final, manual de operación | — |

## Reglas que siguen vigentes

- No reescribir módulos estables; integrar y corregir.
- Conservar el diseño Stitch, temas claro/oscuro/alto contraste y `prefers-reduced-motion`.
- Imprime está descartado; no reactivarlo.
- No migrar la base del 8000, no importar la segunda carpeta, no tocar el piloto 8062 ni la instalación 8072 sin autorización explícita.
- No fusionar documentos por UUID/nombre/RFC; los conflictos siguen en revisión humana.
- No incluir datos, dumps, `.env`, credenciales ni `.qa` en entregas.
- No declarar v1.0 aprobada hasta cerrar la Prioridad 5.
