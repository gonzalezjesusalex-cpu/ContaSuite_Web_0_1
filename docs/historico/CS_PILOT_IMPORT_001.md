# CS-PILOT-IMPORT-001 — preparación y ensayo sintético

12/11/2026. Se continuó ContaSuite_Web_0_1 y se probó el flujo en la aplicación existente. **No se han leído ni importado carpetas empresariales reales.** Falta recibir las dos rutas y autorización expresa de análisis. La confirmación definitiva posterior corresponde al usuario dentro de ContaSuite. No se declara v1.0 aprobada.

## Inspección y respaldo

Se revisaron AGENTS.md, CONTINUAR_EN_CODEX.md, CS_RELEASE_CLOSURE.md, Empresas/importador, modelos y contratos de CS-Storage, proveedor local, clasificador aislado, identidad UUID, permisos, historial y migraciones. El arranque ordinario conserva la comprobación de compatibilidad; no ejecuta migraciones. La confirmación antigua de XLSX/inventario continúa bloqueada.

Antes de editar se verificaron 357 archivos en `../RESPALDOS/CS_PILOT_IMPORT_20261111_180638/before.zip`, SHA-256 **a7d7dbb6c19a47009d0962addcd3cf00b64720369012daa6e4f7d77b5bca8abb**. baseline.json contiene cada huella; final.json, changes.json y pilot.diff documentan el resultado. Inventario exacto: CS_PILOT_IMPORT_001_FILES.md. El respaldo excluye configuración, datos, dependencias y secretos. Se preservaron los módulos estables y el paquete de release anterior; no se generó otro instalador.

## Flujo integrado

Empresas → Importar y conciliar → Fuente → **Desde carpeta local · importar empresas**. El componente muestra “Importar empresas” y mantiene los controles, tarjetas, temas y modal compartidos de Stitch.

1. Un administrador con sesión personal elige las dos carpetas previamente autorizadas en el servidor. No se acepta una ruta arbitraria desde el navegador ni se utiliza un selector que prometa acceso al disco del servidor. Las opciones no exploran contenido. Antes del análisis se exige autorizar expresamente la lectura.
2. Inventario recursivo de nombre/ruta, cantidad/tamaño, extensiones, subcarpetas, exclusiones, incidencias y documentos admitidos. Exclusiones obligatorias para KEY, contenedores privados, contraseñas/credenciales/secretos, respaldos y archivos de entorno; se pueden agregar exclusiones, no quitar las obligatorias. Sólo se abre contenido XML, PDF y CER público. UNC, unidades de red mapeadas, enlaces/reparse points, rutas relativas y carpetas superpuestas se rechazan. El proveedor valida los handles de Windows.
3. XML CFDI con Emisor/Receptor y nombres declarados; PDF con texto mediante proceso aislado, limitado por memoria y tiempo; sugerencias conservadoras de constancia, opinión, acuse, declaración o factura por contenido; CER público validado como contenedor X.509, sin validación SAT. Sin OCR, autenticación de CFDI ni inferencia de vigencia SAT. Los nombres de carpeta nunca seleccionan una empresa automáticamente.
4. Vista previa persistente sobre reconcile_sessions/reconcile_rows existentes. Identidades empresariales vacías hasta revisión expresa; candidatos muestran RFC/fuente. Se editan RFC, razón social, clasificación, inclusión y roles empresariales independientes. Razón social existente se conserva al asociar por RFC. Cada cambio conserva actor, fecha, revisión, motivo y antes/después en la auditoría privada; no se registra texto documental en logs.
5. Un modal exige confirmación explícita. La API vuelve a contrastar inventario y SHA-256 antes de escribir. Una transacción utiliza los servicios de CS-Storage sin commits independientes: si un archivo cambia o falla una operación, se revierten empresas/orígenes/documentos del intento. Se serializan identidad documental y RFC normalizado con los mismos bloqueos de los escritores existentes. El mismo intento confirmado responde idempotentemente; repetir el análisis no duplica empresas, documentos ni versiones por origen/ruta sin cambio.
6. Conflictos por UUID entre archivos nuevos o contra el catálogo permanecen en la revisión documental existente. Se registran primero todos los participantes antes de resolver propuestas no conflictivas. No se fusionan documentos por UUID, nombre, RFC o periodo. Contenido idéntico en ubicaciones distintas conserva documentos independientes y se informa como duplicado; puede vincularse a las dos empresas por Emisor/Receptor. Las correcciones de reimportación agregan revisión, conservan instantáneas/decisiones anteriores y no borran verificaciones.
7. Resultados enlazan a expedientes y Documentos. Se pueden retomar los últimos diez análisis propios. Errores de extracción/formato quedan en las incidencias del análisis, sin crear documentos fiscales ficticios; la bandeja documental contiene los documentos efectivamente registrados que necesitan revisión. Las empresas archivadas bloquean la importación; no se reactivan automáticamente.

