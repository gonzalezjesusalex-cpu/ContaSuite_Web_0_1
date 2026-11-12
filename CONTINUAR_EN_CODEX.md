## Piloto local vigente · 12/11/2026

Consultar docs/CS_PILOT_IMPORT_001.md. Flujo desde Empresas → Importar y conciliar → Desde carpeta local, con staging existente, revisión manual y confirmación expresa. Sólo se ensayaron carpetas generadas en PostgreSQL exclusivo contasuite_pilot_synthetic_001. No leer carpetas reales hasta recibir dos rutas y autorización expresa de análisis; no confundir esa autorización con confirmación definitiva. El piloto está deshabilitado por defecto y exige base PostgreSQL local exclusiva CS_PILOT_DATABASE, CS_PILOT_ENABLED y exactamente dos CS_PILOT_ROOTS. No cambiar .env/datos/infraestructura real ni reusar fixtures como empresas reales. No migraciones automáticas. Ver respaldo, inventario y resultados en el informe. v1.0 sigue sin aprobación operativa completa.

---

## Cierre de release vigente · 11/11/2026

Consultar docs/CS_RELEASE_CLOSURE.md y docs/INSTALL_RELEASE_WINDOWS.md. Nueva revisión explícita integral_0003_document_identity; el arranque sólo verifica esquema. Identidad XML por versión, conflictos UUID en la revisión documental existente y verificación fiscal separada. Paquete Windows con runtime privado, instalación versionada y retiro reversible; no requiere Python en PATH. Registro SCM bloqueado por WinError 5 y TLS/LAN real pendientes: no declarar v1.0 terminada ni desplegar al despacho. No alterar PowerShell, red, servicios reales, datos, .env o secretos para validar.

---

## Estado vigente de integración · 11/11/2026

Consultar docs/CS_INTEGRATION_RECOVERY.md. El arranque ordinario ya NO migra ni siembra datos: exige esquema compatible. Actualizaciones mediante scripts/schema_admin.py explícito, con respaldo/restauración y autorización. Se ejecutó sólo PostgreSQL nuevo sintético; no se tocó infraestructura del despacho. Código y frontend compilados, HTTP/UI parciales comprobados; ContaSuite v1.0 sigue sin aceptación operativa completa. Los textos históricos de migración automática y lanzadores antiguos que siguen debajo quedan sustituidos por este procedimiento. Para instalación usar docs/INSTALL_RECOVERY_WINDOWS.md y los nuevos lanzadores separados, sin habilitar indexación por iniciar alertas.

---

# Continuar ContaSuite Web en Codex

## v0.4 — laboratorio PostgreSQL activado, QA visual pendiente

Leer `CONTASUITE_V0_4_PRUEBAS.md`. PostgreSQL portable aislado en 55484, base contasuite_dev_v04, API 8044 y frontend 4184. Migraciones nuevas aplicadas exclusivamente allí; datos ficticios, sin indexador ni raíces SMB. Secretos de laboratorio cifrados con DPAPI. Usuario devadmin; configurar contraseña con CONFIGURAR_ACCESO_V0_4.bat, sin mostrarla en el chat. Suite 168 aprobadas/1 omitida, diez flujos HTTP reales aprobados y restauración ensayada. QA visual sólo confirmó pantalla de acceso; requiere sesión del usuario para las pantallas internas. No usar INICIAR_PRUEBA.bat para el laboratorio, ni migrar/importar datos reales o contactar SMB. La autorización v0.4 permite ejecutar desarrollo/pruebas en este entorno aislado, sin producción.

## v0.3 Dashboard Integral y Clasificación · sin activar

Leer `DASHBOARD_INTEGRAL_CLASIFICACION.md`. Nuevos servicios modulares y migración independiente `backend/integral_migrations/001_integral.py`; nunca automática. No compilar, desplegar, importar Excel reales, ejecutar migraciones reales ni escanear SMB sin nueva autorización. El dashboard distingue actividad desconocida, fuentes sin activar y cumplimiento verificado por separado. Las clasificaciones de nombre/carpeta requieren revisión; relacionar documentos no cambia estados fiscales. Las rutas originales son administrativas y auditadas. PDF aislado/OCR y conciliación avanzada de períodos quedan pendientes. Los módulos anteriores se conservan.

