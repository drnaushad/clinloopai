(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const ui=window.ClinLoopUI||{set:(el,text)=>{el.textContent=text;}};
  const providers = {
    openai: {label: 'OpenAI', key: 'https://platform.openai.com/settings/organization/api-keys', models: 'https://developers.openai.com/api/docs/models'},
    anthropic: {label: 'Anthropic (Claude)', key: 'https://platform.claude.com/settings/keys', models: 'https://platform.claude.com/docs/en/about-claude/models/overview'},
    gemini: {label: 'Google Gemini', key: 'https://aistudio.google.com/api-keys', models: 'https://ai.google.dev/gemini-api/docs/models'}
  };
  let busy = false, epoch = 0, lastActivity = Date.now(), controller = null;
  function message(text) { ui.set($('status'),text); }
  function returnLink(){
    const link=$('open-review');
    if(link)link.href='https://clinloopai.app/review?provider='+$('provider').value+'&lang='+(document.documentElement.lang==='ko'?'ko':'en');
  }
  function lock(value) {
    busy = value;
    for (const id of ['check', 'save', 'forget', 'provider', 'model', 'key', 'code', 'confirm']) $(id).disabled = value;
  }
  function clear() {
    epoch++; if (controller) controller.abort(); controller = null;
    $('key').value = ''; $('code').value = ''; $('model').value = ''; $('confirm').checked = false;
    $('providers').replaceChildren(); lock(false);
    message('Form cleared. Gateway configuration is unchanged; use Forget selected provider to remove its key. A submitted setup may already have completed.');
  }
  function selection() {
    $('key').value = ''; $('model').value = ''; $('confirm').checked = false;
    const p = providers[$('provider').value];
    $('key-link').href = p.key; $('model-link').href = p.models;
    returnLink();
    message('Selected ' + p.label + '. Enter its model ID and API key. No provider request sent.');
  }
  async function request(path, body, code) {
    if (location.origin !== 'http://127.0.0.1:18127') throw Error('local-only');
    const active = controller, signal = active.signal;
    const timer = setTimeout(() => active.abort(), 15000);
    try {
      const result = await fetch(path, {method: body ? 'POST' : 'GET', headers: {Authorization: 'Bearer ' + code, ...(body ? {'Content-Type': 'application/json'} : {})},
        body: body ? JSON.stringify(body) : undefined, credentials: 'omit', cache: 'no-store', redirect: 'error', signal});
      if (!result.ok) throw Error('setup-rejected');
      return await result.json();
    } finally { clearTimeout(timer); }
  }
  async function perform(action) {
    if (busy) return;
    const current = epoch, provider = $('provider').value, code = $('code').value;
    // Drop the password field immediately; never restore it after an error.
    const key = $('key').value; $('key').value = '';
    if (!/^[A-Za-z0-9_-]{32,128}$/.test(code) || /^(sk-|AIza)/i.test(code)) { message('Enter the separate gateway access code from your private file.'); return; }
    let body;
    if (action === 'save') {
      if (!$('confirm').checked || !/^[!-~]{16,512}$/.test(key) || !/^[A-Za-z0-9._-]{1,160}$/.test($('model').value) || /^(sk-|AIza)/i.test($('model').value)) {
        message('Check the synthetic-research confirmation, exact model ID and provider API key.'); return;
      }
      body = {provider, model: $('model').value, api_key: key};
    } else if (action === 'forget') body = {provider};
    controller = new AbortController(); lock(true); message('Updating your personal gateway…');
    try {
      await request(action === 'save' ? '/review/configure' : action === 'forget' ? '/review/forget' : '/review/status', body, code);
      if (current !== epoch) return;
      const result = await request('/review/status', null, code);
      if (current !== epoch) return;
      $('providers').replaceChildren();
      for (const item of result.providers || []) {
        const li = document.createElement('li');
        ui.set(li,providers[item.id].label + ': ' + (item.configured ? item.model + ' — configured, not provider-verified' : 'not configured'));
        $('providers').append(li);
      }
      message(action === 'save' ? 'Provider configured in gateway memory. No API call or charge was made. Continue to Report review with your gateway access code.' : action === 'forget' ? 'Selected provider forgotten by this gateway. No provider credential was revoked.' : 'Configuration loaded. No provider API request made.');
    } catch (_) {
      if (current === epoch) message('Setup could not be confirmed. Check the gateway access code and local gateway. A submitted change may already have completed; check configured providers before retrying.');
    } finally {
      if (current === epoch) { $('key').value = ''; lock(false); controller = null; }
    }
  }
  $('provider').addEventListener('change', selection);
  for (const action of ['check', 'save', 'forget']) $(action).addEventListener('click', () => perform(action));
  $('clear').addEventListener('click', clear);
  window.addEventListener('pagehide', clear);
  window.addEventListener('pageshow', event => { if (event.persisted) clear(); });
  for (const name of ['pointerdown', 'keydown', 'input']) document.addEventListener(name, () => { lastActivity = Date.now(); }, {passive: true});
  setInterval(() => { if (Date.now() - lastActivity >= 600000) { clear(); lastActivity = Date.now(); } }, 10000);
  if(window.URLSearchParams){
    const requested=new window.URLSearchParams(window.location.search).get('provider');
    if(Object.prototype.hasOwnProperty.call(providers,requested))$('provider').value=requested;
  }
  if(window.MutationObserver)new window.MutationObserver(returnLink).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
  selection();
})();
