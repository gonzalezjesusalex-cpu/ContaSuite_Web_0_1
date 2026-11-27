# Credenciales, Certificados y Centro de Alertas v0.1

## Diagnóstico

Empresas y sus expedientes ya tienen sesiones personales, concesiones de lectura/escritura por empresa y CS-Storage con referencias a documentos. El dashboard existente analiza CER públicos, pero no administra secretos. No existían permisos específicos ni una bóveda, proveedor de claves o reautenticación reciente para revelar contraseñas.

La instalación configurada sigue usando SQLite, no PostgreSQL. El código nuevo usa SQLAlchemy con DDL compatible con PostgreSQL. No se cambió la configuración ni se probó un servidor PostgreSQL. El Control de Obligaciones v0.1 permanece intacto y sin activar. Inicio, motor SMB, rutas de documentos y diseño principal tampoco se modificaron.

## Archivos

Nuevos:

- `backend/app/credential_models.py`: metadata independiente, tablas y catálogo inicial.
- `backend/app/credential_crypto.py`: cifrado autenticado y contrato de autorización de descifrado.
- `backend/app/credential_api.py`: metadatos, credenciales, certificados, permisos e historial.
- `backend/app/credential_alerts.py`: fuentes y conciliación manual de alertas persistidas.
- `backend/app/credential_import.py`: contrato de vista previa redactada del importador futuro.
- `backend/credential_migrations/001_vault.py`: migración aditiva explícita, fuera del arranque automático.
- `backend/tests/test_credentials.py`: pruebas con secretos, claves y CER sintéticos.
- `frontend/src/modules/Credentials.tsx`: credenciales, certificados y componente reutilizable AlertCenter.
- Este documento.

Modificados: `backend/app/main.py` (router y no-cache acotado a la API nueva), `backend/requirements-base.txt` (`tzdata`), `frontend/src/modules/Companies.tsx`, `frontend/src/modules/Dossier.tsx` y `CONTINUAR_EN_CODEX.md`.

## Tablas y migración

| Tabla | Contenido |
|---|---|
| vault_services | Catálogo extensible de servicios SAT, FIEL, CSD, IMSS, IDSE, SIPARE, INFONAVIT y otros |
| vault_grants | Permiso específico por cuenta y empresa |
| vault_credentials | Envelope cifrado, servicio, identidad, revisión y estado histórico |
| vault_versions | Revisiones anteriores cifradas y actor/fecha |
| vault_certificates | CER público, tipo declarado, RFC, serial, sujeto, huella, fechas, revisión, origen y documento |
| vault_audit | Actor, empresa, acción, registro, fecha y metadatos acotados; nunca valores de secretos |
| vault_alert_settings | Umbrales iniciales 60/30/15 días |
| vault_alerts | Identidad deduplicada, fuente, referencia, empresa, prioridad, generación, vencimiento y estado |

Los IDs de empresa existentes se reutilizan; no se crean empresas. Una empresa puede tener varios accesos del mismo servicio, cada uno con sus revisiones cifradas. El borrado de credenciales es archivo lógico. Las claves foráneas conservan referencias y pueden impedir borrar empresas con historial: no hay eliminación en cascada del módulo.

La migración define `upgrade(connection)` para un operador autorizado después de respaldar y ensayar. No se añadió a Alembic de CS-Storage ni al `Base.metadata.create_all` del arranque. La metadata es independiente. Sin tablas, el módulo responde 503 y no crea nada. La migración sólo se ejecutó sobre bases temporales de pruebas; nunca sobre datos reales. El downgrade destructivo está bloqueado.

## Seguridad de la bóveda

### Contraseña maestra (renovación del gestor, fase 1 · cs_0022)

