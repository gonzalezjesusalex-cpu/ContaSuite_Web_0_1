# ContaSuite v1.0 RC1 — instalación y aceptación

Paquete construido desde el repositorio actualizado el 12 de noviembre de 2026.
No usar el ZIP del 11 de noviembre ni el lanzador antiguo del puerto 8000.
Esta entrega es candidata de desarrollo; la aceptación del despacho sigue pendiente.

## Preparar el servidor

1. Verificar el SHA-256 externo y PACKAGE_SHA256.json. Extraer en una carpeta nueva.
2. Instalar PostgreSQL con el instalador oficial o conectar una instancia existente autorizada. Crear una base nueva y un propietario dedicado sin privilegios de superusuario. Escuchar sólo en loopback, autenticación SCRAM, sin regla entrante 5432. No reutilizar ni sobrescribir bases existentes. Los binarios PostgreSQL y Nginx no están incluidos.
3. Elegir rutas separadas: código versionado C:\ContaSuite\versions\RC1, datos C:\ProgramData\ContaSuite\data, logs y configuración privada. Conservar el paquete original fuera del destino.
4. Aprovisionar DATABASE_URL, APP_TOKEN y AGENT_TOKEN en el entorno privado del instalador. No escribirlos en argumentos, scripts públicos o registros. Ejecutar `INSTALL.cmd --mode Install --destination C:\ContaSuite\versions\RC1 --data-dir C:\ProgramData\ContaSuite\data`. Las migraciones son explícitas; el inicio nunca migra. Install rechaza un esquema empresarial existente.
5. Crear configuración del servicio con `runtime\python.exe -B app\scripts\secure_config.py --create C:\ProgramData\ContaSuite\private\service.json`. Solicita conexión PostgreSQL y DNS; genera tokens nuevos y cifra mediante DPAPI de la máquina. Guardar la clave de alta en un gestor de secretos. El cifrado de máquina requiere ACL: sólo administradores/SYSTEM y lectura para la cuenta del servicio. DPAPI no sustituye las ACL. No transportar ese archivo como configuración reutilizable a otra PC: hay que reprovisionar secretos.
6. Preparar con service_admin.py el plan de registro descrito en INSTALL_RELEASE_WINDOWS.md, agregando `--port 8062`. Revisar rutas/cuenta y ejecutar `--apply` únicamente en el servidor autorizado. Cuenta virtual NT SERVICE\ContaSuiteApi sin privilegios administrativos; RX en código y runtime, M en datos/logs y R en configuración. Inicio automático y recuperación 15/30/60 segundos. No se registra ni inicia nada al extraer el paquete.
7. Iniciar con `sc.exe start ContaSuiteApi`; comprobar `sc.exe query ContaSuiteApi`, /api/health y logs rotativos. El servicio verifica PostgreSQL/esquema y levanta API, alertas e indexador. Sólo se recorren fuentes habilitadas y programadas; no habilitar fuentes reales sin autorización. La parada solicita cierre a los tres componentes. Un trabajador que no finaliza marca fallo para recuperación SCM.

## HTTPS y equipos cliente

El instalador acepta `--public-url https://DNS-configurado` para crear ContaSuite.url dentro de la instalación. Copiar ese acceso directo a los escritorios autorizados; no contiene credenciales. ADMIN.cmd consulta el estado del servicio y apunta a esta guía. No cambia el registro ni inicia componentes de la instalación antigua.

Configurar Nginx usando deploy/windows/nginx-lan.conf.example, reemplazando DNS, subred y rutas. Mantener upstream 127.0.0.1:8062 y PostgreSQL en loopback. Usar certificado con SAN del DNS interno, emitido por la CA del despacho, cadena completa y renovación administrada. La clave TLS permanece en el servidor con ACL del proxy.

El administrador instala únicamente el certificado público de la CA interna en «Entidades de certificación raíz de confianza» de los clientes mediante GPO o certmgr.msc tras verificar su huella por un canal independiente. Nunca distribuir la clave privada. No omitir advertencias del navegador. Si existe una CA corporativa ya confiada, no instalar otra raíz.

Autorizar firewall entrante TCP 443 sólo desde la subred aprobada, perfil Domain/Private. Puerto 80 sólo si se habilita redirección y con la misma restricción. No publicar en Internet, no abrir router, 5432 ni 8062. Estas operaciones requieren aprobación del administrador del despacho. Acceder desde clientes a https://DNS-configurado; cada empleado usa cuenta y permisos propios. Verificar denegación entre empresas, expiración, CSRF y cookies Secure en HTTPS desde otro equipo.

