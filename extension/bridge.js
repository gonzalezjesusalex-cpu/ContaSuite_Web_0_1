// Runs only on the ContaSuite address configured in the options. It marks the page so ContaSuite knows the
// extension is installed and relays the one-time ticket to the background worker. No secret passes here.
document.documentElement.dataset.contasuiteExtension = chrome.runtime.getManifest().version;

window.addEventListener('message', (event) => {
  if (event.source !== window || event.origin !== location.origin) return;
  const data = event.data || {};
  if (data.source !== 'contasuite-page' || data.type !== 'autofill' || typeof data.ticket !== 'string') return;
  chrome.runtime.sendMessage(
    { type: 'autofill', ticket: data.ticket, purpose: data.purpose },
    (reply) => {
      const error = chrome.runtime.lastError;
      window.postMessage(
        {
          source: 'contasuite-extension',
          id: data.id,
          ok: !error && !!reply && reply.ok,
          message: error ? 'La extensión no está disponible.' : reply && reply.message,
        },
        location.origin,
      );
    },
  );
});
