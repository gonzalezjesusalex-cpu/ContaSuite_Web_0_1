ORGANIZADOR CFDI - CONTASUITE v0.2 beta

INICIAR
Desde el launcher: INICIAR.bat, después CFDI en la barra lateral.
También puedes abrir apps\CFDI\INICIAR.bat con Python 3.10 o posterior y Tkinter.
Para crear EXE en Windows usa COMPILAR_EXE_WINDOWS.bat (del módulo o la suite).
Este paquete contiene código fuente; no incluye un EXE Windows generado.

MOTOR ORIGINAL
Las reglas de Organizar_CFDI.bat se trasladaron a engine.py, sin cambiar la GUI.
Se incluye Organizar_CFDI_original.bat sin modificaciones para comparación.
La interfaz no abre la consola interactiva: llama al motor adaptado en Python.

ORIGEN (selecciona la carpeta base, normalmente C:\elcfdi\DescargaMasiva)
ORIGEN\Emitidos\RFC\2026-04\*.pdf y *.xml
ORIGEN\Recibidos\RFC\2026-04\*.pdf y *.xml
Solo se toman archivos directos. Las subcarpetas se omiten.
No se lee ni valida el contenido de los PDF o XML ni se busca su UUID.
El periodo y tipo se toman de la ruta, como en el BAT.

REPORTES EXCEL (activados por defecto)
ORIGEN\Reportes\EMITIDOS-RFC-202604.xls, .xlsx o .xlsm
ORIGEN\Reportes\RECIBIDOS-RFC-202604.xls, .xlsx o .xlsm
Se requieren esos nombres exactos (sin distinguir mayúsculas/minúsculas).
Se guardan en la raíz del mes correspondiente, fuera de EMITIDOS/RECIBIDOS.

DESTINO (selecciona la carpeta de la empresa y ejercicio)
DESTINO\04.- ABRIL\EMITIDOS\archivo.xml
DESTINO\04.- ABRIL\RECIBIDOS\archivo.pdf
DESTINO\04.- ABRIL\EMITIDOS-RFC-202604.xlsx
No se añaden carpetas de RFC o ejercicio al destino elegido.
Se crean ambos tipos de carpeta en cada mes seleccionado, incluso sin documentos.
El botón Organizar funciona tras analizar aunque no haya archivos para mover.

USO
1. Selecciona origen, destino, RFC, ejercicio y meses.
2. Conserva los filtros PDF, XML, ambos tipos y reportes para reproducir el BAT.
3. Analiza; revisa los estados y selecciona una fila para ver sus rutas y motivo.
4. Organiza y confirma la operación. Mover es la opción predeterminada.
Si eliges Copiar, el origen se conserva.
La rueda desplaza las opciones y la tabla. Mayús+rueda desplaza horizontalmente.
Puedes arrastrar la división de paneles y cambiar tema o tamaño de fuente.

DUPLICADOS E INFORMES
Igual que el BAT, cualquier nombre ya existente se omite, incluso si el contenido
es diferente. No se compara para reemplazarlo ni se crea un sufijo (2).
El origen del duplicado se conserva. Se comprueba otra vez antes de cada operación.
Antes de eliminar un origen se verifica SHA-256 de la copia y que no haya cambiado.
Cancelar termina el archivo actual y conserva lo ya procesado; no revierte movimientos.
La configuración no puede cambiar durante un proceso. Después, vuelve a analizar.
El informe automático CSV queda en %APPDATA%\ContaSuite\CFDI; también puedes exportarlo.
Se incluyen registros informativos de carpetas de origen faltantes.

DIFERENCIAS DE INTERFAZ RESPECTO AL BAT
Se mantienen selección de archivos/tipos, Copiar, análisis previo, informes y cancelación.
La GUI valida RFC y separa las carpetas de origen y destino antes de ejecutar.
La carpeta predeterminada de destino es la del módulo ejecutado (o tu última elección).
Los meses siguen el formato y estructura exactos del BAT original.

PRUEBAS
python -m unittest discover -p "test_*.py" -v
17 pruebas de motor y 1 de flujo gráfico aprobadas en Linux.
La ejecución y compilación nativa en Windows quedan pendientes de tu prueba.
