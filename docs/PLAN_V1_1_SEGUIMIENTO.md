# ContaSuite Web — Plan v1.1: seguimiento documental y obligaciones

Diseño cerrado el 23/11/2026 y aprobado por el usuario. Estado: **listo para codificar** (no implementado).
Origen de los conceptos: funciones de la plataforma Contalink que el despacho usa hoy. Se replica la **funcionalidad**, no el diseño: íconos, colores y disposición propios, alineados al diseño Stitch de ContaSuite (temas claro, oscuro y alto contraste; `prefers-reduced-motion`).
Lo visual y los detalles finos se ajustan al codificar, después de revisar el código actual en el equipo de desarrollo (no se revisó el código para este borrador).

Reglas que siguen vigentes (ver `AGENTS.md`): no presentar como activas funciones no implementadas (no hay consulta SAT/IMSS/Infonavit automática), no guardar llaves privadas FIEL, cambios de esquema sólo por migración explícita con respaldo.

---

## Cambio 1 — Semáforo documental por empresa

**Qué es.** Cinco indicadores por empresa que muestran la vigencia de los documentos que el despacho rastrea. Aparecen en cada fila/tarjeta del directorio y en el expediente, con tarjetas de resumen en el panel.

| # | Documento | Ícono propuesto (lucide) | Qué determina su estado |
|---|---|---|---|
| 1 | Vigencia de la FIEL | `KeyRound` | Fecha de vencimiento del certificado (ya se lee del CER público) |
| 2 | Constancia de Situación Fiscal (CSF) | `FileBadge` | Fecha de emisión + días de vigencia configurables |
| 3 | Opinión de cumplimiento SAT | `ShieldCheck` | Resultado (positiva / negativa) + fecha de emisión y días de vigencia |
| 4 | Infonavit (opcional) | `Landmark` | Documento vigente; admite «No aplica» (empresas sin trabajadores) |
| 5 | Opinión de cumplimiento IMSS | `HeartPulse` | Resultado + fecha de emisión y días de vigencia |

Los íconos son libres, con una condición: que no se parezcan a los de Contalink.

El buzón tributario **no se incluye** (decisión del 23/11/2026).

**Estados (comunes a los cinco).** Vigente / positiva (verde) · Por vencer (ámbar, umbral configurable) · Vencido / negativa (rojo) · Sin documento (gris) · No aplica (sólo Infonavit e IMSS, cuando la empresa no tiene trabajadores).

**Tarjetas de resumen del panel** (equivalentes a las de Contalink):
- RFC activos con desglose personas físicas / morales.
- Opinión de cumplimiento SAT: porcentaje positivo y conteo positivas / negativas / sin opinión.
- Documentos por vencer en los próximos N días.
- (Por definir) la tercera tarjeta que Contalink muestra en azul.

**Vigencia que usa el despacho (decisión del 23/11/2026).** El semáforo usa la vigencia del despacho, no la oficial. La oficial se guarda tal como viene en el documento.

| Documento | Vigencia oficial (del documento) | Vigencia del despacho | Propuesta de semáforo (configurable) |
|---|---|---|---|
| Opinión SAT | (no la indica el PDF) | **7 días** | Verde 0–5 días · ámbar 6–7 · rojo más de 7 |
| Constancia de Situación Fiscal (SAT) | (no aplica) | **7 días** | Verde 0–5 días · ámbar 6–7 · rojo más de 7 |
| Opinión IMSS | Mismo día, hasta 23:59:59 | **1 día** | Verde el día de emisión · ámbar el día siguiente · rojo después |
| Infonavit | 30 días desde la expedición | **15 días** | Verde 0–12 días · ámbar 13–15 · rojo más de 15 |

Los umbrales de ámbar son una propuesta; el usuario los confirma al implementar. Una opinión negativa o con adeudo va en rojo aunque sea reciente.

**Captura (decisión del 23/11/2026).** Igual que el registro de empresa desde la CSF (Bloque 1): al subir el PDF al expediente se lee en automático (tipo de documento, fecha, resultado, folio, RFC, trabajadores activos) y el usuario confirma o corrige antes de guardar. Los campos leídos se distinguen de los capturados a mano. Si la lectura falla o no coincide con la empresa, el documento queda para revisión humana.


