# Informe · Renovación del Gestor de contraseñas

Spec: «Spec · Gestor de Contraseñas (ContaSuite)», 26/11/2026. Rama `feature/v1.1`, sin push. Detalle técnico en
[CREDENCIALES_CERTIFICADOS.md](CREDENCIALES_CERTIFICADOS.md).

## Fases y commits

| Fase | Commit | Contenido |
| --- | --- | --- |
| 0 | `2805bb3` | Línea base: backend 454 pasadas y 10 omitidas, node 21/21, build en verde |
| 1 | `a573936` | Bóveda con contraseña maestra (Argon2id), código de recuperación, bloqueo y autobloqueo (`cs_0022`) |
| 2 | `a531b1c` | Tipos de contraseña, clases de certificado, permisos de la spec y bitácora con equipo (`cs_0024`) |
| 3 | `9797108` | Lectura del .cer, validación del .key, «Agregar FIEL o CSD» y `obtener_fiel_para_acceso` |
| 4 | `ecc257f` | Importación en 3 pasos, plantilla y exportación con contraseña maestra (`cs_0025`) |
| 5 | `2bf7b37` | Pantallas del lienzo con Stitch v2 y Configuración › Bóveda de contraseñas |
| 6 | (este) | Alertas a 30, 7 y 0 días en la campana; este informe |

`cs_0023_declara_v2` es de la sesión de Declara; la cadena queda `cs_0022 → cs_0023_declara_v2 → cs_0024 → cs_0025`.

## Criterios de aceptación (sección 7)

«Probado» significa con pruebas automatizadas sobre datos sintéticos. «Falta en el despacho» es lo que la spec pide
comprobar en la PC del despacho con datos reales, que no se tocaron (AGENTS.md).

| Criterio | Estado | Evidencia |
| --- | --- | --- |
| Al entrar, la bóveda está bloqueada y no se ve ningún dato de empresas | Probado | `test_vault_master.py::test_vault_starts_locked_and_shows_nothing` (lista, ficha y bitácora responden 423); `e2e/vault.spec.ts` |
| Crear la contraseña maestra genera el código de recuperación y ese código desbloquea | Probado | `test_setup_rules_recovery_code_and_no_plain_text`; `e2e/vault.spec.ts` |
| Se bloquea sola a los 5 min, con «Bloquear ahora», y tras 5 fallos hay que esperar | Probado | `test_auto_lock_after_minutes_without_use_and_logout`, `test_five_failures_wait_five_minutes` |
| En la base no aparece en claro ninguna contraseña, .cer ni .key | Probado / falta en el despacho | Las pruebas vuelcan las tablas y buscan los valores; falta la consulta directa a la base real |
| Las credenciales y certificados actuales se migran sin pérdida | Probado / falta en el despacho | `test_setup_rewraps_the_previous_keyring_in_one_transaction`, `test_migration_fills_types_classes_and_incomplete_certificates`; las instancias 8000, 8062 y 8072 no se migraron |
| Una FIEL real muestra titular, RFC, número y vigencia; un .key o contraseña equivocados impiden guardar | Probado con sintéticos / falta en el despacho | `test_vault_fiel.py` (seis comprobaciones); faltan FIEL y CSD reales de morales y físicas |
| La FIEL del representante aparece en su empresa con la etiqueta REPRESENTANTE | Probado | `test_replace_history_representative_csd_and_expired`; revisión visual |
| Etiquetas de vigencia en la lista y alertas en la campana | Probado | `test_vault_screen.py`, `test_vault_alerts.py` (30, 7 y 0 días, una vez por umbral) |
| Importar el Excel real: relación por RFC, «NA» no toca nada, avisos de la sección 6 | Probado con sintéticos / falta en el despacho | `test_vault_import.py`; falta el Excel real del despacho |
| No hay forma de descargar el .cer ni el .key | Probado | `test_internal_service_for_declara_and_no_http_download` (boleto `sat_fiel` 422, `/files` 410, ninguna respuesta trae los archivos) |
| Ver, copiar, importar, exportar y desbloquear quedan en la bitácora sin secretos | Probado | `test_log_rows_carry_the_spec_action_and_the_computer`, conteos de IMPORTAR y EXPORTAR en `test_vault_import.py` |
| Un usuario autorizado ve y copia, pero no edita, importa ni exporta | Probado | `test_vault_model.py::test_permissions_by_role` |

Las pruebas mínimas de la spec (cifrado y datos asociados, .cer y .key, reglas de importación y permisos por rol)
están en `test_vault_master.py`, `test_vault_fiel.py`, `test_vault_import.py` y `test_vault_model.py`.

## Pendientes por decidir (de la spec)

- **Más de un representante con FIEL:** se implementó uno activo por empresa; los anteriores pasan al historial.
- **Certificado IMSS:** se guarda sólo su contraseña (tipo IMSS_IDSE).
- **Autobloqueo:** 5 minutos por omisión, configurable de 1 a 60 en Configuración › Bóveda de contraseñas.

## Lo que falta para dar el módulo por terminado

1. **En la PC del despacho**, con respaldo y autorización: aplicar `cs_0022` a `cs_0025` a la instancia real.
   - Crear la bóveda en el equipo donde está el llavero DPAPI anterior, porque se necesita una sola vez para re-envolver los secretos actuales.
   - Guardar el código de recuperación impreso.
2. Probar varias FIEL y CSD reales, de personas morales y físicas: cómo vienen el RFC y la clase, y el cifrado del .key.
3. Importar el Excel real del despacho (hoja «CONTRASEÑAS») y revisar los avisos.
4. Hacer la consulta directa a la base real para confirmar que no hay secretos en claro.
5. Decidir si se agrega `xlrd` para leer `.xls`; hoy se pide guardarlo como `.xlsx` o `.csv`.
6. La sesión de Declara pidió un tipo «Carpeta de red» con su servicio interno, ya aprobado en AGENTS.md (excepción a). No forma parte de esta spec; queda para decisión.
