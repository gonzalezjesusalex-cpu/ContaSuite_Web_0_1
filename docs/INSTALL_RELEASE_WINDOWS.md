# Operación Windows/LAN — CS-RELEASE-CLOSURE-001

El paquete incluye Python 3.12 privado, dependencias comprobadas, backend, frontend compilado, migraciones explícitas e instalador CMD/Python. No depende de Python/Node en PATH. PostgreSQL es una dependencia externa que debe aprovisionar el administrador. No se despliega automáticamente ni modifica PowerShell, servicios, firewall, certificados o red.

## Instalación y configuración inicial

1. Verificar el SHA-256 del ZIP y el manifiesto interno PACKAGE_SHA256.json. Extraer el instalador a una carpeta nueva. Conservar esa carpeta para actualizar/retirar versiones; no superponer carpetas.
2. Preparar PostgreSQL soportado (ensayado con 17.11), base nueva y propietario dedicado sin superusuario. Escucha 127.0.0.1 y pg_hba.conf limitado al rol/base. Aprovisionar credenciales nuevas, nunca las sintéticas del laboratorio.
3. Elegir carpetas separadas para instalación versionada, datos, logs, configuración privada y respaldos. El instalador exige rutas absolutas y datos fuera del código. Proteger con ACL de administrador/SYSTEM y la cuenta virtual de servicio correspondiente; la cuenta de servicio necesita RX en código/runtime, M en datos/logs y R en su configuración. No dar permisos de administrador al proceso.
4. Aprovisionar DATABASE_URL, APP_TOKEN y AGENT_TOKEN al proceso de instalación mediante el mecanismo privado del administrador. No ponerlos en el paquete, argumentos, tickets o logs. CS_STORAGE_ALLOWED_ROOTS y CS_STORAGE_SMB_ALLOWED_ROOTS permanecen `[]` hasta autorización independiente.
5. Desde el paquete extraído ejecutar:

       INSTALL.cmd --mode Install --destination C:\ContaSuite\versions\release-001 --data-dir C:\ProgramData\ContaSuite\data

   El Python incluido verifica todos los hashes, copia a una carpeta nueva y aplica explícitamente las migraciones sobre la conexión suministrada. Rechaza destino existente y `--new` rechaza una instalación empresarial existente. Si falla, conserva el código para diagnóstico y no inicia nada.
6. Para arranque local controlado: `START.cmd C:\ProgramData\ContaSuite\data` desde la instalación, con las variables explícitas. O ejecutar su runtime con `app\scripts\service_runtime.py --data-dir ... --host 127.0.0.1 --port 8000`. Crear el primer administrador personal en la interfaz con APP_TOKEN; después ese token no sustituye sesiones personales.

## Servicio Windows nativo

`app/scripts/windows_service.py` implementa el protocolo SCM mediante ctypes: START_PENDING, RUNNING tras readiness, STOP_PENDING, señal de parada y STOPPED. Usa Uvicorn con drenaje de hasta 25 segundos, logs rotativos de 10 MB/8 copias y código de fallo distinto de cero. `service_admin.py` prepara inicio automático y recuperación 15/30/60 segundos con cuenta virtual `NT SERVICE\ContaSuiteApi`. No depende de WinSW ni de una terminal.

Preparar un JSON externo y privado con DATABASE_URL, APP_TOKEN, AGENT_TOKEN y, si se requiere, CS_ALLOWED_HOSTS/raíces. Todos los valores deben ser cadenas; las listas de configuración son JSON serializado dentro de la cadena. No incluir secretos en el ejemplo del paquete. El servicio recibe sólo la ruta mediante `--config-file`; nunca registra valores en su log. La protección de ACL y la cuenta real deben comprobarse antes de registrarlo.

Para revisar el plan (no aplica cambios):

    runtime\python.exe -B app\scripts\service_admin.py --root C:\ContaSuite\versions\release-001 --name ContaSuiteApi --data-dir C:\ProgramData\ContaSuite\data --log-dir C:\ProgramData\ContaSuite\logs --config-file C:\ProgramData\ContaSuite\private\service.json

Sólo en una máquina Windows de pruebas autorizada y con permisos administrativos, repetir con `--apply` después de comprobar ACL/configuración. Rechaza servicios existentes y no los reconfigura. El registro no inicia el servicio. Arranque/parada/reinicio explícitos mediante `sc start ContaSuiteApi`, `sc stop ContaSuiteApi` y arranque posterior; revisar query/logs. Antes de quitarlo, verificar su ruta con `sc qc`, detener únicamente ese servicio y retirar su registro con `sc delete` tras autorización. No borrar datos, roles ni configuración privada.

