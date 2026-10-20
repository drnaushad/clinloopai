(async function () {
  'use strict';
  const $ = id => document.getElementById(id);
  let catalog, plan;
  function invalidate() { plan = null; $('download').disabled = true; $('result').hidden = true; }
  function list(id, values) {
    $(id).replaceChildren();
    for (const value of values) { const li = document.createElement('li'); li.textContent = value; $(id).append(li); }
  }
  $('setup').addEventListener('input', () => { invalidate(); $('message').textContent = 'Build a new plan to check these settings.'; });
  $('setup').addEventListener('submit', event => {
    event.preventDefault(); invalidate();
    try {
      plan = window.ClinLoopDeployment.build({country:$('country').value,language:$('language').value,
        timeZone:$('timezone').value,dateFormat:$('dates').value,
        modules:Array.from(document.querySelectorAll('input[name="module"]:checked'), input=>input.value)},catalog);
      $('setting').textContent = plan.country_or_region+' · '+plan.report_language+' · '+plan.time_zone;
      list('warnings',plan.warnings);list('reviews',plan.required_reviews);
      $('plan').textContent = JSON.stringify(plan,null,2);
      $('result').hidden = false;$('download').disabled = false;
      $('message').textContent = 'Planning checks complete. The running system and clinical authorization are unchanged.';
    } catch (error) { $('message').textContent = error.message; }
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
      label.append(input,document.createTextNode(module.name));$('modules').append(label);
      const tr=document.createElement('tr');
      for(const value of [module.name,module.available,module.needs]) {const td=document.createElement('td');td.textContent=value;tr.append(td)}
      $('capabilities').append(tr);
    }
    for(const source of catalog.sources) {
      const a=document.createElement('a');a.href=source.url;a.textContent=source.title;
      $('sources').append(a,document.createTextNode(' · '));
    }
    $('generate').disabled=false;$('message').textContent='Enter settings only. No report upload is offered on this page.';
  } catch (_) { $('message').textContent='Planning requirements are unavailable. No deployment readiness can be inferred.'; }
})();