**Formato analizado: Opinión de cumplimiento SAT (32-D)** — 4 PDF reales del despacho, revisados el 23/11/2026 (2 positivas, 2 negativas). Aquí no se anotan nombres, RFC ni folios.
- PDF de 1 página generado por el SAT (Apache FOP), **con texto**: no requiere OCR.
- Campos visibles: nombre o razón social, **Sentido** (`POSITIVO` / `NEGATIVO`), RFC, **Folio**, **Fecha y hora de emisión** («25 de abril de 2026 a las 22:41 horas»).
- **Cadena original**: la fuente más fiable para extraer, con formato fijo `||RFC|FOLIO|DD-MM-AAAA|P o N||número de certificado||`. La lectura toma la cadena y comprueba que coincide con los campos visibles. Si no coinciden, el documento queda para revisión humana.
- En las negativas, la sección «Cumplimiento de obligaciones» lista cada **obligación omitida con su ejercicio**, por ejemplo «Declaración anual de ISR del ejercicio Personas morales.» + «2025». El nombre coincide con el catálogo del Cambio 2, así que la omisión puede ligarse a la obligación de la empresa y señalarse en la matriz.
- Validaciones: el RFC de la opinión debe ser el de la empresa del expediente (si no, revisión humana); si ya existe el mismo folio, se trata como duplicado y no se registra dos veces.
- Vigencia: se cuenta desde la fecha de emisión con los días configurados. El sello digital no se verifica, así que la opinión se registra como **leída del documento**, no como validada ante el SAT.
- Faltan ejemplos de otros sentidos que pueda emitir el SAT (por ejemplo, inscrito sin obligaciones o en suspenso) y del documento del Infonavit, cuyo formato es distinto.

**Formato analizado: Opinión de cumplimiento IMSS (32-D, seguridad social)** — 1 PDF real del despacho, revisado el 23/11/2026 (positiva). Aquí no se anotan nombres, RFC ni folios.
- PDF de 1 página generado por el portal IMSS Digital (JasperReports «CartaNoAdeudo»), **con texto**: no requiere OCR. Logotipos como imágenes.
- Campos visibles: fecha, **Folio** (23 dígitos), **Clave de RFC**, nombre o razón social, sentido dentro del párrafo («se emite opinión Positiva»), fecha y hora de la revisión, **vigencia hasta** y **número de trabajadores activos** («Usted tiene registrado(s) 3 trabajador(es) activo(s)»).
- **Cadena original** con pares `Clave:valor` separados por `|`: `Invocante`, `Tramite`, `Fecha`, `Folio`, `RFC`, `Nombre o Razon Social`, `CURP`, `Opinion` (`POSITIVA` / `NEGATIVA` / `SIN OPINIÓN`), `FechaInicioVigencia`, `FechaFinVigencia`. Es la fuente principal de la lectura; puede venir partida en varias líneas y las fechas no siempre traen «de» antes del año.
- Sentidos posibles según el propio documento: **Positiva**, **Negativa** y **Sin opinión**. El tercero se muestra en gris («sin opinión»), no como negativa.
- **Vigencia oficial: el mismo día de la consulta** (hasta las 23:59:59). Si el semáforo usara la vigencia oficial, el indicador IMSS estaría casi siempre en rojo. Decisión (23/11/2026): se guarda la vigencia oficial tal como viene y el semáforo usa la vigencia del despacho (1 día; ver tabla de vigencias).
- **Trabajadores activos**: dato útil para el semáforo. Con 0 trabajadores, IMSS e Infonavit pueden proponerse como «No aplica» (confirmación humana).
- Validaciones iguales a las del SAT: RFC igual al de la empresa, folio no duplicado, lectura marcada como «leída del documento», no validada ante el IMSS.