## Importador y Conciliador v0.1 · sólo propuestas sintéticas

Leer `IMPORTADOR_CONCILIADOR.md`. Lector XLSX en memoria, conciliación y asistente preparados; migración independiente `backend/import_migrations/001_reconciliation.py`, sin activar. Confirmación definitiva bloqueada. No importar archivos reales, ejecutar migraciones reales, compilar ni desplegar sin nueva instrucción. No tocar SMB ni los módulos fiscales/de credenciales. Las sesiones de propuesta caducan a las 24 horas y requieren purga explícita; no hay planificador automático. No se crean empresas ni vínculos documentales al analizar o guardar decisiones.

## Credenciales, Certificados y Alertas v0.1 · sin activar

Leer `CREDENCIALES_CERTIFICADOS.md`. Código y migración explícita independiente en `backend/credential_migrations/001_vault.py`, nunca en arranque automático. No compilar, desplegar, migrar bases reales ni importar contraseñas sin nueva instrucción. Revelación bloqueada hasta integrar reautenticación y gestión externa de claves. CS-Storage, SMB y Control de Obligaciones se conservan intactos. No abrir ni procesar KEY. Pruebas exclusivamente con secretos, claves y CER ficticios.

## Control de obligaciones v0.1 · código preparado, sin activar

Leer `docs/CONTROL_OBLIGACIONES.md`. Se agregó código para Dashboard/Tabla en Empresas, endpoints y migración independiente `backend/fiscal_migrations/001_control_obligaciones.py`. No ejecutar migración real ni compilar/desplegar sin nueva instrucción: el usuario lo prohibió expresamente para esta iteración. La metadata fiscal está separada del arranque y de CS-Storage. Conserva las obligaciones anteriores; no hay importación definitiva ni lector XLSX aún. La base actual sigue siendo SQLite; PostgreSQL sólo tiene validación DDL en esta iteración.

## Actualización de oficina: SMB implementado

El conector remoto SMB está implementado y validado con una muestra de tres documentos del recurso de la oficina, en base temporal y sin escrituras remotas. La instalación conserva sus datos y tiene el origen registrado con frecuencia manual, previo respaldo privado. Leer `docs/SMB.md`. Esta actualización sustituye las menciones históricas de SMB como borrador pendiente; SAT, OCR e infraestructura general siguen fuera de alcance.

El ZIP contiene el proyecto completo con los cambios del parche ya aplicados y el frontend compilado. No vuelvas a aplicar `ContaSuite_Web_Cambios_Pendientes.patch`: ya forma parte de esta entrega.

## Abrir

La versión de visita ya incluye frontend compilado, por autorización explícita del usuario, sin instalador ni ZIP nuevo. Leer `LISTO_PARA_VISITA.md`: ejecutar `VERIFICAR_VISITA.bat`, respaldar base/data/configuración y después iniciar con `INICIAR_PRUEBA.bat`. El backend aplicará la migración aditiva 0004. No se migró la base real durante el desarrollo. El lanzador inicia el trabajador por separado después de la API. Crear el primer administrador con la clave inicial; en arranques posteriores usar la cuenta personal.

## Avance

- Cierre de visita: CS-Storage bloque 5 completado para fuentes locales, configuración del futuro Windows, programación persistente y diagnóstico. Dashboard de primera pestaña y seguimiento de CER públicos FIEL/CSD incorporados por autorización del usuario. Frontend compilado; ver `docs/CS_STORAGE_BLOCK5.md` y `LISTO_PARA_VISITA.md`.
- Validación final: 122 pruebas aprobadas y una omitida; compilación TypeScript/Vite, Edge sobre FastAPI con frontend compilado, tres temas/móvil, programación real en demo y preflight con manifiesto SHA-256. Ningún secreto de la instalación aparece en la compilación. No se cambiaron `.env`, `data/`, base real o `agent/config.json`. SMB remoto sigue como contrato/borrador sin conexión; pueden operarse carpetas físicas locales ejecutando el backend en el servidor Windows.

