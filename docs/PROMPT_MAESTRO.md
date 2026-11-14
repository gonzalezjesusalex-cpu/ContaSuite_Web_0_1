# PROMPT MAESTRO — Modificaciones de ContaSuite Web

Versión: 1 · Fecha: 2026-11-14 · Para ejecutar con Claude Code (Opus 5.5) en el repositorio `ContaSuite_Web_0_1`.

---

## 0. Cómo usar este documento

Eres el agente que ejecutará un conjunto de modificaciones **ya diseñadas y aprobadas por el usuario** sobre ContaSuite Web. Este documento contiene las decisiones; no las reabras ni las reinterpretes. Si algo es ambiguo o choca con otra regla, **detente y pregunta**.

### 0.1 Orden de autoridad

1. `AGENTS.md` (reglas del proyecto) manda sobre este documento, salvo las excepciones que el usuario aprobó expresamente en el Bloque 6 (6.3).
2. `PLAN_FINALIZACION.md` manda sobre cualquier otro documento de planeación. **Este Prompt Maestro son cambios solicitados por el usuario después de esa planeación.** Antes de empezar, léelo y propón dónde encajan estos bloques; no lo sobrescribas ni lo contradigas.
3. Este Prompt Maestro (Bloques 1-6).
4. `ESTADO.md`, `OPERACION.md`, `docs/INFORME_UIUX_v1.md` como referencia.

### 0.2 Reglas permanentes (resumen de AGENTS.md; léelo completo)

- No tocar sin autorización explícita: la instancia del puerto 8000, el piloto 8062, la instalación 8072, `.env`, `data/`, `agent/config.json`, nada dentro de `.qa/`. No abrir secretos (`.env`, `access.json`, `private.json`, configuración del agente, dumps).
- No migrar bases reales ni importar la segunda carpeta del piloto. No fusionar documentos por UUID, nombre ni RFC: los conflictos van a revisión humana.
- Motores originales sin cambios: `backend/app/recopila_engine.py`, `organizador_engine.py`, `declara_engine.py`.
- Nunca aceptar actores, roles ni ámbitos enviados por el cliente fuera de endpoints administrativos autorizados. No guardar llaves FIEL ni contraseñas.
- El arranque solo verifica esquema: **nunca migrar ni sembrar al iniciar.** Todo cambio de esquema es una migración explícita con respaldo previo.
- Conservar el diseño Stitch; mantener temas claro, oscuro y alto contraste; respetar `prefers-reduced-motion`.
- No presentar como activas funciones no implementadas. No declarar v1.0 aprobada.
- Git no está en el PATH: usa el `git.exe` de GitHub Desktop. Sin `push` sin autorización. Sin datos, dumps, `.env`, `.qa/` ni documentos empresariales en commits.
- Datos personales: **nunca** copies al repositorio, a logs, a mensajes de error ni a pruebas los archivos de `ARCHIVOS PRUEBA/` (contienen constancias, INE, NSS y CURP de personas reales). Las pruebas usan archivos sintéticos o anonimizados.

### 0.3 Forma de trabajar (obligatoria)

1. **Una fase a la vez y un punto a la vez.** Cada punto va en su propio commit, con las pruebas afectadas ejecutadas.
2. Antes de cambiar lógica, ejecuta la **línea base de pruebas** y anótala. Después de cada punto, vuelve a ejecutarla y compara.
3. **Presenta el resultado de cada fase y espera la aprobación del usuario** antes de pasar a la siguiente. Al terminar un bloque, resume qué cambió, qué probaste y qué no pudiste verificar.
4. Si una decisión de este documento resulta inviable o riesgosa (p. ej. empaquetado del OCR, emparejamiento del agente), no improvises una alternativa: detente, explica y propón opciones.
5. Comandos de validación: backend `cd backend && python -m pytest -q` (sin `.env` real; ver AGENTS.md); frontend `npm --prefix frontend ci`, `npm --prefix frontend run build`, `npm --prefix frontend exec -- tsc --noEmit -p frontend/tsconfig.json`; e2e `npm --prefix frontend run e2e` con `E2E_PYTHON` (servidor sintético, ver README). Toda ejecución de la app usa el servidor sintético, nunca las instancias reales.

### 0.4 Índice

| Bloque | Título | Estado |
| --- | --- | --- |
| 1 | Registro de empresa desde Constancia de Situación Fiscal, con OCR local | Aprobado |
| 2 | Contador responsable vinculado a usuarios; roles y permisos | Aprobado |
| 3 | Encabezado del expediente de empresa | Aprobado |
| 4 | Agente local vinculado al usuario | Aprobado (con un problema pendiente de diagnóstico) |
| 5 | Tareas y vencimientos con el calendario fiscal como pestaña principal | Aprobado |
| 6 | Evolución visual, UI/UX y animaciones de ContaSuite | Aprobado (con pendientes P1-P6) |

### 0.5 Orden de ejecución sugerido (pendiente de aprobación del usuario)

Dependencias reales entre bloques; el agente propone el orden definitivo contra `PLAN_FINALIZACION.md` y lo confirma con el usuario:

1. **Bloque 2** primero: el modelo de roles y usuarios es la base de los permisos que usan los Bloques 1, 3, 4 y 5.
2. **Bloque 1** (registro desde constancia), que depende del selector de contador del Bloque 2.
3. **Bloques 3 y 5**: reorganización de pantallas; sus botones deben mostrarse por permiso, no por `admin`.
4. **Bloque 4** (agente): requiere antes diagnosticar el problema actual (ver 4.7).
5. **Bloque 6**: la fase 0 (capturas y línea base) puede hacerse al principio; el resto después de los bloques funcionales para no interferir con su finalización.