En este equipo la sonda de creación devolvió WinError 5; no se registró ningún servicio. Se ensaya el mismo ejecutor sin consola mediante `--console-test-seconds`, pero ello no acredita controles/reinicio real del SCM ni arranque del equipo. Es una validación obligatoria pendiente. No se modifica la política de PowerShell.

## Actualización, respaldo y reversión

Detener API, alertas e indexadores de esa instalación. Conservar código anterior. Respaldar base y archivos juntos con `runtime\python.exe -B app\scripts\backup_postgres.py --pg-bin <binarios> --database <base> --destination <respaldo-absoluto> --data-dir <datos-absolutos> --writers-stopped`, con PGHOST/PGPORT/PGUSER/PGPASSFILE aprovisionados privadamente. El script no detiene servicios ni elimina copias anteriores. Configurar tarea programada de mantenimiento sólo en el equipo autorizado, con cuenta/destino restringidos y restauración periódica comprobada.

Restaurar el dump en otra base y copiar/verificar archivos por SHA-256 antes de aprobarlo. Con escritores detenidos ejecutar desde el instalador nuevo:

    INSTALL.cmd --mode Update --destination C:\ContaSuite\versions\release-002 --data-dir C:\ProgramData\ContaSuite\data --backup C:\Respaldos\verificado\database.dump --writers-stopped

Siempre crea otra carpeta; no pisa una versión estable. La actualización del esquema es explícita y exige respaldo suministrado, pero su existencia no demuestra restaurabilidad. Tras la comprobación, cambiar el servicio a la versión nueva es una operación administrativa separada; este paquete no cambia un servicio existente automáticamente.

Para retirar reversiblemente una versión detenida, ejecutar desde el instalador externo `INSTALL.cmd --mode Uninstall --destination <version-a-retirar> --data-dir <datos-externos> --writers-stopped`. Verifica manifiesto/marcador y renombra a `.retired-fecha`, conserva todos sus archivos y no toca base, datos ni configuración. No retira registros SCM automáticamente. No es una purga de datos ni un downgrade del esquema.

Para revertir: conservar nuevos datos/historial; verificar compatibilidad del código anterior con el esquema actual. La migración de identidad no tiene downgrade destructivo. Si es necesario recuperar datos, hacerlo sobre una base nueva y directorio de datos correspondiente al mismo respaldo verificado, nunca sobreescribir la base viva. Cambios humanos posteriores deben reconciliarse antes de volver atrás.

## LAN y TLS

Usar proxy inverso HTTPS con DNS y certificado válido autorizado. `deploy/windows/nginx-lan.conf.example` es plantilla, con dominio, subred y rutas de certificado por sustituir. No trae llaves ni certificados, no crea reglas y no se probó contra Nginx en este equipo. No usar un certificado autofirmado como solución definitiva ni omitir advertencias de seguridad.

Mantener API y PostgreSQL en loopback. CS_ALLOWED_HOSTS debe enumerar el DNS real y nombres locales necesarios, sin comodines; el lanzador privado tiene valores locales restrictivos por defecto. La API confía X-Forwarded-* sólo desde 127.0.0.1; proxy debe reemplazar esos encabezados y preservar Host. Se conservan HTTPS fuera de loopback, cookies HttpOnly/SameSite/Secure y CSRF/origen. Para otro puerto usar `--port`; para binding no local se exige `--allow-lan` y CS_TLS_TERMINATED=1, sin desactivar la seguridad de sesión. Se recomienda mantener upstream local.

Autorizar en firewall sólo 443 desde la subred cliente concreta; no abrir 5432 ni 8000. Verificar desde otro cliente autorizado acceso permitido, denegación de redes/orígenes ajenos, cadena/renovación del certificado y cookies seguras. Esta prueba requiere cliente/red/certificado autorizados que no están disponibles en el laboratorio actual y sigue pendiente; no se alteró la red real.

## Reproducción

Repositorio: scripts/build_private_runtime.py, package_release.py, release_lab.py, release_http.py, release_http_followup.py, release_postgres.py y release_package_test.py. El runtime se construye sólo a partir del CPython/dependencias del entorno probado, con ._pth aislado y licencias/proveniencia; no copia .venv ni configuraciones. La entrega se genera dos veces para contrastar SHA. Los ejecutores de laboratorio sólo permiten nuevas bases/carpetas sintéticas y verifican la ruta del clúster; no deben apuntarse a una base del despacho.
