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
| Agente | `carpeta.analizar` | No se concede por plantilla |
| Historial | `historial.ver` | Todas |

Plantillas: «Solo consulta», «Captura de documentos», «Apoyo fiscal».

Aplicación en servidor (punto 2):

- Las acciones `.ver` las da cualquier permiso de la empresa (lectura o escritura), como hasta ahora; el auxiliar es de solo lectura más sus acciones puntuales.
- Contador: todas las acciones en empresas con escritura; sólo las `.ver` en las de lectura.
- Auxiliar sin acciones registradas en esa empresa (cuentas migradas): conserva lo que permitía su permiso de escritura antes de los roles (subir documentos, tareas, obligaciones y fechas del calendario).
- Empresa visible sin la acción: 403; empresa fuera de sus permisos: 404.

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
6. Historial de responsable en el expediente.
7. Frontend: selector, pastilla, filtros por usuario y «Mis empresas», pantalla de usuarios y plantillas, visibilidad por permiso.
