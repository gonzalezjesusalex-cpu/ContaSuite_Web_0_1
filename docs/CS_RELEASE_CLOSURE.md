# CS-RELEASE-CLOSURE-001 — cierre técnico parcial, operación pendiente

11/11/2026. Se continuó ContaSuite_Web_0_1 sin reconstruir módulos. Se entregan correcciones documentales, fundamentos visuales contrastados con Stitch y paquete Windows con runtime privado. **No se declara ContaSuite v1.0 terminada:** faltan SCM registrado/reinicio real, TLS/LAN desde otro cliente y aceptación visual/accesibilidad integral.

## Inspección, respaldo y cambios conservados

Se leyeron informes e inventarios de recuperación y Lotes 1–4/matrices, AGENTS y CONTINUAR. Se verificaron modelos de documentos/versiones/vínculos/revisiones, historial fiscal, APIs, migraciones y empaquetado anterior. Antes de editar se creó `../RESPALDOS/CS_RELEASE_CLOSURE_20261111_225752/before.zip`: **370 archivos**, SHA-256 **0d048382133ad1e1379028bd6a0c1d7ec7090570fd1d18ef12290f34687d8a5b**, cada entrada contrastada con baseline.json. El ZIP contiene fuentes, pruebas, documentación y build previo; excluye datos/configuración/secrets/dependencias.

Inventario final exacto: CS_RELEASE_CLOSURE_FILES.md; hashes previos/posteriores y diff en la carpeta del respaldo. Se conservaron los cambios previos y el contrato fiscal canónico; sólo se añadió suspensión de lectura/verificación por conflicto de identidad y control de acceso de Host. No se cambió el escritor fiscal, permisos, cifrado/revelación, importador definitivo ni archivos originales de diseño. Ningún acceso a SMB/SAT, base/documento empresarial, contraseña real o KEY. Los archivos y credenciales usados son sintéticos.

## Conciliación documental

Nueva metadata aditiva `document_cfdi_identities`, por versión exacta, con UUID normalizado, SHA-256, condición de conflicto y referencia a revisión/actor/fecha de resolución. Reutiliza Document, DocumentVersion, DocumentCompanyLink y DocumentClassificationReview, no crea documentos/evidencias paralelos. `integral_0003_document_identity` depende de integral_0002; coordinador schema_admin la aplica sólo por comando explícito. El arranque no migra. No hay downgrade destructivo ni lectura de documentos durante migración.

- Un TimbreFiscalDigital único con UUID sintáctico se registra como dato declarado; no es validación SAT/XSD/firma. Timbres múltiples o UUID inválido generan revisión. Mismo UUID con bytes distintos dispara conflicto en todas las versiones actuales afectadas. La comparación SHA es conservadora: diferencias de formato también requieren revisión, no se presumen equivalentes.
- Carga interna y observación autorizada de XML detectan identidad dentro de su transacción antes de clasificar o verificar. No se fusiona por nombre, RFC, periodo ni UUID. Mismos bytes/UUID pueden conservarse como documentos independientes y figurar como duplicados de contenido.
- Cambio de UUID entre versiones conserva versiones anteriores y exige revisión; no extiende vínculos automáticos viejos a contenido nuevo. Resolución sólo mediante las operaciones autorizadas existentes; motivo obligatorio para conflictos. Guarda actor/fecha, vínculos previos/elegidos y razón en la revisión histórica, además de eventos de detección.
- Global advisory lock PostgreSQL serializa detección/resolución/verificación documental; CAS de versión/revisión protege escrituras. Las condiciones idénticas no duplican detecciones ni reabren una decisión humana. Nuevos participantes o contenido cambian la condición y requieren otra revisión. Es un bloqueo deliberadamente conservador; rendimiento sostenido pendiente.
- Verificación fiscal queda suspendida por conflicto sin cambiar fulfilled/pago ni borrar decisiones. Resolver clasificación no recupera por sí solo la verificación: se exige nueva lectura/hash y decisión fiscal posterior. Clasificación virtual no puede cerrar ni sustituir la revisión de identidad.
- Documentos XML históricos sin identidad registrada no se presentan como verificación vigente hasta su análisis autorizado. No hay barrido automático ni backfill de contenido real. Documentos no XML y sus límites de interpretación siguen conservados.