**Formato analizado: Constancia de situación fiscal del Infonavit (aportaciones patronales y entero de descuentos)** — 1 PDF real del despacho, revisado el 23/11/2026 (sin adeudo). Aquí no se anotan nombres, RFC ni folios.
- PDF de 1 página generado por el sistema del Infonavit (SAP, formulario `ZCSFSF_NOADEUDO`), **con texto**: no requiere OCR.
- ⚠️ **Se llama igual que la CSF del SAT** («Constancia de Situación Fiscal…»). El clasificador debe distinguirlas por emisor y título completo («…en materia obligaciones Fiscales relativa a las aportaciones patronales y entero de descuentos», «Instituto del Fondo Nacional de la Vivienda para los Trabajadores»). Verificar en el código que el lector de CSF del Bloque 1 rechace este documento y no lo tome como constancia del SAT.
- Campos: lugar y **fecha de expedición**, **Folio** (formato `número/año`), **RFC**, nombre o razón social, fecha y hora de la solicitud, **resultado** y **trabajadores activos con su bimestre** («cuenta con 9 trabajador(es) activo(s) ante el Infonavit al 4to. Bimestre de 2026»).
- **Resultado**: no viene en la cadena original. Se lee del texto: «Sí se encuentra al corriente… la constancia que se emite es **sin adeudo**» → verde. Hace falta un ejemplo con adeudo para definir la frase negativa → rojo. Si no se reconoce ninguna de las dos frases, el documento queda para revisión humana.
- **Cadena original** corta: `FOLIO | RFC|`. Sirve para comprobar folio y RFC, no el resultado.
- **Vigencia oficial: 30 días a partir de la expedición**, según el propio documento. El despacho la renueva cada 15 días (ver tabla de vigencias).
- Trabajadores activos: con 0, Infonavit puede proponerse como «No aplica» (confirmación humana), igual que en el IMSS.
- Validaciones: RFC igual al de la empresa, folio no duplicado, lectura marcada como «leída del documento», no validada ante el Infonavit.

**Aceptación.** Cada empresa muestra los cinco estados correctos según sus documentos; cambiar un documento o una fecha actualiza el indicador y el resumen; los tres temas mantienen contraste AA; nada indica «validado ante SAT/IMSS».

---

## Cambio 2 — Obligaciones fiscales por periodo (casillas «hecho»)

**Qué es.** Por cada empresa y mes, las obligaciones que le aplican, cada una con una casilla que se marca como **hecha** (sólo hecho / no hecho, decisión del 23/11/2026).

**Catálogo inicial (20 obligaciones, nombres como aparecen en la CSF).**

| Grupo | Obligación | Periodicidad | Régimen / sujeto |
|---|---|---|---|
| IVA | Pago definitivo mensual de IVA | Mensual | General |
| IVA | Declaración de proveedores de IVA | Mensual | General |
| IVA | Declaración informativa de IVA con el anual de ISR | Anual | Según CSF |
| IVA | Pago definitivo mensual de IVA — RESICO | Mensual | RESICO |
| Retenciones | Entero de retenciones mensuales de ISR por sueldos y salarios | Mensual | Patrones |
| Retenciones | Entero de retenciones mensuales de ISR por ingresos asimilados a salarios | Mensual | Quien paga asimilados |
| ISR | Pago provisional mensual de ISR personas morales régimen general | Mensual | PM general |
| ISR | Pago provisional trimestral de ISR personas morales (por inicio de operaciones) | Trimestral | PM |
| ISR | Pago provisional mensual de ISR | Mensual | Según CSF |
| ISR | Pago provisional mensual de ISR por actividades empresariales | Mensual | PF actividades empresariales y profesionales |
| ISR | Pago provisional mensual de ISR RESICO — personas físicas | Mensual | PF RESICO |
| ISR | Pago provisional mensual de ISR RESICO — personas morales | Mensual | PM RESICO |
| ISR | Pago provisional mensual de ISR por arrendamiento de inmuebles | Mensual | PF arrendamiento |
| ISR | Pago definitivo bimestral del RIF | Bimestral | RIF |
| Anuales | Declaración anual de ISR del ejercicio personas morales — régimen general | Anual | PM general |
| Anuales | Declaración anual de ISR del ejercicio personas morales — RESICO | Anual | PM RESICO |
| Anuales | Declaración anual de ISR (personas físicas) | Anual | PF |
| Anuales | Declaración anual de ISR RESICO | Anual | PF RESICO |
| Anuales | Ajuste anual de ISR correspondiente a la declaración anual RESICO (ejercicio siguiente) | Anual | RESICO |
| Informativas | Declaración informativa anual de clientes y proveedores de bienes y servicios (ISR) | Anual | Según CSF |

Las dos repeticiones de la lista dictada se confirmaron (23/11/2026): una versión es de personas físicas y la otra de personas morales. Los nombres exactos se toman de constancias reales al implementar.

