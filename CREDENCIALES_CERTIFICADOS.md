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
