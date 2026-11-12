## Piloto local vigente · 12/11/2026

Consultar docs/CS_PILOT_IMPORT_001.md. Flujo desde Empresas → Importar y conciliar → Desde carpeta local, con staging existente, revisión manual y confirmación expresa. Sólo se ensayaron carpetas generadas en PostgreSQL exclusivo contasuite_pilot_synthetic_001. No leer carpetas reales hasta recibir dos rutas y autorización expresa de análisis; no confundir esa autorización con confirmación definitiva. El piloto está deshabilitado por defecto y exige base PostgreSQL local exclusiva CS_PILOT_DATABASE, CS_PILOT_ENABLED y exactamente dos CS_PILOT_ROOTS. No cambiar .env/datos/infraestructura real ni reusar fixtures como empresas reales. No migraciones automáticas. Ver respaldo, inventario y resultados en el informe. v1.0 sigue sin aprobación operativa completa.

---

## Cierre de release vigente · 11/11/2026

Consultar docs/CS_RELEASE_CLOSURE.md y docs/INSTALL_RELEASE_WINDOWS.md. Nueva revisión explícita integral_0003_document_identity; el arranque sólo verifica esquema. Identidad XML por versión, conflictos UUID en la revisión documental existente y verificación fiscal separada. Paquete Windows con runtime privado, instalación versionada y retiro reversible; no requiere Python en PATH. Registro SCM bloqueado por WinError 5 y TLS/LAN real pendientes: no declarar v1.0 terminada ni desplegar al despacho. No alterar PowerShell, red, servicios reales, datos, .env o secretos para validar.

---

## Estado vigente de integración · 11/11/2026

Consultar docs/CS_INTEGRATION_RECOVERY.md. El arranque ordinario ya NO migra ni siembra datos: exige esquema compatible. Actualizaciones mediante scripts/schema_admin.py explícito, con respaldo/restauración y autorización. Se ejecutó sólo PostgreSQL nuevo sintético; no se tocó infraestructura del despacho. Código y frontend compilados, HTTP/UI parciales comprobados; ContaSuite v1.0 sigue sin aceptación operativa completa. Los textos históricos de migración automática y lanzadores antiguos que siguen debajo quedan sustituidos por este procedimiento. Para instalación usar docs/INSTALL_RECOVERY_WINDOWS.md y los nuevos lanzadores separados, sin habilitar indexación por iniciar alertas.

---

# ContaSuite Web

## Actualización SMB en oficina · 10 noviembre 2026

SMB ya está implementado mediante el proveedor UNC Windows de sólo lectura. Esta actualización sustituye las indicaciones anteriores que lo describen como pendiente. Consultar `docs/SMB.md`: lista separada `CS_STORAGE_SMB_ALLOWED_ROOTS`, identidad de la sesión Windows, sin credenciales guardadas ni escrituras remotas. El origen real de la oficina está registrado en modo manual; se probaron tres documentos sobre una base temporal y sus descargas SHA-256. Mantener las restricciones de raíces locales y las comprobaciones de enlaces/ruta final. La infraestructura general y SAT conservan sus pendientes.

Proyecto de automatización para un despacho contable. React + TypeScript + Vite, API FastAPI, SQLAlchemy, SQLite para pruebas y PostgreSQL como alternativa, agente local Windows.

## Reglas del proyecto

- Continúa el proyecto existente; integra los módulos uno por uno conservando sus reglas de negocio. No reescribas desde cero.
- Conserva el diseño de Stitch: botones, colores, iconos originales de ContaSuite 0.6, bordes, sombras, espaciados y animaciones. Fuentes: `design-source/`, `frontend/src/designs/`, `frontend/tailwind.config.cjs`. Los controles vivos compartidos están en `frontend/src/components/stitch.ts` y las reglas `.stitch-live-module` en `styles.css`.
- Mantén claro, oscuro y alto contraste; respeta `prefers-reduced-motion`.
- Inicio: logo, saludo según hora local, nombre configurado en su propia línea, «Bienvenido a ContaSuite», «Tu espacio de trabajo contable.».
- Omite el módulo experimental de Empresas de la app de escritorio. Conserva el catálogo y expedientes web actuales.
- Las pantallas de Stitch contienen ejemplos. No presentes contadores ficticios, conexión SAT, descarga SAT, OCR o impresión como funciones activas hasta implementarlas realmente.
- Conserva datos existentes: `.env`, `data/`, la base de datos y `agent/config.json`. No incluyas datos de ejecución ni credenciales en las entregas.
- El usuario autorizó explícitamente compilar el frontend para la entrega de visita y sus correcciones, sin instalador. Esta compilación ya se realizó. No generar instaladores ni paquetes de distribución sin autorización; conservar datos y secretos fuera de las entregas.
- Consulta `CONTINUAR_EN_CODEX.md` antes de modificar módulos. No implementes varios módulos a la vez sin una indicación clara del usuario.