No se cambian obligaciones, pagos, cumplimiento declarado/verificado ni selección de certificado actual. Tampoco se activa programación de indexación al importar: los orígenes piloto quedan manuales. Las APIs requieren administrador personal, CSRF y autenticación existentes; respuestas piloto llevan no-store/private. El importador antiguo no puede editar, eliminar o purgar las sesiones piloto, incluidas las confirmadas.

## Aislamiento y configuración

Se creó **contasuite_pilot_synthetic_001**, exclusiva del ensayo, dentro del clúster PostgreSQL sintético ya identificado. Antes de operar se verificó SHOW data_directory contra la ubicación exacta de laboratorio; PostgreSQL escucha sólo 127.0.0.1. No se reutilizó una base empresarial ni se hicieron migraciones sobre bases reales.

La API piloto está deshabilitada por defecto. Exige simultáneamente:

- CS_PILOT_ENABLED=1.
- CS_PILOT_DATABASE igual al nombre real de conexión PostgreSQL local, comenzando por contasuite_pilot_. Una conexión SQLite, remota o con nombre diferente se rechaza.
- CS_PILOT_ROOTS con exactamente dos rutas locales explícitamente autorizadas. Para consultar posteriormente los contenidos mediante CS-Storage, CS_STORAGE_ALLOWED_ROOTS debe autorizar también esas raíces; no se habilita el disco completo.
- Esquema vigente instalado por operador mediante schema_admin explícito, nunca por iniciar la aplicación.

No se preparó una migración nueva: se reutilizan las tablas de conciliación, Empresas, Documentos, versiones, vínculos, revisiones, identidad y auditoría existentes. El laboratorio aplicó explícitamente las migraciones existentes a su base vacía y verificó un respaldo anterior a cualquier importación.

Límites configurables: CS_PILOT_MAX_FILES (predeterminado 200, máximo 1.000), CS_PILOT_MAX_MB (100, máximo 500) y CS_PILOT_MAX_SECONDS (90, máximo 300). Cada archivo mantiene 25 MB como límite; cada raíz tiene un límite adicional de 5.000 entradas. El límite temporal se verifica entre operaciones; una extracción individual puede consumir hasta ocho segundos. Alcanzar un límite aborta el análisis, sin ofrecer una vista parcial como importable. Cambios entre análisis y confirmación exigen volver a analizar. Cambiar exclusiones no amplía silenciosamente un origen ya registrado más restrictivo.

La configuración del ensayo vive únicamente bajo `.qa/pilot-import/lab`, sin .env real, raíces SMB, llaves o credenciales reales. Los scripts pilot_lab/pilot_http/pilot_http_final/pilot_restore son exclusivamente sintéticos: no deben adaptarse sustituyendo sus fixtures por carpetas reales. Para la fase real se debe crear otro entorno piloto vacío y respaldado, con cuentas y rutas autorizadas, sin mezclar los fixtures.

## Resultados anonimizados del ensayo

| Concepto | Resultado sintético |
|---|---:|
| Empresas elegidas tras revisión (P-01 / P-02) | 2 |
| Archivos físicos generados, incluidos excluidos | 11 |
| Archivos inventariados no excluidos | 8 |
| Contenidos analizados | 7 |
| XML CFDI / PDF / CER público | 4 / 2 / 1 |
| Contenidos clasificados / ilegibles | 6 / 1 |
| Archivo de formato no admitido (sin abrir) | 1 |
| Entradas excluidas (incluye directorio) | 3 |
| Documentos registrados / versiones | 6 / 6 |
| Documentos con vínculos confirmados / conflicto pendiente | 4 / 2 |
| Documentos iniciales con contenido compartido idéntico | 2 |
| Vínculos empresariales finales | 6 |
| Obligaciones/registros fiscales creados | 0 / 0 |
| Errores de permisos de lectura del SO simulados | 0; no se afirma haber ensayado ACL denegada real |

El PDF ilegible no se importó. Al reimportar, seis contenidos ya están presentes en el catálogo: el indicador incluye contenido previamente registrado, no seis documentos nuevos ni fusiones. Los originales sintéticos conservaron sus SHA-256; no se movieron, renombraron ni escribieron. No hay cifras de carpetas reales porque no se accedió a ellas.

## Validaciones ejecutadas en esta tarea

