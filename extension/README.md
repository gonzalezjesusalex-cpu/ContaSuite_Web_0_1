# Extensión ContaSuite – acceso al SAT (plan v1.1, Cambio 4)

Llena el acceso del portal del SAT (contraseña o e.firma) con lo guardado en el gestor de contraseñas de ContaSuite,
sólo cuando la persona lo pide desde ContaSuite («Entrar al SAT»).

## Flujo

1. En ContaSuite, el usuario autorizado (administrador o permiso explícito «ver contraseñas» de la empresa) pulsa
   «Entrar al SAT». Si no confirmó su contraseña en los últimos 5 minutos, se le pide.
2. ContaSuite emite un boleto de un solo uso que vence en 60 s (sólo se guarda su hash) y lo pasa a la extensión por
   `window.postMessage`. Queda en la bitácora de la bóveda.
3. La extensión canjea el boleto en `POST /api/credentials/tickets/redeem`, abre el portal del SAT y llena RFC y
   contraseña, o carga `.cer`, `.key` y contraseña de la e.firma. **No envía el formulario**: la persona revisa y entra.
4. El secreto sólo vive en la memoria del service worker para ese llenado; no se escribe en `chrome.storage`, en disco
   ni en registros.

## Instalación (Chrome o Edge)

1. `chrome://extensions` (o `edge://extensions`) → activar «Modo de desarrollador» → «Cargar descomprimida» → esta
   carpeta `extension/`.
2. En las opciones de la extensión, escribir la dirección de ContaSuite (p. ej. `http://servidor:8000`) y aceptar el
   permiso para esa dirección. Recargar ContaSuite.

## Pendiente de verificar en el equipo definitivo

- Los selectores de campos del portal del SAT se buscan por atributos (`rfc`, `password`, archivos `.cer`/`.key`) y
  no se probaron contra el portal real (no se usan credenciales reales en desarrollo). Las páginas de acceso son
  configurables en las opciones porque el SAT las cambia.
- El SAT puede pedir captcha en el acceso con contraseña: la extensión no lo resuelve.