- **Esquema de sobre.** Una llave de datos aleatoria de 256 bits envuelve la llave propia de cada secreto (AES-256-GCM, con la empresa y el registro como datos asociados). La llave de datos sólo se guarda envuelta: una copia por persona autorizada, derivada de su contraseña maestra con Argon2id (3 iteraciones, 4 carriles, 64 MiB; los parámetros viajan con cada copia), y otra con el código de recuperación (24 símbolos, se muestra una sola vez). Tablas `vault_config` y `vault_keys`; ninguna guarda la contraseña maestra.
- **Desbloqueo.** La bóveda empieza bloqueada en cada sesión. Con la contraseña maestra la llave de datos queda sólo en la memoria del servidor (`app/vault_session.py`; la API corre con un solo proceso). Nunca va al navegador, al disco, a cookies ni a registros.
- **Bloqueo.** Solo tras `auto_lock_minutes` sin uso (5 por omisión, de 1 a 60), con «Bloquear ahora», al cerrar sesión, al revocar sesiones o al quitar el acceso a la persona. Tras 5 intentos fallidos se esperan 5 minutos. Cada intento queda en la bitácora.
- **Con la bóveda bloqueada** la lista, la ficha de empresa, la bitácora, la importación y la exportación responden 423: no se ve ningún dato de las empresas.
- **Personas autorizadas.** El administrador da acceso con un código temporal (que la persona cambia al primer desbloqueo) y lo quita. Con el código de recuperación sólo un administrador puede desbloquear; después elige una contraseña maestra nueva.
- **Migración.** Al crear la bóveda, los sobres guardados con el llavero DPAPI anterior se re-envuelven con la llave de datos en una sola transacción, sin volver a cifrar el contenido (los de versión 1 se vuelven a sellar). Si el llavero anterior no se puede leer en ese equipo, no se crea nada.
- Endpoints: `GET /api/credentials/vault/state`, `POST /vault/setup`, `/vault/unlock`, `/vault/lock`, `/vault/touch`, `/vault/password`, `/vault/recovery`, `PUT /vault/settings`, `GET|POST /vault/members`, `DELETE /vault/members/{user_id}`. La reautenticación con la contraseña de inicio de sesión (`/reauth`) se retiró.

### Tipos, certificados y permisos (fase 2 · cs_0024)

- **Tipos de contraseña** (`vault_credentials.kind`): SAT_CIEC, IMSS_IDSE, SIPARE, INFONAVIT, CORREO y OTRO; LLAVE es la contraseña de la llave privada de una FIEL/CSD. Se crean por tipo (`kind`) o por portal del catálogo (`service_id`). Usuario por defecto: el RFC de la empresa (SAT, Infonavit), el registro patronal (IMSS, SIPARE) o la dirección de correo (Correo); se puede editar. `requires_review` marca «Revisar» y `updated_by` guarda quién lo cambió.
- **Certificados** (`vault_certificates`): `cert_class` FIEL_EMPRESA, FIEL_REPRESENTANTE o CSD; datos del titular, `branch` del CSD, `active`, `replaced_by` y `key_password_id`, que apunta a la credencial cifrada con la contraseña de la llave. Hay una sola FIEL activa de cada clase por empresa: registrar otra pide `replace` y la anterior pasa al historial. Los CSD pueden ser varios. Uno vencido nunca queda activo. La migración deja activa la FIEL que vence al último y crea un certificado «Faltan .cer y .key» para cada contraseña de FIEL/CSD que no tenía certificado.
- **Permisos del gestor** (`vault_access`): ver la lista, ver y copiar son para el administrador y las personas con copia de la llave, cada una en las empresas de su cuenta. Agregar, editar, eliminar, archivos, certificados, importar y exportar son sólo para el administrador. En la bitácora, la persona autorizada ve sólo sus acciones. Los demás no ven el módulo (`/api/state` → `vault_access`). Los permisos por empresa de `vault_grants` ya no aplican al gestor. Las demás pantallas (semáforo, tablero, ciclo de vida) conservan `allowed()`.
- **Bitácora** (`vault_audit`): `kind` con la acción de la spec (DESBLOQUEAR, DESBLOQUEO_FALLIDO, VER, COPIAR, CREAR, EDITAR, ELIMINAR, IMPORTAR, EXPORTAR, USO_DECLARA), `resource_type` y `client` (IP y navegador). Sólo se agregan filas, nunca secretos.

