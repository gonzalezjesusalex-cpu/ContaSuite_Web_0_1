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
2. Migración `0008` (`user_company_actions`), catálogo en `backend/app/permissions.py`, `Principal.can()/require()` en servidor y sustitución de los controles operativos; pruebas negativas de escalada. Pendientes de conectar: `recopila/cfdi/declara/recibos.usar` (punto 2b, con `created_by`), `carpeta.analizar` (Bloque 4) y `documentos.clasificar` (la decisión de clasificación sigue en la revisión global del administrador).
3. Gestión de usuarios: contador crea auxiliares con plantillas; último administrador; deshabilitados.
4. Migración `0009`: `Audit` con actor, valor anterior y nuevo en todos los cambios de empresa.
5. Responsable por `id` de usuario: `Company.accountant_id`, respaldo del texto, grant `write`, decisión sobre el acceso del anterior, conciliación en revisión humana.
6. Historial de responsable en el expediente.
7. Frontend: selector, pastilla, filtros por usuario y «Mis empresas», pantalla de usuarios y plantillas, visibilidad por permiso.
