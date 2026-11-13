> Actualización posterior: la empresa de la primera carpeta ya fue importada por instrucción expresa del usuario. Consultar CS_PILOT_IMPORTACION_PRIMERA.md; lo siguiente se conserva como antecedente.

# Primera carpeta autorizada — análisis completo, importación pendiente

Se utilizó exclusivamente la primera carpeta del directorio autorizado por el usuario. Se trata su contenido como sensible, aunque se haya denominado carpeta de prueba. No se analizó el contenido de la segunda carpeta en esta ejecución. No se modificaron originales, bases anteriores, .env, agent/config.json, SMB/SAT ni infraestructura del despacho.

## Resultado anonimizado

| Concepto | Cantidad |
|---|---:|
| Documentos admitidos inventariados P-01 | 25289 |
| Documentos procesados | 25289 |
| Clasificados por contenido (sugerencias) | 11953 |
| Sin clasificación reconocida | 13318 |
| Errores de lectura/extracción/formato | 18 |
| Documentos con contenido duplicado | 877 |
| Documentos con conflicto de UUID | 1717 |
| Empresas creadas / documentos importados definitivamente | 0 / 0 |

Tipos sugeridos: {"acknowledgement": 241, "other": 302, "cfdi": 11250, "unknown": 13336, "declaration": 150, "certificate": 10}. Duplicados y conflictos son indicadores que pueden solaparse; no deben sumarse como archivos adicionales. Todos los RFC/nombres detectados son candidatos, incluidas contrapartes: no se seleccionó una empresa por nombre de carpeta ni por frecuencia. Clasificar no verifica cumplimiento fiscal ni autenticidad SAT. PDF escaneado/OCR y documentos complejos siguen sujetos a revisión.

Errores por código: {"file_too_large": 1, "invalid_format": 17}. El archivo sin huella superó el límite de tamaño y no se abrió su contenido. El filtro de tipo desconocido incluye tanto documentos sin clasificación reconocida como los que tienen error de formato.

## Integridad

Huellas SHA-256 contrastadas de nuevo: 25288. Cambios de contenido detectados: 0. Archivos no disponibles: 0. Errores sin huella: 1. Archivos nuevos/faltantes al repetir el inventario: 0 / 0. Incidencias del recorrido final: 0. Sólo se leyeron PDF/XML/CER admitidos; KEY, credenciales, contenedores privados, secretos y respaldos permanecieron excluidos. Los archivos demasiado grandes o no interpretables no se presentan como verificados.

## Implementación y privacidad

Se reutilizan reconcile_sessions/reconcile_rows/reconcile_history como staging; no hay un catálogo fiscal paralelo. Inventario persistente, checkpoints cada 100 registros, reanudación comprobada tras detener un trabajador identificado y bloqueo PostgreSQL exclusivo para impedir ejecuciones simultáneas. El extractor corre en un proceso limitado a 384 MB, se recicla cada 100 extracciones y tiene timeout por operación. La caché distingue huella y extensión; no se fusionan documentos por contenido ni UUID. La detección global de duplicados/conflictos incluye todos los lotes.

Se creó un clúster PostgreSQL privado y una base exclusiva, con ACL limitada al usuario y SYSTEM, escucha loopback y una cuenta personal nueva de la aplicación. Autenticación, autorización, CSRF y auditoría existentes siguen activas. La vista previa requiere administrador personal y está paginada (50 por defecto, máximo 100); las respuestas no se almacenan en caché. No se tomaron capturas empresariales ni se publicaron RFC, nombres, UUID, archivos o credenciales en el informe compartible.

Se comprobó por HTTP: acceso anónimo 401, página sobredimensionada 422, confirmación mediante importador anterior 404 y Host no autorizado 400. La importación definitiva masiva permanece deshabilitada: esta tarea deja análisis y revisión, no empresas creadas ni documentos vinculados. Hace falta implementar/validar la fase de revisión y confirmación masiva antes de habilitarla; no debe usarse una confirmación del importador pequeño para saltar este límite.

La pantalla permite filtrar conflictos UUID, duplicados, errores y tipo desconocido, con totales y paginación calculados en backend. Los filtros se comprobaron contra PostgreSQL privado publicando únicamente sus conteos.

## Pruebas y respaldos

- 30 pruebas sintéticas del lote/piloto/importador aprobadas; 14 dirigidas de alcance e identidad aprobadas (se solapan).
- Suite backend completa: 198 aprobadas, 1 omitida, 169 advertencias. La omisión es por privilegios de enlaces; advertencias de reflexión SQLite/deprecación conservadas.
- Después se repitieron las 4 pruebas dirigidas del módulo para los últimos filtros; no se presenta la suite completa como repetida tras ese ajuste.
- TypeScript sin emisión y build Vite aprobados; permanece advertencia de chunk >500 KB.
- La primera ejecución dirigida detectó un problema de codificación al editar un archivo: se restauró UTF-8 desde el respaldo y se repitieron las pruebas correctamente.
- Respaldo de esquema vacío anterior a la lectura documental restaurado en una base nueva. Respaldo de vista previa final también restaurado en otra base nueva; 25289 filas de staging y sus contenidos/auditoría contrastados por SHA-256, sin sobrescribir el origen. SHA del dump final: 9a11fa1f7552a5ab17863b4b450faeb601c665e1853bc020730bb406dc7d1664.
- No se considera ejecutada QA visual con datos reales: deliberadamente se evita su captura. La nueva pantalla fue comprobada por tipos/build y contratos HTTP; aceptación visual privada pendiente.

El respaldo de fuentes está en `CS_PILOT_BATCH_20261112_153604` bajo RESPALDOS, con before.zip, baseline.json, final.json, changes.json y diff. Inventario exacto: CS_PILOT_BATCH_FILES.md. Se conservan los resultados anonimizados junto al respaldo. Los archivos operativos privados y dumps están bajo .qa/pilot-first: **no adjuntarlos a Claude ni a entregas compartidas**.

## Acceso y recuperación

Usar ABRIR_PILOTO_PRIMERA_CARPETA.cmd o http://127.0.0.1:8062. Entrar con la cuenta del archivo local protegido .qa/pilot-first/access.json (no incluido en este informe). Empresas → Importar y conciliar → Fuente → Primera carpeta · análisis por lotes. El puerto 8000 y el piloto sintético 8060 son entornos diferentes.

Para revertir código, detener exclusivamente los procesos del piloto, comparar final.json y preservar cambios posteriores; recuperar los modificados desde before.zip y conservar los añadidos antes de retirarlos. Recuperar el build anterior como conjunto. No superponer carpetas sobre datos o configuración. Para recuperar el staging, restaurar el dump en una base NUEVA y verificar huellas, conteos y conexión antes de usarla; no restaurar sobre producción ni eliminar historial.

Lote 5 no iniciado. ContaSuite v1.0 continúa sin aprobación operativa; permanecen las validaciones de SCM, TLS/LAN, Windows limpio, accesibilidad y aceptación integral.
