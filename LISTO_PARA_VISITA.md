# ContaSuite — guía de la visita

**Actualización de oficina:** el proveedor SMB remoto ya está implementado y probado con una muestra acotada; consultar `docs/SMB.md`. Las menciones históricas de Windows como borrador desactivado en esta guía corresponden a la entrega anterior. La lista de raíces SMB es independiente de la local y el acceso utiliza la sesión Windows de esta computadora.

La versión de visita incluye el frontend **compilado**, CS-Storage bloques 1–5, usuarios y permisos, el dashboard de Empresas y seguimiento temporal de certificados públicos FIEL/CSD. Conserva Stitch y los cuatro motores existentes. No se generó instalador ni ZIP de distribución.

## Qué ejecutar

1. **Antes de actualizar una instalación con datos:** detener ContaSuite y su indexador, respaldar la base junto con `data/`, `.env` y `agent/config.json` en un destino privado. Para PostgreSQL usar un respaldo del servidor; no copiar sus archivos de almacenamiento mientras está activo. Verificar que la copia se pueda restaurar en una ubicación de prueba.
2. En este equipo: **`VERIFICAR_VISITA.bat`** comprueba dependencias, la compilación y su integridad. No modifica la base ni se conecta al despacho. Es normal que una base anterior indique migración/alta inicial pendientes antes del primer arranque actualizado.
3. **`INICIAR_PRUEBA.bat`** conserva una configuración existente. En una instalación nueva prepara SQLite; puede necesitar Internet para instalar Python/dependencias. Abre la versión compilada en `http://127.0.0.1:8000`. No necesita Node para usar esta compilación.
4. Crear el primer administrador con la clave que muestra la consola. Después se ingresa por usuario y contraseña; la clave ya no autoriza acceso. Crear colaboradores y permisos en Configuración.
5. El lanzador inicia el indexador como proceso separado cuando la API responde. Cerrar con Ctrl+C detiene ambos. **`INICIAR_INDEXADOR.bat`** permite iniciarlo por separado si la API se ejecutó con otro método. No hace falta abrir varios indexadores; la base limita los análisis simultáneos.

La base real de este workspace **no se migró durante el desarrollo** y no se crearon cuentas reales. La revisión aditiva `cs_storage_0004` se aplicará al arrancar el backend actualizado. No ejecutar primero sobre la única copia del cliente.

## Demostración preparada y reproducible

Para ensayar sin información real, desde la raíz y usando siempre un directorio nuevo:

```powershell
.venv/Scripts/python.exe scripts/storage_demo.py --output .qa/demo-visita-nueva
```

Genera dos empresas ficticias, XML/PDF, duplicados, rutas anidadas, nombres contradictorios, archivos sin RFC, modificación/desaparición, error de acceso **simulado**, tareas/obligaciones y tres CER públicos sintéticos: FIEL vigente, próxima a vencer y anterior vencida. La clave de firma de prueba se crea sólo en memoria y nunca se guarda. No son certificados del SAT.

La demo escribe `environment.json` con su configuración y claves aleatorias **exclusivamente de esa demo**. Mantener ese archivo privado; no anexarlo a una entrega. Para iniciar la demo compilada en otro puerto, sin cambiar `.env`:

```powershell
$demoConfig = Get-Content .qa/demo-visita-nueva/environment.json -Raw | ConvertFrom-Json
foreach ($entry in $demoConfig.PSObject.Properties) {
  [Environment]::SetEnvironmentVariable($entry.Name, [string]$entry.Value, 'Process')
}
# Consultar APP_TOKEN en el archivo privado sólo para crear el administrador de la demo.
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8017
```

En una segunda consola con ese mismo entorno, entrar a `backend` y ejecutar `../.venv/Scripts/python.exe -m app.storage.worker`. Abrir `http://127.0.0.1:8017`. La demostración usa otra base y repositorio; no copiar sus claves/configuración sobre el despacho. Las carpetas `.qa/` no se distribuyen.

## Recorrido sugerido para el cliente

