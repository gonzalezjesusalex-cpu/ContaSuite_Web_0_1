# Informe — Cambios 1 a 5 (ejecución autónoma)

Ejecutado el 2026-11-19 siguiendo `docs/PROMPT_SONNET_CAMBIOS_1_5.md`, sin push, sin tocar las instancias 8000, 8062 ni 8072, `.env`, `data/`, `agent/config.json` ni `.qa/`, sin abrir `ARCHIVOS PRUEBA/` (todas las pruebas usan archivos sintéticos generados por la propia prueba) y sin aplicar migraciones a ninguna base real. **No se declara v1.0.**

## Línea base y resultados finales

| | Línea base (antes del primer cambio) | Final |
|---|---|---|
| Backend `pytest -q -m "not slow"` | 396 aprobadas, 10 omitidas, 1 deseleccionada | — |
| Backend `pytest -q` completo (incluida la prueba `slow` del agente real) | — | **434 aprobadas, 10 omitidas** |
| `tsc --noEmit` y `npm run build` | sin errores | sin errores |
| E2E Playwright (`E2E_PORT=8096`) | — | **21 aprobadas** (humo, flujos, contraste AA en los 3 temas, teclado, borradores) |
| Ruff (`check`) sobre lo tocado | — | sin hallazgos |

Entorno: el `.venv` del repo no tiene `pytest`; se creó un venv temporal en el scratchpad con `py -3.12` y `backend/requirements-dev.txt`. Las pruebas corren sin `.env` real (`CS_TEST_SQLITE=1`).

**Revisión visual** (instancia sintética en el puerto 8095, ya detenida): pestañas de Documentos en tema claro y oscuro; anchos 320 y 768 sin desbordamiento horizontal (`scrollWidth` igual al ancho). El tema de alto contraste se verificó con la prueba E2E de contraste AA (el conmutador de la barra sólo alterna claro/oscuro). No se revisó con ojo cada pantalla nueva de Recopila/CFDI con datos reales: se comprobaron por tipos, build y pruebas de API.

La prueba viva (`slow`, `verify_live_agent.py`) se extendió: el agente real vinculado escribe un CFDI en la carpeta de una empresa, copia byte a byte, y una segunda corrida reporta «Duplicado» sin sobrescribir.

## Puntos, commits y estado

| Punto | Commit | Estado |
|---|---|---|
| 1.1 Línea de resumen en el encabezado | e9a9d27 | hecho |
| 1.2 Pestaña «Clasificación de carpeta» | e9a9d27 | hecho |
| 1.3 Pestaña «Por revisar» | e9a9d27 | hecho |
| 1.4 Explorador más ordenado | 899c5ec | hecho |
| 1.5 Grupos navegables | 686500d | hecho (parcial por diseño: 3 grupos) |
| 2.1 Datos del `.cer` | 51f30ed | hecho |
| 2.2 Una sola función de estado | 51f30ed | hecho |
| 2.4 «Detectados en la carpeta» | addc334 | hecho |
| 2.3 Chip en el encabezado | 02b1e3f | hecho |
| 2.5 Resumen en «Clasificación de carpeta» | 02b1e3f | hecho |
| 3A.1–3A.3 Periodos, diccionario y PAGO | e28c27a | hecho |
| 3A.7 Lector XLSX y pruebas | f1e124a | hecho |
| 3A.5 Catálogo | 3401c4d | hecho |
| 3A.4 Equivalencias | 929ca0a | hecho |
| 3A.6 Importar › Vista previa | 5fd8ad8 | hecho |
| 4.1 Enriquecimiento | 9bc1ee1 | hecho |
| 4.2, 4.3 Ajustes y persistencia | b7ba704 | hecho |
| 4.5 Guardar en expediente | 510e4c1 | hecho |
| 4.6, 4.4 Indicador, «Por revisar», documentos de la empresa | 72c102b | hecho |
| 4.7 Detección de formato no compatible (UI) | 5d2ac20 (detección en 9bc1ee1) | hecho; lector Contalink **pendiente** |
| 5.2, 5.3 Revisión de contenido y omitidos | 0eab765 | hecho |
| 5.1, 5.4, 5.5 Sugerencia, contraste con el expediente, guardado parcial | 4a71b18 | hecho |
| 5.7 Escribir en carpeta con el agente | 51c5c09 | hecho |
| 5.6 Indicador, corridas y UI de CFDI | 2c2ebd4 | hecho |

Los puntos 1.1–1.3 comparten `Documents.tsx` y se confirmaron juntos; 2.1/2.2 y 2.3/2.5, igual, por compartir archivos. 4.3 (migración) quedó después de 4.2 en el historial porque los ajustes ya necesitan sus tablas.

## Decisiones tomadas (sin preguntar)

