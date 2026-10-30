(function () {
  'use strict';
  const ui=(typeof window !== 'undefined' && window.ClinLoopUI)||{set:(e,v)=>{e.textContent=v;},source:(e,v)=>{e.textContent=v;},reset:()=>{}};
  const placeholder=()=>{const option=new Option('Connect first','');ui.set(option,'Connect first');return option;};
  const byId = id => document.getElementById(id);
  const status = byId('status');
  let lastActivity = Date.now();
  let uiEpoch = 0;
  const workspace = new window.ClinLoopPrivate.Workspace(window.fetch.bind(window), event => {
    if (event.type === 'cleared') {
      uiEpoch += 1;
      byId('prompt').value = '';
      ui.set(byId('answer'), 'No response yet.');
      if (!event.connected) {
        byId('model').replaceChildren(placeholder());
        byId('local-only').checked = false;
      }
      sync();
    }
    if (event.type === 'connected') {
      byId('local-only').checked = true;
      byId('model').replaceChildren(...event.models.map(name => new Option(name, name)));
      ui.set(status, 'Connected directly to your loopback Ollama. Conversation history is not saved by this page.');
      lastActivity = Date.now();
    }
    if (event.type === 'answer') ui.source(byId('answer'), event.text);
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
    if (expireIfIdle()) return;
    const operation = workspace.connect(byId('endpoint').value, byId('local-only').checked);
    const current = uiEpoch;
    ui.set(status, 'Connecting to your own Ollama…'); sync();
    try { await operation; } catch (error) { if (current === uiEpoch) ui.set(status, error.message); }
    if (current === uiEpoch) sync();
  });
  byId('run').addEventListener('click', async () => {
    if (expireIfIdle()) return;
    const current = uiEpoch;
    ui.set(byId('answer'), 'Waiting for your local model…');
    const operation = workspace.run(byId('model').value, byId('prompt').value);
    ui.set(status, 'Processing locally. The response will be unverified.'); sync();
    try { await operation; if (current === uiEpoch) ui.set(status, 'Local response received. No conversation history saved.'); }
    catch (error) {
      if (current === uiEpoch) { ui.set(byId('answer'), 'No verified response available.'); ui.set(status, error.message); }
    }
    if (current === uiEpoch) sync();
  });
  byId('sample').addEventListener('click', () => {
    byId('prompt').value = 'Fictional report for a synthetic adult: a small pulmonary nodule is described. The reporting clinician recommends comparison with prior imaging. List the explicitly stated follow-up request and missing context. Do not invent a deadline or diagnosis.';
  });
  function clear(disconnect) {
    workspace.clear(disconnect);
    ui.set(status, disconnect ? 'Disconnected. Workspace cleared.' : 'Conversation cleared. Your model connection is still available.');
  }
  byId('clear').addEventListener('click', () => clear(false));
  byId('disconnect').addEventListener('click', () => clear(true));
  function expireIfIdle() {
    if (Date.now() - lastActivity < 600000) return false;
    clear(true); lastActivity = Date.now(); return true;
  }
  // A suspended tab may not run its timer. Expire before accepting activity,
  // otherwise the first keystroke could renew an already expired session.
  ['pointerdown', 'keydown', 'input'].forEach(name => document.addEventListener(name, () => {
    expireIfIdle(); lastActivity = Date.now();
  }, {passive: true}));
  document.addEventListener('visibilitychange', () => { if (!document.hidden) expireIfIdle(); });
  setInterval(expireIfIdle, 10000);
  window.addEventListener('pagehide', () => clear(true));
  window.addEventListener('pageshow', event => {
    if (event.persisted) clear(true); else expireIfIdle();
    lastActivity = Date.now(); sync();
  });
  // Do not restore form values from browser history or a duplicated tab.
  byId('prompt').value = '';
  byId('local-only').checked = false;
  sync();
})();