---

## BLOQUE 1 — Registro de empresa desde Constancia de Situación Fiscal (CSF), con OCR local

### 1.1 Objetivo

En «Registrar empresa», permitir subir la CSF en PDF; el sistema extrae los datos, rellena el formulario y el usuario revisa y confirma. Sirve para personas morales y físicas. **No se crea nada hasta que el usuario confirme.**

### 1.2 Código actual relevante

- Formulario: `frontend/src/modules/CompanyForm.tsx` (3 pasos: Datos generales, Información fiscal, Expediente digital; borrador en `localStorage`).
- Modelo: `backend/app/models.py` → `Company` (`name`, `rfc` único, `person_type`, `trade_name`, `regime`, `accountant`, `email`, `phone`, `location`, `folder`, `notes`). No existe idCIF, CURP ni domicilio.
- Esquema: `backend/app/schemas.py`. Ya existe `pypdf` en `requirements-base.txt`; `PyMuPDF` está disponible en el entorno de desarrollo pero **no** es dependencia del proyecto: no lo uses sin autorización.
- `backend/app/pilot_extract.py` reconoce la CSF como tipo de documento (`'CONSTANCIA DE SITUACI'`), útil como referencia.

### 1.3 Mapa documento → formulario

| Campo del sistema | Dato en la CSF |
| --- | --- |
| Tipo de contribuyente | Deducido del RFC: 12 caracteres = Moral; 13 = Física |
| RFC | «RFC» |
| **idCIF (campo nuevo, obligatorio)** | «idCIF» (recuadro superior). **De 8 a 11 dígitos; no fuerces 11.** |
| **CURP (campo nuevo)** | «CURP». Obligatoria en personas físicas; opcional en morales |
| Razón social / Nombre completo | Moral: «Denominación/Razón Social». Física: «Nombre(s)» + «Primer Apellido» + «Segundo Apellido» |
| Nombre comercial | «Nombre Comercial» (puede venir vacío) |
| Correo y teléfono | No vienen en la CSF: quedan vacíos |
| Ciudad / Estado | Localidad o municipio + entidad federativa |
| Régimen fiscal | Sección «Regímenes», mapeado a clave SAT (p. ej. «Régimen General de Ley Personas Morales» → 601; «Sueldos y Salarios e Ingresos Asimilados a Salarios» → 605) |
| Observaciones fiscales | Resumen armado con los datos extra |
| Ruta de carpeta | No viene en la CSF (paso 3) |
| **Contador responsable** | **Excluido: la CSF no lo toca** (ver Bloque 2) |

**Campos nuevos aprobados** (requieren migración): idCIF, CURP, **domicilio fiscal** completo (código postal, tipo y nombre de vialidad, número exterior e interior, colonia, localidad, municipio, entidad, entre calles; todos opcionales salvo lo que el SAT siempre trae), **fecha de inicio de operaciones**, **estatus en el padrón**, **fecha de emisión** de la constancia, y **todos los regímenes vigentes** (el principal primero).

### 1.4 Flujo en tres tiempos

1. **Analizar:** el backend lee el PDF y devuelve los datos extraídos. No crea ni guarda nada.
2. **Revisar:** los campos se rellenan en el formulario con la etiqueta «De la constancia»; el usuario puede corregir cualquiera. Los de baja confianza (OCR) se resaltan en ámbar.
3. **Confirmar:** se guarda con el botón de registro habitual.

Entrada: tarjeta al inicio del paso 1, «Registrar desde Constancia de Situación Fiscal», con zona para soltar el PDF y enlace «Prefiero capturar manualmente». Estilo Stitch actual.

### 1.5 Validaciones

- El documento debe contener «CONSTANCIA DE SITUACIÓN FISCAL».
- Estructura válida del RFC y de la CURP. En personas físicas, los primeros 10 caracteres del RFC deben coincidir con los de la CURP.
- RFC ya existente: avisar y ofrecer abrir la empresa existente. **Nunca fusionar.**
- Estatus distinto de ACTIVO: advertencia.
- Régimen sin coincidencia en el catálogo: dejar vacío con aviso; no adivinar.
- Catálogo de regímenes: completarlo (personas morales y físicas); hoy el selector tiene 8.
- La CSF no es validación oficial ante el SAT: se mantiene la leyenda «La captura de datos no constituye validación oficial ante el SAT». Aunque traiga sello digital, no se valida contra el SAT.

### 1.6 Extracción y OCR (decisión tomada: incorporar OCR local)

- **Orden:** primero la capa de texto con `pypdf` (exacta e instantánea; es el caso de las CSF descargadas del SAT). Solo si el PDF no tiene texto, OCR.
- **Motor aprobado:** **RapidOCR (ONNX)**, local, sin nube ni ejecutables externos. Debe quedar con **versión fija** en `backend/requirements-base.txt` y `requirements.lock.txt`, y funcionar en el runtime empaquetado de Windows.
- **Verificación previa obligatoria:** comprueba que corre en el runtime empaquetado, mide el tiempo con un escaneo sintético y reporta el peso añadido a la instalación. **Si el empaquetado falla, detente y propón alternativa (Tesseract); no cambies de motor por tu cuenta.**
- Los escaneos vienen torcidos y con ruido: preprocesa (enderezar, escala de grises, contraste).
- Un PDF puede traer varios documentos (p. ej. INE + IMSS + CSF en un solo archivo): localiza **solo la página de la constancia** por su texto y descarta las demás. Procesa solo esa página y **no conserves ni registres el contenido de las otras.**
- Nunca guardar sin revisión del usuario. El OCR puede equivocar un carácter del RFC, la CURP o el idCIF.
- En pantalla, el OCR se muestra como disponible **solo cuando funcione y esté probado** (AGENTS.md). Actualiza el texto del paso 2 que hoy dice que la extracción «aún no está integrada».

