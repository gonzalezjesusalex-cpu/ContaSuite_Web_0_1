# Informe de implementación — plan v1.1 (24/11/2026)

Rama `feature/v1.1` (desde `main` 8cd8a43 + commit del plan). Sin push. Implementado sin pruebas por etapa, por
indicación del usuario; una prueba completa al final (ver «Validación»).

## Paso 1 — Revisión del código (qué se reutilizó)

| Cambio | Se reutiliza | Faltaba | Migración |
|---|---|---|---|
| 2 Obligaciones | `fiscal_control` (catálogo, aplicabilidad, registros, `fiscal_history`), lector de CSF del Bloque 1, contador responsable | Nombre oficial, grupo, periodicidad bimestral, regla de vencimiento, fechas inicio/fin por empresa; la tabla de obligaciones de la CSF se leía mal (tomaba la columna de vencimiento como descripción, sin fecha fin ni renglones partidos) | `cs_0018_csf_obligations` |
| 1 Semáforo | `integral_opinions` (autoridad, fecha, resultado, documento), `vault_certificates` (fechas del CER), `companies.csf_issued_on`, subida al expediente de la CSF | Folio, trabajadores, vigencia oficial, campos leídos, omisiones; «No aplica»; vigencias del despacho; lectores de opinión SAT/IMSS/Infonavit | `cs_0019_document_status` |
| 3 Calendario CFDI | Clasificador y subida/indexado de CS-Storage | No se guardaba día, importe ni RFC emisor/receptor por XML | `cs_0020_cfdi_calendar` |
| 4 Gestor | Bóveda (`vault_*`), permisos por empresa, bitácora, alertas de certificados | Revelado (estaba en 423), reautenticación, cifrado por sobre y llave maestra fuera del entorno, archivos .cer/.key, importador real, exportación | `cs_0021_password_manager` |

Hallazgos verificados con PDF sintéticos: el lector de CSF **aceptaba** la «Constancia de situación fiscal» del
Infonavit (corregido: ahora la rechaza con un mensaje que manda al semáforo). Con los dos generadores (Oracle,
3 páginas, columnas separadas; cairo, 2 páginas, con y sin encabezado) las obligaciones salen completas.

Línea base antes de cambiar código (worktree limpio de `main`): **435 pasadas, 10 omitidas, 1 deseleccionada (lenta)**.

## Commits

1. `33a33dd` Cambio 2 — catálogo y casillas por periodo (backend, lector de CSF).
2. `e88a7da` Cambio 1 — semáforo documental (lectores y vigencias).
3. `e414a3a` Vista del panel — tarjetas, semáforo, obligaciones por empresa (frontend).
4. `75326c1` Cambio 3 — calendario de CFDI.
5. `4448563` Cambio 4 — gestor de contraseñas y extensión.
6. Prueba final (este informe, `tests/test_v11.py` y correcciones).

## Decisiones tomadas por defecto (confirmar)

- **Llave maestra**: DPAPI de Windows en `<DATA_DIR>/vault/keyring.dpapi`, creada con `scripts/vault_keyring.py --init`
  (alcance del usuario de Windows; `--machine` si el servicio corre con otra cuenta) y respaldo fuera de línea con
  `--backup`. `CONTA_VAULT_KEYRING` queda sólo para pruebas/desarrollo.
- **Umbrales del semáforo** (editables por un administrador): SAT y CSF verde 0–5 / ámbar 6–7; IMSS verde el día /
  ámbar el siguiente; Infonavit 0–12 / 13–15; FIEL ámbar a 30 días del vencimiento.
- **Reautenticación**: 5 minutos. TOTP no existe aún (pendiente).
- **Revelar contraseñas**: administrador o permiso explícito «reveal» por empresa (el contador responsable ya no
  basta, ningún rol lo incluye).
- Las obligaciones bimestrales/trimestrales/anuales se muestran en el mes que cierra su periodo; el vencimiento no se
  recorre por días inhábiles.
- Tercera tarjeta azul de Contalink: no se agregó (por definir).

## Pendientes y límites conocidos

- Selectores del portal del SAT en la extensión: sin verificar contra el portal real; páginas configurables.
- Calendario de CFDI: los XML que sólo ve el índice virtual del agente (sin entrar a CS-Storage) no aparecen.
- Ejemplos aún faltantes: Infonavit con adeudo (la frase negativa es supuesta y queda para revisión), opinión SAT con
  otros sentidos, CSF de actividades empresariales/arrendamiento/RIF (nombres del catálogo no vistos en CSF reales
  son aproximados y editables).
- Instancias 8000/8062/8072 sin migrar (requiere autorización y respaldo).

## Validación (prueba única final, 24/11/2026)

- Backend: **451 pasadas, 10 omitidas, 0 fallas** (`-m "not slow"`; línea base 435). Nuevas: `tests/test_v11.py`
  (16: lector de CSF con Oracle/cairo e Infonavit rechazado, reglas de vencimiento, casillas con bitácora y vencidas,
  lectores SAT/IMSS/Infonavit, semáforo con vigencias y «No aplica», calendario de CFDI, gestor: reautenticación,
  revelado, boletos de un solo uso, importación de los dos Excel, exportación).
- Pruebas existentes ajustadas a decisiones del plan: cabeza de migraciones `cs_0021`, columnas nuevas de empresa y
  sesión, filas sembradas por las migraciones nuevas (ninguna fila previa cambia) y revelado para administradores
  (ahora 428 sin reautenticación en lugar de 403/423).
- E2E: **26/26**. Frontend: `tsc` y ESLint sin errores, build correcto. Ruff: limpio salvo un aviso preexistente en
  `tests/test_virtual_tree.py` (no tocado).
- Calendario con 25 000 CFDI sintéticos: ~0.2 s por año en SQLite.
- Revisión visual con servidor sintético: panel, directorio, expediente, casillas (tarjetas y matriz), calendario y
  gestor; tema oscuro y 375 px sin desbordamiento. Correcciones encontradas: foco del diálogo de reautenticación,
  barra de filtros antigua visible en «Obligaciones del periodo», empresas sin obligaciones en la matriz y texto
  duplicado «Sin documento».
- Llavero DPAPI probado en este equipo (crear, abrir, cifrar y descifrar).
