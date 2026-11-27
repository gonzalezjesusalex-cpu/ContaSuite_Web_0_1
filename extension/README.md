# Extensión ContaSuite – acceso al SAT (plan v1.1, Cambio 4)

Llena el acceso del portal del SAT con contraseña (CIEC) guardada en el gestor de contraseñas de ContaSuite, sólo
cuando la persona lo pide desde ContaSuite («Entrar al SAT»).

> Renovación del gestor, fase 3: la e.firma ya **no** se entrega a la extensión. El servidor nunca envía el `.cer` ni
> el `.key` por HTTP (un boleto `sat_fiel` responde 422). El acceso con e.firma lo hará Declara desde el servidor con
> `obtener_fiel_para_acceso`. El código de la extensión para cargar archivos queda sin uso.

## Flujo

1. En ContaSuite, una persona con acceso a la bóveda (administrador o persona autorizada) pulsa «Entrar al SAT»
   con la bóveda desbloqueada con su contraseña maestra.
2. ContaSuite emite un boleto de un solo uso que vence en 60 s (sólo se guarda su hash) y lo pasa a la extensión por
   `window.postMessage`. Queda en la bitácora de la bóveda.
3. La extensión canjea el boleto en `POST /api/credentials/tickets/redeem`, abre el portal del SAT y llena RFC y
   contraseña. **No envía el formulario**: la persona revisa y entra.
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
