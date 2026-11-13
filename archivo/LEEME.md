# Archivo

Lanzadores y scripts de iteraciones anteriores, conservados sólo como referencia. **No funcionan desde esta carpeta**: usan rutas relativas a su ubicación original (`%~dp0`, `parents[1]`).

- `lanzadores/`: laboratorio v0.4 (`CONFIGURAR_ACCESO_V0_4.bat`, `INICIAR_DESARROLLO_V0_4.bat`), visita (`VERIFICAR_VISITA.bat`) y paquete de recuperación del 11/11/2026 (`Install-ContaSuite.*`, `Start-ContaSuite.*`, puerto 8000 fijo), sustituidos por `deploy/windows/INSTALL.cmd` y `START.cmd`.
- `scripts/`: generadores de paquetes, manifiestos e informes de un solo uso (`integration_package.py`, `recovery_manifest.py`, `pilot_manifest.py`, `pilot_first_report.py`).

Los lanzadores vigentes están en `deploy/windows/` (instalación empaquetada) y en la raíz (desarrollo e instancia 8000, que se conservan hasta decidir su destino).
