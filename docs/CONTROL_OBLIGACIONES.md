# Control de obligaciones v0.1

## Diagnóstico y alcance

Empresas usa `Companies.tsx`, expedientes por `/empresas/:id` y registros anteriores en `Records.tsx`/`obligations`. Estos registros permanecen intactos. Se agregó la pestaña Control de obligaciones y dos vistas con el mismo endpoint. El mes/ejercicio se selecciona en el encabezado existente de Empresas. Inicio, CS-Storage, SMB y sus migraciones no se modificaron.

La sesión existente proporciona permisos por empresa, protección CSRF y usuarios internos. Las empresas se relacionan por ID existente, con RFC para identificación y vista previa de importación; el módulo nunca crea empresas.

La configuración actual es SQLite. SQLAlchemy conserva compatibilidad con PostgreSQL; se validó la generación DDL de su dialecto, no una instancia PostgreSQL real. No se cambió la URL de conexión.

## Modelo y migración preparada

`backend/app/fiscal_control.py` utiliza metadata independiente para impedir que el `create_all` del arranque cree estas tablas sin autorización:

| Tabla | Función |
|---|---|
| fiscal_catalog | Identidad estable, nombre y periodicidad mensual/trimestral/anual |
| fiscal_applicability | Aplicación y responsable predeterminado por empresa/obligación; revisión concurrente |
| fiscal_periods | Períodos canónicos con inicio/fin; AAAA-MM, AAAA-Qn, AAAA-A |
| fiscal_records | Empresa, catálogo y período únicos; estado, responsable, registro/presentación/vencimiento, pago y revisión |
| fiscal_evidence | Vínculo a documento existente y función documental |
| fiscal_history | Actor, fecha, valores anteriores/nuevos; cambios atómicos con el registro |
| fiscal_import_batches | Procedencia, huella, actor, estado y mapeo de importación futura |
| fiscal_import_rows | Hoja/fila, valores originales, propuesta y conflictos |

La migración explícita `backend/fiscal_migrations/001_control_obligaciones.py` crea sólo las nuevas tablas y los once conceptos iniciales. Pago es atributo, no declaración. Los conceptos iniciales se proponen mensuales para el control interno; la periodicidad y fechas legales deben revisarse antes de operar. El catálogo permite nuevos conceptos mensuales, trimestrales o anuales, sin columnas permanentes por concepto.

No está conectada a la cadena automática Alembic de CS-Storage ni se aplica al iniciar. `upgrade(connection)` sólo debe invocarse tras aprobar copia de seguridad y ensayo aislado. No incluye CLI que pueda ejecutarse accidentalmente contra producción. `downgrade` destructivo está deshabilitado. En ausencia de tablas los endpoints responden 503 con explicación, sin crear ni migrar nada. No se ha autorizado ni ejecutado una migración real.

## Endpoints

Todos requieren autenticación existente; lectura limitada a empresas visibles y edición a empresas con escritura. Ningún cuerpo acepta identidades o roles del actor.

- `GET /api/fiscal-control?year=2026&month=11`: matriz compartida, catálogo, empresas visibles, reglas y responsables.
- `PUT /api/fiscal-control/cell`: creación/edición con revisión esperada; duplicados y ediciones concurrentes responden 409.
- `GET /api/fiscal-control/history/{record_id}`: últimos cien cambios, con autorización por empresa.
- `PUT /api/fiscal-control/applicability`: regla por empresa/obligación y responsable predeterminado, con revisión e historial; preparado para administración futura.
- `POST /api/fiscal-control/catalog`: alta administrativa de conceptos extensibles; sin modificación retroactiva de periodicidad.

Dashboard y tabla derivan los indicadores de la misma respuesta persistida, con filtros compartidos. Sin revisar incluye las celdas aún no registradas; no se crean registros al consultar. Las reglas de no aplicación son predeterminados y un registro explícito prevalece. Las métricas cuentan celdas, no certificaciones de autoridad. Los períodos trimestrales/anuales se comparten entre los meses correspondientes.

Vencida es un estado derivado para pendientes/en proceso con fecha límite marcada como verificada y anterior a hoy; no se guarda arbitrariamente ni se deriva de una celda vacía o fecha importada. El usuario puede capturar cumplida sin afirmar validación SAT. El pago se registra por obligación.

Las evidencias se vinculan por ID mediante el panel contextual y deben existir y estar asociadas a la empresa con acceso para la cuenta. No se copian ni abren archivos remotos al asociarlas; se conservan ubicaciones originales. No se cambia el motor SMB. Un selector visual de documentos y vistas de administración de catálogo/aplicabilidad quedan pendientes; los servicios están preparados.

## Importador histórico preparado

`fiscal_import.py` recibe hojas/filas/celdas normalizadas de un lector futuro, detecta mes/año explícitos, mapea encabezados, identifica empresas por RFC o nombre exacto normalizado y reporta ambigüedades. Distingue fechas, NA, texto y blanco; conserva procedencia y originales. Fechas importadas quedan sin revisar y sin validación ante autoridad. Pago requiere asociarse a una obligación. Detecta repeticiones dentro del lote.

Pendiente: lector binario XLSX (no se añadió dependencia), fórmulas/celdas combinadas, resolución interactiva, comparación de propuestas con registros existentes, autorización de sobrescritura e importación transaccional final. No existe endpoint de importación definitiva en esta iteración y no se ejecutó ninguna importación.

## Validación y límites

TypeScript se comprueba con `tsc --noEmit`; no se compiló Vite ni se modificó `frontend/dist`. Pruebas aisladas comprueban guardia de migración, permisos, persistencia, historial, conflicto de revisión, vencimientos verificados, períodos anuales únicos, DDL PostgreSQL y vista previa. No se probó una instancia PostgreSQL, interacción visual en navegador ni infraestructura de producción. El navegador seguirá mostrando la entrega compilada anterior hasta una futura compilación y migración expresamente autorizadas.

No hay automatización SAT, fechas fiscales oficiales precargadas, datos ficticios de cumplimiento ni conversión automática de obligaciones anteriores.

## Archivos de esta iteración

Creados: `backend/app/fiscal_control.py`, `backend/app/fiscal_import.py`, `backend/fiscal_migrations/001_control_obligaciones.py`, `backend/tests/test_fiscal_control.py`, `frontend/src/modules/FiscalControl.tsx`, `frontend/src/modules/fiscal-control.css` y este documento.

Modificados: `backend/app/main.py` (registro del router antes del fallback web), `frontend/src/modules/Companies.tsx` (pestaña adicional) y `CONTINUAR_EN_CODEX.md` (continuidad).