Centro Documental incorpora bandeja paginada sobre las revisiones existentes, filtrable por contexto empresarial, sólo administrativa. Permisos se aplican en backend; los lectores no ven la bandeja global ni metadatos de otras empresas. El editor muestra motivo/conflicto, vínculos independientes y decisión humana; comparte guardas de borrador. Asociar no confirma cumplimiento fiscal.

## Stitch y accesibilidad

Se encontró `design_references/stitch_contasuite_enterprise_fiscal_platform (2).zip`, con 12 code.html, 12 screen.png y un DESIGN.md. Se inspeccionaron y extrajeron a .qa sólo para comparación; no se ejecutaron HTML ni recursos CDN. Manifiesto SHA por referencia conservado con resultados.

| Referencia | Pantalla funcional / tratamiento |
|---|---|
| inicio_contasuite | Inicio: saludo/nombre/logo/textos existentes conservados |
| empresas_centro_de_control_fiscal | Empresas: jerarquía, cabecera, sidebar, tarjetas/pestañas/tablas; datos y secciones reales conservados |
| expediente_distribuidora_baj_o | Expediente: estructura existente y controles compartidos; comparación completa pendiente |
| registro_de_empresas_contasuite | Formulario empresarial existente; controles compartidos, comparación completa pendiente |
| tareas_y_vencimientos_contasuite | Tareas existente; fundamento visual conservado, comparación completa pendiente |
| recopilador_cfdi_contasuite / organizador_cfdi_contasuite / generador_de_recibos_contasuite | Recopila / CFDI / Recibos existentes; iconos/recursos y motores preservados |
| configuraci_n_del_sistema_contasuite | Preferencias y temas existentes, sin estados ficticios |
| relacionador_documental_contasuite / renombrador_de_cotizaciones_contasuite | Referencias conservadas; no se convierten maquetas en motores nuevos |
| centro_de_impresi_n_contasuite | Excluido por instrucción del proyecto; no se reactiva |

No hay referencia dedicada para Declara, login, conciliación nueva, calendario, alertas o gestión de certificados. Se usan los componentes/tokens disponibles, sin inventar fidelidad específica. Se priorizó el HTML de la pantalla: sus radios lg=8/xl=12 difieren del bloque narrativo de DESIGN.md. Se consolidaron Inter, paleta #f8f9ff/#213145/#004ac6, tipografía de cabecera 30/38, botones/inputs, tarjetas, foco, pestañas y editor contextual. Se conservan oscuro/alto contraste y reduced-motion; no se copiaron métricas ficticias ni “SAT conectado”.

Se añadió nombre accesible a dialog y enlace para saltar al contenido. Comparación visual observada de Inicio/Empresas, bandeja, revisión y editor; modal con nombre accesible y Escape comprobados. Capturas reales en docs/qa-release. Se comprobó además el salto de teclado al main, claro/oscuro/alto contraste y editor móvil de 375 px útiles sin scroll horizontal (entrada de 271 px, una columna). No se certifica coincidencia de píxeles ni accesibilidad completa por estas comprobaciones; pendientes lector de pantalla, contraste exhaustivo, todos los flujos/temas y aprobación humana.

## Windows, instalación y LAN

El paquete amplía el mecanismo anterior mediante allowlist; incluye CPython 3.12 privado, DLL/stdlib, las 43 distribuciones probadas y sus metadatos/licencias, código y frontend compilado. `_pth` aísla entorno/registro/user site; no copia .venv/configuración. Instalador verifica manifiesto, usa su Python y crea carpetas versionadas sin pisar una instalación. Update exige escritores detenidos y respaldo suministrado/restaurado. Uninstall retira reversiblemente el código por renombrado, conserva datos/base/configuración y no quita servicios automáticamente. PostgreSQL debe aprovisionarse por separado.

