# Declara web

Declara está disponible en `/declara`, con el icono original y los controles compartidos de Stitch. El expediente de cada empresa incluye un acceso en la pestaña Declaraciones. No había una pantalla específica de Declara en las referencias Stitch; se utilizan las mismas tarjetas, botones, temas, tipografía y transiciones de los módulos funcionales existentes.

## Flujo

1. Selecciona la empresa y su nombre corto para los archivos.
2. Carga PDF individuales, la carpeta de una empresa/ejercicio o un único ZIP. Se admite un envoltorio de carpeta. El motor procesa sólo los PDF directos; no combina subcarpetas. Máximo 100 MB de carga, 1,000 PDF seleccionados o 5,000 PDF/500 MB descomprimidos en ZIP.
3. Revisa los nombres propuestos, RFC, periodo, tipo, excepciones y control mensual. Selecciona una fila para ver el PDF original y su detalle.
4. Si hace falta, resuelve otra copia o corrige el tipo en el plan. Los cambios se registran como manuales; el nombre final se aplica al generar. El mes debe haberse identificado para corregir el tipo.
5. Genera las copias y descarga los PDF renombrados en ZIP y la auditoría CSV por separado. Los archivos omitidos, ilegibles o de otro RFC no se incluyen en el ZIP; la auditoría los conserva y los originales siguen disponibles en el equipo y en la entrada del análisis.

## Reglas conservadas

El motor se extrae de `reference/desktop/Declara/organizador_sat_v26.py` mediante `scripts/extract_declara_engine.py`. La extracción elimina Tkinter, widgets, configuración y automatización de Firefox; las funciones de análisis, nombres, meses y renombrado conservan su AST original. Dos métodos del gestor de conflictos se convierten en funciones, sustituyendo únicamente `self.infos` y el widget del nombre de empresa por argumentos.

- Declaración normal: `N.- DECLARACION ISR E IVA MES EMPRESA.pdf`.
- Declaración complementaria: `N.1.- ...`.
- Acuse normal: `N.2.- ...`.
- Acuse complementaria: `N.3.- ...`.
- Se conservan consecutivos explícitos de complementarias y sub-consecutivos de copias adicionales.
- RESICO/SALARIOS conservan sus excepciones, respaldo por nombre/otras páginas y numeración dinámica. No se inventan RFC ni ejercicio cuando el PDF no permite recuperarlos.
- Se conserva la detección del RFC principal y la exclusión de RFC diferentes.
- Un mes se completa con declaración normal y acuse normal. Las complementarias no completan el mes. Los meses anteriores al alta de persona moral y los aún no exigibles conservan las reglas originales. Esto es control documental de los PDF cargados, no certificación fiscal ni consulta al SAT.

### Parches aprobados del rediseño (26/11/2026)

El extractor aplica sobre el original sólo la lista `PATCHES` de `scripts/extract_declara_engine.py`; la prueba de paridad (`backend/tests/test_declara_rules.py`) exige «original + esos parches» y compara los nombres finales contra el motor de escritorio sin parches.

- Copias idénticas por SHA-256: el primero (orden del resolvedor de colisiones) se procesa; los demás quedan en `COPIA IDÉNTICA` («Igual a …»), sin renombrar ni consecutivo y sin contar en el control. Las copias con huella distinta siguen con sub-consecutivos.
- Consecutivo de complementaria: sólo 1 o 2 dígitos tras COMPL/COMPLEMENTARIA o entre paréntesis o corchetes; nunca un año. El consecutivo final de un nombre que ya sigue el estándar (`N.k.- … 2`) se conserva para que reanalizar no cambie nombres correctos.
- RFC contra la empresa: `analyze_folder(..., expected_rfc)` marca `RFC DIFERENTE` lo que no coincide con la empresa seleccionada.
- PDF escaneado: «El PDF es una imagen, sin texto: clasifícalo manualmente.»
- `PdfInfo` añade `identical_to`, `count_in_control` y `origin`.

Lógica nueva fuera del motor, en `backend/app/declara_rules.py`: estado por mes (`COMPLETO`, `POR_VENCER`, `VENCIDO`, `EN_CURSO`, `FUTURO`, `NO_APLICA_ALTA`) con día límite configurable (17), faltantes, complementarias, RESICO y SALARIOS y fecha de vencimiento; fecha de alta de la Constancia con respaldo del RFC; nombre manual con validación, detección del estándar y casilla de conteo; estado `EXCLUIDO`. El adaptador web todavía no los usa (fase 2).

## Adaptación web

