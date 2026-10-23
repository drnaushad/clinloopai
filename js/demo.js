/**
 * demo.js: the public demo, for anyone, on any device.
 *
 * Two cases:
 *  1. A ClinLoop server started with CLINLOOP_DEMO=1 sets window.CLINLOOP_DEMO (in /config.js):
 *     banner, published view-only token, automatic sign-in.
 *  2. The public website (clinloopai.app) has no server at all. The clinical pages then read a
 *     read-only snapshot of the demo (demo/api/, built by scripts/build_static_demo.py) through
 *     the same requests they would send to a server: the whole app works from static files, so
 *     any number of people can use it at once. Practice mode (on by default there) answers the
 *     actions too, in the browser only: acknowledge, assign, defer, close, patient messages, rule
 *     sign-off and second-reader verdicts work on the synthetic patients and are kept in this
 *     browser until "Reset". Nothing is sent anywhere.
 * On a hospital's own server neither applies and this script does nothing.
 */
(function () {
  'use strict';
  var CLINICAL_PAGE = /\/(worklist|patient|quality|governance|imaging|pilot)(\.html)?$/;   // GitHub Pages also serves /worklist
  var local = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(window.location.hostname);
  var STATIC_PATH = '/__static-demo__';

  if (!window.CLINLOOP_DEMO && window.CLINLOOP_API_BASE == null && !local &&
      CLINICAL_PAGE.test(window.location.pathname) && window.fetch) {
    startStatic();
  }
  var demo = window.CLINLOOP_DEMO;
  if (!demo || !demo.token) return;

  // ── 2. static snapshot ────────────────────────────────────────────────────
  function startStatic() {
    var base = window.location.origin + STATIC_PATH;
    window.CLINLOOP_API_BASE = base;
    document.documentElement.classList.add('static-demo');      // hides the server connection form
    window.CLINLOOP_DEMO = {
      token: 'public-demo-static', static: true,
      note: 'Public demo: synthetic patients only, read-only snapshot. Do not enter real patient information.'
    };
    var realFetch = window.fetch.bind(window);
    function explainSnapshot() {
      var note = document.createElement('p');
      note.id = 'snapshot-status'; note.setAttribute('role', 'note');
      note.textContent = 'Synthetic snapshot · no live hospital connection. Actions here are browser-only simulations. / 합성 예시 · 실제 병원 연결 없음.';
      note.style.cssText = 'margin:12px;padding:10px;border:1px solid currentColor;border-radius:8px;font-size:.9rem';
      var shell = document.querySelector('.wrap');
      if (shell) { var heading = shell.querySelector('header'); if (heading) heading.after(note); else shell.prepend(note); }
      else document.body.prepend(note);
      var forms = document.querySelectorAll('#note-form, #report-form, #file-form, #dicom-form, #ct-form');
      forms.forEach(function (form) {
        var help = document.createElement('p');
        help.textContent = 'Unavailable on this public snapshot. Use an approved local installation, or try synthetic text in Analyse patient. / 공개 예시에서는 사용할 수 없습니다.';
        var link = document.createElement('a'); link.href = 'analyse'; link.textContent = ' Analyse patient'; help.append(link);
        form.before(help);
        var disclosure = document.createElement('details');
        disclosure.className = 'snapshot-tools';
        var summary = document.createElement('summary');
        summary.textContent = 'View local-installation controls (unavailable in this demo) / 로컬 설치용 기능 보기';
        form.before(disclosure); disclosure.append(summary); disclosure.append(form);
        form.querySelectorAll('input,textarea,select,button').forEach(function (control) { control.disabled = true; });
        form.addEventListener('submit', function (event) { event.preventDefault(); event.stopImmediatePropagation(); }, true);
      });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', explainSnapshot);
    else explainSnapshot();

    function fnv1a(text) {
      var bytes = new TextEncoder().encode(text), h = 0x811c9dc5;
      for (var i = 0; i < bytes.length; i++) {
        h ^= bytes[i];
        h = Math.imul(h, 0x01000193) >>> 0;
      }
      return ('0000000' + h.toString(16)).slice(-8);
    }
    function reply(status, body) {
      return Promise.resolve(new Response(JSON.stringify(body), {
        status: status, headers: { 'Content-Type': 'application/json' }
      }));
    }
    function snapshot(path, params) {
      var pairs = [];
      Object.keys(params || {}).forEach(function (k) { if (params[k] !== '' && params[k] != null) pairs.push([k, String(params[k])]); });
      pairs.sort(function (a, b) { return a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0; });
      var key = path + (pairs.length ? '?' + pairs.map(function (p) { return p[0] + '=' + p[1]; }).join('&') : '');
      return realFetch(new URL('demo/api/' + fnv1a(key) + '.json', window.location.href).href)
        .then(function (r) {
          if (!r.ok) return { status: 404, body: { detail: 'Not part of the public demo snapshot. ' +
            'Try a listed patient, or run your own server for anything else.' } };
          // A role-limited endpoint is stored as its refusal ({__status, detail}) and answered the same way
          return r.json().then(function (body) {
            return body && body.__status ? { status: body.__status, body: { detail: body.detail } } : { status: 200, body: body };
          });
        })
        .catch(function () { return { status: 503, body: { detail: 'Could not load the demo snapshot. Check your connection.' } }; });
    }
    window.CLINLOOP_PRACTICE = practiceLayer(snapshot, reply);
    window.fetch = function (input, opts) {
      var url = typeof input === 'string' ? input : (input && input.url) || '';
      if (url.indexOf(base) !== 0) return realFetch(input, opts);
      var method = ((opts && opts.method) || (input && input.method) || 'GET').toUpperCase();
      var u = new URL(url);
      var path = decodeURIComponent(u.pathname.slice(STATIC_PATH.length));
      var params = {};
      u.searchParams.forEach(function (v, k) { params[k] = v; });
      var body = null;
      try { body = opts && opts.body ? JSON.parse(opts.body) : null; } catch (e) { body = null; }
      var handled = window.CLINLOOP_PRACTICE.handle(method, path, params, body);
      if (handled) return handled;
      if (method !== 'GET') {
        return reply(403, { detail: 'This public demo cannot do this: it needs your own ClinLoop server ' +
          '(see the README: one command with Docker). Practice mode covers the worklist, rule sign-off and ' +
          'second-reader review.' });
      }
      return snapshot(path, params).then(function (r) { return reply(r.status, r.body); });
    };
  }

  // ── practice mode: act on the synthetic patients, in this browser only ─────
  // Every action the clinical pages send is answered here with the same rules the server applies
  // (which state a loop may move from, required fields, who may do what), and kept in this
  // browser's storage until "Reset". Nothing leaves the browser. The snapshot stays the same.
  function practiceLayer(snapshot, reply) {
    var KEY = 'clinloop_practice_v1';
    var USER = { user: 'practice.clinician', role: 'clinician' };
    var STAFF = ['practice.clinician', 'dr.kim', 'dr.lee', 'nurse.park', 'navigator.choi'];
    var ACTIVE = ['new', 'acknowledged'];
    var REASONS = ['patient_declined', 'completed_elsewhere', 'not_clinically_indicated'];
    function fresh() {
      return { on: true, seq: 0, loops: {}, audit: {}, messages: {}, prefs: {}, reviews: {}, verdicts: {},
               started: new Date().toISOString() };
    }
    var st = fresh();
    try {
      var saved = JSON.parse(window.localStorage.getItem(KEY) || 'null');
      if (saved && saved.loops) st = saved;
    } catch (e) { /* storage blocked: practice still works until the page is closed */ }
    function save() { try { window.localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) { /* not kept */ } }
    function now() { return new Date().toISOString().slice(0, 19); }
    function err(status, detail) { return reply(status, { detail: detail }); }
    function audit(key, action, detail) {
      st.seq += 1;
      (st.audit[key] = st.audit[key] || []).push({ id: 100000 + st.seq, ts: now(), actor: USER.user, role: USER.role,
        action: action, loop_key: key, detail: detail || {}, practice: true });
    }
    function loopState(loop) { return Object.assign({}, loop, st.loops[loop.loop_key] || {}); }
    function overlayLoop(loop) {
      var l = loopState(loop);
      if (st.reviews[l.rule_id]) l.rule_signoff = ruleStatus(l.rule_id, { status: l.rule_signoff }).status;
      return l;
    }
    function allLoops() {
      return snapshot('/api/v1/worklist', { include_inactive: 'true' }).then(function (r) {
        return r.status === 200 ? r.body : null;
      });
    }
    function findLoop(key) {
      return allLoops().then(function (wl) {
        return wl ? (wl.loops.filter(function (l) { return l.loop_key === key; })[0] || null) : null;
      });
    }
    // A workflow step: allowed only from the states the server allows it from
    function transition(key, action, from, change, detail) {
      return findLoop(key).then(function (loop) {
        if (!loop) return err(404, 'No such loop in the demo');
        var cur = loopState(loop);
        if (from.indexOf(cur.workflow_state) < 0) {
          return err(409, 'Cannot ' + action + ' a loop that is ' + cur.workflow_state.replace(/_/g, ' '));
        }
        st.loops[key] = Object.assign(st.loops[key] || {}, change, { updated_at: now() });
        audit(key, action, detail);
        save();
        return reply(200, overlayLoop(loop));
      });
    }
    // Rule sign-off: the server's rule (rule_status in governance.py), one approval required in the demo
    function ruleStatus(ruleId, base) {
      var mine = st.reviews[ruleId] || [];
      if (!mine.length) return base;
      var last = mine[mine.length - 1];
      var status = last.decision === 'reject' ? 'rejected' : last.decision === 'request_changes' ? 'changes_requested'
        : 'approved';
      return Object.assign({}, base, { status: status, approvals: status === 'approved' ? 1 : 0,
        approvers: status === 'approved' ? [USER.user] : [], reviews: (base.reviews || []).concat(mine) });
    }
    var SUGGESTIONS = [
      { id: 'a1b2c3d4e5f60718293a4b5c6d7e8f90', patient_id: 'SYN-003', report_ref: 'DiagnosticReport/practice-1',
        report_kind: 'radiology', report_date: '2026-08-14', category: 'imaging_followup',
        quote: 'Please obtain a dedicated pelvic MRI at the earliest convenience',
        reason: 'MRI recommended for a complex adnexal cyst', model: 'practice example', created_at: '2026-08-15T09:00:00' },
      { id: 'b2c3d4e5f60718293a4b5c6d7e8f90a1', patient_id: 'SYN-011', report_ref: 'DiagnosticReport/practice-2',
        report_kind: 'radiology', report_date: '2026-08-20', category: 'specialist_referral',
        quote: '흉부외과 협진 요망', reason: 'Thoracic surgery consultation requested', model: 'practice example',
        created_at: '2026-08-21T09:00:00' },
      { id: 'c3d4e5f60718293a4b5c6d7e8f90a1b2', patient_id: 'SYN-019', report_ref: 'DiagnosticReport/practice-3',
        report_kind: 'pathology', report_date: '2026-09-02', category: 'abnormal_pathology',
        quote: 'Atypical cells present; malignancy cannot be excluded', reason: 'Indeterminate cytology',
        model: 'practice example', created_at: '2026-09-03T09:00:00' }
    ];
    var LABELS = { imaging_followup: ['follow-up imaging', '추적 영상검사'], specialist_referral: ['specialist referral', '타과 의뢰'],
                   abnormal_pathology: ['abnormal pathology', '이상 병리 결과'], biopsy_or_workup: ['biopsy or work-up', '조직검사·정밀검사'],
                   critical_finding: ['critical finding to communicate', '위급 소견 통보'] };
    function suggestions() {
      return SUGGESTIONS.map(function (x) {
        var v = st.verdicts[x.id] || {};
        return Object.assign({}, x, { label: { en: LABELS[x.category][0], ko: LABELS[x.category][1] },
          verdict: v.verdict || null, urgent: v.urgent ? 1 : 0, safety_referral: v.safety_referral || null,
          note: v.note || null, reviewer: v.reviewer || null, reviewed_at: v.reviewed_at || null });
      });
    }
    function draftText(lang) {
      return lang === 'en'
        ? '[Practice] Hello, this is your hospital. Your care team asks you to book a follow-up appointment. Please call the clinic.'
        : '[연습] 안녕하세요, 병원입니다. 담당 의료진이 후속 진료 예약을 요청드립니다. 외래로 연락 부탁드립니다.';
    }

    function handle(method, path, params, body) {
      if (!st.on) return null;
      var m;
      if (method === 'GET' && path === '/api/v1/me') return reply(200, USER);
      if (method === 'GET' && path === '/api/v1/users') {
        return reply(200, { users: STAFF.map(function (u) { return { user: u, role: u.indexOf('dr.') === 0 || u === USER.user ? 'clinician' : 'navigator' }; }) });
      }
      if (method === 'GET' && path === '/api/v1/worklist') {
        return allLoops().then(function (wl) {
          if (!wl) return err(503, 'Could not load the demo snapshot.');
          var loops = wl.loops.map(overlayLoop);
          if (params.include_inactive !== 'true') {
            loops = loops.filter(function (l) { return ACTIVE.indexOf(l.workflow_state) >= 0 || l.deferral_expired; });
          }
          if (params.owner) loops = loops.filter(function (l) { return l.owner === params.owner; });
          return reply(200, Object.assign({}, wl, { loops: loops, count: loops.length, practice: true }));
        });
      }
      if ((m = path.match(/^\/api\/v1\/loops\/(.+)\/(audit|outreach|acknowledge|assign|defer|close)$/))) {
        var key = m[1], what = m[2];
        if (method === 'GET' && what === 'audit') {
          return snapshot(path, {}).then(function (r) {
            var base = r.status === 200 ? r.body.audit : [];
            return reply(200, { loop_key: key, audit: base.concat(st.audit[key] || []) });
          });
        }
        if (method === 'GET' && what === 'outreach') return reply(200, { messages: st.messages[key] || [] });
        if (method !== 'POST') return null;
        if (what === 'acknowledge') {
          return transition(key, 'acknowledge', ['new', 'deferred'], { workflow_state: 'acknowledged', owner: USER.user }, {});
        }
        if (what === 'assign') {
          var owner = String((body && body.owner) || '').trim();
          if (STAFF.indexOf(owner) < 0) return err(422, 'Choose someone from the staff list');
          return transition(key, 'assign', ACTIVE.concat(['deferred']), { owner: owner }, { owner: owner });
        }
        if (what === 'defer') {
          if (!body || REASONS.indexOf(body.reason_code) < 0) return err(422, 'Choose a reason for deferring');
          if (body.reason_code === 'not_clinically_indicated' && !(body.note || '').trim()) {
            return err(422, 'Write why follow-up is not indicated: a clinical judgement must be explained');
          }
          return transition(key, 'defer', ACTIVE.concat(['deferred']), { workflow_state: 'deferred', defer_reason: body.reason_code,
            defer_note: body.note || '', defer_until: body.until || null }, { reason_code: body.reason_code, note: body.note || '' });
        }
        if (what === 'close') {
          var ev = String((body && body.evidence) || '').trim();
          if (ev.length < 3) return err(422, 'Closing needs evidence: what closed the loop (an order, a visit, a result)');
          return transition(key, 'close', ACTIVE.concat(['deferred']), { workflow_state: 'closed_by_clinician', closure_evidence: ev },
            { evidence: ev });
        }
        if (what === 'outreach') {
          var pid = key.split('|')[0];
          if ((st.prefs[pid] || {}).opted_out) return err(409, 'This patient asked not to be messaged');
          st.seq += 1;
          var msg = { id: 'practice-' + st.seq, loop_key: key, status: 'draft', channel: (body && body.channel) || 'kakao',
            language: (body && body.language) || 'ko', draft_text: draftText(body && body.language), drafted_at: now(),
            drafted_by: USER.user };
          (st.messages[key] = st.messages[key] || []).push(msg);
          audit(key, 'outreach_drafted', { message: msg.id, channel: msg.channel });
          save();
          return reply(200, msg);
        }
      }
      if (method === 'POST' && (m = path.match(/^\/api\/v1\/outreach\/([^/]+)\/decision$/))) {
        var found = null;
        Object.keys(st.messages).forEach(function (k) {
          st.messages[k].forEach(function (x) { if (x.id === m[1]) found = x; });
        });
        if (!found) return err(404, 'No such message');
        if (found.status !== 'draft') return err(409, 'This message was already decided');
        if (body && body.approve) {
          // Practice never sends anything: the message is marked as it would be, with a note saying so
          Object.assign(found, { status: 'sent', final_text: body.text || found.draft_text, decided_by: USER.user,
            decided_at: now(), note: 'Practice mode: nothing was sent.' });
        } else {
          Object.assign(found, { status: 'rejected', decided_by: USER.user, decided_at: now() });
        }
        audit(found.loop_key, 'outreach_' + found.status, { message: found.id });
        save();
        return reply(200, found);
      }
      if ((m = path.match(/^\/api\/v1\/patients\/([^/]+)\/outreach-preference$/))) {
        var p = m[1];
        if (method === 'GET') return reply(200, Object.assign({ patient_id: p, opted_out: false }, st.prefs[p] || {}));
        if (method === 'PUT') {
          st.prefs[p] = { patient_id: p, opted_out: !!(body && body.opted_out), reason: (body && body.reason) || '',
                          recorded_by: USER.user, recorded_at: now() };
          save();
          return reply(200, st.prefs[p]);
        }
      }
      if (method === 'GET' && (path === '/api/v1/governance/rules' || path === '/api/v1/rules')) {
        return snapshot(path, params).then(function (r) {
          if (r.status !== 200) return reply(r.status, r.body);
          var out = Object.assign({}, r.body, { rules: r.body.rules.map(function (x) {
            if (path === '/api/v1/rules') {
              return st.reviews[x.rule_id] ? Object.assign({}, x, { signoff: ruleStatus(x.rule_id, x.signoff) }) : x;
            }
            return ruleStatus(x.rule_id, x);
          }) });
          return reply(200, out);
        });
      }
      if (method === 'GET' && path === '/api/v1/governance/summary') {
        return Promise.all([snapshot(path, params), snapshot('/api/v1/governance/rules', {})]).then(function (rs) {
          if (rs[0].status !== 200 || rs[1].status !== 200) return reply(rs[0].status, rs[0].body);
          var by = {};
          rs[1].body.rules.forEach(function (x) { var s = ruleStatus(x.rule_id, x).status; by[s] = (by[s] || 0) + 1; });
          return reply(200, Object.assign({}, rs[0].body, { by_status: by, rules_approved: by.approved || 0 }));
        });
      }
      if (method === 'POST' && (m = path.match(/^\/api\/v1\/governance\/rules\/([^/]+)\/review$/))) {
        var rid = m[1];
        if (!body || ['approve', 'reject', 'request_changes'].indexOf(body.decision) < 0) return err(422, 'Choose a decision');
        if (!String(body.specialty || '').trim()) return err(422, 'Give your specialty');
        (st.reviews[rid] = st.reviews[rid] || []).push({ decision: body.decision, reviewer: USER.user,
          specialty: body.specialty, note: body.note || '', decided_at: now(), rule_hash: body.fingerprint, practice: true });
        save();
        return reply(200, ruleStatus(rid, { rule_id: rid, fingerprint: body.fingerprint, status: 'pending', approvals: 0,
          approvals_required: 1, approvers: [], reviews: [] }));
      }
      if (method === 'GET' && path === '/api/v1/quality/second-reader/suggestions') {
        var items = suggestions().filter(function (x) { return params.pending !== 'true' || !x.verdict; });
        return reply(200, { count: items.length, items: items, practice: true });
      }
      if (method === 'GET' && path === '/api/v1/quality/second-reader') {
        return snapshot(path, params).then(function (r) {
          if (r.status !== 200) return reply(r.status, r.body);
          var cats = JSON.parse(JSON.stringify(r.body.categories)), total = { n: 0, reviewed: 0, real_miss: 0,
            already_handled: 0, not_needed: 0, wrong_quote: 0, urgent: 0 };
          Object.keys(cats).forEach(function (c) {
            ['n', 'reviewed', 'real_miss', 'already_handled', 'not_needed', 'wrong_quote', 'urgent'].forEach(function (k) { cats[c][k] = 0; });
          });
          suggestions().forEach(function (x) {
            var c = cats[x.category]; if (!c) return;
            c.n += 1; total.n += 1;
            if (x.verdict) { c.reviewed += 1; total.reviewed += 1; c[x.verdict] += 1; total[x.verdict] += 1; }
            if (x.urgent) { c.urgent += 1; total.urgent += 1; }
          });
          Object.keys(cats).concat(['_total']).forEach(function (k) {
            var c = k === '_total' ? total : cats[k];
            c.precision = c.reviewed ? Math.round(1000 * c.real_miss / c.reviewed) / 1000 : null;
            c.precision_ci95 = c.reviewed ? wilson(c.real_miss, c.reviewed) : null;
          });
          return reply(200, Object.assign({}, r.body, { mode: 'silent', categories: cats, total: total, practice: true }));
        });
      }
      if (method === 'POST' && (m = path.match(/^\/api\/v1\/quality\/second-reader\/suggestions\/([0-9a-f]{32})\/review$/))) {
        var sid = m[1];
        if (!SUGGESTIONS.some(function (x) { return x.id === sid; })) return err(404, 'No such suggestion');
        if (!body || ['real_miss', 'already_handled', 'not_needed', 'wrong_quote'].indexOf(body.verdict) < 0) {
          return err(422, 'Choose a verdict');
        }
        var urgent = !!body.urgent && body.verdict === 'real_miss';
        if (urgent && !String(body.safety_referral || '').trim()) {
          return err(409, 'An urgent real miss needs a safety referral: who on the treating team was told, and how');
        }
        st.verdicts[sid] = { verdict: body.verdict, urgent: urgent, safety_referral: body.safety_referral || '',
                             note: body.note || '', reviewer: USER.user, reviewed_at: now() };
        save();
        return reply(200, suggestions().filter(function (x) { return x.id === sid; })[0]);
      }
      return null;
    }
    function wilson(k, n) {
      var z = 1.96, p = k / n, c = (p + z * z / (2 * n)) / (1 + z * z / n),
          h = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n);
      return [Math.round(1000 * Math.max(0, c - h)) / 1000, Math.round(1000 * Math.min(1, c + h)) / 1000];
    }
    return {
      handle: handle,
      on: function () { return st.on; },
      changes: function () {
        return Object.keys(st.loops).length + Object.keys(st.reviews).length + Object.keys(st.verdicts).length +
          Object.keys(st.messages).length + Object.keys(st.prefs).length;
      },
      reset: function () { st = fresh(); try { window.localStorage.removeItem(KEY); } catch (e) { /* nothing kept */ } },
      setOn: function (on) { st.on = !!on; save(); }
    };
  }

  // ── banner, sign-in, patient list ─────────────────────────────────────────
  function run() {
    if (!demo.static) {
      var ko = (document.documentElement.lang || '').indexOf('ko') === 0;
      var banner = document.createElement('div');
      banner.setAttribute('role', 'note');
      banner.id = 'clinloop-demo-banner';
      banner.style.cssText = 'background:#7c2d12;color:#fff7ed;padding:8px 16px;font:600 13px/1.4 system-ui,sans-serif;' +
        'text-align:center;position:relative;z-index:1000;overflow-wrap:anywhere;';
      banner.textContent = ko
        ? '공개 데모: 합성(가상) 환자만 · 읽기 전용 · 재시작 시 초기화 · 실제 환자 정보를 입력하지 마십시오'
        : demo.note;
      document.body.insertBefore(banner, document.body.firstChild);
    }

    if (demo.static) {
      window.fetch(window.CLINLOOP_API_BASE.replace(STATIC_PATH, '') + '/demo/api/index.json')
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (index) {
          if (!index) return;
          var input = document.getElementById('patient');
          if (input && index.patients) {          // patient page: offer the demo patients
            var list = document.createElement('datalist');
            list.id = 'demo-patients';
            index.patients.forEach(function (p) { var o = document.createElement('option'); o.value = p; list.appendChild(o); });
            document.body.appendChild(list);
            input.setAttribute('list', 'demo-patients');
            if (!input.value) input.placeholder = index.patients.slice(0, 3).join(', ') + ' …';
          }
        })
        .catch(function () {});
    }

    var token = document.getElementById('token');
    var form = token && token.closest('form');
    if (!form || form.id !== 'connect-form' || !form.requestSubmit) return;
    var base = document.getElementById('api-base');
    if (base && (demo.static || !base.value)) base.value = window.CLINLOOP_API_BASE || window.location.origin;
    if (demo.static || !token.value) {
      token.value = demo.token;
      form.requestSubmit();
      return;
    }
    // A token from this tab's session is already filled in. Some pages sign in with it
    // themselves; sign in here only if, after a moment, none has happened.
    setTimeout(function () {
      var app = document.getElementById('app');
      var status = document.getElementById('status');
      if (app && app.hidden && !(status && status.textContent.trim())) form.requestSubmit();
    }, 1500);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
  else run();
})();
