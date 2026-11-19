# Bloque 2 — Roles, permisos y contador responsable

Decisiones aprobadas por el usuario el 14/11/2026 (Apéndice A.1 de [PROMPT_MAESTRO.md](PROMPT_MAESTRO.md)). Complementa el Bloque 2 de ese documento; no lo sustituye.

## Roles

| Rol | Alcance |
| --- | --- |
| `admin` | Permisos totales. No puede ser responsable de una empresa. |
| `contador` | Todas las acciones del catálogo en las empresas donde tiene escritura. Crea auxiliares en esas empresas sin darles más de lo que él tiene. |
| `auxiliar` | Sólo las acciones concedidas por empresa (plantillas o selección fina). |

## Catálogo de acciones (por empresa)

| Módulo | Acciones | Plantillas del auxiliar |
| --- | --- | --- |
| Empresa | `empresa.ver`, `empresa.editar`, `empresa.archivar` | Todas: `empresa.ver` |
| Documentos y expediente | `documentos.ver`, `documentos.subir` (incluye la constancia), `documentos.clasificar`, `documentos.eliminar` | Captura: ver y subir |
| Obligaciones y control fiscal | `obligaciones.ver`, `obligaciones.editar`, `obligaciones.verificar`, `calendario.gestionar` | Apoyo fiscal: ver y editar |
| Tareas | `tareas.ver`, `tareas.editar` | Captura y Apoyo fiscal: editar |
| Automatización | `recopila.usar`, `cfdi.usar`, `declara.usar`, `recibos.usar` | Apoyo fiscal: las cuatro |
| Agente | `carpeta.analizar`, `carpeta.exportar` | No se conceden por plantilla |
| Datos personales | `trabajadores.ver` («Ver expedientes de trabajadores (datos personales)») | No se concede por plantilla |
| Historial | `historial.ver` | Todas |

Plantillas: «Solo consulta», «Captura de documentos», «Apoyo fiscal».

Aplicación en servidor (punto 2):

- Las acciones `.ver` las da cualquier permiso de la empresa (lectura o escritura), como hasta ahora; el auxiliar es de solo lectura más sus acciones puntuales.
- Contador: todas las acciones en empresas con escritura; sólo las `.ver` en las de lectura.
- Auxiliar sin acciones registradas en esa empresa (cuentas migradas): conserva lo que permitía su permiso de escritura antes de los roles (subir documentos, tareas, obligaciones y fechas del calendario).
- Empresa visible sin la acción: 403; empresa fuera de sus permisos: 404.

## Expedientes de trabajadores (`trabajadores.ver`)

Los archivos del grupo Trabajadores (identificaciones, seguridad social) son datos personales. Cualquier acceso de lectura concede `documentos.ver`, pero **no** esta acción:

- El administrador la tiene siempre. El contador con escritura en la empresa la tiene como el resto del catálogo. Un auxiliar sólo la recibe si se le asigna de forma explícita (no está en ninguna plantilla ni en el permiso de escritura heredado). Un contador no puede conceder a un auxiliar una acción que él no tiene.
- Sin ella, en el índice virtual (`/api/companies/{id}/virtual-index/…`): `files` y `tree` excluyen la sección `trabajadores`, `summary` no la cuenta (ni sus faltantes ni copias) y `files/{id}/content` responde 403 para esos archivos.
- Sin ella, el resultado del análisis que entrega `GET /api/companies/{id}/jobs/latest` no trae la sección `trabajadores`; su grupo del resumen conserva sólo el conteo, sin ejemplos ni subgrupos, y la lista simple de archivos omite lo clasificado como trabajadores. La interfaz oculta la pestaña «Trabajadores» del inventario.
- No requiere migración: las acciones se guardan como texto en `user_company_actions`.

## Resultados de los trabajos

`GET /api/state` devuelve los 50 trabajos más recientes con un resumen pequeño del resultado (error, progreso y cancelación de la descarga del SAT, bandera de recorrido incompleto o truncado, avisos, resumen de la copia interna y el número de archivos clasificados), nunca el resultado completo. El resultado completo de un trabajo se pide a `GET /api/companies/{company_id}/jobs/latest?kind=scan_folder|export_virtual|sat_declaraciones[&status=queued|running|completed|failed]`: devuelve el último trabajo de ese tipo de la empresa (o `null`), con la misma visibilidad que `/api/state` (empresa fuera del alcance: 404; el `payload`, que lleva rutas, sólo para administradores). La interfaz lo vuelve a pedir al cambiar el estado del trabajo en `/api/state` y con el evento `contasuite-data-changed`.

**Sólo administrador:** configuración, respaldos, rutas autorizadas y revocación de agentes, migraciones, importadores de cartera, catálogo fiscal, revisión global de clasificación, configuración del emisor de Recibos, alta de contadores y cambio de roles, asignación de responsable.

## Respuestas a las preguntas abiertas

1. **Alta de empresas por un contador:** permitida; el contador recibe escritura automáticamente, pero no queda como responsable (lo asigna el administrador).
2. **«Sus empresas»:** para operar, las empresas donde el contador tiene escritura; para Credenciales, sólo aquellas de las que es responsable.
3. **Revelar secretos (`reveal`):** se mantiene el permiso explícito, también para el administrador; ser responsable no lo concede.
4. **Permisos actuales de credenciales:** derivados del rol (responsable o administrador); la tabla actual queda sólo para `reveal`.
5. **Ejecuciones de Recopila, CFDI y Recibos sin empresa:** se registra quién las crea (`created_by`); un no administrador ve sólo las suyas o las de sus empresas.
6. **Cuentas no administradoras existentes al migrar:** pasan a `auxiliar` conservando su acceso de lectura o escritura.
7. **Historial para el auxiliar:** incluido en las tres plantillas.

