# Estado actual de la visita

Cierre CS-Storage 1–5, dashboard/CER y frontend compilado: **122 pruebas aprobadas y una omitida**, Edge sobre compilación, tres temas/móvil, señal y programación real del trabajador en demo. Consultar `../LISTO_PARA_VISITA.md` y `CS_STORAGE_BLOCK5.md`. La base original se conservó; conexión SMB y servidor real no validados. Lo que sigue es el registro histórico de validaciones anteriores.

# Validación de la entrega 0.1

Fecha: 9 de noviembre de 2026. Entorno: Linux, Python 3.12, Node.js 24. Base de datos usada en las pruebas: SQLite.

## Comprobaciones ejecutadas

- TypeScript en modo estricto y compilación de producción con Vite: correctos.
- Nueve pruebas automatizadas de API: correctas. Incluyen acceso, RFC duplicado e inválido, tipo de persona, crear/editar empresas, tareas, obligaciones, documentos, descarga, eliminación con registros relacionados, cola del agente, persistencia al reiniciar y carga DEMO una sola vez.
- Verificación real por HTTP con FastAPI y un proceso independiente del agente: correcta. Se comprobó conexión, publicación del trabajo, reclamación, escaneo y devolución del inventario.
- El contenido de la llave privada de prueba no se transmitió y los archivos originales permanecieron intactos.
- Navegador: alta de empresa en tres pasos, apertura del expediente y guardado de tarea comprobados. El diálogo de eliminación exige RFC y comienza deshabilitado. La eliminación efectiva se comprobó mediante la API.
- Navegador: directorio con tres empresas marcadas DEMO, dashboard y navegación a los seis módulos de automatización y Configuración comprobados.
- Se corrigieron nodos de espacios en tablas importadas que provocaban advertencias de React.
- El paquete excluye bases de prueba, claves de prueba, entornos virtuales y node_modules. Incluye frontend/dist y package-lock.json.

## Límites de la validación

Los archivos BAT y la instalación completa no se ejecutaron en Windows en este entorno. PostgreSQL/Docker están configurados pero no pudieron probarse aquí porque no hay Docker ni servidor PostgreSQL disponibles. El análisis de rutas UNC debe verificarse con la cuenta Windows y los permisos reales del despacho.

Los temas alternativos y los puntos de corte móviles están implementados; la revisión visual principal se hizo en escritorio claro. No se afirma validación exhaustiva de accesibilidad, seguridad de producción ni regresión de los motores anteriores. Se integraron posteriormente los iconos originales de ContaSuite 0.6.

## Repetir las pruebas en Windows

Desde la raíz del proyecto, con .venv creada:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe -m pytest backend\tests -q
.\.venv\Scripts\python.exe backend\tests\verify_live_agent.py
```

Las pruebas usan bases y documentos temporales; no modifican la base normal del despacho. La prueba de rutas con enlaces simbólicos requiere permiso para crear enlaces en Windows (Modo desarrollador o terminal con el permiso correspondiente). Los comandos de prueba no requieren que esté iniciada la aplicación.

## Corrección 0.1.1 de arranque Windows

Catorce pruebas automatizadas correctas, incluidas cinco nuevas para rechazar Python 3.15, preferir 3.12, aceptar 3.11 y respetar el perfil real de base de datos. Se verificó la resolución de requirements-base.txt sin dependencia de psycopg. El BAT no pudo ejecutarse en Windows aquí.

## Iconos originales

Frontend local y demo compilan con el paquete original. Los PNG de uso web conservan los bytes del archivo adjunto. Se añade la ruta estática /icons en FastAPI para la versión Windows.
