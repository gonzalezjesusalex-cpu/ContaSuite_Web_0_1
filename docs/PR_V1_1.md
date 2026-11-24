**Título:** v1.1: semáforo documental, obligaciones por periodo, calendario de CFDI y gestor de contraseñas

## Qué cambia

Implementa el plan `docs/PLAN_V1_1_SEGUIMIENTO.md` (aprobado el 23/11/2026) sobre los módulos existentes, sin módulos paralelos:

- **Cambio 2 — Obligaciones por periodo** (`cs_0018`): catálogo de 20 obligaciones con nombre oficial de la CSF y regla de vencimiento; asignación desde la CSF con fechas de inicio y fin; casilla «hecho» con bitácora en `fiscal_history`; vencidas calculadas al leer; tarjetas, matriz y exportación a Excel. El lector de CSF ahora **rechaza la constancia del Infonavit** y lee la tabla de obligaciones por columnas (Oracle y cairo).
- **Cambio 1 — Semáforo documental** (`cs_0019`): lectores de opinión SAT (cadena original contra datos visibles y omisiones), opinión IMSS e Infonavit; cinco indicadores con vigencias del despacho configurables; «No aplica»; RFC distinto o folio repetido no se registran. Nada se presenta como validado ante la autoridad.
- **Vista del panel**: tarjetas de resumen, semáforo en el directorio y el expediente.
- **Cambio 3 — Calendario de CFDI** (`cs_0020`): emitidas y recibidas por mes y día desde los XML de CS-Storage; sin consulta al SAT.
- **Cambio 4 — Gestor de contraseñas** (`cs_0021`): cifrado por sobre con llave maestra protegida por DPAPI (`scripts/vault_keyring.py`); revelar o copiar sólo para administrador o permiso explícito, con reautenticación de 5 min y bitácora; archivos .cer/.key cifrados; importador de los dos Excel del despacho; exportación sólo para administradores; extensión MV3 (`extension/`) para llenar el acceso al portal del SAT con un boleto de un solo uso.

Detalle, decisiones confirmadas y pendientes: `docs/INFORME_V1_1.md`.

## Para revisar

- **Este PR incluye además 54 commits de `main` local que no estaban en `origin/main`** (Bloques del Prompt Maestro, cambios 1–5, centro documental, migraciones `cs_0014`–`cs_0017`). La rama v1.1 parte de `main` local 8cd8a43.
- Cambio de regla en `AGENTS.md`: se levanta la prohibición de guardar llaves FIEL y contraseñas **sólo** dentro del gestor.
- Pruebas existentes ajustadas a decisiones del plan: cabeza de migraciones `cs_0021`, columnas nuevas, filas sembradas por las migraciones (ninguna fila previa cambia) y revelado para administradores (428 sin reautenticación).
- Migraciones aditivas e idempotentes; aplicar sólo con `scripts/schema_admin.py` y respaldo. Ninguna instancia real se migró.
- Sin verificar: selectores del portal del SAT en la extensión.

## Validación

- Backend: 451 pasadas, 10 omitidas, 0 fallas (línea base 435); nuevas en `tests/test_v11.py` (16, documentos sintéticos).
- E2E: 26/26. `tsc`, ESLint y build sin errores.
- Calendario con 25 000 CFDI sintéticos: ~0.2 s por año.
- Revisión visual con servidor sintético (tema oscuro y 375 px).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