### Importación, plantilla y exportación (fase 4 · cs_0025)

- `app/vault_import.py` aplica la sección 6 de la spec. Se procesa en memoria del servidor; el navegador vuelve a mandar el archivo en cada paso y su SHA-256 debe ser el mismo de la vista previa. Es sólo para administradores con la bóveda desbloqueada.
- **1 · Archivo** (`POST /import/read`): `.xlsx` o `.csv` (UTF-8 o Latin-1, separado por coma, punto y coma o tabulador), hasta 5 MB. Se elige la hoja que tiene columna RFC y al menos una columna de contraseña; los encabezados son la primera fila que contiene «RFC». Los `.xls` responden 422 con la indicación de guardarlos como `.xlsx`, porque hace falta la dependencia `xlrd`, pendiente de autorizar.
- **2 · Columnas**: los encabezados se reconocen sin mayúsculas, acentos ni espacios (tabla de la spec). La asignación corregida se guarda en `vault_import_templates` por la firma de los encabezados, sin valores de celdas.
- **3 · Revisar cambios** (`POST /import/preview`): una línea por celda con valor. Las acciones son Agregar, Actualizar, Sin cambios, No se toca (vacía, NA, N/A, - o SIN), Revisar y Necesita tu decisión.
  - Un RFC que no existe pide crear la empresa u omitirla, y un valor con «/» pide elegir cuál o guardar todos.
  - Una contraseña de FIEL/CSD sin archivos crea «Faltan .cer y .key». Si no abre la llave guardada queda en «Revisar» y no se aplica.
  - Un registro patronal o un nombre distintos sólo generan un aviso. Con un RFC repetido gana la última fila, y las filas sin RFC se cuentan.
  - Nunca se muestran contraseñas: la comparación usa la huella con llave.
- **Aplicar** (`POST /import/apply`): todo en una transacción. Responde 409 si quedan decisiones o si el archivo cambió. Registra una fila IMPORTAR con el nombre del archivo y los conteos.
- En CORREO, «dirección / contraseña» guarda la dirección como usuario. Una celda con sólo la dirección no se toca. En IMSS y SIPARE, el usuario es el registro patronal del archivo o el de la empresa.
- `GET /import/template` genera la plantilla vacía. `POST /export` produce el mismo formato con los datos, pide otra vez la contraseña maestra y registra EXPORTAR. De cada tipo exporta la credencial más reciente y la contraseña de la llave de cada certificado activo. El archivo exportado se vuelve a importar sin cambios.
- La importación anterior, que mezclaba las hojas EMPRESAS y CONTRASEÑAS y rellenaba giro, REPSE y trabajadores, se retiró: la spec sólo importa contraseñas.

### Lectura y validación de FIEL/CSD (fase 3)