**Formato analizado: CSF del SAT (sección «Obligaciones»)** — 1 PDF real del despacho, revisado el 23/11/2026 (persona moral, régimen general). Aquí no se anotan nombres ni RFC.
- PDF de 3 páginas con texto (Oracle XML Publisher). ContaSuite ya lo lee en el registro de empresa (Bloque 1); se reutiliza ese lector.
- Tabla de obligaciones con 4 columnas: **Descripción de la obligación**, **Descripción vencimiento**, **Fecha inicio**, **Fecha fin**. Las descripciones largas se parten en dos líneas y el punto final no es constante («Pago definitivo mensual de IVA.» / «Declaración de proveedores de IVA»): comparar con el catálogo normalizando mayúsculas, acentos, espacios y puntuación.
- Nombres exactos vistos: «Pago definitivo mensual de IVA.», «Declaración anual de ISR del ejercicio Personas morales.», «Declaración de proveedores de IVA», «Entero de retenciones mensuales de ISR por sueldos y salarios», «Pago provisional trimestral de ISR de personas morales por inicio de segundo ejercicio. Régimen General.», «Pago provisional mensual de ISR personas morales régimen general».
- **La regla de vencimiento viene en la propia CSF**: «A más tardar el día 17 del mes inmediato posterior al periodo que corresponda», «A más tardar el último día del mes inmediato posterior…», «Dentro de los tres meses siguientes al cierre del ejercicio». El catálogo guarda esa regla (texto oficial + regla calculable) y se llena con lo que traen las constancias; el despacho sólo corrige excepciones.
- **Fechas de inicio y fin por obligación**: p. ej. el pago trimestral por inicio de segundo ejercicio tiene inicio y fin (un trimestre) y después empieza el pago mensual. La matriz sólo muestra una obligación en los periodos dentro de sus fechas, incluidas fechas futuras.
- Fecha de emisión de la CSF: en la cadena original del sello (`||AAAA/MM/DD hh:mm:ss|RFC|CONSTANCIA DE SITUACIÓN FISCAL|…||`) y en «Lugar y fecha de emisión». Se usa para la vigencia de 7 días del semáforo.
- **Segunda CSF analizada: persona física en RESICO** (23/11/2026). Mismo contenido y columnas, pero **otro generador de PDF** (cairo, 2 páginas, en vez de Oracle XML Publisher, 3 páginas): el lector no debe depender del generador ni del número de páginas, sólo de los títulos de sección («Regímenes:», «Obligaciones:») y de las columnas. Nombres exactos vistos: «Ajuste anual de ISR correspondiente a la declaración anual. Régimen Simplificado de Confianza.» (vence «a más tardar el día 30 del mes de abril del ejercicio siguiente») y «Pago provisional mensual de ISR. Régimen Simplificado de Confianza.» (día 17 del mes inmediato posterior). En RESICO el nombre del régimen va dentro del nombre de la obligación, después de un punto; la comparación con el catálogo debe conservarlo para no confundirla con la del régimen general.
- Otras CSF (actividades empresariales, arrendamiento, RIF, sueldos) pueden traer más obligaciones; se agregan al catálogo cuando aparezcan.

**Modelo propuesto.**
1. *Catálogo de obligaciones*: clave, nombre oficial (texto de la CSF), nombre corto, grupo, periodicidad, régimen/sujeto y regla de vencimiento configurable (las fechas las confirma el despacho).
2. *Asignación empresa ↔ obligación*: se propone desde las obligaciones leídas de la CSF (con sus fechas de inicio/fin) y se confirma o corrige a mano.
3. *Registro por periodo*: empresa × obligación × periodo → hecho (sí/no), quién lo marcó y cuándo (bitácora). Acuse opcional como evidencia.
4. *Vencidas*: una obligación no marcada después de su vencimiento se muestra como vencida (cálculo de lectura, no un estado capturado).

**Vista propuesta (concepto; lo visual se ajusta al codificar).**
- Tarjeta por empresa con el semáforo documental y las obligaciones agrupadas por impuesto (IVA, ISR, retenciones, informativas, anuales) con su avance («2/2»); al abrir un grupo aparecen las casillas.
- Sólo se muestran las obligaciones que aplican; las bimestrales, trimestrales y anuales sólo en su periodo.
- Vista de matriz alternativa para escritorio (columnas agrupadas por impuesto, encabezados cortos con nombre completo al pasar el cursor).
- Filtros: año y mes, contador responsable (existente), «con pendientes», personas físicas / morales; exportar a Excel.
- Resumen del mes: obligaciones hechas / totales, pendientes y vencidas.

