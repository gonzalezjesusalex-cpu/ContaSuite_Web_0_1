# ContaSuite v0.3 — Dashboard Integral y Clasificación Documental

## Estado de esta entrega

Código fuente preparado, con migración independiente sin activar. No se compiló, desplegó, importó Excel real ni ejecutó migración real. No se realizaron conexiones/escaneos SMB ni lecturas de documentos del servidor durante el desarrollo. No se modificaron Inicio, Obligaciones, Credenciales, Alertas, Importador ni el proveedor SMB. La integración cambia únicamente navegación de Empresas/expedientes y registro de nuevos endpoints.

La instalación local sigue usando SQLite. SQLAlchemy y las estructuras nuevas admiten PostgreSQL; se comprobó generación DDL, no una instancia PostgreSQL. No se alteró `.env`, datos, usuarios o configuración del agente.

## Diagnóstico y reutilización

Se revisaron AGENTS, continuidad y los documentos de Obligaciones, Credenciales e Importador. Empresas proporciona ID estable/RFC, régimen y responsable. Los nuevos módulos fiscales y bóveda tienen metadata independiente sin activar; CS-Storage aporta documentos, versiones, localizaciones, relaciones y revisiones humanas. No se construyó otro índice, padrón, visor PDF ni bóveda.

Incompatibilidades detectadas y tratadas:

- Empresa no tenía indicador de actividad: la actividad se confirma en tabla complementaria; registrada no equivale a activa. Se muestra actividad desconocida.
- Cumplida no equivale a evidencia verificada: se agregó verificación independiente por revisión de obligación y versión documental. El dashboard no cambia estados fiscales.
- Una fecha de documento no identifica período fiscal: se usan las claves canónicas de Obligaciones, incluyendo sus reglas mensuales/trimestrales/anuales; el nombre de un mes sin año nunca asigna ejercicio.
- No todas las migraciones están disponibles: fuentes fiscales/certificados pendientes se representan como no disponibles y métricas null, no como ceros definitivos. La migración v0.3 sí es requisito para entrar al dashboard nuevo.
- El catálogo de tareas no tiene fecha de ejecución: las tareas completadas se informan como conteo histórico, sin inferir productividad o fecha de realización.
- La existencia de documentos no prueba expediente completo: no se evalúa completitud sin requisitos configurados.

## Dashboard

`integral_dashboard.dashboard` agrega registros autorizados sin modificar módulos. Reutiliza `fiscal_control.matrix`, `credential_api.temporal/allowed`, `credential_alerts.candidates/alert_key`, el ámbito de `DocumentCatalog`, y los modelos de Empresas, tareas, documentos y trabajos.

Filtros: período, empresa, régimen y responsable. Los conteos se calculan después de autorización y filtros. Se muestran empresas registradas, actividad confirmada/desconocida, empresas presentes en el período, estados fiscales, cumplidas con/sin verificación independiente, certificados por vigencia temporal/origen, trabajo por responsable, catálogo documental, fuentes comprobadas, alertas y calidad de datos.

Las categorías NA se muestran separadas, sin incorporarlas a un porcentaje de cumplimiento. Sólo se cuentan obligaciones registradas; las celdas aún inexistentes no se inventan como incumplimientos. El catálogo fiscal completo se lee del módulo existente: nuevos conceptos como Buzón, pago federal u obligaciones anuales deben configurarse por sus servicios existentes, no se insertan silenciosamente al abrir el dashboard.

Las verificaciones de cumplimiento dejan de contar cuando cambia la revisión fiscal, la versión del documento o su asociación a la empresa. Su registro es una revisión interna del despacho, no validación SAT. Asociar evidencia virtual no registra esa verificación.

Certificados: bandas >60, 31–60, 16–30, 0–15, vencido y desconocido. Sólo origen `cs_storage` utiliza fechas como extraídas de CER; otros orígenes quedan sin fecha confiable hasta conciliación. Se respeta permiso específico de metadatos además del ámbito empresarial. No se consultan envelopes, contraseñas ni referencias KEY.

Las alertas del dashboard reutilizan candidatos e IDs del Centro existente y añaden incidencias de calidad por el mismo patrón de identidad. Son una proyección local actual, sin volver a insertar las alertas persistidas del Centro. Se actualizan al consultar/filtrar, recuperar foco o cada 30 segundos mientras la vista está visible. No se ejecuta conciliación de red. El Centro de Alertas anterior conserva sus fuentes persistidas; incorporar las fuentes nuevas a esa pantalla queda como adaptador de integración posterior, sin modificarlo en esta etapa.

La navegación permite ver el registro fiscal exacto en un panel, con ID, revisión y evidencias virtuales disponibles, y abrir expedientes. Los enlaces generales de certificado/calidad llevan al expediente y muestran la referencia; el enfoque automático de un certificado específico en la pantalla anterior queda pendiente.

Diagnóstico documental: separa documentos indexados de disponibilidad del origen. Cero en catálogo no implica servidor accesible ni escaneado. Se informa la fecha del último trabajo completado y comprobaciones guardadas, sin sondear SMB. Los diagnósticos de fuentes/errores globales se restringen a administración. Máximo 5.000 documentos autorizados por consulta del dashboard; si se supera, devuelve 413 y pide acotar filtros, sin presentar conteos parciales como definitivos.