### 1.7 Seguridad y privacidad

- El PDF se procesa en memoria, con límite de tamaño y de tipo. Sin datos fiscales ni personales en logs ni mensajes de error.
- Pruebas con archivos sintéticos o anonimizados. Los PDF de `ARCHIVOS PRUEBA/` sirven solo como referencia de formato y no se copian al repositorio. Ya hay una CSF de persona moral (texto) y una de persona física (escaneo mezclado con otros documentos): construye equivalentes sintéticos.

### 1.8 Después del alta

- **Adjuntar la CSF al expediente automáticamente al registrar**, con su fecha de emisión; se adjunta **solo la página de la constancia**, nunca el archivo completo con INE o NSS.
- **Actualizar desde una CSF nueva** (en una empresa existente): subir la nueva y mostrar qué cambió (domicilio, régimen, obligaciones) **antes de aplicar**.
- **Obligaciones sugeridas:** a partir de las obligaciones de la CSF, proponer las del módulo Obligaciones, siempre con confirmación del usuario. Depende de cómo esté el módulo hoy; revísalo al llegar ahí.
- **Alerta de constancia vieja:** aviso cuando la CSF tenga más de 3 meses de emisión.

### 1.9 Migración

Columnas nuevas en `Company` (o tablas auxiliares) por **migración explícita con respaldo**, sin migrar ni sembrar al arrancar. Prueba con datos sintéticos. No toques bases reales.

### 1.10 Aceptación

CSF moral digital y CSF física escaneada (sintéticas) rellenan el formulario correctamente; RFC duplicado avisa sin fusionar; campos de baja confianza resaltados; nada se guarda sin confirmar; la CSF queda adjunta; pruebas backend y e2e pasan.

---

## BLOQUE 2 — Contador responsable vinculado a usuarios; roles y permisos

### 2.1 Estado actual

- `Company.accountant` es texto libre (`String(150)`, «Sin asignar» por omisión). Se usa en filtros de Empresas, tablero integral (`integral_dashboard.py`), Control Fiscal, expediente (`Dossier.tsx`), `company_lifecycle.py`, `fiscal_control.py` y pruebas. Todo compara cadenas.
- Usuarios: `UserAccount` (`username`, `display_name`, `password_hash`, `admin`, `enabled`, `revision`), `UserCompanyGrant` (`access` = `read` | `write`), sesiones y `SecurityEvent` en `backend/app/accounts.py`. `Audit` es solo texto y fecha, sin actor.

### 2.2 Roles (decisión aprobada)

| Rol | Alcance |
| --- | --- |
| **Administrador** | Rol de desarrollador. Permisos totales. **No puede ser responsable de una empresa.** |
| **Contador** | Opera todo lo contable y fiscal de las empresas a las que tiene acceso. **Puede crear y gestionar auxiliares** (única excepción de usuarios). No cambia nada del sistema. |
| **Auxiliar** | Solo lectura, más las acciones puntuales que se le concedan al crearlo. Es el «contador de apoyo» de una empresa. |

### 2.3 Responsable y apoyo

- El responsable es **siempre un contador**, guardado por **`id` de usuario**, no por nombre.
- **Solo un administrador asigna o reasigna** responsables. (Decisión futura, no ahora: que un contador pueda traspasar.)
- Auxiliares: se vinculan por empresa; sus permisos finos se definen al crear el usuario o al darle acceso a la empresa, con plantillas rápidas por módulo («Solo consulta», «Captura de documentos», «Apoyo fiscal»).
- Al asignar un contador se le crea o actualiza `UserCompanyGrant` con `write` (con aviso visible). **Al cambiar de responsable se pregunta qué hacer con el acceso del anterior; no se quita automáticamente.**
- `write` automático es solo para contadores y administrador. Para auxiliares se decide al crear el usuario (por omisión `read`).

### 2.4 Matriz de permisos (propuesta, a corregir por el usuario antes de implementar)

| Acción | Admin | Contador | Auxiliar |
| --- | --- | --- | --- |
| Configuración del sistema, respaldos, agente, migraciones | ✔ | ✘ | ✘ |
| Crear/deshabilitar contadores, cambiar roles | ✔ | ✘ | ✘ |
| Crear auxiliares y definir sus permisos | ✔ | ✔ (solo en sus empresas) | ✘ |
| Asignar o reasignar contador responsable | ✔ | ✘ | ✘ |
| Registrar, editar o archivar empresas | ✔ | ✔ (sus empresas) | según permiso |
| Subir y adjuntar documentos, constancia, expediente | ✔ | ✔ | según permiso |
| Recopila, CFDI, Declara, Recibos (operar) | ✔ | ✔ | según permiso |
| Obligaciones y tareas | ✔ | ✔ | según permiso |
| Ver historial de cambios | ✔ | ✔ (sus empresas) | según permiso |
| **Credenciales y certificados: ver y adjuntar** | ✔ | ✔ (solo contador responsable de esa empresa) | ✘ |

El agente define un **catálogo de acciones por módulo** para los permisos del auxiliar y lo presenta al usuario antes de implementar.

### 2.5 Reglas de seguridad

