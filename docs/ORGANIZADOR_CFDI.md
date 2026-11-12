# Organizador web

La ruta `/organizador-cfdi` usa el motor original de escritorio, conservado sin modificaciones en `backend/app/organizador_engine.py`. El adaptador `backend/app/organizador.py` gestiona archivos subidos, historial, tareas y descargas. No clasifica por el contenido de XML ni consulta el SAT.

## Uso

1. Abre Organizador. Selecciona una empresa opcionalmente; su RFC se propone como RFC de origen y se puede ajustar.
2. Carga un ZIP o selecciona la carpeta base, manteniendo esta estructura:

```text
Base/
  Emitidos/RFC/2026-10/archivo.xml
  Recibidos/RFC/2026-10/archivo.pdf
  Reportes/EMITIDOS-RFC-202610.xlsx
  Reportes/RECIBIDOS-RFC-202610.xls
```

Se admite un único nivel de carpeta que envuelva la base. La selección de carpeta sube copias al servidor, no concede acceso directo a sus rutas locales. Los límites son 100 MB por carga, 1,000 archivos seleccionados o 5,000 documentos en ZIP y 500 MB descomprimidos. Los formatos admitidos son PDF, XML, XLS, XLSX y XLSM. No se abren ni ejecutan macros de los reportes.

3. Selecciona RFC, ejercicio, meses, Emitidos/Recibidos, PDF/XML y reportes Excel. Pulsa **Analizar origen**.
4. Revisa la estructura propuesta, avisos y auditoría. Pulsa el nombre de un archivo para ver sus rutas y el motivo del estado. Los parámetros se guardan con cada análisis; para cambiarlos, carga y analiza nuevamente.
5. Pulsa **Organizar copias**. Una vez terminado, descarga el ZIP de carpetas y la auditoría CSV por separado. Revisa los errores antes de utilizar la salida.

El ZIP corresponde al destino de empresa y ejercicio elegido en escritorio; no añade niveles de RFC ni año:

```text
10.- OCTUBRE/
  EMITIDOS/archivo.xml
  RECIBIDOS/archivo.pdf
  EMITIDOS-RFC-202610.xlsx
  RECIBIDOS-RFC-202610.xls
```

Se incluyen EMITIDOS y RECIBIDOS para cada mes elegido, aunque estén vacíos. Se procesan sólo archivos directos de los periodos; las subcarpetas quedan fuera. La selección de rutas no distingue mayúsculas, y los archivos conservan su nombre y extensión originales.

## Integridad y ejecución

El adaptador fija la operación del motor en `copy`, porque sólo recibe copias de carga. El modo `move` del motor original permanece intacto, pero no se expone como una operación sobre originales locales. El agente existente continúa siendo de lectura.

El motor omite por nombre cualquier destino existente, aunque su contenido sea distinto; no lo reemplaza ni genera sufijos. Verifica SHA-256 y que el origen no haya cambiado. Cada análisis se ejecuta una vez; una repetición requiere una nueva carga y crea un destino independiente.

Los datos se guardan bajo `data/organizador/<id>` junto con una fila en `organizador_runs`. Las rutas absolutas del servidor no se muestran en las filas de auditoría ni en el CSV. Las empresas con análisis vinculados conservan su historial y no se pueden eliminar. Las rutas peligrosas, enlaces ZIP y rutas duplicadas se rechazan.

La tarea usa el proceso FastAPI. Un reinicio marca las tareas pendientes como error y requiere repetir la carga. No ejecutar varios workers sin sustituir este mecanismo por una cola coordinada. El ZIP sólo se ofrece tras terminar la generación; si hay errores de archivos individuales, se entregan las copias verificadas y se informa de los errores en la tabla y el CSV.

## Comprobaciones

- Motor original y copia integrada: SHA-256 idéntico.
- `python -m pytest -q`: 31 aprobadas, una omitida por falta del privilegio de enlaces simbólicos de Windows. Incluye seis pruebas nuevas de Organizador.
- Compilación TypeScript y Vite con las versiones del `package-lock.json` original.
- Flujo verificado en Edge sin ventana con datos aislados: carga ZIP, análisis, tres copias verificadas, detalle, CSV y capturas de los tres temas. Sin errores JavaScript ni desbordamiento horizontal de página a 390 px. Descarga real repetida en Edge: ZIP completo de 875 bytes con tres documentos cuyos bytes coinciden con los originales; CSV de 459 bytes con tres registros Copiado. La respuesta vacía anterior era causada por el agente de descargas que interceptaba el enlace, según confirmó el usuario; la incidencia quedó resuelta. La interfaz conserva la detección de descargas vacías.
- El frontend compilado se actualiza para el lanzador existente. No se ha creado un ZIP de entrega nuevo.
