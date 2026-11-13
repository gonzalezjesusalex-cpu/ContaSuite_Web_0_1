# Importación autorizada — primera carpeta

El usuario solicitó expresamente importar la empresa de la carpeta ya analizada para consultar el Dashboard y Empresas. Esta autorización posterior sustituye la parada previa de análisis. Se ejecutó un operador local controlado; no se afirma que se haya pulsado una confirmación en el asistente web masivo, que conserva su lectura de análisis.

## Resultado anonimizado

- Empresas registradas: **1**. Identidad obtenida del contenido documental: coincidencia única con 11.250 declaraciones; no se eligió sólo por el nombre de carpeta. El RFC aprobado se conserva únicamente en configuración privada.
- Documentos incorporados al catálogo: **25271**, con **25271 versiones**.
- Documentos asociados inequívocamente a la empresa: **10017**. Los restantes permanecen disponibles para revisión administrativa, sin atribuirles propiedad fiscal automáticamente.
- Excluidos: **18** (17 formatos inválidos y 1 archivo superior al límite). Se conservan en la vista del análisis; no se borraron originales.
- Obligaciones y registros fiscales creados: **0**. Cumplimiento verificado: **0**. No se seleccionaron certificados actuales ni se alteraron pagos.

Los originales siguen en su carpeta: CS-Storage registra versiones, huellas y referencias de sólo lectura; no se movieron ni se copiaron íntegramente a la base. Cada contenido incorporado se contrastó por SHA-256 con el análisis autorizado. La segunda carpeta no se importó. No se accedió a SMB/SAT, ni a la base antigua del puerto 8000, ni se desplegó al despacho.

## Integración y controles

Se reutilizaron StorageService, el proveedor local protegido, revisiones, identidad UUID y auditoría existentes. Checkpoints por bloques de 20 permiten continuar sin repetir documentos. La importación se pausó y reanudó; se conserva una versión por documento en este primer ingreso. Los conflictos UUID quedan sujetos a revisión, sin fusiones por UUID o contenido. Se corrigió conservadoramente cualquier propuesta temprana no CFDI que contuviera varios RFC, preservando la revisión anterior como supersedida.

El Dashboard rechazaba más de 5.000 documentos. Se elevó su límite explícito a 50.000, manteniendo los conteos completos; listas visibles limitadas a 100 alertas y 200 incidencias, con sus totales y consulta paginada en Documentos. Este ajuste cubre el volumen actual; no sustituye una futura optimización SQL/paginación integral para mayores volúmenes. La ficha empresarial conserva régimen/actividad pendientes de revisión, sin inventar valores fiscales.

## Validación

- Dashboard, Directorio, catálogo y consulta documental por empresa: HTTP **200**, primero durante la carga y después con los **25.271 documentos**.
- Regresiones sintéticas afectadas: **23 aprobadas** (integral, identidad y lotes). La suite general de 198 aprobadas/1 omitida corresponde al estado previo; no se presenta como repetida tras esta intervención.
- TypeScript sin emisión y build Vite aprobados; advertencia de chunk >500 KB conservada.
- Origen local comprobado disponible mediante el servicio existente, sólo lectura.
- Dump posterior restaurado en una base NUEVA del clúster privado, sin sobrescribir origen: conteos de empresas, documentos, versiones, vínculos, registros fiscales y obligaciones iguales. SHA-256 del dump: **7da43ad7910e1ebb2abed383b39a8d92f30248bd05c3dda1fc6fcc08276ab3aa**. No se afirma una comparación de todos los campos de todas las tablas de esa restauración; el control actual es conteos + hash del artefacto + restauración exitosa.
- No se tomaron capturas con datos fiscales reales. La validación visual completa privada sigue pendiente; se comprobaron contratos HTTP y compilación, no aceptación visual exhaustiva.

## Acceso

Dashboard: http://127.0.0.1:8062/empresas?tab=Dashboard%20general

Directorio: http://127.0.0.1:8062/empresas?tab=Directorio

También se puede utilizar ABRIR_PILOTO_PRIMERA_CARPETA.cmd. Credenciales: archivo local protegido .qa/pilot-first/access.json. No adjuntar ese archivo, private.json, dumps ni metadatos empresariales a terceros. Para una pestaña que estaba abierta antes de la importación, actualizar datos o recargar.

La vista por lotes muestra ahora el número realmente incorporado. Los documentos asociados y los pendientes se consultan en Documentos y en el expediente. El indicador del último escaneo del indexador estándar puede continuar sin fecha: esta operación está auditada como importación piloto, no como un trabajo de ese indexador.

## Recuperación y límites

Antes de la operación se conservó after-analysis.dump, ya restaurado durante la fase anterior; antes del análisis también existe before-analysis.dump. El nuevo after-authorized-import.dump permanece privado bajo .qa/pilot-first, con configuración y ACL locales. No compartirlo como parte de una entrega de código.

Fuentes previas modificadas: before.zip/baseline.json en RESPALDOS/CS_PILOT_IMPORT_AUTORIZADA_20261112. Los scripts nuevos se enumeran en el inventario. Para revertir, preservar cambios posteriores, comparar los hashes y recuperar sólo las fuentes necesarias; recompilar el frontend con las dependencias existentes. El respaldo de esta intervención no contiene el build inmediatamente anterior como conjunto; no se debe prometer recuperar ese build sin recompilar. No restaurar el Dashboard de límite 5.000 sobre esta base de 25.271 documentos. Para volver a datos anteriores, restaurar el dump elegido en otra base y configurar explícitamente una conexión privada compatible, conservando el origen y el historial; no restaurar sobre producción.

No se habilitó importación definitiva XLSX ni de otras carpetas. Lote 5 y aceptación operativa de v1.0 siguen pendientes; este resultado no acredita SCM, TLS/LAN, instalación en Windows limpio ni validación SAT.
