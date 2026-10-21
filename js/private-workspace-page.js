(function () {
  'use strict';
  const byId = id => document.getElementById(id);
  const status = byId('status');
  let lastActivity = Date.now();
  let uiEpoch = 0;
  const workspace = new window.ClinLoopPrivate.Workspace(window.fetch.bind(window), event => {
    if (event.type === 'cleared') {
      uiEpoch += 1;
      byId('prompt').value = '';
      byId('answer').textContent = 'No response yet.';
      if (!event.connected) {
        byId('model').replaceChildren(new Option('Connect first', ''));
        byId('local-only').checked = false;
      }
      sync();
    }
    if (event.type === 'connected') {
      byId('local-only').checked = true;
      byId('model').replaceChildren(...event.models.map(name => new Option(name, name)));
      status.textContent = 'Connected directly to your loopback Ollama. Conversation history is not saved by this page.';
      lastActivity = Date.now();
    }
    if (event.type === 'answer') byId('answer').textContent = event.text;
  });
  function sync() {
    const connected = Boolean(workspace.address && workspace.models.length);
    byId('connect').disabled = workspace.busy;
    byId('endpoint').disabled = connected || workspace.busy;
    byId('local-only').disabled = connected || workspace.busy;
    ['model', 'prompt', 'sample', 'run'].forEach(id => { byId(id).disabled = !connected || workspace.busy; });
  }
  byId('connect-form').addEventListener('submit', async event => {
    event.preventDefault();
    const operation = workspace.connect(byId('endpoint').value, byId('local-only').checked);
    const current = uiEpoch;
    status.textContent = 'Connecting to your own Ollama…'; sync();
    try { await operation; } catch (error) { if (current === uiEpoch) status.textContent = error.message; }
    if (current === uiEpoch) sync();
  });
  byId('run').addEventListener('click', async () => {
    const current = uiEpoch;
    byId('answer').textContent = 'Waiting for your local model…';
    const operation = workspace.run(byId('model').value, byId('prompt').value);
    status.textContent = 'Processing locally. The response will be unverified.'; sync();
    try { await operation; if (current === uiEpoch) status.textContent = 'Local response received. No conversation history saved.'; }
    catch (error) {
      if (current === uiEpoch) { byId('answer').textContent = 'No verified response available.'; status.textContent = error.message; }
    }
    if (current === uiEpoch) sync();
  });
  byId('sample').addEventListener('click', () => {
    byId('prompt').value = 'Fictional report for a synthetic adult: a small pulmonary nodule is described. The reporting clinician recommends comparison with prior imaging. List the explicitly stated follow-up request and missing context. Do not invent a deadline or diagnosis.';
  });
  function clear(disconnect) {
    workspace.clear(disconnect);
    status.textContent = disconnect ? 'Disconnected. Workspace cleared.' : 'Conversation cleared. Your model connection is still available.';
  }
  byId('clear').addEventListener('click', () => clear(false));
  byId('disconnect').addEventListener('click', () => clear(true));
  ['pointerdown', 'keydown', 'input'].forEach(name => document.addEventListener(name, () => { lastActivity = Date.now(); }, {passive: true}));
  setInterval(() => { if (Date.now() - lastActivity >= 600000) { clear(true); lastActivity = Date.now(); } }, 10000);
  window.addEventListener('pagehide', () => clear(true));
  window.addEventListener('pageshow', () => { lastActivity = Date.now(); sync(); });
  // Do not restore form values from browser history or a duplicated tab.
  byId('prompt').value = '';
  byId('local-only').checked = false;
  sync();
})();