| Prueba | Resultado |
|---|---|
| Suite backend general | 193 aprobadas, 1 omitida, 161 advertencias; antes de las últimas correcciones específicas |
| Suite afectada final: piloto + identidad + importador previo | 37 aprobadas, 27 advertencias; incluye 14 específicas del piloto; solapa la suite general |
| HTTP inicial PostgreSQL | 40 comprobaciones aprobadas: autenticación/CSRF, permisos, preview, decisiones, confirmación, reimportación y exclusión del importador anterior |
| HTTP final PostgreSQL | 15 comprobaciones aprobadas; confirmaciones simultáneas: 1 commit y 1 respuesta idempotente; documentos/versiones/revisiones/vínculos y huellas permanecieron iguales |
| Cambio de archivo / fallo intermedio | Pruebas sintéticas aprobadas: rechazo antes de guardar o rollback completo |
| Archivado y bloqueo fuera del piloto | Aprobados; no reactivación automática y rechazo de base no autorizada |
| TypeScript sin emisión / compilación Vite | Aprobados tras cambios finales; advertencia de chunk principal >500 KB |
| Navegador sobre la aplicación | Acceso, selector de dos carpetas, análisis, revisión empresarial/roles, guardado, modal y confirmación sintética observados; capturas reales en qa-pilot |
| Restauración | Respaldos anterior y posterior restaurados en dos bases sintéticas nuevas, sin reemplazar origen; comparación de conteos de todas las tablas y contenido de filas documentales/auditoría aprobada |

Las advertencias incluyen reflexión SQLite del índice de expresión preexistente y una deprecación de Starlette/AnyIO. La omitida corresponde a privilegios de enlaces simbólicos. La primera tentativa con Python privado no encontró app durante colección; posteriormente se usó el entorno de desarrollo con importación explícita. Nueve errores iniciales de fixtures de las pruebas nuevas fueron corregidos antes de las 37 aprobadas. Una ejecución restringida fue interrumpida sin resultado; no se cuenta como aprobada. La revisión automática de aprobación falló temporalmente por límite de uso; al reanudar pudo completarse y las pruebas se ejecutaron. No se deshabilitaron protecciones.

QA visual detectó superposición de selectores, corregida con estilos limitados al piloto. El guardado y modal se comprobaron. La prueba de cancelación de borrador mediante diálogo nativo del navegador no pudo confirmarse de forma fiable por la automatización; la guarda compartida permanece integrada. No se declara auditoría completa de accesibilidad, todos los temas/resoluciones ni fidelidad píxel a píxel.

## Respaldos piloto y recuperación

- before-import.dump, SHA-256 **4c68561e9ab63c1600b89d84d07936ebdb7b532f6de56e629906f0f557f5cb84**: esquema preparado, anterior a la importación.
- after-import.dump, SHA-256 **e8d6ee6877f74a05ee5217b59ba5be4a3366a44eebc6650613a0418a701babff**: instantánea posterior a QA visual, con historial.
- Ambos están bajo `.qa/pilot-import/lab`; se restauraron en contasuite_pilot_empty_restore_001 y contasuite_pilot_restore_001. Las tablas y filas se contrastaron con esa instantánea. Una reimportación final posterior sólo agregó sesiones/auditoría de ensayo, sin cambiar documentos/revisiones. Resultados anonimizados y hashes se conservan junto al respaldo de fuentes, en results.

Para revertir código, detener únicamente la API piloto, conservar cambios posteriores y comparar con final.json. Extraer desde before.zip sólo los archivos modificados verificando baseline.json; conservar aparte los añadidos antes de retirarlos. Recuperar también el build previo como conjunto, sin mezclar assets entre compilaciones. No superponer nada sobre .env, data, bases o agent/config.json.

Para recuperar el piloto, detener sus escritores y restaurar el dump elegido en una base NUEVA; verificar conteos, filas, esquema y raíces antes de cambiar exclusivamente la conexión piloto. No borrar historial ni restaurar encima de producción. Como los documentos se referencian externamente sin modificar sus bytes, verificar también sus huellas y permisos de acceso. Los dumps sintéticos no son respaldos empresariales.

## Pendientes y siguiente autorización

Se detiene aquí la fase sintética. Faltan las dos rutas de copias locales reales y autorización expresa para analizarlas. Después se debe mostrar la vista previa real al usuario; su importación definitiva requerirá confirmación dentro de ContaSuite. No autoriza importar al proporcionar únicamente una ruta.

Reconocimiento pendiente: OCR de escaneos, identificación conservadora de razón social en PDFs, variantes documentales y CER complejos. Opiniones/constancias son sugerencias por texto, nunca confirmación de situación fiscal. Pendientes operativos de v1.0 —SCM, TLS/LAN y aceptación global— se conservan. No hubo acceso SMB/SAT, despliegue, modificación de infraestructura real, lectura de secretos empresariales ni inicio del Lote 5.