**Idea a revisar en el código.** Marcar la casilla automáticamente al registrar un acuse en Declara o en el expediente.

**Relación con lo existente (verificar en el equipo de desarrollo).** ContaSuite ya tiene control de obligaciones (`FiscalControl`), lectura de obligaciones desde la CSF (Bloque 1) y contador responsable (Bloque 2). Este cambio debe integrarse sobre ellos, sin un módulo paralelo.

**Aceptación.** Una empresa nueva registrada con su CSF recibe sus obligaciones propuestas; marcar una casilla queda en la bitácora con usuario y fecha; el resumen y los filtros cuadran con las casillas; una obligación no marcada aparece vencida después de su fecha.

---

## Cambio 3 — Calendario de CFDI por empresa (panel CFDI)

**Qué es.** Un calendario anual por empresa que muestra en qué meses y días hay facturas (CFDI) en ContaSuite, separando **emitidas** y **recibidas**. Tomado del «Historial de descarga» de Contalink (año × mes × día con estado por celda), adaptado: Contalink marca el estado de la descarga del SAT; ContaSuite marca **qué CFDI tiene registrados**, porque no descarga del SAT.

**Dos niveles.**
1. *Vista por meses (inicial)*: 12 filas o tarjetas con el conteo de emitidas y recibidas de cada mes. Si falta un tipo, se dice expresamente; por ejemplo, enero «Emitidas: 34 · Recibidas: no hay registradas».
2. *Vista por días (al abrir un mes o en modo detallado)*: cuadrícula de días del mes, cada celda con su estado.

**Estados de celda (día o mes).** Sin CFDI · Sólo emitidas · Sólo recibidas · Emitidas y recibidas. Al pasar el cursor o tocar: conteos e importe total por tipo; desde ahí se abre la lista de esos CFDI.

**Reglas.**
- El día se toma de la fecha del CFDI (fecha de emisión; validar en el código si conviene la de timbrado).
- Emitida o recibida se decide comparando el RFC emisor / receptor con el RFC de la empresa.
- Redacción honesta: «no hay registradas en ContaSuite», nunca «no existen» ni «validado ante SAT», porque no hay consulta al SAT.
- Fuente: los XML que ya entran por CFDI (antes Organizador), CS-Storage y el agente; no se crea otra importación.

**Fuera de alcance (Contalink sí lo tiene).** Descarga automática del SAT y configuración de FIEL para descargar: **no se implementa** (decisión del 23/11/2026); queda sólo como idea futura y no aparece en la pantalla.

**Aceptación.** Con XML de prueba de un año, cada mes y día muestra los conteos correctos por tipo; un mes con sólo emitidas lo indica explícitamente; cambiar de año o de empresa recalcula; tiempo de carga aceptable con 25 mil documentos (medir con el piloto sintético).

---

## Cambio 4 — Gestor de contraseñas y archivos FIEL (borrador en discusión)

**Qué es.** Bóveda para guardar de forma segura las credenciales de cada empresa (contraseña SAT, portales IMSS/Infonavit/estatales, etc.) y sus archivos FIEL (`.cer`, `.key` y su contraseña) y CSD.

**Cambio de regla (aprobado por el usuario el 23/11/2026).** Se levanta la prohibición de guardar llaves privadas FIEL y contraseñas, **sólo dentro de este gestor** y con las protecciones de esta ficha. `AGENTS.md` ya refleja el cambio. La revelación de secretos, hoy deshabilitada (423), se habilita únicamente con reautenticación y permiso. Construir sobre la bóveda existente (`credential_api.py`, `credential_crypto.py`, `credential_models.py`), no un módulo paralelo — verificar en el equipo de desarrollo.