1. Un contador **no** puede dar a un auxiliar más permisos de los que tiene, ni sobre empresas a las que no accede.
2. El servidor valida todo; el cliente nunca envía roles ni permisos que se acepten sin verificar.
3. No se puede quitar el último administrador.
4. Los usuarios deshabilitados pierden sesión y no aparecen para asignar (si ya estaban asignados se muestran «(inactivo)» hasta reasignar).

### 2.6 Historial

- Cada alta, cambio o retiro de responsable queda con **quién, cuándo, valor anterior y nuevo**; sección «Historial» en el expediente.
- **`Audit` guarda `actor_id` en todos los cambios de empresa** (decisión aprobada), no solo en el de responsable.

### 2.7 Vistas

Filtros de Empresas, tablero integral y Control Fiscal agrupan por usuario. «Sin responsable» se calcula por vínculo vacío, no por el texto «Sin asignar». Cada contador tiene filtro «Mis empresas».

### 2.8 Selector en el formulario

El campo «Contador responsable» pasa a selector de usuarios activos con rol contador («Ana Pérez · ana»), con búsqueda y «Sin asignar». Solo un administrador puede cambiarlo. En el registro desde constancia (Bloque 1) la CSF nunca lo rellena.

### 2.9 Migración

- `UserAccount.admin` (booleano) pasa a `role`, por **migración explícita con respaldo**. Hoy **no existen usuarios no administradores**: los contadores y auxiliares se crean en la siguiente prueba manual.
- El texto libre de `Company.accountant` se concilia con una tabla de coincidencias por nombre exacto, **sin aplicarse automáticamente**; los que no coincidan quedan en revisión humana y el nombre original se conserva en un campo de respaldo. El texto actual se retira solo cuando el administrador lo confirme.
- Todo se prueba con datos sintéticos; no se tocan las bases reales.

### 2.10 Aceptación

Roles aplicados en servidor; un contador no escala permisos; asignación genera grant `write` y registro; historial visible; filtros por usuario; pruebas de autorización (negativas incluidas) pasan.

---

## BLOQUE 3 — Encabezado del expediente de empresa

Archivo principal: `frontend/src/modules/Dossier.tsx` (y `FiscalSummary.tsx`).

### 3.1 Problemas

Orden invertido (resumen fiscal primero, nombre al final); barra con selector, dos botones y casilla nativa sin estilo; «Volver» en medio; cinco botones que se parten en dos filas; responsable y avisos dispersos; resumen fiscal muy grande.

### 3.2 Decisiones aprobadas

```
← Directorio de empresas                         [ Empresa ▾ SERVICIO DE EVENTOS… ]
┌ ▣ Expediente │ ◫ Dashboard │ ☑ Obligaciones ┐
 SE  NOMBRE DE LA EMPRESA                       [Emitir recibo] [Analizar carpeta] [⋯]
     RFC · Persona · Régimen
     (Control fiscal por periodo) (Sin consulta SAT) · Responsable: [A] Ana Pérez
 Pestañas
 Resumen fiscal (compacto, solo en la pestaña «Resumen», debajo de las pestañas)
```

- Identidad primero; «Volver» arriba como migas de pan.
- Selector de empresa compacto con **«Incluir archivadas autorizadas» como interruptor dentro**.
- **Selector segmentado de vistas** (Expediente / Dashboard de empresa / Control de obligaciones), con la vista actual resaltada y `aria-current`; conserva la vista al cambiar de empresa; mismas rutas (`tab=Panel`, `tab=Obligaciones`, con empresa y periodo); en móvil, carrusel horizontal.
- Acciones: **«Analizar carpeta» es el botón principal azul**; «Emitir recibo» visible; **Recopila pasa al menú «⋯»** junto con Editar y Archivar.
- Resumen fiscal compacto (cuatro cifras en una fila baja) debajo de las pestañas, solo en «Resumen»; «Históricos» sigue plegable.
- Responsable como pastilla con el nombre del usuario (Bloque 2).
- **Las acciones se muestran según el permiso del rol**, no según `current_user.admin` (hoy `Dossier.tsx:169`).
- **«Analizar carpeta»** muestra el motivo exacto cuando no puede ejecutarse (agente desconectado, empresa sin ruta, ruta fuera de las autorizadas) y un enlace corto a las instrucciones del agente.
- Se conservan el diseño Stitch, los tres temas, `prefers-reduced-motion`, las rutas actuales y la adaptación a pantallas angostas.

---

## BLOQUE 4 — Agente local vinculado al usuario

Código: `agent/agent.py`, `agent/config.example.json`, `backend/app/agent_jobs.py`, `INICIAR_AGENTE.bat`.

### 4.1 Situación actual

El agente es un programa aparte (inventario de solo lectura de carpetas). Hoy se inicia a mano con `INICIAR_AGENTE.bat`, lee `agent/config.json` (`api_url`, `agent_id`, `allowed_roots`, `token`; HTTP solo en localhost) y usa un token compartido (`AGENT_TOKEN`).

### 4.2 Decisiones aprobadas

