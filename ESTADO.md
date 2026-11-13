# Estado de ContaSuite Web

Actualizado: 13/11/2026. Versión `1.0.0-rc.1`. **v1.0 no está aprobada**: falta la aceptación en el equipo definitivo (Prioridad 5 de [PLAN_FINALIZACION.md](PLAN_FINALIZACION.md)).

## Instancias conocidas

Datos tomados de los informes de cada iteración; no se abrió su configuración privada. Ninguna se toca sin autorización explícita del usuario.

| Puerto | Instancia | Base | Datos / configuración | Estado |
|---:|---|---|---|---|
| 8000 | Instalación antigua (visita/v0.x) | Base antigua, esquema incompatible con RC1 | `.env` y `data/` de esta carpeta | Congelada. No iniciar ni migrar. Decisión pendiente (plan, punto 28). |
| 8062 | Piloto «primera carpeta» | PostgreSQL privado, clúster bajo `.qa/pilot-first` | `.qa/pilot-first` (incluye `access.json`, `private.json`, dumps) | 1 empresa, 25.271 documentos importados; 18 excluidos; conflictos UUID y asociaciones ambiguas en revisión. Segunda carpeta **no** importada. |
| 8072 | Instalación local de pruebas (instalador RC1) | PostgreSQL privado `contasuite_local_*` | Carpeta de instalación `Pruebas-20261112-174658` (fuera de este repositorio) | Agente conectado. Importación PRISMA **pausada** (new=1197, duplicates=3); no reanudar sin instrucción. |
| 8060 | Piloto sintético | `contasuite_pilot_synthetic_001` | `.qa/` | Sólo datos generados. |
| 8056 / 8044 | Laboratorios de recuperación y v0.4 | Clústeres sintéticos | `.qa/` | Históricos; sólo datos ficticios. |

## Módulos vigentes

- **Inicio**: logo, saludo por hora, nombre configurado en su línea, «Bienvenido a ContaSuite» / «Tu espacio de trabajo contable.».
- **Empresas**: catálogo, expedientes, dashboard integral (primera pestaña), tareas, obligaciones, documentos, credenciales/certificados públicos, importar y conciliar. El módulo experimental de Empresas de escritorio no se integra.
- **CS-Storage**: núcleo documental, Centro Documental, indexador con lease/checkpoint, clasificación con revisión humana, fuentes locales y SMB (UNC de sólo lectura con la identidad Windows; ver `docs/SMB.md`).
- **Cuentas**: alta del primer administrador con `APP_TOKEN` (después deja de servir), scrypt, sesiones HttpOnly con CSRF, expiración por inactividad, HTTPS fuera de loopback. Colaboradores con lectura/escritura por empresa; Recopila, CFDI, Declara, Recibos, agentes, revisión global y administración requieren administrador.
- **Recopila, CFDI (antes Organizador), Declara, Recibos**: motores originales integrados por adaptadores web; trabajan con copias subidas, nunca modifican originales.
- **Importador**: XLSX con diagnósticos; confirmación definitiva de Excel real bloqueada.
- **Imprime**: descartado; no se muestra ni se integra.

## Lo que NO está activo

Conexión/descarga SAT automática, OCR, validación fiscal externa, revelación de secretos de credenciales, custodia de llaves privadas FIEL. Las fechas de un CER público no validan autenticidad ni revocación. La presencia de documentos no acredita cumplimiento.

## Validación más reciente

- Backend: 216 aprobadas, 1 omitida (privilegio de enlaces simbólicos en Windows) — 13/11/2026, suite aislada sin `.env` real.
- Frontend: compilación TypeScript/Vite correcta en RC1 (12/11/2026); advertencia de chunk principal >500 KB. En este equipo falta Node.js para repetirla.
- Rendimiento RC1 del dashboard con 25.271 documentos: ~2,5 s y 92 consultas (plan, punto 5).

## Pendientes

Ver [PLAN_FINALIZACION.md](PLAN_FINALIZACION.md). Resumen:

1. Defectos: `/api/state` sin límite, crecimiento de `SecurityEvent`, trabajos del agente atascados, doble ruta del agente, dashboard lento, puertos incoherentes.
2. Orden: separar datos del código, migraciones unificadas, lanzadores.
3. Calidad: formato, linters, bundle, pruebas frontend, dependencias.
4. Infraestructura y aceptación: SCM, HTTPS/LAN, respaldo externo programado, decisión sobre la base 8000, aceptación con usuarios.

Los informes de iteraciones anteriores están en `docs/historico/` (sólo consulta).