Los datos se vinculan a una empresa existente mediante `declara_runs`, con instantánea del RFC esperado, nombre corto, resumen, control de meses, fecha de evaluación y revisión del plan. Los planes e inputs se conservan en `data/declara/<id>`. La evaluación mensual se recalcula al consultar un análisis terminado si ha cambiado el día. Cada carga es un análisis independiente: sus meses describen sólo esa entrada; no deben sumarse o tratarse como un expediente consolidado sin una regla explícita de agregación para el dashboard.

La vinculación web añade una protección: si el RFC principal difiere de la empresa seleccionada, bloquea la generación y no publica control mensual. Tampoco permite resolver manualmente documentos de otro RFC para incluirlos en esa empresa. No cambia las reglas internas del motor.

La generación copia los PDF a un espacio de trabajo propio y aplica allí el renombrado original. Comprueba SHA-256 antes y después; nunca renombra los archivos subidos ni los originales del usuario. Sólo publica el ZIP al terminar. Cada plan se genera una vez; repetirlo exige una nueva carga. Las revisiones manuales usan control de versión y un cambio de estado atómico para impedir que otra sesión genere un plan desactualizado.

Las tareas se ejecutan dentro de FastAPI y requieren el lanzador de un solo proceso. Un reinicio durante análisis, edición o generación marca el análisis como error y pide repetir la carga. Antes de usar varios workers, sustituir esta recuperación por una cola coordinada. Las empresas con análisis de Declara conservan su historial y no se pueden eliminar.

Incluye `data/declara` en el respaldo junto con la base. No distribuyas `.qa/`, datos de ejecución, bases, credenciales ni paquetes de dependencias.

## Límites y siguiente etapa

La descarga desde el SAT se integra por fases con el agente local. Fases 1 y 2 (hechas): el agente abre un Firefox visible con perfil propio, la persona inicia sesión ella misma, el agente descarga uno por uno los PDF de la consulta, valida que sean PDF y los envía a ContaSuite; la tarjeta «Acceso SAT» muestra el estado (esperando al agente, abriendo, esperando inicio de sesión, descargando n de m, enviando). Sólo se ofrece cuando la configuración del agente trae `sat.base_url`, pensada hasta ahora para un SAT simulado: no se ha probado contra el portal real. Fase 3 (hecha): filtro por ejercicio, entrada guiada opcional al portal (`sat.guided`: pestaña «Declara» y enlace «Pagos provisionales del ISR», sin forzar la URL del inicio de sesión) y botón «Analizar PDF descargados», que crea el análisis de Declara con los PDF recibidos (una sola vez por descarga; después, «Ver análisis»). Fase 4 (hecha): cada fila con fallo de red o de tiempo se reintenta (2 veces); un archivo que no es PDF no se reintenta y tres seguidos detienen la cola por sesión vencida; «Cancelar descarga» desde la web detiene la cola al terminar la fila actual y conserva los PDF ya recibidos; cerrar la ventana del navegador termina el trabajo con un aviso claro; la tarjeta lista las filas con error (periodo, tipo, operación, motivo e intentos) y el registro del agente anota cada fila sin datos del usuario. Preparación de la prueba real (hecha): «prueba en seco» (`sat.dry_run`: reconoce la tabla y la describe sin descargar nada), `scripts/sat_preflight.py`, `INSTALAR_NAVEGADOR_SAT.bat` y la guía [PRUEBA_REAL_SAT.md](PRUEBA_REAL_SAT.md); la prueba contra el portal real no se ha ejecutado. Pendiente: recorrer las páginas de la tabla del SAT (el original sólo descarga las filas visibles) y la prueba contra el portal real. No hay captura de FIEL, llaves privadas ni contraseñas. No se han realizado descargas ni presentaciones ante SAT. No hay OCR: los formatos ordinarios requieren texto extraíble.

El siguiente trabajo acordado es el dashboard en la primera pestaña de Empresas, con seguimiento de FIEL y otros indicadores por definir. La lectura de vigencia de certificados públicos y la consolidación del control de Declara se implementarán en esa etapa; todavía no son funciones activas del dashboard.

## Validación

- Diez pruebas nuevas: paridad del motor por AST, normales/complementarias, control mensual, alta de persona moral, RESICO/SALARIOS, copias, correcciones manuales, revisiones obsoletas, RFC ajeno, límites, rutas peligrosas, contenido modificado y recuperación tras reinicio.
- Suite completa: 41 aprobadas, una omitida por falta del privilegio de enlaces simbólicos de Windows. Advertencia existente de obsolescencia en Starlette/AnyIO.
- Compilación TypeScript/Vite correcta.
- Flujo en Edge con datos sintéticos: carga, vista previa, resolución manual, generación, enlace del expediente y descarga real ZIP/CSV. Se verificaron los bytes originales de los tres PDF descargados y el registro manual en CSV. Revisión en los tres temas y móvil de 390 px, sin errores JavaScript ni desbordamiento horizontal de página.