- **Un agente por sesión de Windows.** Arranca con el inicio de sesión de Windows del usuario, en segundo plano, con icono en la bandeja (no como servicio).
- **Vinculación al login de ContaSuite:** al iniciar sesión en la app, esta y el agente local se emparejan por conexión local con un **código de un solo uso y vida corta**; el agente actúa como ese usuario. Al cerrar sesión, expirar o revocarse la sesión, se desvincula y no acepta trabajos hasta el siguiente login.
- **Sin token compartido**: credenciales propias y temporales por vinculación; no se guardan contraseñas.
- **Carpetas:** solo el administrador define `allowed_roots`; el agente solo lee carpetas de empresas a las que el usuario vinculado tiene acceso.
- **Atribución:** cada análisis guarda usuario, equipo y agente, y va al historial (Bloque 2).
- **Encabezado:** «Agente conectado como Ana», o el motivo de la desconexión.
- **Sin agente:** se deshabilitan **solo** las funciones que lo requieren (p. ej. Analizar carpeta), cada una con su motivo y un enlace de ayuda; el resto de la app funciona normal.
- Un administrador puede reiniciar o revocar un agente desde la app.
- Se mantienen la lectura exclusiva, la exclusión de secretos y el control de rutas autorizadas.

### 4.3 Advertencia técnica

Una página web **no puede iniciar por sí sola** un programa de Windows. El emparejamiento se hace por conexión local (el agente ya está corriendo desde el inicio de sesión de Windows). **El agente propone el diseño del emparejamiento y lo presenta al usuario para su aprobación antes de implementarlo** (alternativa considerada: protocolo registrado en la instalación, descartada como principal por permisos del navegador).

### 4.4 Instalación

La configuración y el token se aprovisionan en la instalación y no se editan a mano. Lanzador con el inicio de sesión de Windows a través del instalador del paquete, no un `.bat` manual.

### 4.5 Operación documentada

Actualizar `OPERACION.md` (sección «Análisis del agente local») con el nuevo flujo.

### 4.6 Aceptación

Vinculación y desvinculación por sesión; análisis atribuidos; funciones sin agente deshabilitadas con motivo; pruebas del agente (`verify_live_agent.py`, marca `slow`) siguen pasando.

### 4.7 Pendiente antes de empezar

**El usuario reportó un problema al analizar carpetas con el agente y quedó para después.** Antes de implementar este bloque, el agente pide el mensaje de error o lo que muestra la ventana del agente (sin el token) y diagnostica. No uses ni toques las instancias reales para reproducirlo sin autorización.

---

## BLOQUE 5 — Tareas y vencimientos con el calendario fiscal como pestaña principal

Archivos: `frontend/src/modules/TasksAndDeadlines.tsx`, `FiscalCalendar.tsx`, `CalendarManagement.tsx`, `Records.tsx`.

### 5.1 Situación actual

La pestaña por omisión es **Tareas**; el calendario es secundario (`tab=calendario`). El calendario ya tiene vistas Mes, Semana y «Próximos 30 días», y un bloque de gestión de fechas arriba.

### 5.2 Decisiones aprobadas

- Pestañas: **«Calendario fiscal» primera y predeterminada**, «Tareas» segunda. Los enlaces `tab=tareas` y `tab=calendario` siguen funcionando.
- **Calendario mensual** (con vista semanal opcional) con **agenda lateral**: lista cronológica que **combina vencimientos fiscales registrados y tareas con fecha límite**. Al hacer clic en un día, la agenda se enfoca en él y permite crear una tarea con esa fecha. En pantallas angostas la agenda va debajo.
- **Resúmenes distintos por pestaña:** Calendario → hoy, vencen esta semana, vencidas, próximos 30 días; Tareas → registradas, pendientes, vencidas, completadas.
- «Gestionar fechas» (`CalendarManagement`) pasa a un **desplegable cerrado por omisión**.
- Filtros visibles: empresa, tipo y estado (el estado deja de ser texto libre y pasa a selector); «Incluir archivadas» como interruptor.
- Se conserva «Sin reglas legales inferidas»: no se inventan vencimientos ni cumplimiento.
- Filtro «Mis pendientes» para contadores; los auxiliares ven solo lo asignado o permitido (Bloque 2). Crear y editar tareas se muestra según permiso.
- La pestaña Tareas conserva su tabla completa con búsqueda, filtros y exportación.
- Se conservan Stitch, temas, móvil y `prefers-reduced-motion`.

---

## BLOQUE 6 — Evolución visual, UI/UX y animaciones de ContaSuite

> Base de hallazgos con archivo y línea: [INFORME_UIUX_v1.md](INFORME_UIUX_v1.md). Todas las propuestas (6.2-B) y las excepciones a AGENTS.md (6.3) fueron **aprobadas por el usuario el 2026-11-14**. En el momento de su aprobación solo se había hecho análisis y documentación; **no se ha implementado nada**. Se ejecuta por fases (6.5), con aprobación del usuario en cada una, y **sin interferir con la finalización de los módulos funcionales**.

### 6.0 Requisitos obligatorios (no negociables)

1. Conservar la identidad visual de Stitch (`design-source/`, `frontend/src/designs/`, `frontend/tailwind.config.cjs`, `components/stitch.ts`, reglas `.stitch-live-module`).
2. Respetar los tres temas: claro, oscuro y alto contraste. Todo cambio de color debe pasar `frontend/e2e/contrast.spec.ts` en los tres.
3. Mantener accesibilidad (WCAG AA como mínimo, foco visible, teclado) y diseño responsive (320, 768, 1280 y 1920 px; zoom 200 %).
4. Respetar `prefers-reduced-motion`: se eliminan desplazamientos y escalas; se conservan los cambios de opacidad y color que ayudan a comprender.
5. No modificar lógica funcional, backend, motores originales (`recopila_engine.py`, `organizador_engine.py`, `declara_engine.py`) ni bases de datos.
6. No instalar dependencias nuevas sin autorización expresa y justificada. Este bloque no necesita ninguna.
7. No presentar como activas funciones no implementadas. No tocar instancias reales (8000, 8062, 8072), `.env`, `data/`, `agent/config.json` ni `.qa/`. Toda revisión visual usa el servidor sintético de pruebas.
8. Una fase a la vez; cada punto en su propio commit, con las pruebas afectadas ejecutadas y aprobación antes de seguir. Sin `push` sin autorización. Este bloque **no debe interferir con la finalización de los módulos funcionales**: ninguna fase se inicia mientras bloquee o retrase un bloque funcional pendiente, salvo que el usuario lo indique.

