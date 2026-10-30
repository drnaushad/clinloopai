/* A settings-only planning tool. It neither imports reports nor changes clinical rules. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ClinLoopDeployment = api;
})(typeof window === 'object' ? window : this, function () {
  'use strict';
  function build(input, catalog) {
    const country = String(input.country || '').trim();
    if (country.length < 2 || country.length > 80 || /[<>\u0000-\u001f]/.test(country)) throw new Error('Enter the country or region where the hospital operates.');
    let language;
    try {
      const raw = String(input.language || '').trim();
      if (!raw || raw.length > 60) throw new Error();
      language = Intl.getCanonicalLocales(raw)[0];
    } catch (_) { throw new Error('Enter a language tag such as en, ko, hi, ar, es or fr.'); }
    const timeZone = String(input.timeZone || '').trim();
    try {
      if (!timeZone || timeZone.length > 100) throw new Error();
      new Intl.DateTimeFormat('en', { timeZone }).format(new Date(0));
    } catch (_) { throw new Error('Enter an IANA time zone such as Asia/Seoul, Asia/Kolkata or Europe/London.'); }
    const formats = ['iso8601', 'day_first_confirmed', 'month_first_confirmed'];
    if (!formats.includes(input.dateFormat)) throw new Error('Choose a source-date convention confirmed by the institution.');
    if (!Array.isArray(input.modules) || !input.modules.length || new Set(input.modules).size !== input.modules.length) throw new Error('Choose at least one distinct report type.');
    const selected = input.modules.map(id => {
      const item = catalog.report_modules.find(m => m.id === id);
      if (!item) throw new Error('Unsupported report type in this planner.');
      return { id: item.id, name: item.name, existing_capability: item.available, required_validation: item.needs, clinical_validation: 'not_established' };
    });
    const warnings = [
      'Country selection does not apply a local guideline pack or establish legal eligibility.',
      'Language selection does not translate reports or activate a validated clinical parser.',
      'The chosen date convention is a planning requirement; ambiguous source dates require verification before import.',
      'Original values, units, reference ranges, source text and timestamps must remain traceable; missing information must remain unresolved.',
      'Guidelines and deadlines need institution-specific review; changing display language must not change clinical meaning.'
    ];
    if (!['en', 'ko'].includes(language.split('-')[0])) warnings.push('Published report-text checks currently cover English/Korean examples; this report language requires new language-specific evaluation.');
    return {
      schema_version: 1, status: 'planning_only', clinical_authorization: 'not_established',
      runtime_configuration_changed: false,
      country_or_region: country, report_language: language, time_zone: timeZone,
      source_date_convention: input.dateFormat, unit_policy: 'preserve_original_and_verify_local_reference_ranges',
      modules: selected, required_reviews: catalog.required_reviews.slice(), warnings,
      evidence_page: 'https://clinloopai.app/validation', catalog_version: catalog.version
    };
  }
  return { build };
});