**Cambio 1**
- **Contador de «Por revisar»:** «Sin clasificar» (documentos con clasificación pendiente) y «Conciliación» (revisiones de identidad/UUID) parten del mismo estado de clasificación, así que un documento puede aparecer en ambas y deduplicar exigiría backend. Se muestran **dos conteos separados** en la pestaña y en cada sección, nunca un total. Si el usuario sólo tiene un permiso, sólo ve esa sección; sin ninguno no hay pestaña.
- **1.4:** el detalle del documento sólo existe con un documento seleccionado; en anchos ≤ 900 px es un panel lateral fijo con botón de cierre.
- **1.5:** mapeo estático en el frontend, sin cambio de backend ni migración: «CFDI (XML)» → `cfdi`, «Representaciones PDF» → `cfdi_pdf`, «Reportes del SAT» → `sat_report`. «Declaraciones, acuses y pagos» comparte dos tipos documentales, e IMSS, nómina, financieros, legal e identificaciones no tienen tipo: quedan informativos. Los grupos sensibles nunca son navegables.

**Cambio 2**
- La vigencia usa `floor` de días completos hasta `notAfter`: vigente > 90, por vencer 30–90 inclusive, crítico < 30 aún vigente, vencido al pasar fecha y hora (90 d y 1 s todavía es «por vencer» porque el piso da 90). Se mantiene `aun_no` sólo si el inicio no llegó.
- El adaptador de lectura del `.cer` es `backend/app/cert_groups.py` (lo usa el agente; `agent/adapters.py` no lee certificados): añade serie (los 20 dígitos del SAT), emisor y fechas con hora UTC, y **deduplica por número de serie**. Las pruebas existentes se actualizaron: usaban serie fija 1 para todos los certificados.
- La UI recalcula los días desde `hasta_ts` con una copia mínima de la función del backend (`frontend/src/certStatus.ts`) para que un análisis viejo no muestre días obsoletos; la definición única sigue siendo la del backend.
- «Registrar» abre el flujo existente (el registro exige un documento `.cer` ya en el Centro Documental); nunca se asocia solo.

**Cambio 3A**
- Las migraciones del Control de obligaciones siguen su cadena propia: `backend/fiscal_migrations/002_catalogo_excel.py` y `003_equivalencias_excel.py` (idempotentes, sólo manuales, nunca al arrancar), no `migrations/versions`.
- Diccionario versionado en `backend/app/fiscal_dictionary.json`. El valor original se conserva literal en cada celda. `OK` sin fecha → cumplida + revisión; una fecha dentro de `PAGO` no acredita pago (queda `pending` + aviso); `paid` sólo con fecha en `PAGO IMPUESTOS FED`; `CEROS` conserva su propio `payment=not_applicable` aunque `PAGO` diga «CON PAGO».
- `fiscal_import.classify` (usada por los diagnósticos de empresas) no cambia; la lógica nueva es `propose`.
- La vista previa es sólo para administración, en memoria, no conserva el archivo ni escribe `fiscal_records`, lotes ni filas (verificado con conteos en la prueba). Sin tablas de equivalencias el servidor responde 503 al confirmar y la pantalla lo explica.
- Sin equivalencia confirmada la fila no entra a la propuesta; una coincidencia única por nombre sólo se propone.

**Cambio 4**
- Migración `cs_0016_recopila_policies` (pólizas, relación póliza–CFDI con origen motor/propuesta/manual, ajustes con actor y fecha). El motor `recopila_engine.py` no se tocó; `test_recopila.py` pasa sin cambios.
- El archivo RECOPILADOR general se guarda con el periodo del mes más reciente del análisis; los de `POR_MESES` con su propio mes. Se guarda como documento nuevo o **versión nueva** del que tenga misma empresa, tipo, periodo y nombre; contenido idéntico → «ya registrado».
- «Usar documentos de la empresa» toma todos los PDF/XML de la empresa con ese periodo (excepto tipo RECOPILADOR), incluidos los CFDI guardados desde el Organizador (5.6).
- La «pareja no verificada» no marca nada como representación de un CFDI: Recopila no registra representaciones individuales, sólo el RECOPILADOR.
- Estados de póliza: Completa / Parcial / XML sin PDF / Sin soporte; el porcentaje del indicador es Completa ÷ pólizas del periodo. Sin RFC de empresa no se compara RFC.