### 6.1 Referencias a bloques anteriores (decisiones aprobadas, no se modifican)

| Bloque | Tema | Efecto visual ya aprobado que este bloque respeta |
| --- | --- | --- |
| 1 | Registro de empresa desde constancia, con OCR local | Tarjeta de carga al inicio del paso 1; campos marcados «De la constancia»; idCIF, CURP y domicilio; campos de baja confianza resaltados; OCR solo se muestra disponible si funciona |
| 2 | Contador responsable vinculado a usuarios; roles admin, contador y auxiliar | Selector de usuarios en lugar de texto; «Responsable» como pastilla; filtro «Mis empresas»; acciones visibles según permiso del rol, no según `admin` |
| 3 | Encabezado del expediente | Identidad primero; selector de empresa compacto con interruptor de archivadas; selector segmentado Expediente / Dashboard / Obligaciones; acciones: Analizar carpeta (principal), Emitir recibo, menú «⋯» |
| 4 | Agente local vinculado al usuario | Estado «Agente conectado como …» o motivo de desconexión; se deshabilitan solo las funciones que requieren el agente, con motivo |
| 5 | Tareas y vencimientos | Calendario fiscal primera pestaña y predeterminada; calendario mensual con agenda lateral que combina vencimientos fiscales y tareas con fecha; resúmenes distintos por pestaña; «Gestionar fechas» plegado |

### 6.2 Clasificación de las mejoras

Resumen de estado: **Aprobadas** las decisiones previas (A) y todas las propuestas (B); **Pendientes** solo P1-P6 (C), que se resuelven con la fase 0.

#### A. APROBADAS (decisiones ya confirmadas por el usuario)

- Reordenar el expediente y su barra de acciones (Bloque 3).
- Calendario como pestaña principal con agenda lateral (Bloque 5).
- Selector de usuarios como contador responsable y visibilidad por permisos (Bloque 2).
- Mensajes de agente desconectado con motivo exacto (Bloque 4).
- Reglas de AGENTS.md: identidad Stitch, tres temas, `prefers-reduced-motion`, nombres visibles de módulos, pantalla de inicio.

- Excepciones a AGENTS.md aprobadas el 2026-11-14: O1 (escala tipográfica), O2 (radios y sombras de botones y tarjetas), O3 (sin entrada animada repetitiva en tarjetas y encabezados) y O4 (sin realce animado de sombra en KPI). Detalle en 6.3.

#### B. PROPUESTAS — **APROBADAS el 2026-11-14** (A1-A6, B1-B6, C1-C7)

El usuario aprobó todas las propuestas de esta sección. A1, A2, C2 y C6 incluyen además su excepción a AGENTS.md (6.3). «Aprobada» significa que el diseño está decidido; su ejecución se hace por fases (6.5) con la aprobación de cada fase. Dos matices técnicos que el agente debe respetar:

- **A4 y P3:** antes de quitar el `outline: none` de la búsqueda global hay que verificar visualmente su foco actual (P3) para no dejarla sin indicador.
- **C6:** se aplica como se decidió en O4 (sin realce animado en KPI); el realce en tarjetas clicables, bajo `hover: hover`, es opcional.

**Prioridad alta**

| ID | Propuesta | Componentes y archivos |
| --- | --- | --- |
| A1 | Escala tipográfica única con piso de 12 px (metadatos) y 13 px (tablas, botones, pestañas). Hoy: tablas 11 px, encabezados de tabla 9 px, 29 declaraciones de 10 px o menos | `styles.css` (`:root`, `table`, `th`, `td`, `.btn`, `.tabs button`, `.toast`, `.kpi`), `stitch-refinements.css` |
| A2 | Un solo botón y una sola tarjeta con variantes (`primary`, `secondary`, `danger`, `icon`); `.btn`/`.card` y `.stitch-button`/`.stitch-card` quedan como alias hasta migrar | `components/stitch.ts`, `components/ui.tsx`, `styles.css:415`, `:2295-2360` |
| A3 | Tokens semánticos por tema (`--ok`, `--warn`, `--danger`, `--info`, sus fondos y textos, `--on-primary`, `--elev-1/2`) en lugar de hexadecimales repetidos. La paleta visible no cambia | `styles.css` (136 hexadecimales; bloques `[data-theme]`), `stitch-refinements.css` |
| A4 | Una sola regla de foco con `:focus-visible` y `--stitch-focus`; quitar el `outline` casi transparente de `input:focus`; anillo con `:focus-within` en la búsqueda global | `styles.css:289`, `:710-714`, `stitch-refinements.css:41-50` |
| A5 | Envolver las 19 reglas `:hover` en `@media (hover: hover) and (pointer: fine)` | `styles.css` |
| A6 | Estado de pulsación uniforme: `scale(0.97)`, transición de `transform` de 120-160 ms, también en `.btn` y pestañas | `styles.css`, `stitch-refinements.css` |

**Prioridad media**