**Recomendaciones propuestas (a discutir).**
1. Cifrado por sobre: cada secreto y archivo con su propia llave AES-256-GCM; esas llaves cifradas con una llave maestra que no vive en la base ni en `.env` en claro (protegida con DPAPI de Windows u otra opción a decidir).
2. Archivos FIEL/CSD cifrados fuera de la carpeta documental; nunca indexados por CS-Storage ni leídos por el agente (el agente ya excluye `.key`).
3. Acceso: sólo roles autorizados y por empresa; para ver, copiar o descargar un secreto se pide de nuevo la contraseña (reautenticación) y, de preferencia, un segundo factor (TOTP), que hoy no existe.
4. Revelado mínimo: el secreto se muestra unos segundos o se copia y se borra del portapapeles; nunca aparece en listas, registros, errores ni exportaciones.
5. Bitácora inalterable de cada consulta, copia, descarga y cambio (quién, cuándo, qué empresa, motivo).
6. Respaldos: la base respaldada lleva los secretos cifrados; la llave maestra se respalda aparte (fuera de línea). Sin ella el respaldo no recupera secretos; documentar la recuperación.
7. Vencimientos: las fechas del `.cer` alimentan el semáforo (FIEL) y avisan antes de que venza.
8. Resguardo formal: carta o contrato del cliente que autoriza al despacho a custodiar su FIEL.

**Dirección acordada (23/11/2026).** Renovar la bóveda actual y convertirla en un gestor de contraseñas al estilo del de Chrome:
- Lista por empresa y por portal (SAT, IMSS, Infonavit, estatal, bancos…) con búsqueda; usuario visible, contraseña oculta.
- Botones de mostrar y copiar (con reautenticación), editar y nota por registro.
- Generador de contraseñas seguras.
- Revisión local de contraseñas débiles o repetidas (sin consultar servicios externos de filtraciones).
- Importar desde un archivo (CSV/Excel) con vista previa y confirmación; exportar sólo con reautenticación y advertencia.
- Archivos FIEL/CSD dentro del registro de la empresa, con sus fechas de vigencia.
Formato de importación: se definirá con los archivos de ejemplo del despacho (sólo su estructura; ningún valor real entra al repositorio ni a este plan).

**Formato analizado: Excel de contraseñas del despacho** — copia censurada revisada el 23/11/2026 (1 hoja, ~60 filas, una fila por empresa). Aquí sólo se anota la estructura.

| Columna(s) del Excel | Destino en ContaSuite |
|---|---|
| No., Empresa, RFC | Empresa existente, emparejada **por RFC** (sin fusionar automáticamente: si no hay coincidencia exacta, revisión humana) |
| Régimen (texto libre: CONFIANZA, GENERAL P.M, P.F ACT EMP, PF, RIF, SUELDOS, NO LUCRATIVA…) | Sólo referencia; el régimen oficial sale de la CSF. Se muestra una diferencia si no coincide |
| Contraseña | Credencial **SAT – contraseña (CIEC)** |
| Contraseña FIEL + fecha inicial / final + vencimiento | Registro **FIEL**: contraseña cifrada; fechas tomadas del `.cer` cuando se suba (las del Excel sólo como referencia); el vencimiento (fórmula `=final-HOY()`) se calcula, no se importa |
| Contraseña sello digital + fechas + vencimiento | Registro **CSD**, igual que FIEL |
| Reg. patronal | Dato de la empresa (IMSS); también indica que IMSS/Infonavit aplican en el semáforo |
| Usuario / contraseña IDSE | Credencial **IMSS – IDSE** |
| Usuario / contraseña SIPARE | Credencial **IMSS – SIPARE** |
| (Infonavit) reg. patronal / correo + contraseña | Credencial **Infonavit – portal empresarial** |
| Imp. s/ nómina | Credencial **portal estatal (ISN)** |
| Correo + contraseña | Credencial **correo de la empresa** |
| FEL facturación | Credencial **portal de facturación** |
| Créditos, cuenta Izzi, firma Contpaqi nómina | Credenciales de tipo **Otro** con nombre libre |

**Modelo propuesto.** Credencial = empresa + tipo de portal (catálogo editable: SAT, FIEL, CSD, IDSE, SIPARE, Infonavit, estatal ISN, correo, facturación, otro) + usuario + contraseña (cifrada) + datos extra (registro patronal, URL) + notas + vigencia y archivos (FIEL/CSD).

**Importador específico para este Excel.** Detecta las columnas por encabezado (incluidas las combinadas «fecha inicial / final»); separa celdas con formato «usuario / contraseña»; pasa a notas los comentarios entre paréntesis; ignora filas vacías o sin RFC (las manda a revisión); vista previa por empresa antes de guardar; nunca muestra contraseñas en la vista previa, sólo «presente / vacía»; el archivo subido se borra al terminar.

