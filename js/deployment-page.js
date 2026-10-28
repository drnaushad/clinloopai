(async function () {
  'use strict';
  const ui=(typeof window !== 'undefined' && window.ClinLoopUI)||{set:(e,v)=>{e.textContent=v;},source:(e,v)=>{e.textContent=v;},reset:()=>{}};
  const $ = id => document.getElementById(id);
  let catalog, plan;
  function invalidate() { plan = null; $('download').disabled = true; $('result').hidden = true; }
  function list(id, values) {
    $(id).replaceChildren();
    for (const value of values) { const li = document.createElement('li'); ui.set(li, value); $(id).append(li); }
  }
  $('setup').addEventListener('input', () => { invalidate(); ui.set($('message'), 'Build a new plan to check these settings.'); });
  $('setup').addEventListener('submit', event => {
    event.preventDefault(); invalidate();
    try {
      plan = window.ClinLoopDeployment.build({country:$('country').value,language:$('language').value,
        timeZone:$('timezone').value,dateFormat:$('dates').value,
        modules:Array.from(document.querySelectorAll('input[name="module"]:checked'), input=>input.value)},catalog);
      ui.source($('setting'), plan.country_or_region+' · '+plan.report_language+' · '+plan.time_zone);
      list('warnings',plan.warnings);list('reviews',plan.required_reviews);
      ui.source($('plan'), JSON.stringify(plan,null,2));
      $('result').hidden = false;$('download').disabled = false;
      ui.set($('message'), 'Planning checks complete. The running system and clinical authorization are unchanged.');
    } catch (error) { ui.set($('message'), error.message); }
  });
  $('download').addEventListener('click', () => {
    if (!plan) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(plan,null,2)+'\n'],{type:'application/json'}));
    const a = document.createElement('a');a.href=url;a.download='clinloop-deployment-plan.json';
    document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  try {
    const response = await fetch('data/deployment_modules.json',{cache:'no-store'});
    if (!response.ok) throw new Error();catalog=await response.json();$('modules').replaceChildren();
    for (const module of catalog.report_modules) {
      const label=document.createElement('label'), input=document.createElement('input');
      input.type='checkbox';input.name='module';input.value=module.id;
      const name=document.createElement('span');ui.set(name,module.name);label.append(input,name);$('modules').append(label);
      const tr=document.createElement('tr');
      for(const value of [module.name,module.available,module.needs]) {const td=document.createElement('td');ui.set(td, value);tr.append(td)}
      $('capabilities').append(tr);
    }
    for(const source of catalog.sources) {
      const a=document.createElement('a');a.href=source.url;ui.set(a, source.title);
      $('sources').append(a,document.createTextNode(' · '));
    }
    $('generate').disabled=false;ui.set($('message'), 'Enter settings only. No report upload is offered on this page.');
  } catch (_) { ui.set($('message'), 'Planning requirements are unavailable. No deployment readiness can be inferred.'); }
})();