- CS-Storage, bloque 4 completado: alta personal inicial, contraseñas scrypt, sesiones HttpOnly revocables con CSRF, permisos de lectura/escritura por empresa y auditoría. Usuarios y permisos en Configuración; login nuevo con Stitch. La clave de instalación deja de autorizar tras crear el primer administrador. No se crearon cuentas en la base real. Consulta `docs/CS_STORAGE_BLOCK4.md`.
- Validación del bloque 4: 107 pruebas aprobadas y una omitida; 23 nuevas. TypeScript `--noEmit` y Edge: alta, permisos, carga/descarga, cookie, recarga, revocación, contraseña, temas y móvil. Sin compilación ni cambios en frontend/dist. Los motores globales y el agente requieren administración; las cuentas colaboradoras se limitan a Empresas/tareas/obligaciones/Documentos según concesiones. HTTPS fuera del loopback.

- CS-Storage, bloque 3 completado: indexador local independiente, cola con lease/checkpoint, reanudación, versiones incrementales por SHA-256, duplicados, desapariciones seguras e incidencias; clasificación RFC de XML CFDI/PDF con texto y revisión confirmable/corregible/rechazable. Panel de análisis y evidencia en Documentos con Stitch. Demo reproducible en carpetas nuevas; consultar `docs/CS_STORAGE_BLOCK3.md`.
- Validación del bloque 3: 84 pruebas aprobadas y una omitida; 14 nuevas. CLI independiente real, Edge con cola/trabajador y confirmación/corrección/rechazo, tres temas y móvil sin desbordamiento; TypeScript `--noEmit` correcto. No se compiló ni se tocó la base real. El worker debe iniciarse por separado; el panel de configuración/frecuencia sigue pendiente.

- CS-Storage, bloque 2 completado: Centro Documental en Empresas → Documentos y en cada expediente. Búsqueda y filtros paginados, cargas PDF/XML/CER públicos validados, bandeja sin clasificar, detalle de versiones y huellas, comprobación y descarga verificada, vista previa PDF/XML. Acceso con APP_TOKEN de instalación; sesiones personales pendientes del bloque 4. Consulta `docs/CS_STORAGE_BLOCK2.md`.
- Validación del bloque 2: 70 pruebas aprobadas, una omitida; 11 pruebas nuevas de catálogo/API y revisión en Edge mediante servidores de desarrollo aislados. TypeScript `--noEmit` correcto. No se compiló ni se actualizó frontend/dist. No se ejecutaron migraciones sobre la base real durante las pruebas.

- CS-Storage v0.1, bloque 1: núcleo documental, proveedores de carpeta local de sólo lectura y repositorio interno, contratos SMB pendientes, versiones/huellas/ubicaciones/vínculos/revisiones/eventos y migraciones Alembic reproducibles. Sin cambios de interfaz. Consultar `docs/CS_STORAGE.md` antes de continuar. No compilar ni empaquetar sin autorización explícita.
- Validación del bloque 1: 59 pruebas aprobadas, una omitida y una advertencia previa de Starlette/AnyIO; incluye 18 pruebas nuevas de CS-Storage. Se probó un punto de unión Windows y el rechazo de UNC antes de realizar sondeos de red. SQLite se probó con migraciones reales sobre bases temporales; PostgreSQL sólo con DDL de su dialecto, no contra un servidor. No se ejecutaron migraciones sobre la base real durante las pruebas. Los documentos con historial no se pueden borrar mediante las rutas antiguas; la gestión documental se incorporará en el bloque 2.