**Segundo formato analizado: Excel por corporativo** (copia revisada el 23/11/2026; sólo estructura). Dos hojas:
- *EMPRESAS*: No., empresa, RFC, régimen, **giro**, nivel (no se importa), registro patronal, **REPSE (SI/NO)**, **trabajadores**, banco, **representante legal**, observaciones (p. ej. «falta FIEL del representante»).
- *CONTRASEÑAS*: No., empresa, RFC, nivel (no se importa), contraseña, **FIEL de la empresa**, **FIEL del representante**, sello digital, correo, Infonavit, registro patronal, **contraseña del certificado IMSS**, SIPARE.

Consecuencias para el diseño:
- Una empresa puede tener **dos FIEL**: la de la empresa y la de su **representante legal** (persona física). El gestor las distingue y el semáforo vigila ambas.
- Datos nuevos de la empresa que no son credenciales: giro, REPSE, número de trabajadores, banco y representante legal. Se proponen como campos del expediente (verificar cuáles existen ya en el código).
- Número de trabajadores: se compara con el de las opiniones IMSS/Infonavit y alimenta «No aplica» del semáforo.
- Nuevo tipo de credencial: **IMSS – certificado digital** (archivo y contraseña).
- El importador debe aceptar los dos formatos (una hoja por despacho y dos hojas por corporativo) y cruzar las hojas por RFC.

**Decisiones del 23/11/2026.**
1. Ver y copiar contraseñas: el **administrador** y los **usuarios autorizados** (permiso explícito «ver contraseñas», por empresa; no viene incluido en ningún rol por defecto).
2. La FIEL **no se descarga**: se usa mediante un **autocompletado** al entrar al portal del SAT desde ContaSuite. Restricción técnica: una página web no puede llenar formularios de otro sitio (sat.gob.mx) ni el SAT permite mostrarse dentro de un marco. Opciones a decidir en el equipo de desarrollo:
   - **Extensión de navegador de ContaSuite** (Chrome/Edge), ligada a la sesión: al abrir el portal del SAT llena RFC/contraseña o carga `.cer`, `.key` y contraseña de la FIEL. Es el modelo del gestor de Chrome. **Elegida por el usuario (23/11/2026).**
   - Alternativa descartada: navegador controlado por el agente local de Windows.
   En ambas: la llave se descifra sólo en memoria y para un uso, se pide reautenticación, nunca se escribe en disco y cada uso queda en la bitácora.
3. Se quita la regla de no guardar FIEL (ver arriba).

La columna «nivel» de los Excel no se usa (decisión del 23/11/2026).

**Pendiente de decidir.** Dónde vive la llave maestra (propuesta: DPAPI de Windows en el servidor, con respaldo fuera de línea).

---

## Orden de implementación sugerido

1. **Revisión del código actual** (sin cambios): bóveda de credenciales, lector de CSF (Bloque 1), `FiscalControl`, panel integral, CFDI y CS-Storage. Anotar qué se reutiliza y la línea base de pruebas.
2. **Cambio 2 — Catálogo y obligaciones por periodo** (base de datos y lector de CSF): catálogo con reglas de vencimiento, asignación desde la CSF, registro «hecho» con bitácora, vencidas.
3. **Cambio 1 — Semáforo documental**: lectores de opinión SAT, IMSS e Infonavit y vigencia de CSF/FIEL; vigencias configurables; liga de la opinión negativa con la obligación omitida (requiere el Cambio 2).
4. **Vista del panel**: tarjetas de resumen, semáforo y obligaciones agrupadas por empresa; vista de matriz para escritorio.
5. **Cambio 3 — Calendario de CFDI**.
6. **Cambio 4 — Gestor de contraseñas**: cifrado y llave maestra, permisos y bitácora, interfaz estilo Chrome, importador de los dos Excel. Después, la **extensión de navegador** para el autocompletado en el portal del SAT.

Cada paso con su migración explícita (con respaldo), sus pruebas y la aprobación del usuario antes de seguir, como dice `AGENTS.md`. Para las pruebas usar documentos **sintéticos** con el mismo formato que los reales analizados; ningún documento real entra al repositorio.

## Pendientes para la etapa de código

- Dónde vive la llave maestra del gestor (propuesta: DPAPI de Windows + respaldo fuera de línea).
- Ajustes visuales con el diseño Stitch.
- Ejemplos opcionales: constancia del Infonavit con adeudo; opinión del SAT con otro sentido; CSF de actividades empresariales, arrendamiento o RIF.