## SMB y programación

Configurar raíces UNC explícitas en CS_STORAGE_SMB_ALLOWED_ROOTS (lista JSON como cadena). Usar identidad Windows dedicada con lectura en recurso y NTFS; no guardar contraseñas SMB en ContaSuite. En dominio, conceder acceso a una cuenta administrada o identidad de equipo según política del administrador; una cuenta virtual no sustituye una identidad de dominio en todos los entornos. La elección y prueba de esta identidad sigue siendo trabajo de instalación, no se modifica el servidor documental desde el paquete.

Registrar origen desde Configuración, probar conexión, explorar y configurar exclusiones/frecuencia antes de habilitarlo. El indexador supervisado conserva leases/checkpoints y catálogo ante desconexión. La sincronización manual usa la cola existente; no importar la segunda carpeta. Los documentos sin atribución y los conflictos conservan revisión humana e historial.

## Respaldo programado y recuperación

backup_postgres.py produce dump consistente y copia de data con escritores detenidos, más sha256.json. No copia originales SMB. Respaldar aparte configuración protegida y material del gestor de secretos; DPAPI de máquina no se puede recuperar en otro servidor sin reprovisionamiento. Conservar también configuración del proxy, certificados y procedimiento del rol PostgreSQL en un repositorio administrativo protegido; nunca en el instalador.

maintenance_backup.py --config C:\ProgramData\ContaSuite\private\backup.json ejecuta una ventana de mantenimiento. El JSON contiene exactamente pg_bin, database, destination (UNC externa), data_dir, service (ContaSuiteApi) y retention (entero >=2). PGHOST/PGPORT/PGUSER/PGPASSFILE se aprovisionan en la identidad de respaldo. Usar pgpass con ACL restringida, sin contraseña en argumentos. La cuenta necesita detener/iniciar sólo este servicio, leer datos y escribir en destino externo. La retención elimina únicamente copias anteriores verificadas en ese destino; definirla con el administrador.

Crear una tarea diaria en Programador de tareas, «Ejecutar tanto si el usuario inició sesión como si no», bajo esa identidad y con ruta absoluta a runtime\python.exe, argumentos `-B <ruta-absoluta>\app\scripts\maintenance_backup.py --config <ruta-absoluta>\backup.json`. Ajustar la hora a una ventana sin trabajo; se interrumpe el acceso brevemente. La tarea devuelve fallo ante error; backup.status.json conserva resultado sin secretos. Configurar aviso del sistema de monitorización ante resultado distinto de cero o estado obsoleto. No hay envío automático de correo incorporado.

Verificar con `runtime\python.exe -B app\scripts\restore_postgres.py --backup <carpeta> --verify-only`. Restaurar con --pg-bin, --database contasuite_restore_FECHA y --data-dir <carpeta-nueva>. Rechaza base/carpeta existente; no usa --clean ni --create de pg_restore. Si falla conserva el destino nuevo para diagnóstico. Comprobar conteos e historial antes de cambiar una conexión. La verificación SHA no reemplaza el ensayo de restauración.

## Actualizar, retirar y migrar el piloto

Detener esta instalación y cualquier escritor externo, respaldar y ensayar restauración en otra base. `INSTALL.cmd --mode Update --destination <nueva-version> --data-dir <datos> --backup <dump-verificado> --writers-stopped` conserva código anterior. El cambio de ruta del servicio es administrativo explícito; no secuestra servicios existentes. Retiro mediante --mode Uninstall conserva datos y renombra el código, como detalla INSTALL_RELEASE_WINDOWS.md. No hacer downgrade destructivo.

Migración del piloto: inventariar versión/esquema y conteos, detener escritores con autorización, crear respaldo conjunto, transferir por canal protegido, verificar hashes, restaurar en base nueva del servidor y comparar empresas/documentos/versiones/vínculos/revisiones. Reprovisionar secretos y raíces autorizadas; validar antes de cambiar DNS/conexión. No ejecutar sobre la base antigua ni sobrescribir el piloto. No se ejecutó migración real en esta entrega.

## Aceptación obligatoria en el servidor

Probar registro SCM, reinicio de PC sin sesión interactiva, recuperación de caída, parada durante sincronización, permisos efectivos SMB, TLS con otro cliente, firewall, sesiones simultáneas, restauración externa y tiempos con volumen real. Confirmar 25.271 documentos y versiones, asociaciones y pendientes contra el inventario autorizado sin reclasificar. SAT automático continúa pendiente. Consultar RC1_VALIDATION.md para distinguir pruebas ejecutadas de verificaciones pendientes.