- Nombres visibles actuales: **Recopila**, **CFDI**, **Declara** y **Recibos**. CFDI es el módulo antes llamado Organizador. Las rutas y motores internos se conservan. El Centro de impresión se retiró de la navegación y de las rutas de la aplicación.

- Declara: motor separado de la GUI original, carga PDF/carpeta/ZIP, revisión y vista previa, resolución manual de tipos/copias, control mensual por empresa, historial y ZIP/CSV con copias verificadas SHA-256. Acceso desde el menú y desde Declaraciones en el expediente. Diez pruebas nuevas; suite completa: 41 aprobadas y una omitida por privilegios de enlaces simbólicos de Windows.
- Inicio: saludo por hora, nombre independiente y textos de bienvenida.
- Empresas web: catálogo, expedientes, tareas, obligaciones y documentos. No se integró Empresas experimental de escritorio.
- Recibos: clientes por nombre libre, catálogo opcional con eliminación que conserva historial, concepto personalizado, montos en letra, membrete original, folios anuales, vista previa, historial y exportación individual/ZIP/PDF combinado. Varios meses en individual y en masa: las casillas agregan una fila por mes y cliente. El importe se aplica completo a cada recibo. Editar una fila no expande nuevamente los meses.
- Recopila: motor original de escritorio integrado por API. Admite ZIP, carpeta o PDF/XML; análisis por UUID, pólizas sin CFDI, complementos de pago y sobrantes; revisión y vista previa, recopilador general, separadores, reportes y salida por meses opcional. Procesos en segundo plano con estados persistidos y selección de análisis recientes.
- Recibos y Recopila: controles con tokens visuales de Stitch, sombras y transiciones; animación discreta de tarjetas/modales/resultados y movimiento reducido.
- Organizador: adaptador web conectado al motor original sin cambios (`backend/app/organizador_engine.py`, copia idéntica de `reference/desktop/CFDI/engine.py`). Carga ZIP o carpeta, filtros de RFC/ejercicio/meses/tipos/formatos, reportes Excel, análisis previo con rutas, generación de copias verificadas SHA-256, descarga ZIP y auditoría CSV. Historial persistido y recuperación de procesos interrumpidos. Paneles de origen, estructura y auditoría con los controles y temas compartidos de Stitch. Consulta `docs/ORGANIZADOR_CFDI.md`.

## Siguiente trabajo

Los cinco bloques de **CS-Storage v0.1** y el dashboard/CER solicitados para la visita están cerrados y compilados. Lo siguiente es ejecutar la guía de aceptación presencial, no afirmar que el servidor del despacho fue validado. Para operar con archivos del servidor en el modo disponible, ejecutar API/indexador allí y configurar raíces físicas locales de sólo lectura. SMB remoto requiere completar y validar el adaptador antes de habilitarlo; Windows en la interfaz permanece como borrador desactivado. No se ha contactado el despacho. Respaldar base/data/configuración antes de aplicar la revisión 0004 a datos reales.

Pendientes fuera de esta entrega local: infraestructura/TLS y permisos reales, PostgreSQL real si se elige, SMB remoto, sesión/descarga automática SAT en Declara, OCR y custodia especializada de llaves. Los motores web actuales conservan sus flujos de copias y generación; no se presentan como integración SAT. El módulo de impresión permanece descartado. El usuario autorizó la compilación del frontend para esta entrega, sin instalador; no volver a pedir la misma autorización para correcciones de la visita, ni extenderla a paquetes/instaladores.


Referencias incluidas:
- `reference/desktop/CFDI/engine.py`: rutas Emitidos/Recibidos por RFC y ejercicio, nombres de meses, reportes Excel, copiar/mover con SHA-256, duplicados por nombre. No clasifica por contenido XML.
- `reference/desktop/Declara/organizador_sat_v26.py`: lógica y GUI originales juntas. Incluye renombrado, conflictos, normales/complementarias, control de meses y automatización SAT. La descarga SAT requiere trabajo específico; no debe darse por conectada por mostrar su maqueta.
- `reference/desktop/Imprime/` se conserva sólo como referencia histórica; el módulo de impresión está descartado.

