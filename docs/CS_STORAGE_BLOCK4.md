# CS-Storage v0.1 — bloque 4

Cuentas personales, sesiones revocables, permisos por empresa y auditoría integrados en el proyecto existente. Se conserva el diseño de Stitch, la bienvenida y los tres temas. No se compiló, empaquetó ni modificó `frontend/dist`; tampoco se modificaron `.env`, `data/`, `agent/config.json` o la base real.

## Implementación y archivos

| Archivo | Cambio |
|---|---|
| `backend/app/models.py` | Cuenta, sesión, permisos por empresa, estado de alta inicial, límite de intentos y eventos de seguridad. |
| `backend/migrations/versions/0003_identity.py` | Migración aditiva y congelada; no modifica documentos, archivos, revisiones 0001/0002 ni sus instantáneas. |
| `backend/app/security.py` | Identidad obtenida del servidor, cookies/sesiones, CSRF, origen, transporte y autorización. |
| `backend/app/accounts.py` | Alta inicial, login/logout, contraseña, administración, revocación, consulta de auditoría y recuperación local. |
| `backend/app/main.py` | Aislamiento del estado general y rutas antiguas, autorización de tareas/obligaciones, protección de módulos globales, auditoría HTTP y errores de validación sin inputs. |
| `backend/app/storage/service.py`, `router.py` | Actor de la sesión, lectura/escritura diferenciadas y protección de modificaciones de documentos compartidos. |
| `frontend/src/modules/Login.tsx` | Alta del primer administrador y acceso personal. |
| `frontend/src/modules/AccountSecurity.tsx` | Mi cuenta, contraseña, cierre de sesiones, usuarios, permisos y auditoría en Configuración. |
| `frontend/src/App.tsx`, `api.ts`, `types.ts` | Sesión por cookie, identidad, CSRF, actividad real del navegador, cierre al caducar y navegación según perfil. |
| `frontend/src/modules/Documents.tsx`, `Companies.tsx`, `Dossier.tsx`, `Records.tsx` | Controles según permisos; el backend los comprueba de forma independiente. |
| `frontend/src/modules/Receipts.tsx` | CSRF también en las solicitudes binarias POST de Recibos. |
| `frontend/vite.config.ts` | Conserva Host al reenviar la API para que la comprobación del origen funcione en desarrollo. |
| `frontend/src/styles.css` | Paneles y tablas con tokens existentes; auditoría con desplazamiento acotado y adaptación móvil. |
| `backend/tests/test_accounts.py`, `test_storage_core.py`, `test_storage_migrations.py` | 23 pruebas adicionales de identidad, aislamiento, sesiones, auditoría y migración. |

Las altas administrativas guardan cuenta, perfil, estado y concesiones en una sola transacción, también al crear una cuenta desactivada.

Se añaden `identity_state`, `user_accounts`, `user_company_grants`, `user_sessions`, `login_throttles` y `security_events`. Se reutilizan `Company`, documentos, revisiones, trabajos y eventos documentales. No había una entidad de usuarios anterior que duplicar.

## Alta inicial y acceso

La aplicación muestra el alta del primer administrador cuando `identity_state.initialized` es falso. Requiere la clave `APP_TOKEN` existente, nombre, usuario y contraseña de 12–128 caracteres. La creación y el cierre del alta se guardan en una sola transacción bajo bloqueo; una segunda alta se rechaza. No se crea una contraseña predeterminada ni una cuenta ficticia en la instalación.

Hasta esa alta se conserva el acceso técnico anterior con la clave de instalación para compatibilidad. La interfaz nueva exige crear la cuenta personal antes de abrir el espacio. Una vez creada, `APP_TOKEN` deja de autorizar las rutas normales y no sirve para recuperar acceso. Si se presenta junto con la cookie de un colaborador, sigue aplicándose la identidad del colaborador; no eleva sus permisos. El registro inicial queda cerrado incluso si posteriormente se desactiva una cuenta.

Las contraseñas se almacenan con scrypt, sal aleatoria individual, `N=2^17`, `r=8`, `p=1`, salida de 32 bytes. Se permiten dos verificaciones simultáneas por proceso HTTP para acotar memoria. Los nombres de usuario se normalizan a minúsculas. Los intentos sobre nombres desconocidos también realizan el cálculo costoso y devuelven el mismo error que una contraseña incorrecta.

El límite de intentos se persiste en la base, no en memoria: hasta ocho por usuario y ochenta por dirección de conexión en una ventana de quince minutos. Las solicitudes admitidas se contabilizan antes de verificar la contraseña. Un acceso correcto reinicia el contador del usuario; el de dirección conserva su ventana. El bloqueo temporal puede requerir esperar incluso si se conoce la contraseña. No se confía en un header de dirección enviado por el cliente; la configuración de proxies de Uvicorn debe limitarse a proxies confiables.

## Sesiones y CSRF

