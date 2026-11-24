// ContaSuite extension, plan v1.1 (Cambio 4). The secret is requested with a single-use, 60-second ticket issued
// by ContaSuite after the person re-authenticated; it lives only in this worker's memory for one fill and is never
// written to storage, logs or disk. The page of the SAT receives it through a script injected into that tab only.

const DEFAULTS = {
  server: '',
  // Login addresses of the SAT; editable in the options because the SAT changes them.
  ciecUrl: 'https://portalcfdi.facturaelectronica.sat.gob.mx/',
  fielUrl: 'https://portalcfdi.facturaelectronica.sat.gob.mx/',
};

async function settings() {
  return { ...DEFAULTS, ...(await chrome.storage.sync.get(Object.keys(DEFAULTS))) };
}

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message?.type !== 'autofill') return false;
  handle(message, sender)
    .then((text) => reply({ ok: true, message: text }))
    .catch((err) => reply({ ok: false, message: err.message || 'No se pudo completar.' }));
  return true;
});

async function handle(message, sender) {
  const config = await settings();
  const origin = sender.url ? new URL(sender.url).origin : '';
  // Only the ContaSuite address configured by the person may ask for a fill.
  if (!config.server || origin !== config.server || sender.id !== chrome.runtime.id) {
    throw new Error('Esta página no es la dirección de ContaSuite configurada en la extensión.');
  }
  let data = await redeem(config.server, message.ticket);
  const url = data.purpose === 'sat_fiel' ? config.fielUrl : config.ciecUrl;
  const tab = await chrome.tabs.create({ url, active: true });
  await loaded(tab.id);
  let filled = false;
  for (let attempt = 0; attempt < 10 && !filled; attempt++) {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      func: fill,
      args: [data],
    });
    filled = results.some((r) => r.result === true);
    if (!filled) await new Promise((r) => setTimeout(r, 1000));
  }
  data = null; // Drop the secret as soon as the fill was attempted.
  if (!filled) {
    throw new Error('Se abrió el portal del SAT, pero no se encontraron los campos de acceso. Captúralos a mano.');
  }
  return 'Acceso llenado en el portal del SAT. Revisa y entra; ContaSuite no envía el formulario por ti.';
}

async function redeem(server, ticket) {
  const response = await fetch(server + '/api/credentials/tickets/redeem', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'omit',
    cache: 'no-store',
    body: JSON.stringify({ ticket }),
  });
  if (!response.ok) throw new Error('El boleto de ContaSuite venció o ya se usó. Vuelve a intentarlo desde ContaSuite.');
  return response.json();
}

function loaded(tabId) {
  return new Promise((resolve) => {
    const done = (id, info) => {
      if (id === tabId && info.status === 'complete') {
        chrome.tabs.onUpdated.removeListener(done);
        resolve();
      }
    };
    chrome.tabs.onUpdated.addListener(done);
    setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(done);
      resolve();
    }, 20000);
  });
}

// Injected into the SAT tab (all frames). Finds the access fields by their attributes; never submits.
function fill(data) {
  const visible = (el) => !!el && el.offsetParent !== null && !el.disabled;
  const setValue = (el, value) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(el, value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const inputs = () => Array.from(document.querySelectorAll('input'));
  const byHint = (re, type) =>
    inputs().find((el) => (!type || el.type === type) && visible(el) && re.test([el.id, el.name, el.placeholder].join(' ')));
  if (data.purpose === 'sat_fiel') {
    // Switch to the e.firma form when the page offers it.
    const efirma = Array.from(document.querySelectorAll('button, a, input[type=button]')).find((el) =>
      /e\.?firma/i.test(el.textContent || el.value || ''),
    );
    const files = inputs().filter((el) => el.type === 'file');
    if (files.length < 2 && efirma && visible(efirma)) efirma.click();
    const cer = inputs().find((el) => el.type === 'file' && /cer|certif/i.test([el.id, el.name, el.accept].join(' ')));
    const key = inputs().find((el) => el.type === 'file' && /key|llave|privad/i.test([el.id, el.name, el.accept].join(' ')));
    const pass = inputs().find((el) => el.type === 'password' && visible(el));
    if (!cer || !key || !pass || !data.cer || !data.key) return false;
    const toFile = (part) => {
      const bytes = Uint8Array.from(atob(part.data), (c) => c.charCodeAt(0));
      return new File([bytes], part.name, { type: 'application/octet-stream' });
    };
    for (const [input, part] of [
      [cer, data.cer],
      [key, data.key],
    ]) {
      const transfer = new DataTransfer();
      transfer.items.add(toFile(part));
      input.files = transfer.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }
    setValue(pass, data.password);
    const rfc = byHint(/rfc/i);
    if (rfc && !rfc.value) setValue(rfc, data.rfc);
    return true;
  }
  const rfc = byHint(/rfc|usuario|user/i, 'text') || byHint(/rfc/i);
  const pass = inputs().find((el) => el.type === 'password' && visible(el));
  if (!rfc || !pass) return false;
  setValue(rfc, data.username || data.rfc);
  setValue(pass, data.password);
  pass.focus();
  return true;
}