- `app/sat_certificates.py` lee el `.cer` (DER o PEM) con la librería X.509 de `cryptography`, porque no hay en Python un equivalente mantenido de phpcfdi/credentials. Saca el titular (`name`/CN), el RFC (x500UniqueIdentifier 2.5.4.45, «RFC empresa / RFC representante» en morales), la CURP (serialNumber 2.5.4.5), el número de certificado (los 20 dígitos ASCII del número de serie), la vigencia, el emisor, la clase (un CSD trae OU, que es la sucursal, y un uso de llave sin acuerdo de llave ni cifrado de datos) y la huella SHA-256. Abre el `.key` PKCS#8 cifrado con su contraseña y comprueba que la llave pública sea la misma, con una prueba de firmar y verificar.
- Hay seis comprobaciones: certificado del SAT, contraseña, par `.cer`/`.key`, clase, RFC (empresa o CSD = RFC de la empresa; representante = persona física de 13 caracteres, que coincida con el que trae la FIEL de la empresa) y vigencia. Las cinco primeras bloquean. Un certificado vencido se guarda sólo como historial.
- Endpoints: `POST /api/credentials/companies/{cid}/certificates/check` (no guarda nada) y `/certificates/upload` (sólo administradores, con la bóveda desbloqueada). La subida guarda cifrados el `.cer`, el `.key` y la contraseña de la llave. Reemplazar la FIEL activa pide `replace`. Si había un certificado «Faltan .cer y .key» de esa clase, recibe los archivos.
- La subida suelta de archivos `POST /secrets/{id}/files` responde 410, y los boletos `sat_fiel` responden 422. Ninguna ruta entrega el `.cer` ni el `.key`.
- `app/vault_fiel.py: obtener_fiel_para_acceso(db, p, company_id)` (alias `obtenerFielParaAcceso`) es un servicio interno para Declara, no una ruta HTTP. Con la bóveda desbloqueada en la sesión devuelve `cer`, `key`, `password` y `rfc` de la FIEL activa de la empresa, y registra USO_DECLARA en la bitácora. Lanza `VaultLocked` o `FielUnavailable`.
- Las pruebas usan certificados sintéticos con la forma de los del SAT (`backend/tests/sat_fixtures.py`). Falta probar con varias FIEL y CSD reales del despacho, de morales y de físicas.

### Antes de la fase 1

- AES-256-GCM mediante `cryptography`, ya presente. Nonce aleatorio de 96 bits por escritura; empresa, ID de credencial, contexto y versión de clave se autentican como AAD.
- La base conserva ciphertext, nonce, algoritmo y versión; no contiene claves de cifrado.
- El proveedor de referencia recibe `CONTA_VAULT_KEYRING` y `CONTA_VAULT_ACTIVE_KEY` exclusivamente del entorno del proceso provisionado externamente. Nunca escribirlos en `.env`, repositorio o configuración versionada. No se generaron ni instalaron claves reales. Antes de producción se requiere un gestor de secretos/servicio de claves con política de acceso, respaldos y recuperación.
- Configuración ausente/inválida o verificación criptográfica fallida bloquean la operación con error genérico. No se devuelve la causa interna ni material criptográfico.
- Los envelopes incluyen versión para permitir lectura de versiones anteriores con un keyring rotado. No hay trabajo automático de recifrado; el operador deberá planificarlo y conservar claves antiguas hasta completar migración y respaldos.
- Las consultas generales excluyen ciphertext, nonces, usuarios fiscales y secretos. La UI muestra máscara constante; el secreto sólo vive transitoriamente en el campo password y se borra tras guardar, error o cierre. No se usa almacenamiento web, URL ni portapapeles.
- Creación/modificación requieren sesión personal y permisos backend. Administra una cuenta nominal; la clave inicial de instalación no puede escribir secretos.
- El administrador puede gestionar metadatos y concesiones, pero no hereda permiso de revelación. Aun con concesión explícita, la ruta de revelación devuelve 423: no hay adaptador de reautenticación reciente habilitado.
- El descifrado interno requiere callback de autorización reciente suministrado por código confiable. No existe parámetro HTTP que lo active. Las pruebas usan callbacks y claves ficticios. No habilitarlo usando un booleano enviado por el navegador.
- Historial registra consulta de metadatos/historial, creación, cambios, archivo, revelación bloqueada y concesiones. Las denegaciones HTTP conservan la auditoría de seguridad existente. No se guardan valores anteriores/nuevos de secretos en auditoría; sólo en versiones cifradas.
- Todas las respuestas de la familia API, incluidos errores de autenticación/validación, llevan `Cache-Control: no-store, private` y `Pragma: no-cache`. Se reutiliza la redacción existente de errores de validación, que excluye inputs.
- Ningún cambio relaja CSRF, cookies, autenticación o aislamiento existentes. No hay API para consultar versiones cifradas ni referencias KEY.