La cookie `contasuite_session` contiene un token aleatorio de 256 bits; la base sólo guarda SHA-256. Es HttpOnly, SameSite=Strict y está limitada a `/api`. Se marca Secure con HTTPS. La sesión no se guarda en localStorage ni sessionStorage. La cookie legible `contasuite_csrf` permite enviar `X-CSRF-Token`; el hash correspondiente queda vinculado a la sesión en la base.

Todas las operaciones autenticadas que cambian estado verifican ese token y rechazan orígenes diferentes o `Sec-Fetch-Site: cross-site`. Login y alta inicial aceptan JSON y comprueban el origen, sin depender de una sesión previa. No se habilita CORS amplio. El proxy Vite conserva el Host de la aplicación para comparar el origen real de desarrollo; no se resuelve el problema confiando en cualquier Origin o header reenviado.

Se requiere HTTPS fuera del equipo local. Para desarrollo se permite HTTP únicamente cuando hostname y dirección de conexión corresponden al loopback local; `testserver`/`testclient` son la excepción del cliente de pruebas. No hay una variable para desactivar esa exigencia en toda la red. Para el despacho debe configurarse TLS y un proxy de confianza antes de habilitar cuentas por LAN; este bloque no despliega ese servidor.

La sesión vence a las doce horas como máximo o después de treinta minutos sin actividad. Las solicitudes POST autorizadas y las solicitudes con actividad reciente renuevan el último uso, como máximo una vez por minuto. El navegador señala actividad reciente de teclado, puntero, rueda, tacto o foco; los sondeos automáticos sin interacción no prolongan indefinidamente la sesión. El servidor usa su propia hora, no un timestamp del cliente. El límite absoluto no se renueva. Un cliente que conserve credenciales puede indicar actividad, pero no superar las doce horas.

Un nuevo acceso rota la cookie de ese navegador e invalida su sesión previa. Se conservan hasta cinco sesiones no revocadas por usuario. Cerrar sesión revoca el token en la base. Hay cierre de todas las sesiones propias y revocación administrativa. Cambiar contraseña, restablecerla, desactivar o modificar perfil/permisos revoca las sesiones existentes; el usuario vuelve a ingresar. No se borran cuentas ni historial. Se impide desactivar o degradar al último administrador activo; los cambios de cuenta usan una revisión para rechazar ediciones obsoletas.

La autorización se comprueba al inicio de cada solicitud. Revocar una sesión impide nuevas solicitudes; no retira bytes que ya fueron autorizados y entregados ni cancela una operación que ya estaba en curso.

## Matriz de permisos

| Operación | Administrador | Colaborador con lectura | Colaborador con escritura |
|---|---|---|---|
| Ver empresa, tareas y obligaciones | Todas | Empresas asignadas | Empresas asignadas |
| Consultar documentos, versiones, vista previa y descarga | Todos | Documentos vinculados a sus empresas | Igual que lectura |
| Cargar documentos | Todas / sin clasificar | No | Sólo empresas con escritura |
| Crear/editar tareas y obligaciones | Todas | No | Sólo empresas con escritura, tanto origen como destino |
| Modificar un documento compartido | Sí | No | Requiere escritura para **todas** sus empresas vinculadas |
| Revisar clasificaciones y documentos sin clasificar | Sí | No | No |
| Indexación/configuración de orígenes | Sí | No | No |
| Crear/editar/eliminar empresas | Sí, con protección de historial | No | No |
| Recopila, CFDI, Declara, Recibos y agente local | Sí | No | No |
| Usuarios, concesiones y auditoría global | Sí | No | No |
| Cambiar contraseña y cerrar sesiones propias | Sí | Sí | Sí |

Los módulos de automatización conservan su lógica y datos, pero sus historiales todavía son globales y algunos contienen nombres libres sin empresa asociada. Se reservan a administración en **todos** sus endpoints, incluidas vistas previas y descargas. No se presenta como implementada una delegación granular de esos motores. Incorporarla requiere un trabajo posterior sobre propiedad de sus registros.

El estado general se filtra en la API: un colaborador no recibe empresas ajenas, rutas de carpeta, resultados del agente ni auditoría global. Las consultas del catálogo, detalles, huellas, candidatos duplicados y contenidos se restringen por empresa. Las versiones posteriores pendientes no se entregan a colaboradores hasta resolver su clasificación. Las ubicaciones privadas y configuración del proveedor siguen fuera de las respuestas públicas.

Las rutas anteriores también están protegidas: la descarga usa el actor de la sesión y la misma comprobación de integridad; la carga comprueba escritura antes de abrir un destino y no devuelve `storage_name` a colaboradores. Los permisos de lectura y escritura no se confunden si un usuario tiene distintos niveles en varias empresas. Una cuenta sin concesiones puede ingresar y gestionar su sesión, pero no consultar expedientes.