1. Inicio: bienvenida y nombre de la sesión.
2. Empresas → primera pestaña: KPI del despacho, dashboard FIEL, caducidades y documentos por empresa. Mostrar que un CER renovado vigente evita que el anterior vencido marque a la empresa como vencida.
3. Expandir certificados: distinguir **uso declarado** FIEL/CSD de vigencia temporal. Mostrar que no se piden `.key`, contenedores privados ni contraseña de e.firma.
4. Documentos: búsqueda, filtros, versión/huella, XML/PDF, descarga y revisión de una propuesta ambigua. Los originales externos permanecen intactos.
5. Configuración → Almacenamiento documental: origen local, prueba real de listado, exclusiones, frecuencia, señal del trabajador e historial. Windows se muestra como preparación desactivada, nunca como conexión exitosa.
6. Ingresar como colaborador: sólo ve sus empresas; lectura no permite cargar. Desactivar o revocar su cuenta desde administración y comprobar que termina la sesión.
7. Abrir Recopila, CFDI, Declara y Recibos como administrador. Sus motores siguen integrados; descarga automática SAT, OCR y funciones pendientes no se presentan como activas.

## Levantamiento del servidor Windows

Registrar durante la visita, sin guardar contraseñas en ContaSuite ni en el acta:

- Equipo, Windows/Python, ubicación de ejecución de la API y del trabajador, responsable técnico.
- Dónde están los archivos fiscales, volumen/tamaño, profundidad de carpetas, exclusiones y frecuencia acordada.
- Cuenta dedicada del proceso y permisos efectivos **de lectura/listado**. Si se usa un recurso compartido, revisar permisos de recurso y NTFS. No habilitar escritura para comprobar conectividad.
- Red/TLS, nombre de acceso, puerto, respaldo/retención y usuario responsable de la recuperación.
- Muestra de XML/PDF/CER autorizados, RFC de empresas y casos que deberán revisarse manualmente.

**Modalidad operativa ya compatible:** ejecutar API e indexador en el mismo Windows donde están los documentos y registrar carpetas locales autorizadas, por ejemplo `D:/Expedientes`. Esas fuentes funcionan con el proveedor local de sólo lectura. Configurar `CS_STORAGE_ALLOWED_ROOTS` con rutas concretas y reiniciar API/trabajador; luego registrar el origen desde la interfaz. Para entrar desde otros equipos se requiere HTTPS y configurar un proxy de confianza; HTTP sólo se acepta para sesiones locales de desarrollo.

**SMB remoto sigue siendo un contrato y borrador preparado**, no un adaptador productivo habilitado. Guardar servidor/recurso/subcarpeta/cuenta prevista en Configuración no abre una conexión ni indexa UNC. La visita debe comprobar red y permisos; la enumeración remota desde ContaSuite requiere completar y validar ese adaptador antes de prometer uso productivo mediante SMB. No usar unidades mapeadas como forma de eludir esta limitación; usar carpetas físicas locales del servidor en la modalidad compatible.

## Pruebas de aceptación en el equipo del cliente

- [ ] Copia de seguridad y restauración de ensayo comprobadas.
- [ ] Preflight sin errores de dependencia/compilación; migración sobre copia de prueba correcta.
- [ ] Primer administrador, recuperación local y dos colaboradores con permisos distintos verificados.
- [ ] Carpeta local autorizada visible; carpeta fuera de la lista, enlaces y llaves privadas rechazados.
- [ ] Análisis inicial, incremental, duplicado, archivo ausente y error de lectura registrados sin escribir en el origen.
- [ ] Programación con trabajador activo y sin trabajos duplicados.
- [ ] RFC/roles revisados con muestras autorizadas; ambigüedades no se asignan silenciosamente.
- [ ] CER, RFC, fechas, renovación y uso FIEL/CSD revisados; no confundir fechas con validación SAT o revocación.
- [ ] Descarga íntegra y denegación de otra empresa comprobadas.
- [ ] HTTPS y acceso desde LAN validados antes de exponer cuentas en red.
- [ ] Pendientes SMB/SAT y responsables asentados con fecha, sin marcarlos como terminados.

**No es una certificación productiva del despacho.** PostgreSQL real, infraestructura/TLS, permisos y documentos del cliente, SMB remoto y acceso/descarga SAT se validan en el entorno correspondiente. No se ha contactado su servidor desde este desarrollo.

Detalle técnico: [CS-Storage bloque 5 y dashboard](docs/CS_STORAGE_BLOCK5.md). Recuperación local de cuentas y matriz de permisos: [bloque 4](docs/CS_STORAGE_BLOCK4.md).
