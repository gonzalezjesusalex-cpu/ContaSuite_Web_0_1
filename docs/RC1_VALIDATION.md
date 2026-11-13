# RC1 — resultados y límites de verificación

Fecha: 12 de noviembre de 2026. Candidata para pruebas; no aprobación de producción.

## Código integrado

Se conservaron los cambios recientes del importador/piloto, motores, migraciones, permisos y diseño Stitch. El paquete se genera desde el repositorio actual con lista permitida, Python privado y manifiesto SHA-256, no desde el ZIP anterior. Excluye .env, .qa, data, dumps, configuración del agente y documentos empresariales.

Cambios RC1: servicio con trabajadores de alertas e indexación y detención coordinada; bloqueo de instancia por directorio de datos; puerto predeterminado 8062; configuración DPAPI de máquina; consulta administrativa del servicio; acceso directo opcional HTTPS; herramientas de verificación/restauración en destinos nuevos; mantenimiento con retención y estado persistente; redirección HTTP y guía de CA interna. Dashboard lee identificadores y evita consultas individuales para comprobar clasificación vigente, con vistas previas limitadas y totales explícitos.

## Pruebas ejecutadas

- Suite completa aislada: 202 aprobadas, 1 omitida, 168 advertencias de reflexión SQLite sobre índice de expresión. La prueba omitida corresponde al privilegio Windows de enlaces simbólicos; no se modificaron pruebas para ocultar fallos.
- Regresiones tras optimización: 27 aprobadas, 176 no seleccionadas. Segunda suite completa sobre cambios finales de comportamiento: 202 aprobadas, 1 omitida en 150,76 s. Posteriormente sólo se actualizaron identificadores de versión visibles y documentación.
- TypeScript y Vite: compilación correcta; advertencia de bundle principal mayor de 500 KB, sin desactivar controles.
- DPAPI Windows: cifrado/descifrado correcto con secreto sintético, sin credenciales reales.
- Paquete intermedio RC1: instalación en carpeta nueva, runtime aislado sin Python en PATH, servicio oculto con secuencia START_PENDING/RUNNING/STOP_PENDING/STOPPED, cierre de ambos trabajadores, rechazo de esquema vacío sin migración, autenticación, rechazo de Host ajeno, respaldo/restauración PostgreSQL, actualización versionada y retiro conservando datos. Ensayo scripts/release_package_test.py, run-id rc1a. Las correcciones posteriores se ensayan con otro identificador; no se equipara este ensayo intermedio a una prueba del SCM registrado.
- Restauración nueva: la herramienta restore_postgres.py verificó manifiesto y restauró una base nueva sin sobrescribir existentes. El ensayo final incluye archivo sintético para verificar también recuperación de bytes.
- Segundo ensayo de paquete, rc1b: configuración DPAPI cargada por el ejecutor, segunda instancia con el mismo directorio rechazada aun usando otro puerto, ambos trabajadores cerrados, restauración con dos archivos verificados, instalación/actualización/retiro aprobados. El paquete de entrega se regenera con la identificación de versión RC1 y esta documentación, y se vuelve a ensayar antes de entregarlo.

## Rendimiento medido

Base PostgreSQL exclusiva, creada tras verificar la ruta del clúster sintético. 25.271 filas documentales: 10.017 asociadas y 15.254 sin asociación. No se copiaron documentos reales ni conflictos UUID del piloto. Tres lecturas del dashboard tras limitar vistas previas: 2.502,06 / 2.476,20 / 2.221,63 ms; mediana 2.476,20 ms; 92 consultas por lectura; 68.344 bytes JSON. Primera medición antes de limitar vistas previas: 6.331.064 bytes. Mediciones con otras pruebas ejecutándose: no implican mejora de latencia ni SLA. Los cambios reducen volumen de respuesta, no prueban escalabilidad ilimitada.

No se midieron vista previa PDF remota, descargas SMB reales, concurrencia multi-PC ni volumen de versiones/conflictos real. Sigue existiendo límite explícito de 50.000 documentos por resumen; para crecimiento adicional se requiere agregación/paginación completa del resumen. El Centro Documental conserva su paginación existente. La aceptación de rendimiento del despacho continúa pendiente.

## Limitaciones reales pendientes

1. Registro/control SCM, recuperación tras caída y arranque tras reiniciar Windows en el servidor definitivo. Los ensayos sin consola no equivalen a SCM. No se intentó registrar un servicio en esta tarea.
2. Certificado, DNS, Nginx instalado, firewall autorizado y prueba HTTPS desde otra PC. Se entrega plantilla y procedimiento; no se cambiaron red ni certificados.
3. Identidad Windows con acceso efectivo SMB, destino externo de respaldo y tarea programada bajo esa identidad. El ejecutor de mantenimiento está preparado, pero no se detuvo un servicio real ni se ejecutó retención remota. Avisos mediante monitorización del resultado/estado; no hay correo automático incorporado.
4. Configuración privada y secretos deben reprovisionarse para recuperación en otra PC: DPAPI de máquina no es portable. El respaldo conjunto cubre base/data, no una copia de todos los secretos del sistema ni documentos SMB.
5. Migración real del piloto, segunda carpeta y aceptación con usuarios del despacho requieren intervención autorizada; no se ejecutaron.
6. Integración automática SAT, OCR y validación fiscal externa siguen pendientes como antes. La presencia de documentos no acredita cumplimiento ni pago.

La instalación autorizada debe seguir INSTALL_RC1.md y completar la aceptación en el equipo definitivo. Ningún resultado sintético permite declarar ContaSuite aprobada para producción.