Permisos preparados: metadata, create, modify, reveal, certificates, history, alerts y permissions. Los colaboradores requieren concesión específica además del acceso existente a la empresa. Administración de permisos y configuración/conciliación global de alertas se mantienen exclusivas de administradores, aunque existan permisos reservados para futuras delegaciones.

## Endpoints

Prefijo `/api/credentials`:

- `GET /companies/{id}`: catálogo, metadatos enmascarados, certificados, capacidades y umbrales. Audita consulta.
- `POST /companies/{id}/secrets`: crea; `?ident={id}` actualiza con revisión esperada, sin devolver secreto. Las etiquetas públicas se fijan como «Acceso» para evitar registrar secretos accidentalmente como títulos.
- `DELETE /companies/{id}/secrets/{id}?revision=N`: archivo lógico, con control concurrente.
- `POST /companies/{id}/secrets/{id}/reveal`: bloqueado; permiso explícito no sustituye reautenticación.
- `POST /companies/{id}/certificates`: asociación manual a CER público ya vinculado a la empresa, o registro pendiente sin documento.
- `PUT /companies/{id}/certificates/{id}`: cambia tipo declarado/notas y fecha de revisión con control de versión; auditado sin valores sensibles.
- `GET /companies/{id}/history`: últimos cien eventos autorizados.
- `PUT /companies/{id}/permissions`: concesión/revocación específica por administrador; exige acceso vigente del destinatario a la empresa.
- `POST /services`: alta administrativa de servicio configurable.
- `GET /alerts`: alertas persistidas filtradas por acceso, máximo mil filas; requiere conciliación manual para actualizar.
- `POST /alerts/refresh`: conciliación administrativa local explícita, sin red ni tareas automáticas.
- `PUT /alerts/settings`: umbrales de certificados entre 1 y 365 días, auditados.

## Certificados y documentos

El analizador acepta únicamente CER público DER/PEM hasta 1 MB, usando X.509. Extrae serial, sujeto, huella SHA-256 y fechas UTC. El tipo FIEL/CSD es declarado manualmente: nunca se deduce del nombre. Si hay RFC reconocible y no corresponde a la empresa, se rechaza la asociación. Sin RFC en el CER, la asociación documental manual no prueba identidad ni autenticidad: requiere revisión humana.

Se usa el lector existente de CS-Storage sólo ante la solicitud explícita de asociar un documento CER registrado. Se verifica su relación con la empresa antes de leerlo. No se modifican ubicaciones ni originales. PDF/acuse conservan sus referencias en el expediente existente; un modelo ampliado de respaldos por certificado queda pendiente.

No se abren, procesan, copian ni descargan KEY. El localizador de referencias privadas queda reservado para un adaptador seguro futuro, sin endpoint público ni acceso al motor SMB. No se amplía la lista de formatos de CS-Storage.

Los días restantes usan `America/Mexico_City`; inicio/fin se comparan como instantes UTC. La expiración no se redondea al día siguiente. `tzdata==2026.6` se añadió porque Windows carecía de la base IANA para `zoneinfo`; no se usa un desplazamiento fijo que pierda reglas históricas. Vigencia temporal no acredita cadena, revocación ni validación SAT. Los umbrales son configurables y seleccionan el nivel más próximo aplicable.

## Centro de Alertas

Dos fuentes locales: certificados registrados y registros persistidos de Control de Obligaciones. Los IDs se derivan de fuente/referencia/tipo con SHA-256. Conciliar otra vez actualiza la misma alerta y conserva fecha de generación; las condiciones desaparecidas quedan resueltas. No se ejecuta un planificador automático.