| ID | Propuesta | Archivos |
| --- | --- | --- |
| B1 | Títulos con una sola escala (hoy 28 / 30 / 24 px) | `styles.css:65`, `stitch-refinements.css:23` |
| B2 | Componente de barra de herramientas con grupos e interruptores en lugar de casillas sueltas | `Companies.tsx`, `FiscalCalendar.tsx`, `Dossier.tsx` |
| B3 | Tablas: 13 px, encabezado fijo en las largas, fila mínima de 44 px, truncado al centro para nombres de archivo y RFC, `title` con el valor completo, columna de acciones fija | `styles.css:738-770`, `Documents.tsx`, `Companies.tsx`, `Records.tsx` |
| B4 | Formularios: etiqueta de 12-13 px, obligatorios accesibles, error por campo con `aria-describedby`, validación al salir del campo | `components/ui.tsx` (`Field`), `CompanyForm.tsx`, demás formularios |
| B5 | Estados vacíos con icono y acción según el contexto | `components/ui.tsx` (`Empty`) |
| B6 | Pestañas y subpestañas con un solo estilo y vista activa visible en alto contraste | `styles.css:454-484`, `stitch-refinements.css:55-71` |

**Prioridad baja (movimiento; el sistema necesita poco)**

| ID | Propuesta | Valores exactos |
| --- | --- | --- |
| C1 | Variables de movimiento y sustitución de curvas | `--ease-out: cubic-bezier(0.23, 1, 0.32, 1)`; `--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1)`; duraciones 120 / 160 / 200 ms |
| C2 | Quitar la animación de entrada de `.stitch-card` y `.page-heading` (se repite en cada cambio de pantalla, decenas de veces al día); mantenerla solo en resultados que aparecen tras una acción | `styles.css:2370-2375` |
| C3 | Toast con transición (`@starting-style`) en lugar de `@keyframes`; sale por el mismo borde; 200-250 ms | `styles.css:1388`, `:2426`, `App.tsx:536` |
| C4 | Diálogo: mantener la entrada actual y añadir salida de 120-150 ms | `styles.css:2410`, `components/ui.tsx:24` |
| C5 | Barra lateral móvil con curva de cajón a 250 ms | `styles.css:1608` |
| C6 | Quitar el realce animado de sombra en KPI (repinta cada fotograma); si se conserva, solo en tarjetas clicables y bajo `hover: hover` | `styles.css:2345-2360` |
| C7 | `prefers-reduced-motion`: conservar opacidad y color, quitar solo desplazamiento y escala | `styles.css:2286`, `:2481`, `:3118`, `stitch-refinements.css:168` |

**No animar (rechazado a propósito):** pestañas, navegación lateral, filtros, números de KPI, gráficos y tablas; el buscador global (se invoca con teclado, cientos de veces al día); transiciones de lista al filtrar u ordenar.

**Rendimiento visual:** solo `transform` y `opacity`; nunca `transition: all`; sin `will-change` salvo fotogramas perdidos medidos; sin librerías de animación; el único coste de repintado detectado es C6.

#### C. PENDIENTES (necesitan revisión o pruebas antes de decidir)

| ID | Pendiente | Cómo se resuelve |
| --- | --- | --- |
| P1 | Módulos solo inferidos del código: Inicio, Empresas (directorio), Dashboard y control fiscal, Documentos, Recopila, CFDI, Declara, Recibos, Credenciales y Configuración | Fase 0: capturas en los tres temas y dos anchos, con el servidor sintético |
| P2 | Comportamiento con datos extremos (casos de `break-ui`): listas de más de 1 000 filas, nombres largos, conteos 0 y 1 | Fase 0: fixture sintético «Normal / Peor caso» solo para desarrollo |
| P3 | Foco de la búsqueda global (`outline: none` en `styles.css:289`) | Verificar visualmente antes de A4 |
| P4 | Si `td` con `max-width: 300px` garantiza acceso al valor completo en todas las tablas | Revisar tabla por tabla en la fase 0 |
| P5 | `review-animations` no está instalada en este equipo | Instalarla o cubrir su función con revisión manual al implementar C1-C7 |
| P6 | Interacción de A1 con el diseño de cada módulo (anchos de columna, tarjetas), ahora que O1 está aprobada | Prototipos antes/después por módulo |

### 6.3 Excepciones a AGENTS.md: decididas por el usuario

Estas propuestas **chocaban con una regla vigente de AGENTS.md** («conservar el diseño Stitch: botones, colores, iconos, bordes, sombras, espaciados, animaciones»). El usuario las **aprobó el 2026-11-14**, como excepciones acotadas a esa regla. Aprobar la decisión **no autoriza implementarla**: la implementación sigue sujeta a la aprobación por fase de 6.4.

| # | Decisión | Estado | Alcance de la excepción |
| --- | --- | --- | --- |
| O1 | A1: textos de 11 px a 13 px (piso de 12 px en metadatos) | **Aprobada** | Solo tipografía. Se alinea con los tamaños del propio `tailwind.config.cjs` de Stitch (`body-sm`, `body-md`, `data-tabular`). Sin tocar espaciados salvo lo que exija el nuevo tamaño |
| O2 | A2: unificar radios y sombras tomando `.stitch-button` (8 px) como referencia | **Aprobada** | Botones y tarjetas. Colores e iconos originales sin cambio |
| O3 | C2: quitar la animación de entrada de tarjetas y encabezados | **Aprobada** | Solo la entrada repetitiva en cada cambio de pantalla; se mantiene en resultados que aparecen tras una acción |
| O4 | C6: quitar el realce animado de sombra en KPI | **Aprobada** | Solo KPI. En tarjetas clicables puede conservarse bajo `hover: hover` |
| O5 | Acciones del encabezado por permisos de rol en lugar de `current_user.admin` | Depende del Bloque 2 (no contradice) | Se implementa cuando exista el modelo de roles |

