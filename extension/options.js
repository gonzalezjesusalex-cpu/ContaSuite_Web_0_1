const DEFAULTS = {
  server: '',
  ciecUrl: 'https://portalcfdi.facturaelectronica.sat.gob.mx/',
  fielUrl: 'https://portalcfdi.facturaelectronica.sat.gob.mx/',
};
const $ = (id) => document.getElementById(id);

chrome.storage.sync.get(Object.keys(DEFAULTS)).then((saved) => {
  const s = { ...DEFAULTS, ...saved };
  $('server').value = s.server;
  $('ciec').value = s.ciecUrl;
  $('fiel').value = s.fielUrl;
});

$('save').addEventListener('click', async () => {
  const status = $('status');
  let origin;
  try {
    origin = new URL($('server').value.trim()).origin;
  } catch {
    status.textContent = 'Escribe una dirección válida.';
    return;
  }
  // Ask for access to that single address, then run the bridge only there.
  const granted = await chrome.permissions.request({ origins: [origin + '/*'] });
  if (!granted) {
    status.textContent = 'Sin permiso para esa dirección; no se guardó.';
    return;
  }
  const previous = await chrome.scripting.getRegisteredContentScripts({ ids: ['contasuite-bridge'] });
  if (previous.length) await chrome.scripting.unregisterContentScripts({ ids: ['contasuite-bridge'] });
  await chrome.scripting.registerContentScripts([
    { id: 'contasuite-bridge', matches: [origin + '/*'], js: ['bridge.js'], runAt: 'document_start', persistAcrossSessions: true },
  ]);
  await chrome.storage.sync.set({ server: origin, ciecUrl: $('ciec').value.trim(), fielUrl: $('fiel').value.trim() });
  status.textContent = 'Guardado. Recarga ContaSuite para activar el acceso al SAT.';
});