## Validación y ejecución

- Backend: instala `backend/requirements-dev.txt`, entra a `backend` y ejecuta `python -m pytest -q`.
- Frontend: `npm --prefix frontend ci`, después `npm --prefix frontend run build`.
- Sólo tipos, sin emitir archivos: `npm --prefix frontend exec -- tsc --noEmit -p frontend/tsconfig.json`.
- Windows: `INICIAR_PRUEBA.bat` selecciona Python 3.12/3.11 de 64 bits y abre la versión compilada con SQLite. Requiere Internet para instalar dependencias la primera vez. No necesita Node para ejecutar la entrega.
- Desarrollo: configura `.env` y `.venv`, instala Node y ejecuta `npm --prefix frontend run dev`. `scripts/dev.mjs` también acepta `CONTA_PYTHON` con la ruta al Python preparado. Vite usa 4173 y FastAPI 8000.

## Motores y referencias

Recopila usa un motor original sin cambios en `backend/app/recopila_engine.py`; el adaptador web es `backend/app/recopila.py`. Las referencias para los próximos módulos están en `reference/desktop/`. Son fuentes para leer y adaptar, no módulos web ya conectados. Declara ya está integrado: `backend/app/declara_engine.py` se extrae sin cambiar las funciones del motor original mediante `scripts/extract_declara_engine.py`; el adaptador es `backend/app/declara.py`. La sesión Firefox y descarga SAT originales aún requieren integración con el agente. El dashboard está integrado en la primera pestaña de Empresas e incluye seguimiento temporal de CER públicos FIEL/CSD; no valida ante el SAT. Inicio conserva su bienvenida. El usuario descartó Imprime / Centro de impresión: no se muestra en la aplicación ni se contempla integrarlo. Los nombres visibles de los módulos son Recopila, CFDI, Declara y Recibos. CFDI corresponde al módulo antes llamado Organizador.

## CS-Storage v0.1

CS-Storage bloques 1–5 cerrados para operación local y visita técnica: núcleo, Centro Documental, indexador, clasificación, cuentas/permisos/auditoría y configuración/programación de fuentes. También está integrado el dashboard de Empresas y fechas de certificados públicos FIEL/CSD. Consultar `LISTO_PARA_VISITA.md` y `docs/CS_STORAGE_BLOCK5.md` antes de cambiar el alcance. El frontend de visita está compilado y verificado con SHA-256. No confundir preparación con habilitación de SMB remoto: el proveedor sigue pendiente, sin conexión de red; el modo operativo disponible usa carpetas físicas locales en el servidor Windows donde corren API e indexador.

El alta del primer administrador usa APP_TOKEN; después la clave deja de dar acceso. Sesiones HttpOnly con CSRF y HTTPS salvo loopback. Los colaboradores tienen lectura/escritura por empresa. Recopila, CFDI, Declara, Recibos, agentes, revisión global y administración requieren administrador. Nunca aceptar actores/roles/ámbitos suministrados por clientes fuera de endpoints administrativos autorizados. No guardar llaves privadas FIEL ni contraseñas de red. Fechas del CER y uso declarado no son validación de autenticidad, revocación ni sesión SAT.

Validación de cierre: 122 pruebas aprobadas y una omitida, TypeScript/Vite correctos, Edge sobre la compilación con dashboard/conector y cuatro módulos, programación real contra demo y preflight sin secretos. `.env`, `data/`, base real y `agent/config.json` se conservaron. El backend aplicará la revisión aditiva 0004 al arrancar; respaldar y ensayar sobre copia antes de actualizar datos del cliente. Las instalaciones nuevas no se siembran automáticamente con empresas ficticias. La infraestructura, TLS, permisos/documentos reales, PostgreSQL si se elige y SMB/SAT se validan presencialmente; no presentarlos como certificados ni activos. El lanzador inicia el trabajador después de la API, en un proceso independiente.