Al aplicar estas excepciones, `AGENTS.md` **no se edita sin autorización**; al integrar este bloque al Prompt Maestro se citará esta aprobación como respaldo.

### 6.4 Instrucciones para el agente que ejecute este bloque

1. Lee `AGENTS.md`, `PLAN_FINALIZACION.md` y `docs/INFORME_UIUX_v1.md`. Ejecuta y anota la línea base de pruebas antes de tocar nada.
2. La implementación está autorizada a comenzar, pero **presenta cada fase y espera la aprobación del usuario antes de pasar a la siguiente**. Una fase a la vez; un commit por punto. Empieza por la fase 0 (sin cambios de código).
3. Antes de cada fase, muestra capturas «antes» y prototipos de lo que cambiará; después, capturas «después» en los tres temas y en 320 / 768 / 1280 / 1920 px.
4. Aplica el orden de dependencias de 6.5.
5. Toca solo `frontend/src` y los CSS indicados. Si un cambio exige tocar backend, lógica o dependencias, detente y consulta.
6. Las excepciones de 6.3 (O1-O4) están aprobadas y se aplican con el alcance indicado. Si surge otro choque con AGENTS.md, no lo apliques sin la decisión del usuario.
7. Usa las skills `emil-design-eng`, `animate`, `animation-performance`, `improve-animations`, `break-ui` y `review-animations` (si está disponible); lee sus instrucciones antes de aplicarlas.

### 6.5 Fases y dependencias

| Fase | Contenido | Depende de | Riesgo |
| --- | --- | --- | --- |
| 0. Línea base | Capturas, pasada visual de módulos inferidos (P1-P4), línea base de pruebas | Ninguna | Nulo |
| 1. Tokens | A3, A1 (O1 aprobada) | Fase 0 | Medio (contrastes) |
| 2. Controles | A2 (O2 aprobada), A4, A5, A6 | Fase 1 | Medio |
| 3. Tablas, formularios, vacíos y pestañas | B1-B6 | Fase 2 | Medio |
| 4. Pantallas ya aprobadas | Bloques 1, 3 y 5 sobre el sistema nuevo; el Bloque 2 debe existir para los permisos por rol | Fases 1-3, Bloques 1-5 funcionales | Medio |
| 5. Movimiento | C1, C3, C4, C5, C7; C2 y C6 (O3 y O4 aprobadas) | Fase 2 | Bajo |
| 6. Pasada final | Alto contraste, anchos, zoom 200 %, reducción de movimiento, dispositivo real | Todas | Bajo |

### 6.6 Criterios de aceptación

- Los tres temas pasan `contrast.spec.ts` y axe sin violaciones nuevas.
- Ningún texto de interfaz de datos o de acción por debajo de 12 px (O1 aprobada).
- Todo control interactivo tiene foco visible, estado `:active` y es operable con teclado.
- No hay desplazamiento horizontal de página a 320 px; zoom 200 % utilizable.
- Con `prefers-reduced-motion: reduce` no hay desplazamientos ni escalas; los cambios de opacidad y color se conservan.
- Cada animación nueva cumple: propósito nombrado, `transform`/`opacity`, menos de 300 ms (diálogos y avisos hasta 500 ms), curva de `--ease-out`, interrumpible; sin `transition: all`.
- Sin fotogramas perdidos en las animaciones al medir con la app ocupada (carga de datos).
- Identidad Stitch intacta: iconos originales, paleta base, radios y sombras salvo las excepciones aprobadas en 6.3.
- Sin cambios en backend, bases de datos, `package.json` (sin dependencias nuevas) ni lógica.

### 6.7 Pruebas de regresión

- `npm --prefix frontend run build` (incluye `tsc -b`), `npm --prefix frontend run lint`, `npm --prefix frontend run format:check`.
- `npm --prefix frontend run e2e` con `E2E_PYTHON` (servidor sintético): `smoke`, `keyboard`, `contrast`, `drafts`.
- Backend sin cambios: `cd backend && python -m pytest -q` debe dar el mismo resultado que la línea base.
- Capturas antes/después por módulo, en tres temas y cuatro anchos, guardadas fuera de `.qa/` y sin datos reales.
- Revisión manual en cámara lenta (2-5x) de cada movimiento, y prueba en un dispositivo táctil real para hover y gestos.
- `git diff --stat` por fase: solo archivos de `frontend/src` y `docs/`.


---

## Apéndice A — Decisiones abiertas del usuario (no las resuelvas tú)

1. Matriz de permisos del Bloque 2 (2.4) y catálogo de acciones del auxiliar: se corrigen con el usuario antes de implementar.
2. Orden definitivo de ejecución (0.5) y su encaje con `PLAN_FINALIZACION.md`.
3. Diagnóstico del problema del agente (4.7) y diseño del emparejamiento (4.3).
4. Si un contador podrá traspasar responsables en el futuro (hoy: solo administrador).
5. Si `AGENTS.md` debe reflejar las excepciones visuales del Bloque 6 (6.3); no lo edites sin autorización.

## Apéndice B — Entregables esperados de cada bloque

Por bloque: resumen de cambios, archivos tocados, resultado de la línea base antes y después, pruebas ejecutadas, lo que no se pudo verificar, y confirmación de que no se tocaron instancias reales, secretos ni datos.