## Puntos de implementación (un commit cada uno)

1. Migración `0007`: `UserAccount.role` (con respaldo), cuentas y sesión con rol.
2. Migración `0008` (`user_company_actions`), catálogo en `backend/app/permissions.py`, `Principal.can()/require()` en servidor y sustitución de los controles operativos; pruebas negativas de escalada. Pendientes de conectar: `carpeta.analizar` (Bloque 4) y `documentos.clasificar` (la decisión de clasificación sigue en la revisión global del administrador).
2b. Migración `0009` (`created_by` en ejecuciones de Recopila, CFDI y Declara y en recibos) y acceso por `recopila/cfdi/declara/recibos.usar` (`backend/app/run_access.py`): el módulo se abre con la acción en al menos una empresa; se ven las ejecuciones propias y las de empresas con la acción; las anteriores sin empresa ni autor, sólo el administrador. En Recibos, la configuración del emisor y borrar clientes siguen siendo del administrador.
3. Gestión de usuarios (`/api/auth/users`, `/api/auth/catalog`):
   - El administrador gestiona todas las cuentas; el contador, sólo auxiliares que compartan alguna de sus empresas con escritura, y sólo ve y cambia los permisos de esas empresas (los demás se conservan).
   - El contador sólo crea auxiliares, con al menos una de sus empresas, y no concede acciones que él no tenga.
   - Nombre, estado y contraseña de un auxiliar que también trabaja en empresas ajenas sólo los cambia el administrador.
   - Los auxiliares nuevos o editados guardan siempre acciones explícitas (lectura = ninguna; escritura sin elegir = el alcance anterior a los roles). Cambiar a otro rol borra sus acciones.
   - Sigue vigente: no se quita el último administrador; un usuario deshabilitado pierde sus sesiones. Ocultarlo al asignar responsable va con el punto 5.
4. Migración `0010`: `audit_events.actor_id` y `changes` (`{campo: {before, after}}`). Registran autor las altas y ediciones de empresa, tareas, obligaciones y documentos, el archivado, las solicitudes de análisis (el agente como `agent:<id>`) y lo que generan Recopila, CFDI, Declara y Recibos (autor de la ejecución). La ruta de carpeta sólo deja constancia de que cambió. Las filas anteriores quedan sin autor. Credenciales, control fiscal y almacenamiento ya tenían su propio historial con actor.
5. Responsable por `id` de usuario (migración `0011`, `backend/app/responsible.py`, rutas `/api/responsible/...`, sólo administrador):
   - `companies.accountant_id` (sin llave foránea: se valida en la aplicación) y `accountant_legacy`, copia del texto libre anterior. `accountant` pasa a ser el nombre mostrado del responsable.
   - Sólo un contador activo puede ser responsable; `candidates` no lista deshabilitados. Asignar crea o amplía su permiso de escritura y lo avisa.
   - Cambiar o retirar exige `previous_access` (`keep`, `read`, `remove`) para el responsable anterior; nada se quita por omisión. Un cambio concurrente da 409.
   - Conciliación: `reconciliation` propone coincidencias por nombre exacto (`match`, `ambiguous`, `none`), `reconciliation/apply` aplica sólo las confirmadas y `reconciliation/retire` retira el texto anterior cuando el administrador lo confirma.
   - Con responsable asignado, el texto ya no se edita desde los datos de la empresa. Un contador que es responsable no puede cambiar de rol hasta reasignar sus empresas.
   - Credenciales: administrador y contador responsable tienen todos los permisos salvo `reveal`, que sigue exigiendo permiso explícito. Los permisos explícitos de credenciales de otras cuentas dejan de aplicar, salvo `reveal`.
   - Todo cambio queda en el historial con autor, valor anterior y nuevo.
6. Historial en el expediente: `GET /api/companies/{id}/history` (acción `historial.ver`, es decir, cualquier permiso de la empresa) con autor (o «(inactivo)»), fecha, acción y valores anterior y nuevo; vista «Historial» de la sección Actividad (`CompanyHistory.tsx`), ahora visible para todos los roles, no sólo el administrador.
7. Frontend:
   - `frontend/src/permissions.ts` (`can`, `canAnywhere`): menús, rutas y botones según las acciones que devuelve el servidor (`current_user.actions`), no según `admin`. Siguen siendo de administrador: Analizar carpeta (hasta el Bloque 4), importadores, conector de almacenamiento, revisión global y auditoría.
   - Responsable: selector con búsqueda de contadores activos («Ana Pérez · ana», «Sin asignar») en el formulario de empresa y en el diálogo del expediente (sólo administrador), con la pregunta sobre el acceso del anterior; pastilla «Responsable» con «(inactivo)»; `/api/state` incluye `responsibles`.
   - Directorio: filtro por responsable (`responsible`: todos, «Mis empresas» para contadores, «Sin responsable» por vínculo vacío, o un usuario). El tablero integral filtra por el nombre del responsable asignado y marca «sin responsable» por vínculo vacío.
   - Configuración › Cuentas: roles, plantillas y acciones personalizadas por empresa para auxiliares; el contador ve «Auxiliares de mis empresas». Conciliación de contadores para el administrador.