## Clasificación virtual

Dieciséis categorías iniciales: Contabilidad; Obligaciones fiscales; Declaraciones y acuses; Pagos de impuestos; FIEL y CSD; Opiniones de cumplimiento; CFDI; Nómina; IMSS e INFONAVIT; Expediente fiscal; Expediente laboral; Contratos; Documentos administrativos; Estados financieros; Otros; Sin clasificar. Un servicio administrativo permite agregar categorías/reglas. Los términos se interpretan literalmente, sin ejecutar expresiones suministradas por usuarios.

El motor analiza nombres/rutas relativas ya indexados, normaliza acentos y separadores y conserva procedencia de regla/contexto/nombre, candidatos y ambigüedades. Carpeta sugiere confianza 0,35; nombre 0,65. Estas cifras son heurísticas, no probabilidades de verdad. Años contradictorios y múltiples empresas/categorías permanecen para revisión. Reutiliza la conciliación documental y alias del Importador si sus tablas están presentes.

Ninguna propuesta de nombre/carpeta se confirma automáticamente. Se usan las revisiones versionadas existentes `DocumentClassificationReview`; no se duplica una bandeja de propuestas en otra tabla. Repetir análisis conserva la propuesta vigente y decisiones humanas. La reapertura explícita por un administrador crea una revisión nueva y conserva el historial.

Confirmar requiere administrador, versión vigente, empresa/categoría válidas y justificación. Guarda clasificación virtual, etiquetas, ejercicio/período, actor y fecha; conserva identidad documental y vínculos anteriores. Si falta el vínculo con la empresa elegida, se agrega usando `DocumentCompanyLink` existente, sin mover archivos ni quitar otras asociaciones. Los cambios concurrentes se rechazan. Rechazar conserva las asociaciones anteriores.

Los vínculos fiscales exigen empresa y período mensual exactos; anuales/trimestrales quedan pendientes de un conciliador específico. Los vínculos a certificados exigen la misma empresa. Se registran en relaciones complementarias y aparecen como evidencia disponible del dashboard. No se cambia fiscal_records.status ni se copian automáticamente a las evidencias del módulo anterior.

## Análisis de contenido y certificados

`analyze_public` es un contrato offline acotado a 1 MB, sin llamadas automáticas a proveedores:

- XML: reutiliza el clasificador CFDI existente y XML protegido.
- CER: reutiliza el analizador X.509 existente; no infiere FIEL/CSD del nombre.
- XLSX: reutiliza el lector acotado de metadatos del Importador, sin evaluar fórmulas ni devolver columnas sensibles.
- PDF: devuelve pendiente de analizador aislado. La extracción segura por trabajador del sistema existente debe conectarse antes de activarla aquí.
- OCR y KEY: deshabilitados. KEY/PFX/P12/PEM se excluyen de clasificación y endpoints nuevos.

No se conectó un análisis masivo de contenido a la nueva bandeja. Las clasificaciones automáticas basadas en contenido suficiente siguen perteneciendo al clasificador/worker existente; su orquestación con categorías v0.3 queda preparada, sin inventar resultados.

El endpoint explícito de comparación de certificados puede usar el lector autorizado existente sólo para un CER público de la misma empresa. Compara fechas/huella con el registro actual, crea o resuelve una incidencia deduplicada y nunca sobrescribe el certificado. Las pruebas usan CER sintéticos locales. Alta, deduplicación por huella y administración de certificados siguen en sus endpoints anteriores.

## Explorador y visor reutilizado

En cada expediente se agregó Explorador documental con vistas Organizada y Estructura original. Comparten documentos/versiones. La vista organizada agrupa por categoría y permite filtrar ejercicio/período/tipo/estado. La estructura original muestra rutas relativas registradas, con agrupación por carpeta e indentación; no crea carpetas físicas. Está paginado a cien documentos.

Las rutas sólo se revelan a administración mediante consulta explícita auditada. Nunca se devuelven raíces UNC/configuración privada. Los colaboradores reciben documentos autorizados con ruta protegida. Vista previa y descarga abren el componente `Documents` existente: no se creó otro visor. El enfoque directo del documento seleccionado dentro de ese visor queda pendiente; se abre su catálogo de empresa.

La revisión permite categoría, etiquetas, ejercicio, período, obligación/certificado existentes y justificación. Se revisa contra la empresa del expediente; corregir hacia otra empresa puede hacerse mediante la bandeja administrativa existente de CS-Storage o el endpoint autorizado. Historial conserva decisiones sin borrar originales.

## Calidad, opiniones y CFDI

Calidad deriva RFC inválido/faltante, régimen/responsable faltante, posibles nombres duplicados, documentos sin empresa, sin clasificación y compartidos para revisión. Un documento compartido no se declara incorrecto: puede ser legítimo. Incidencias de certificados sólo se muestran a quien tiene permiso de sus metadatos. La procedencia usa tipo/ID de registro, sin rutas/secretos. Los enlaces de corrección llevan a interfaces existentes; no hay eliminación ni corrección automática.

