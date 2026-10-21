/* No analytics, shared API, local model requests or retained FHIR history. */
(function () {
  'use strict';
  const status = document.getElementById('status');
  const output = document.getElementById('reports');
  const start = document.getElementById('start');
  const disconnect = document.getElementById('disconnect');
  const client = new window.ClinLoopSmartSandbox.Sandbox();
  let active = true, redirecting = false, timer;
  function clear() {
    active = false; clearTimeout(timer); client.close(); output.replaceChildren();
    status.textContent = 'Disconnected. The records in this page have been cleared. Restart from the SMART launcher to connect again.';
    if (start) start.disabled = true;
  }
  function resetTimer() { clearTimeout(timer); if (active) timer = setTimeout(clear, 10 * 60 * 1000); }
  disconnect.addEventListener('click', clear);
  window.addEventListener('pagehide', () => {
    if (redirecting) { active = false; clearTimeout(timer); client.close(true); output.replaceChildren(); }
    else clear();
  });
  window.addEventListener('pageshow', event => { if (event.persisted) clear(); });
  document.addEventListener('pointerdown', resetTimer);
  document.addEventListener('keydown', resetTimer);
  resetTimer();
  const callback = location.pathname.endsWith('/callback.html');
  const original = location.href;
  const launcher = document.getElementById('launcher');
  if (launcher) launcher.href = window.ClinLoopSmartSandbox.launcherFor(original);
  if (callback) history.replaceState(null, '', location.pathname);
  async function run() {
    try {
      status.textContent = 'Checking the synthetic SMART sandbox connection…';
      if (!callback) {
        start.disabled = true;
        const target = await client.authorize(original, document.getElementById('synthetic').checked);
        if (active) { redirecting = true; location.replace(target); }
      } else {
        const result = await client.complete(original);
        if (!active) return;
        status.textContent = 'Connected to SMART R4 sandbox. Patient context verified. Read-only access succeeded.';
        const summary = document.createElement('p');
        summary.textContent = result.reports.length + ' synthetic diagnostic reports received. ' +
          (result.partial ? 'This is a partial list; additional records may exist.' : 'This search returned no additional page.') +
          ' Connection verification does not measure clinical accuracy.';
        output.appendChild(summary);
        for (const report of result.reports) {
          const article = document.createElement('article');
          const h = document.createElement('h3'); h.textContent = 'Report status: ' + report.status;
          const p = document.createElement('p'); p.className = 'report-text'; p.textContent = report.conclusion;
          article.append(h, p); output.appendChild(article);
        }
        if (!result.reports.length) {
          const empty = document.createElement('p');
          empty.textContent = 'No DiagnosticReport records were returned for the selected synthetic patient. This does not establish a normal result or completed follow-up.';
          output.appendChild(empty);
        }
      }
    } catch (_) {
      if (active) {
        client.close(); output.replaceChildren();
        status.textContent = 'Connection could not be verified. No clinical conclusion was made. Restart from the SMART launcher; confirm the launch URL, public client ID and redirect URL.';
        if (start) start.disabled = true;
      }
    }
  }
  if (callback) run();
  else start.addEventListener('click', () => {
    if (document.getElementById('synthetic').checked) run();
    else status.textContent = 'Confirm synthetic sandbox data before connecting.';
  });
})();