El agente conserva `AGENT_TOKEN` como credencial técnica separada: no sirve para iniciar sesión ni acceder a la API de usuarios. El transporte del agente se identifica en auditoría como `agent_transport`; no se afirma que cada equipo tenga ya una identidad personal distinta.

## Auditoría

`storage_events` conserva operaciones documentales con el ID personal real, o la identidad técnica correspondiente al trabajador/migración. `security_events` registra altas, accesos, cambios de contraseña/cuenta, revocaciones y solicitudes API con resultado HTTP. También registra rechazos, validación y errores inesperados. Las peticiones de login no autenticadas figuran como anónimas; el acceso correcto tiene un evento adicional con el usuario identificado.

La auditoría HTTP registra la plantilla de ruta, sin copiar query strings, cuerpos, contraseñas, cookies o mensajes del sistema de archivos. Los errores de validación tampoco devuelven los valores originales de Pydantic. El panel de Configuración permite consultar hasta cien eventos por página de seguridad o documentales; la interfaz usa cincuenta y desplazamiento acotado. Sólo los administradores acceden al registro global. Los eventos de lectura indican autorización y verificación en el servidor, no prueban que el navegador haya terminado de guardar una descarga.

No hay endpoint para borrar o editar eventos. No se implementa almacenamiento WORM, firma criptográfica del registro ni protección contra el propietario de la base. Las sesiones caducadas y el historial se conservan; la política operativa de retención/respaldo sigue siendo necesaria antes de producción. No se purgan datos automáticamente.

## Uso y recuperación

1. Respaldar base y `data/` antes de actualizar una instalación. El backend ejecutará la revisión 0003 al arrancar; durante este desarrollo sólo se migraron bases ficticias.
2. Abrir el frontend de desarrollo y crear el primer administrador con la clave de instalación existente. Configuración → Usuarios y permisos permite crear cuentas y asignar lectura/escritura por empresa.
3. Iniciar el trabajador documental por separado, como en el bloque 3. Las cuentas nuevas no cambian sus raíces autorizadas ni habilitan SMB.

El frontend compilado de entregas anteriores no incluye estas pantallas. Se probó con Vite; la compilación y el empaquetado siguen pendientes de autorización explícita.

Para recuperar una cuenta existente desde el equipo que administra la base, con el mismo entorno del backend:

```powershell
# Desde backend; no contiene la contraseña en argumentos ni en historial de consola.
../.venv/Scripts/python.exe -m app.accounts --username nombre-del-administrador
```

El comando solicita dos veces una contraseña sin eco, recupera la cuenta seleccionada como administradora activa, revoca sus sesiones y registra `local_recovery`. No crea cuentas implícitas ni elimina datos. Requiere acceso local a la base/configuración; no hay un endpoint remoto de recuperación ni un restablecimiento mediante `APP_TOKEN`.

Endpoints principales bajo `/api/auth`: `status`, `bootstrap`, `login`, `me`, `logout`, `logout-all`, `password`, `users`, `users/{id}`, `users/{id}/revoke` y `audit`. Los payloads no aceptan propiedades adicionales para simular identidad, sesión o concesiones. Sólo la administración puede establecer perfiles y permisos.

## Validación y límites pendientes

Resultado: **107 pruebas aprobadas, una omitida y una advertencia previa de Starlette/AnyIO**. Las 23 adicionales incluyen sesiones/replay/expiración, CSRF y origen, HTTPS, bloqueo persistente, aislamiento por empresa y rutas antiguas, escritura diferenciada, revocación/desactivación, contraseñas/restablecimiento, último administrador, auditoría sin secretos, permisos de documentos compartidos y migración desde un catálogo realista del bloque 3 sin alterar sus filas. La omisión anterior por privilegios de symlink en Windows se mantiene; la prueba de junction sí se ejecuta.

TypeScript `--noEmit` correcto. Edge con servidores de desarrollo y base ficticia: alta inicial, creación de colaborador, lectura/escritura diferenciadas, denegación de empresa ajena por ruta antigua, recarga sin clave en sessionStorage, cookie HttpOnly, desactivación con revocación observable, cambio de contraseña y nuevo acceso, tres temas, móvil sin desbordamiento horizontal ni errores JavaScript.

SQLite se probó con migraciones y transacciones reales; PostgreSQL sólo con DDL del dialecto. No se certificó un servidor PostgreSQL, TLS del despacho, múltiples procesos HTTP en producción, conexión SMB ni infraestructura real. No se implementaron MFA, recuperación por correo ni una ACL individual para motores de automatización. El siguiente bloque es configuración del futuro conector Windows y su frecuencia; la conexión real requiere validación presencial. Dashboard y vigencia FIEL continúan pendientes.

Referencias primarias utilizadas para parámetros y controles: [OWASP: almacenamiento de contraseñas](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [OWASP: sesiones](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) y [OWASP: CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html). No constituyen una certificación de seguridad del despliegue.