Servicio nativo preparado con StartServiceCtrlDispatcherW/RegisterServiceCtrlHandlerExW, estados SCM, readiness, detención/drenaje, logs rotativos y salida de error. Plan de registro explícito: autoarranque, cuenta virtual de privilegios mínimos y recuperación 15/30/60 s. **Sonda de creación: WinError 5; ningún servicio registrado o modificado.** Ejecución oculta sin consola comprueba el host y parada por señal interna; no acredita entrega real de controles SCM, recuperación por SCM o arranque tras reboot.

Plantilla HTTPS/LAN sin certificados/llaves incluidas; CS_ALLOWED_HOSTS explícitos, sin comodines, confianza de proxy limitada a loopback, origen/CSRF y seguridad de sesiones conservadas. Host ajeno rechazado 400 y Origin ajeno 403 en HTTP real. PostgreSQL sólo escucha 127.0.0.1. No se modificaron firewall, red, política de PowerShell o servicios reales. Falta certificado válido, proxy disponible y otro cliente autorizado para QA TLS/LAN; la plantilla no se considera TLS operativo.

Guía completa: INSTALL_RELEASE_WINDOWS.md. Fuentes técnicas consultadas: [protocolo de servicio Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/winsvc/nf-winsvc-registerservicectrlhandlerexw), [distribución y aislamiento de Python Windows](https://docs.python.org/3.12/using/windows.html).

## Pruebas de esta tarea

| Prueba | Estado / evidencia actual |
|---|---|
| Pytest completo final | 179 aprobadas, 1 omitida por privilegios de enlaces simbólicos; 142 advertencias de reflexión SQLite de índice de expresión preexistente |
| Regresiones aisladas Lotes 1–4 | 48 aprobadas, red/procesos externos bloqueados |
| Regresión documental dirigida | 18 aprobadas; tras preservar instantáneas/propuestas antiguas y añadir reapertura explícita se aprobaron 10 de identidad y 2 del controlador/plan Windows. Hay solapamiento con la suite general |
| Lógica frontend / clasificador | 8 / 7 aprobadas |
| TypeScript sin emisión y build Vite | Aprobados; chunk principal >500 kB, advertencia de rendimiento |
| HTTP inicial | 33 comprobaciones y rechazo de Host no permitido |
| HTTP final de carga/identidad/permisos | 10 comprobaciones aprobadas; identidad antes de clasificación y cola sin duplicación virtual |
| PostgreSQL | Base nueva, migración explícita, dump/restauración, archivos SHA, actualización sintética previa y concurrencia aprobados |
| Concurrencia real | 2 contenidos UUID contradictorios quedan pendientes; 6 verificaciones producen 1 decisión nueva/5 idempotentes; 8 evaluadores producen 1 ejecución/7 not_due |
| Navegador | Login, Inicio/Empresas, conflicto, corrección empresarial guardada, modal con nombre/Escape y editor contextual observados |
| Servicio registrado SCM/reboot | Bloqueado: acceso de creación denegado WinError 5; no se elevan privilegios ni alteran servicios |
| Instalador/runtime privado y host oculto | Aprobado en el primer paquete y repetición del ZIP definitivo contrastada por SHA en package-results-final.json: Python incluido con PATH sin Python, instalación/update/retiro reversible, host oculto/parada, fallo sin migración y respaldo/restauración |
| TLS/LAN real/otro equipo | No ejecutado: sin certificado/cliente/red autorizados; ningún certificado inseguro utilizado |

Estas son ejecuciones de cierre; no se suman como nuevas las cifras históricas de recuperación. Suite general/aislada/dirigida se solapan. Tentativa dirigida en sandbox dio 5 write_error al crear archivos sintéticos; repetición fuera de esa limitación con los mismos fixtures aprobó. No se relajó seguridad. La primera compilación de una mejora auxiliar tuvo ruta de Python incorrecta; se corrigió y se ejecutó TypeScript/build después.

PostgreSQL: sólo bases nuevas del clúster sintético previamente marcado, contrastando SHOW data_directory. Migración limpia incluyó integral_0003; ensayo de actualización retiró únicamente esa tabla en una copia sintética restaurada para representar el estado previo, conservó historial fiscal y reanalizó/revisó documentos sintéticos antes de nuevas verificaciones. No es un procedimiento para borrar tablas reales. El origen no perdió historial. Escritores detenidos al comparar el respaldo estable; resultados en postgres-results-final.json.

## Matriz final de aceptación

| Criterio | Estado | Pendiente real |
|---|---|---|
| Identidad UUID/contradicción/versionado | Probado en unidad, HTTP y PG | Revisión de XML históricos mediante operación autorizada; no análisis SAT/XSD |
| No fusión / vínculos independientes / historial | Probado | Política empresarial de conservación/conciliación de históricos reales |
| Correcciones y permisos backend | Probado | Aceptación con cuentas/roles del despacho sin usar datos reales en esta tarea |
| Evidencia fiscal separada de asociación | Probado | Aceptación documental final del despacho |
| Stitch componentes y pantallas comparadas | Parcial | Todas las pantallas/resoluciones y aprobación visual humana; referencias dedicadas ausentes identificadas |
| Accesibilidad / movimiento reducido | Parcial | Auditoría completa, lector de pantalla y cancelación de todos los borradores |
| Servicio sin terminal y detención del host | Ensayo aislado disponible | Registro, controles, fallo/reboot y ACL/cuenta virtual bajo SCM real |
| Runtime sin Python manual / instalación / actualización / retiro | Ensayo local aprobado | Validación en otro Windows limpio |
| PostgreSQL, respaldo y recuperación sintéticos | Aprobado en laboratorio | Plan operativo de respaldo/retención/disco/restore del despacho |
| TLS, LAN, firewall mínimo | Preparado, bloqueado de aceptación | Certificado válido, proxy/firewall autorizados y cliente adicional |
| Lotes 1–2 y 4 | Regresionados, aceptación parcial | Matrices previas no se convierten automáticamente en aprobadas |
| Lote 3 | Bloqueos de identidad/historial corregidos y ensayados | Clasificación de todo formato, PDFs/CER complejos, archivo histórico completo y QA global |
| ContaSuite v1.0 operativa | No aprobada | Criterios obligatorios de servicio/red/aceptación pendientes |

## Riesgos y recuperación

Rechazar conserva la cuarentena. Una reapertura administrativa explícita con motivo crea otra revisión, conserva el rechazo anterior y es idempotente; no modifica cumplimiento ni restaura automáticamente la verificación fiscal.

La identificación UUID se limita al XML CFDI con TimbreFiscalDigital; PDFs/archivos no interpretables no se convierten en CFDI verificado. El hash compara bytes, no equivalencia fiscal. No hay asociación dual automática nueva ni fusión irreversible. El bloqueo global simplifica consistencia pero necesita medición bajo carga. Reanálisis histórico debe ser explícito; migración no lee contenidos. No se recuperan verificaciones sobrescritas antes del historial de recuperación.

Antes de revertir, conservar modificaciones posteriores. Comparar cada archivo con final.json; extraer sólo los modificados desde before.zip y verificar baseline.json. Conservar añadidos antes de retirarlos; no superponer carpetas sobre datos/configuración ni eliminar tablas/historial. La compilación anterior está respaldada. No volver a código que ignore conflictos/historial sin revisión de compatibilidad. Para bases sintéticas se conservan dumps y archivos restaurados en .qa; no son respaldo empresarial. Para operación real, seguir instalación versionada y dump+datos restaurados en destino nuevo.

No hubo despliegue en el despacho, migración real, acceso SMB/SAT, lectura de claves privadas/secretos reales ni cambios de red o política de PowerShell. Servicio y LAN no se declaran aprobados por haber preparado scripts.