Incidencias de datos históricos incompletos y períodos fiscales malformados requieren un adaptador de diagnóstico adicional. La tabla de calidad está preparada, pero no se ejecuta saneamiento del historial.

Opiniones SAT/IMSS/INFONAVIT: registro manual de autoridad, fecha, resultado, próxima revisión opcional, documento autorizado, responsable y notas. No hay una duración uniforme asumida ni consultas oficiales.

CFDI: registro manual por empresa/período/tipo (emitido/recibido/nómina), fecha de revisión, estado, incidencias y responsable; no deduce cumplimiento de la existencia de XML. Las pantallas iniciales permiten altas simples; edición avanzada y configuración de incidencias quedan pendientes.

## Modelo y endpoints

Tablas nuevas: virtual_categories, virtual_rules, virtual_document_metadata, virtual_evidence_relations, integral_compliance_verification, integral_company_activity, integral_quality_issues, integral_opinions, integral_cfdi_reviews, integral_audit e integral_settings. Las propuestas/asociaciones empresariales reutilizan tablas existentes de CS-Storage. Los índices únicos previenen relaciones duplicadas por versión/objetivo. La configuración de documentos requeridos inicia vacía y no declara incompletitud.

La migración `backend/integral_migrations/001_integral.py` sólo se invoca con conexión explícita aprobada; no se registra en el arranque ni en Alembic de CS-Storage. No requiere aplicar las otras migraciones para crear sus tablas, aunque sus funciones dependientes quedan no disponibles hasta que existan sus fuentes. Downgrade destructivo bloqueado.

Prefijo `/api/integral`:

- GET `/dashboard?year=&month=&company_id=&regime=&responsible=`.
- PUT `/companies/{id}/activity`, confirmación administrativa explícita.
- GET `/companies/{id}/documents?original=&offset=`.
- POST `/classification/analyze`, máximo cincuenta IDs y reapertura explícita opcional.
- GET `/classification/reviews`, bandeja administrativa acotada.
- POST `/classification/documents/{id}/decision`.
- POST `/classification/categories`, catálogo/reglas configurables.
- GET `/documents/{id}/history`.
- POST `/obligations/{id}/verify`, verificación interna independiente y versionada.
- POST `/certificates/{id}/compare`, comparación explícita de CER sin sobrescritura.
- POST `/companies/{id}/opinions` y `/companies/{id}/cfdi`.

Autenticación, CSRF, auditoría de seguridad y headers no-cache son los existentes. Las decisiones de clasificación exigen administración, coherente con la revisión global de CS-Storage. Los indicadores, búsquedas y documentos respetan ámbito por empresa. No se almacenan secretos en evidencia de reglas. Las observaciones humanas deben evitar incluir contraseñas; el sistema no debe usarse como bóveda a través de esos campos.

## Archivos

Nuevos: `backend/app/integral_models.py`, `integral_dashboard.py`, `integral_api.py`, `virtual_classifier.py`; `backend/integral_migrations/001_integral.py`; `backend/tests/test_integral.py`; `frontend/src/modules/IntegralDashboard.tsx`, `VirtualExplorer.tsx`; este documento.

Modificados: `backend/app/main.py` (router), `frontend/src/modules/Companies.tsx` (dashboard general y secciones contextuales, sin duplicar el menú ejecutivo anterior), `frontend/src/modules/Dossier.tsx` (explorador) y `CONTINUAR_EN_CODEX.md`. No se añadieron dependencias.

## Validación y activación

Comprobación ampliada: **48 pruebas aprobadas** sobre v0.3, Importador, Credenciales, Obligaciones y dashboard documental existente; una advertencia deprecada de Starlette/AnyIO. TypeScript sin emitir archivos aprobado. Se verifican períodos/NA, estados registrados frente a verificados, invalidación de evidencias, filtros por responsable, permisos, bandas de certificados y ocultamiento, fuentes faltantes, cero documentos frente a origen no disponible, idempotencia, decisión manual sin cambiar obligaciones, vistas sobre los mismos documentos, rutas protegidas, nombres/ejercicios ambiguos, exclusión KEY y contratos de análisis.

No hubo QA visual en navegador ni pruebas PostgreSQL real. El contrato de comparación CER requiere más escenarios de integración antes de activarlo con documentos del despacho. Los conteos de tareas son históricos. El dashboard requiere actualización para reflejar cambios de otra pantalla; realiza consulta local al recuperar foco/cada treinta segundos, sin asumir eventos externos.

Plan de piloto posterior: aprobar una base aislada nueva; respaldar y ensayar migraciones allí; crear sólo empresas/documentos sintéticos con distintos ejercicios y orígenes disponibles/no disponibles; contrastar manualmente indicadores, permisos, clasificación y rechazos; verificar que asociación no cambia cumplimiento; revisar visualmente los tres temas y móvil. Sólo después autorizar una muestra real mínima, de lectura, con cuentas y documentos aprobados. No realizar un escaneo general como primera validación. Compilación, migraciones reales y despliegue requieren nueva instrucción.
