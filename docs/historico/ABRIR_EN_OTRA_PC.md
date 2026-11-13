# Llevar ContaSuite a otra computadora

El proyecto está en estos archivos; instalar Codex por sí solo no copia la carpeta de esta PC. Lleva el ZIP del proyecto en una USB y conserva el respaldo original aquí.

## Dos copias con propósitos distintos

- **Proyecto USB:** fuentes, referencias de diseño, documentación, scripts y frontend compilado. Excluye datos, `.env`, configuración privada del agente, dependencias instaladas y pruebas temporales. Puede iniciar una instalación nueva.
- **Datos PRIVADOS:** copia consistente de SQLite, archivos de `data/`, `.env` y `agent/config.json`. Sirve para conservar los registros y configuración actuales. Contiene claves de instalación y puede contener información del despacho; no compartir como entrega pública. El ZIP no está cifrado: proteger la USB y su acceso.

Para conservar tus registros, necesitas **ambos ZIP**. La carpeta raíz de ambos es `ContaSuite_Web_0_1` para poder superponerlos. La verificación del respaldo queda en el archivo `LEEME_RESPALDO.md` junto a los ZIP.

## En la computadora de la visita

1. Copiar los ZIP desde la USB al disco local, por ejemplo a `C:\ContaSuite`. Conservar los ZIP sin modificar como recuperación.
2. Extraer primero **Proyecto USB**. Si se van a usar tus registros actuales, extraer después **Datos PRIVADOS** en la misma ubicación, para que `.env`, `data/` y `agent/config.json` queden dentro de la misma carpeta `ContaSuite_Web_0_1`. Hacerlo **antes del primer arranque**; no sobrescribir una instalación del cliente que ya tenga datos.
3. Instalar Python **3.12 de 64 bits**, incluyendo el lanzador `py`. El primer arranque necesita Internet para preparar las dependencias; Codex no sustituye Python. El frontend ya está compilado y no necesita Node para usar la aplicación. No se copia `.venv` porque debe crearse para la ruta y Python de la nueva máquina.
4. Ejecutar `INICIAR_PRUEBA.bat`. El script conserva una configuración existente, crea el entorno e inicia aplicación e indexador. La base del respaldo puede ser anterior: el backend aplica las migraciones sobre **la copia extraída**, sin alterar los ZIP originales.
5. Si ya hay usuarios en la copia, usar sus cuentas. Si no existen, crear el primer administrador con la clave inicial mostrada por la consola. La clave inicial no restablece cuentas existentes.
6. Revisar `LISTO_PARA_VISITA.md` y ejecutar `VERIFICAR_VISITA.bat` después de preparar el entorno. Si se usó sólo Proyecto USB, la base empieza vacía y las claves se generan en esa computadora.

La base actual usa una ruta SQLite relativa dentro de `data/`, por lo que puede trasladarse junto con la carpeta. Las rutas de carpetas externas y del agente pertenecen a cada equipo: hay que autorizarlas/configurarlas nuevamente para las carpetas reales de la visita. Los documentos que sólo existan en orígenes externos no viajan por aparecer en el catálogo; este respaldo incluye los archivos guardados dentro del proyecto y de su `data/`.

## Continuar trabajando con Codex

Abre la carpeta extraída que contiene `AGENTS.md`. Como instrucción de continuidad puedes usar:

> Lee AGENTS.md, CONTINUAR_EN_CODEX.md, LISTO_PARA_VISITA.md y ABRIR_EN_OTRA_PC.md. Es la versión de visita de ContaSuite con frontend compilado, CS-Storage 1–5 y dashboard de certificados públicos. Conserva Stitch y los datos. Primero verifica el entorno y el estado actual sin recrear la base ni sobrescribir .env o agent/config.json. SMB remoto y acceso SAT no se deben presentar como implementados.

La documentación guarda el estado técnico para continuar sin depender de tener abierta esta conversación. Para modificar y volver a compilar el frontend también se necesitarán Node y las dependencias de `frontend/package-lock.json`; para ejecutarlo ya compilado basta el entorno Python del proyecto.