Obligaciones: pendiente de revisión, fecha verificada próxima (15 días), vencida con fecha verificada y cumplida sin evidencia documental registrada (aviso de revisión documental, no incumplimiento legal). No se crean obligaciones ni se infiere vencimiento de blancos. Las celdas aún inexistentes no generan alertas masivas. Si la migración fiscal no existe, se informa fuente no disponible y se conservan las funciones de certificados.

Los registros históricos de certificados pueden producir avisos aunque haya una renovación; la selección de certificado operativo/sustituido queda pendiente. Revisar los avisos antes de usarlos como indicador definitivo.

## Interfaz

Pestañas de Empresas: Credenciales y Certificados y Centro de Alertas. El expediente tiene su propia pestaña de credenciales. Se reutilizan componentes/tokens Stitch, formularios, modales, tablas adaptables y navegación. No se cambió Inicio ni Control de Obligaciones.

La vista de credenciales está acotada a la empresa seleccionada, con filtros por régimen/empresa y subsecciones Resumen, Accesos fiscales, FIEL, CSD, IMSS/INFONAVIT, Otros e Historial. Sus seis tarjetas se calculan sobre esa empresa, no sobre todo el despacho. La tabla filtra tipo, estado y fecha límite. Se permite crear/actualizar accesos y registrar referencias CER. Revelar/copiar permanece deshabilitado. La administración visual de permisos, umbrales, servicios y edición avanzada de certificados está pendiente; sus endpoints están preparados.

El Centro de Alertas filtra por empresa, origen, prioridad y estado, con acceso a expedientes. Usa datos persistidos y puede estar vacío antes de conciliar. No contiene cifras de demostración.

## Importación futura

No se abrió `copia de CONTRASEÑAS.xlsx`, no se copió al proyecto y no se ejecutó importación. `credential_import.preview` recibe filas normalizadas de un lector futuro y un mapeo de encabezados. Compara RFC, reporta duplicados/ambigüedades, distingue presencia de secreto/fecha y exige confirmación. No devuelve originales, fórmulas, usuarios, servicios recibidos ni valores sensibles. No persiste ni crea temporales.

Pendiente: lector XLSX con límites, validación de fechas originales sin confiar en fórmulas, interfaz administrativa de coincidencias y ejecución transaccional confirmada que cifre cada secreto antes de escribir. No existe endpoint de importación definitiva ni vista previa de contraseñas reales.

## Pruebas y activación pendiente

Comprobación final ampliada: **26 pruebas aprobadas**, incluyendo el módulo nuevo, Control de Obligaciones y el dashboard documental existente. TypeScript `--noEmit` aprobado. Se conserva una advertencia deprecada de Starlette/AnyIO; no hubo fallos.

Pruebas aisladas de credenciales más Obligaciones: 14 aprobadas, con advertencia previa de Starlette/AnyIO. Incluyen cifrado/descifrado autorizado, AAD de empresa/registro, lectura tras rotación, bloqueo por claves ausentes, secretos redactados, headers no-cache, autorización, revelación bloqueada aun con permiso, versiones, archivo lógico, CER sintéticos, duplicados documentales, zona horaria, deduplicación de alertas y fechas de obligaciones verificadas. DDL PostgreSQL generado sin conectarse a un servidor. TypeScript se verifica sin emitir archivos.

No se compiló frontend, no se desplegó, no se ejecutó ninguna migración real ni se cambiaron `.env`, datos empresariales, cuentas o configuración SMB. El código no aparecerá en la entrega compilada abierta actualmente.

Para activar posteriormente: aprobar migración y ensayo de restauración, provisionar claves desde un gestor externo, validar backups cifrados/recuperación/rotación y permisos mínimos, integrar reautenticación con sesión y límite temporal/rate limiting antes de habilitar reveal, revisar logging/proxy/telemetría de infraestructura, probar PostgreSQL real y hacer QA visual/accesibilidad. Después se requerirá autorización para compilar y desplegar. No presentar esta iteración como bóveda productiva certificada.