**Cambio 5**
- Migración `cs_0017_organizador_items` (archivo revisado, su estado y la decisión de quien revisa). El motor `organizador_engine.py` no se tocó; `test_organizador.py` pasa sin cambios.
- Incoherencia = emisor ≠ empresa en Emitidos, receptor ≠ empresa en Recibidos, fecha fuera del mes de la carpeta o XML ilegible; un PDF emparejado con un XML incoherente se bloquea también. Pareja sólo por UUID presente en el texto del PDF, nunca por nombre.
- Bloqueados o en revisión (incoherencia, mismo SHA ligado a otra empresa o a ninguna, mismo UUID con contenido distinto) van a «Por revisar › CFDI». Quien revisa **sólo puede guardar** un archivo cuya única incoherencia sea el periodo (elige carpeta o XML y queda con usuario y fecha); en cualquier otro motivo sólo puede descartarlo.
- El RFC del análisis debe ser el de la empresa para guardar en su expediente.
- 5.7: destino = carpeta de la empresa + ejercicio del análisis (`<carpeta>\AAAA\MM.- MES\EMITIDOS|RECIBIDOS`). Se escriben sólo los archivos aceptados (guardados o ya registrados) del ejercicio del análisis. Requiere agente vinculado, `cfdi.usar` y `carpeta.exportar`, y la casilla de confirmación explícita en pantalla.
- El tipo «Reportes del SAT» existe, pero **los reportes Excel no se guardan en el expediente**: el Centro Documental sólo admite PDF, XML y CER. El CSV de auditoría añade UUID, incoherencia, pareja y estado de guardado.

## Migraciones creadas (ninguna aplicada a una base real)

- `backend/migrations/versions/0016_recopila_polizas.py` y `0017_organizador_items.py` (cadena alembic; `HEAD` actualizado en `test_unified_baseline.py` y `scripts/verify_postgres.py`). Una base sin ellas no arranca con este código hasta migrarla con `scripts/schema_admin.py --apply --backup`.
- `backend/fiscal_migrations/002_catalogo_excel.py` y `003_equivalencias_excel.py` (manuales).

## Pendientes y bloqueados

- **4.7 Lector Contalink:** sólo detección («N páginas parecen pólizas en un formato no compatible»); el lector espera una muestra y no se adivina el formato.
- **3B:** importación definitiva, exportación XLSX y doble captura.
- **Panel global de certificados en Inicio** (fuera de alcance).
- **Lectura directa con el agente** (sin subir archivos) para Recopila y CFDI.
- **Reportes Excel del SAT en el expediente:** requiere ampliar los formatos del Centro Documental.
- **Tema de alto contraste:** sin conmutador en la barra; sólo verificado por la prueba de contraste AA.
- Sin verificar: los flujos de Recopila/CFDI con el agente real de punta a punta en el navegador (sí hay prueba viva del agente para 5.7), PostgreSQL y las migraciones sobre bases reales. Los flujos con datos sintéticos sí se verificaron: ver «Verificación posterior».

## Verificación posterior (2026-11-19)

Pasada de verificación con datos sintéticos, sin tocar datos ni instancias reales (servidor temporal en el puerto 8096).

**Pruebas E2E nuevas** (`frontend/e2e/`, helpers compartidos en `synthetic.ts`; todo el contenido lo genera la prueba):
- `cfdi-flow.spec.ts`: analizar un ZIP, contrastar con el expediente, guardado parcial (2 bloqueados a Por revisar › CFDI) e indicador por periodo.
- `recopila-flow.spec.ts`: analizar pólizas y CFDI, generar, guardar en el expediente, indicador y sección Recopila en Por revisar.
- `recopila-extra.spec.ts`: asociar un sobrante a una póliza y revertir el ajuste, aviso de formato no compatible y «Usar documentos de la empresa».
- `expectNoOverflow` (en `helpers.ts`): sin desborde horizontal en los tres temas (claro, oscuro y alto contraste) y a 320, 768 y 1280 px con resultados en pantalla (contraste de CFDI, Por revisar › CFDI, Recopila generado y expediente). Con `E2E_SHOTS` guarda capturas.

**Correcciones encontradas** (commits `fix:` propios):
- El indicador de Recopila decía «1 facturas sin póliza»; ahora usa singular.
- **Windows:** la detección de formato no compatible (4.7) contaba doble cada página, porque `rglob('*.pdf')` y `rglob('*.PDF')` listan el mismo archivo en un sistema de archivos que no distingue mayúsculas. Ahora hay un solo recorrido y la prueba exige exactamente 1.
- El aviso de formato no compatible decía «1 páginas parecen…»; ahora usa singular.

**Resultados:** E2E completo 25 aprobadas; `tsc` y build sin errores; backend completo 433 aprobadas, 10 omitidas y 1 fallo intermitente de la prueba `slow` del agente real (`test_live_agent_scan_over_http`), que corrida sola pasa en 29 s. Se atribuye a la carga de una suite de casi 9 minutos y queda anotado, sin causa confirmada.

**Siguen pendientes**
- 4.7 lector de Contalink: espera una muestra del formato.
- 3B (importación definitiva, exportación XLSX, doble captura) y panel global de certificados en Inicio: fuera de alcance de este prompt.
- Lectura directa con el agente para Recopila y CFDI.
- Reportes Excel del SAT en el expediente: requiere ampliar los formatos del Centro Documental.
- Conmutador de alto contraste en la barra.
- Escritura en la carpeta con el agente desde el navegador (sólo tiene prueba viva del agente).
- PostgreSQL y las migraciones 0016/0017/fiscal_002/003 sobre bases reales (requieren autorización: `scripts/schema_admin.py --apply --backup`).