Relacionador y Renombrador tienen referencias visuales, pero sus motores no venían en el ZIP de escritorio utilizado. No marcarlos como integrados. El agente actual sólo tiene análisis de carpetas de lectura.

## Límites y revisiones pendientes

- Organizador trabaja con copias subidas al servidor y nunca mueve los originales del equipo. Máximo 100 MB por carga, 1,000 archivos seleccionados o 5,000 en ZIP, 500 MB descomprimidos. Conserva la estructura Tipo/RFC/AAAA-MM y los nombres de reportes originales; no analiza contenido XML, no empareja UUID y no valida SAT. El ZIP de salida equivale a la carpeta de empresa/ejercicio. Las carpetas de ambos tipos se incluyen aun estando vacías.
- Organizador ejecuta tareas dentro de FastAPI, con la misma limitación de un solo proceso que Recopila. Los reinicios marcan las tareas interrumpidas como error y exigen una nueva carga; las copias parciales permanecen en el servidor, sin ofrecerlas como resultado completo. Respalda también `data/organizador` junto con la base. No añadas `.qa/`, datos de prueba, credenciales ni paquetes de dependencias a una entrega.
- Validación de Organizador: seis pruebas nuevas de API/motor. Suite completa en Windows: 31 aprobadas y una omitida porque Windows no permite crear enlaces simbólicos con este usuario; la comprobación del agente con enlaces requiere privilegios o modo desarrollador. Compilación TypeScript/Vite correcta con las versiones de `package-lock.json`.
- Revisión de Organizador en Edge: flujo de carga/análisis/generación y CSV correctos, con tres copias SHA-256 verificadas y los tres temas revisados. Descarga ZIP repetida y verificada en Edge: archivo completo de 875 bytes, tres documentos con contenido idéntico al origen y CSV de 459 bytes con tres registros Copiado. La respuesta vacía anterior se debía al agente de descargas que interceptaba el enlace, según confirmó el usuario. Incidencia resuelta. Se conserva la detección de descargas vacías.
- Recopila trabaja con copias subidas al servidor, no modifica las carpetas originales. Hasta 100 MB por carga; 1,000 documentos seleccionados o 5,000 dentro de un ZIP, 500 MB descomprimidos. El motor depende del texto extraíble y no incluye OCR.
- Recopila ejecuta tareas dentro del proceso FastAPI. Está pensado para el lanzador de un solo proceso; antes de desplegar varios workers, sustituir la recuperación de trabajos al arranque por una cola/lease coordinada. Un reinicio puede interrumpir la tarea y se informa como error.
- El motor original puede omitir documentos ilegibles al generar y relaciona PDF por nombre/UUID; revisar avisos y coincidencias. No prometer reconocimiento de cualquier formato de póliza o escaneo.
- Los recibos web tienen su propio consecutivo. No se importó el historial de escritorio; antes de emitir en producción con una numeración compartida se necesita migración y acuerdo del despacho.
- Respalda la base junto con `data/receipts`, `data/documents`, `data/recopila`, `data/organizador` y `data/declara`.
- Las pruebas automatizadas se ejecutan con SQLite; PostgreSQL necesita verificación en una instalación real.
- El diseño final debe contrastarse con Stitch en el navegador: las adaptaciones están funcionales y los estilos se comparten, pero no se ha certificado coincidencia exacta de todas las pantallas.

## Petición inicial sugerida para Codex

«Lee AGENTS.md y CONTINUAR_EN_CODEX.md. Revisa el estado actual sin reconstruir el proyecto desde cero. Conserva el diseño de Stitch y los datos existentes. El parche anterior ya está aplicado. Continuaremos con el dashboard en la primera pestaña de Empresas, con seguimiento de FIEL y los datos documentales de Declara. La automatización SAT por agente sigue pendiente. Antes de cambiar reglas del motor, explícame la adaptación propuesta.»
