/* Standalone browser-to-Ollama transport. No clinical API or persistent history. */
(function (root) {
  'use strict';
  const MAX_TEXT = 6000;
  const MAX_REPLY = 30000;
  function object(value) { return value && typeof value === 'object' && !Array.isArray(value); }
  function localAddress(value) {
    let url;
    try { url = new URL(value); } catch { throw new Error('Use a loopback Ollama address.'); }
    if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(url.hostname) ||
        url.username || url.password || url.search || url.hash || url.pathname !== '/') {
      throw new Error('Only http://127.0.0.1:PORT or http://localhost:PORT is allowed.');
    }
    return url.origin;
  }
  function localModel(model) {
    return model && typeof model.name === 'string' && model.name.length > 0 &&
      model.name.length < 200 && !/cloud/i.test(model.name) && !model.remote_host &&
      !model.remote_model && (!model.details || (!model.details.remote_host && !model.details.remote_model));
  }
  class Workspace {
    constructor(fetcher, changed = function () {}) {
      this.fetcher = fetcher;
      this.changed = changed;
      this.epoch = 0;
      this.controllers = new Set();
      this.address = '';
      this.models = [];
      this.busy = false;
    }
    clear(disconnect = false) {
      this.epoch += 1;
      this.controllers.forEach(controller => controller.abort());
      this.controllers.clear();
      this.busy = false;
      if (disconnect) { this.address = ''; this.models = []; }
      this.changed({type: 'cleared', connected: Boolean(this.address)});
    }
    async request(path, body, epoch) {
      if (epoch !== this.epoch || !this.address) throw new Error('Session cleared.');
      const controller = new AbortController();
      this.controllers.add(controller);
      const timer = setTimeout(() => controller.abort(), body && path === '/api/generate' ? 180000 : 15000);
      try {
        const response = await this.fetcher(this.address + path, {
          method: body ? 'POST' : 'GET', mode: 'cors', credentials: 'omit',
          redirect: 'error', cache: 'no-store', referrerPolicy: 'no-referrer',
          headers: body ? {'Content-Type': 'application/json'} : {},
          body: body ? JSON.stringify(body) : undefined, signal: controller.signal
        });
        if (response.status !== 200) throw new Error('Local model request failed.');
        const data = await response.json();
        if (epoch !== this.epoch || controller.signal.aborted) throw new Error('Session cleared.');
        return data;
      } finally {
        clearTimeout(timer);
        this.controllers.delete(controller);
      }
    }
    async connect(value, attested) {
      this.clear(true);
      if (!attested) throw new Error('Confirm that you control this local-only Ollama instance.');
      this.address = localAddress(value);
      const epoch = this.epoch;
      this.busy = true;
      try {
        const tags = await this.request('/api/tags', null, epoch);
        if (!tags || !Array.isArray(tags.models)) throw new Error('Invalid model list.');
        this.models = [...new Set(tags.models.filter(localModel).map(model => model.name))];
        if (!this.models.length) throw new Error('No eligible local models found.');
        this.changed({type: 'connected', models: this.models.slice()});
        return this.models.slice();
      } catch {
        if (epoch === this.epoch) {
          this.address = ''; this.models = [];
          throw new Error('Could not connect. Check Ollama, its exact allowed website origin and browser local-network permission.');
        }
        throw new Error('Session cleared.');
      } finally { if (epoch === this.epoch) this.busy = false; }
    }
    async run(model, text, review = null) {
      if (!this.address || !this.models.includes(model) || this.busy) throw new Error('Connect and choose an installed local model first.');
      if (typeof text !== 'string' || !text.trim() || new TextEncoder().encode(text).length > MAX_TEXT) throw new Error('Use 1–6000 UTF-8 bytes of synthetic text.');
      const epoch = this.epoch;
      this.busy = true;
      try {
        // Inspect the selected model before sending user text. Aliased cloud models may be in /tags.
        const details = await this.request('/api/show', {model}, epoch);
        if (!object(details) || details.remote_host || details.remote_model || !object(details.details) ||
            details.details.remote_host || details.details.remote_model ||
            !object(details.model_info) || !Object.keys(details.model_info).length || !Array.isArray(details.capabilities) ||
            !details.capabilities.includes('completion')) throw new Error('Model locality could not be established.');
        let contextWindow=8192;
        if(review){
          const lengths=Object.entries(details.model_info).filter(([key,value])=>key.endsWith('.context_length')&&Number.isSafeInteger(value)&&value>0).map(([,value])=>value);
          if(!lengths.length)throw new Error('Model context capacity is not declared.');
          contextWindow=Math.min(16384,...lengths);
          // UTF-8 bytes give a conservative input budget; reserve room for schema, template and output.
          const budget=new TextEncoder().encode(text+review.system+JSON.stringify(review.schema)).length+2048+512;
          if(budget>contextWindow)throw new Error('Complete report does not fit the verified model context.');
        }
        const data = await this.request('/api/generate', {
          model, prompt: text, stream: false,
          system: review ? review.system : 'Research test on synthetic text only. Do not diagnose or prescribe. Distinguish quoted facts from uncertainty. Your answer is unverified and requires human review.',
          ...(review ? {format: review.schema} : {}),
          options: {temperature: 0, num_predict: review?2048:768, num_ctx: contextWindow}, keep_alive: 0
        }, epoch);
        if (!data || data.error || data.model !== model || data.done !== true || data.done_reason !== 'stop' ||
            typeof data.response !== 'string' || !data.response.trim() || data.response.length > MAX_REPLY || /<\/?think\b/i.test(data.response)) {
          throw new Error('Incomplete or unexpected model response.');
        }
        this.changed({type: 'answer', text: data.response, model});
        return data.response;
      } catch {
        if (epoch === this.epoch) throw new Error('Local request failed or the model response could not be verified. No shared server was used.');
        throw new Error('Session cleared.');
      } finally { if (epoch === this.epoch) this.busy = false; }
    }
  }
  const api = {Workspace, localAddress, localModel};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.ClinLoopPrivate = api;
})(typeof window === 'undefined' ? globalThis : window);
