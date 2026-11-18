# Prueba real de la descarga de declaraciones del SAT

Guía para la primera prueba contra el portal real. Hasta ahora todo se probó con un SAT simulado. **Esta prueba la ejecuta una persona en su equipo, con su propia sesión; nada de esto se corre sin su autorización.**

## Reglas de la prueba

- La persona inicia sesión en la ventana del SAT con su FIEL o CIEC. ContaSuite y el agente nunca reciben, escriben ni guardan esos datos; el perfil del navegador sólo conserva cookies de navegación.
- El CAPTCHA, si aparece, lo resuelve la persona. No se automatiza.
- Una empresa, un ejercicio, una descarga a la vez. La cola ya descarga fila por fila con pausas; no se acelera.
- No se usa la instancia 8000, el piloto 8062 ni la instalación local 8072, ni su `.env`, `data/` o `agent/config.json`. Se usa una instancia de prueba aparte (ver abajo).
- Si algo no se reconoce, el agente no hace clics a ciegas: se detiene y lo dice.

## 1. Instancia y equipo de prueba

1. Instancia de prueba aparte: `INICIAR_PRUEBA_MANUAL.bat` (SQLite propio en `%LOCALAPPDATA%\ContaSuite\prueba-manual`, API en un puerto de 8090–8099, agente local vinculado). Crea ahí el primer administrador con la clave que muestra la consola.
2. Registra una empresa de prueba con el **RFC de la empresa cuyas declaraciones se van a consultar**. Los PDF descargados quedarán en esa instancia de prueba; se borran al terminar (paso 5).
3. La descarga no usa carpetas de la empresa ni carpetas autorizadas.

## 2. Preparar el agente

1. Ejecuta `INSTALAR_NAVEGADOR_SAT.bat`. Instala Playwright (versión fijada en `agent/requirements-sat.txt`) y el Firefox propio del agente en `%LOCALAPPDATA%\ContaSuite\agent\playwright-browsers`. Descarga unos 100 MB de la fuente oficial de Playwright.
2. En el `config.json` **del agente de la instancia de prueba** agrega el bloque de `agent/config.sat.example.json`:
   - `base_url`: la página de Personas Morales del original.
   - `guided: true`: hace el recorrido «Declara» › «Pagos provisionales del ISR».
   - `dry_run: true`: **primera prueba en seco** (no descarga nada).
3. Ejecuta `python scripts/sat_preflight.py --config <ruta del config.json de prueba>`. Sólo lee el equipo y la configuración (no imprime tokens, rutas ni la dirección completa) y debe terminar con «Listo para la prueba».
4. Reinicia el agente (`INICIAR_AGENTE.bat`) y entra a ContaSuite en la instancia de prueba para vincularlo.

## 3. Prueba en seco (no descarga nada)

En Declara, elige la empresa y pulsa «Descargar del SAT». Debe suceder, en orden:

| Estado de la tarjeta | Qué pasa en el equipo |
|---|---|
| Abriendo el navegador | Se abre una ventana de Firefox |
| Inicia sesión en el SAT… | El agente entra a Personas Morales y pulsa «Declara» y «Pagos provisionales del ISR». **Tú inicias sesión y llegas a la tabla «Consulta de declaraciones».** |
| Prueba en seco: se reconocieron N declaraciones | El agente lee la tabla y se detiene |

Se anota, sin datos del contribuyente:

- ¿La entrada guiada llegó sola a la pantalla de login, o hubo que seguir a mano?
- ¿La tarjeta dice «Dirección de consulta reconocida: sí»? Si dice «no», hay que ajustar `CONSULTA_URL_PARTS`.
- Los encabezados que reconoció (en «Lo que se reconoció en la tabla») frente a los reales: ¿están «No. de operación», «Tipo de declaración», «Ejercicio» y «Periodo»?
- ¿N coincide con el número de filas con icono PDF que se ven?
- ¿Dice que la tabla tiene más páginas? Si sí, esta versión sólo lee la visible (la paginación sigue pendiente).

Si no se reconoce nada (`sat_sin_controles` o `sat_sin_consulta`), no se pasa a la descarga: se ajustan los selectores en `agent/sat_selectors.py` con lo anotado.

## 4. Descarga real

Sólo con la prueba en seco correcta:

1. Quita `dry_run` del bloque `sat` y reinicia el agente.
2. Elige **un ejercicio** y descarga. Pausa y reintentos son automáticos; «Cancelar descarga» detiene la cola al terminar la fila actual y conserva lo ya recibido.
3. Revisa: PDF recibidos frente a filas detectadas, la lista «filas con error» (motivo e intentos) y que ninguna dice «El SAT no entregó un PDF» (señal de sesión vencida).
4. «Analizar PDF descargados» y revisa el análisis de Declara como con una carga manual.

Criterio de éxito: todas las filas con PDF descargadas o con su motivo; ningún archivo que no sea PDF; el análisis se crea una sola vez; el navegador nunca pidió ni recibió datos de acceso de ContaSuite.

## 5. Al terminar

- Cierra la ventana de Firefox, quita el bloque `sat` del `config.json` de prueba si no seguirás probando, y reinicia el agente.
- Borra el análisis y los PDF de la instancia de prueba (viven en su carpeta de `%LOCALAPPDATA%\ContaSuite\prueba-manual`; `INICIAR_PRUEBA_MANUAL.bat --reset` la conserva renombrada y empieza otra). Si quieres cerrar la sesión del SAT, ciérrala en la propia página.
- Para olvidar la sesión del navegador, borra `%LOCALAPPDATA%\ContaSuite\agent\sat-profile`.

## Qué traer de vuelta

Sin datos del contribuyente: el resultado de la prueba en seco (encabezados reconocidos, si coincidió la dirección, si hay paginación), los motivos de las filas con error y qué pasos de la entrada guiada hubo que hacer a mano. Con eso se ajustan selectores y se decide la paginación.

## Límites conocidos

- La paginación de la tabla no se recorre.
- El portal puede cambiar su página sin aviso; los selectores están aislados en `agent/sat_selectors.py` para ajustarlos rápido.
- Esta función es control documental de los PDF descargados; no certifica cumplimiento fiscal.
