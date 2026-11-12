# SMB desde la computadora de la oficina

El proveedor `windows_smb` permite catálogo, indexación, descarga verificada y programación sobre rutas UNC desde Windows. Usa exclusivamente la identidad del proceso de ContaSuite y las conexiones de Windows de esa sesión. No almacena ni cambia credenciales; no instala software en el servidor y no escribe en los originales. Si Windows solicita autenticación, abrir la carpeta desde el Explorador con el mismo usuario antes de iniciar ContaSuite.

## Configuración

Autorizar en `.env` únicamente las carpetas necesarias mediante `CS_STORAGE_SMB_ALLOWED_ROOTS`, una lista JSON entre comillas simples. Ejemplo ficticio:

```dotenv
CS_STORAGE_SMB_ALLOWED_ROOTS='["//servidor/contabilidad/clientes"]'
```

Reiniciar API e indexador para cargar la configuración. No usar `CS_STORAGE_ALLOWED_ROOTS` ni unidades mapeadas para SMB. Las raíces locales siguen rechazando UNC. La API sólo permite que un administrador registre orígenes que estén dentro de las raíces SMB autorizadas; los servidores ajenos se rechazan antes de sondear la red. Los borradores desactivados se pueden guardar sin acceso a red.

En Configuración → Almacenamiento documental → Conectar servidor SMB, capturar servidor, recurso y subcarpeta. La subcarpeta admite `/` o `\`. Guardar, comprobar lectura y solicitar análisis. El tipo y destino son inmutables para conservar el historial; registrar otro origen para cambiarlos. La frecuencia puede quedar manual o usar la programación persistente existente. El indexador debe estar activo bajo una identidad Windows con acceso al recurso.

## Controles y límites

- Sólo PDF, XML y CER públicos. KEY, ZIP, PFX, P12 y demás formatos privados no se enumeran ni abren por este proveedor.
- Se conservan límites de entradas, tamaño y recorrido, exclusiones, validación de contenido y huellas SHA-256. Se rechazan rutas ascendentes, dispositivos, ADS, enlaces y puntos de unión. La ruta final del archivo abierto debe permanecer dentro del origen.
- Una desconexión o recorrido parcial genera error/incidencias y no permite inferir desapariciones masivas. Repetir el análisis cuando regrese la conexión. Un archivo desaparecido realmente puede quedar marcado como no localizado.
- Las operaciones SMB individuales dependen de los tiempos de espera de Windows: el límite de recorrido no interrumpe una llamada de red bloqueada. No ejecutar una copia masiva de todo el despacho como primera prueba. Empezar con una empresa y revisar la carga del servidor.
- No conecta SAT, no comprueba revocación de certificados y no asigna una empresa por el nombre de su carpeta. La clasificación existente usa evidencia documental y mantiene revisión de casos ambiguos.
- La validación de la ruta final se basa en [GetFinalPathNameByHandleW de Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew). Permisos insuficientes para normalizar componentes pueden impedir una lectura; se rechaza sin reducir la validación.

## Validación en oficina

Se probó un recurso real desde esta computadora: tres PDF de una empresa, recorrido acotado con el proveedor SMB, cola real en SQLite temporal, clasificación y tres descargas con huellas SHA-256 coincidentes. No se escribieron archivos en el recurso. No equivale a haber recorrido o clasificado las 51 carpetas principales del despacho.

El origen de la oficina quedó registrado en modo manual y con una copia privada previa de la base y configuración en `RESPALDOS`. No se requiere migración nueva de esquema. La interfaz está compilada para usar el conector.
