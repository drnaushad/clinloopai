/**
 * ClinLoop AI - Interactive Dashboard Controller 2.0
 */

class ClinLoopApp {
  constructor() {
    this.cases = [];
    this.filteredCases = [];
    this.currentCase = null;
    this.hypergraph = null;
    this.safetyGauge = null;
    this.soundEnabled = true;
    this.audioCtx = null;
    this.closedOverrides = new Set();
    this.currentFilter = 'all';
    this.searchQuery = '';
    this.currentScrubDays = 35;
    this.currentView = 'hypergraph';
    this.outreachLang = 'ko';
  }

  async init() {
    this.hypergraph = new HypergraphVisualizer('hypergraph-container');
    this.safetyGauge = new SafetyClockGauge('safety-gauge-canvas', 'sigmoid-canvas');

    await this.loadData();
    this.setupEventListeners();
    this.setupLiveClock();
    this.applyFilters();

    const urlParams = new URLSearchParams(window.location.search);
    const caseParam = urlParams.get('case') || urlParams.get('scenario');
    if (caseParam && this.cases.some(c => c.scenario_id === caseParam)) {
      this.selectCase(caseParam);
    } else if (this.filteredCases.length > 0) {
      this.selectCase(this.filteredCases[0].scenario_id);
    if (!window.location.hash) { this.switchView('summary'); }
    }

    if (window.location.hash === '#biomcp' || window.location.search.includes('biomcp=1')) {
        this.populateBioMcpModal();
        const m = document.getElementById('biomcp-modal');
        if (m) m.classList.add('open');
    } else if (window.location.hash === '#counterfactual' || window.location.search.includes('view=counterfactual')) {
        this.switchView('counterfactual');
    } else if (window.location.hash === '#standards' || window.location.search.includes('view=standards')) {
        this.switchView('standards');
    } else if (window.location.hash === '#outreach' || window.location.search.includes('outreach=1')) {
        this.updateOutreachModal();
        const m = document.getElementById('outreach-modal');
        if (m) m.classList.add('open');
    }

    window.addEventListener('hashchange', () => {
      const h = window.location.hash;
      if (h === '#counterfactual') this.switchView('counterfactual');
      else if (h === '#standards') this.switchView('standards');
      else if (h === '#hypergraph') this.switchView('hypergraph');
      else if (h === '#biomcp') {
        this.populateBioMcpModal();
        document.getElementById('biomcp-modal')?.classList.add('open');
      } else if (h === '#outreach') {
        this.updateOutreachModal();
        document.getElementById('outreach-modal')?.classList.add('open');
      }
    });
  }

  async loadData() {
    try {
      const resp = await fetch('data/cases.json');
      this.cases = await resp.json();
    } catch (e) {
      console.error('Failed to load cases.json, using fallback data', e);
      this.cases = this._getFallbackCases();
    }
    this.filteredCases = [...this.cases];
  }

  setupEventListeners() {
    // Action button
    const btnAction = document.getElementById('btn-close-action');
    const orderModal = document.getElementById('order-modal');
    const btnConfirmOrder = document.getElementById('btn-confirm-order');
    const btnCancelOrder = document.getElementById('btn-cancel-order');

    if (btnAction && orderModal) {
      btnAction.addEventListener('click', () => {
        if (!this.currentCase || this.closedOverrides.has(this.currentCase.scenario_id)) return;
        document.getElementById('modal-pt-name').textContent = `${this.currentCase.patient_id} (${this.currentCase.scenario_name})`;
        document.getElementById('modal-order-desc').textContent = this.currentCase.missing_followup || 'Mandatory clinical follow-up';
        orderModal.classList.add('open');
      });
    }

    if (btnConfirmOrder && orderModal) {
      btnConfirmOrder.addEventListener('click', () => {
        orderModal.classList.remove('open');
        this.handleCloseLoop();
      });
    }

    if (btnCancelOrder && orderModal) {
      btnCancelOrder.addEventListener('click', () => orderModal.classList.remove('open'));
    }

    // Timeline Scrubber Slider
    const scrubber = document.getElementById('timeline-scrubber');
    const scrubberVal = document.getElementById('scrubber-days-val');
    
    const updateScrubDays = (days) => {
      this.currentScrubDays = days;
      if (scrubber) scrubber.value = days;
      if (scrubberVal) scrubberVal.textContent = `${days} Days`;
      
      // Update active preset pill
      document.querySelectorAll('.preset-pill').forEach(pill => {
        const pDays = parseInt(pill.dataset.days, 10);
        pill.classList.toggle('active', pDays === days);
      });

      if (this.currentCase && !this.closedOverrides.has(this.currentCase.scenario_id)) {
        this.safetyGauge.updateTimeScrub(days);
        this.hypergraph.render(this.currentCase, false, days);
        this.updateStandardsView();
      }
    };

    if (scrubber) {
      scrubber.addEventListener('input', (e) => {
        const days = parseInt(e.target.value, 10);
        updateScrubDays(days);
      });
    }

    // View Mode Switcher Tabs
    document.querySelectorAll('.stage-tab-btn').forEach(tab => {
      tab.addEventListener('click', (e) => {
        const targetView = e.currentTarget.dataset.view;
        this.switchView(targetView);
      });
    });

    // Patient Outreach Simulator Modal
    const btnOutreach = document.getElementById('btn-patient-outreach');
    const cfBtnOutreach = document.getElementById('cf-btn-open-outreach');
    const outreachModal = document.getElementById('outreach-modal');
    const btnCloseOutreach = document.getElementById('btn-close-outreach');

    if (btnOutreach && outreachModal) {
      btnOutreach.addEventListener('click', () => {
        this.updateOutreachModal();
        outreachModal.classList.add('open');
      });
    }

    if (cfBtnOutreach && outreachModal) {
      cfBtnOutreach.addEventListener('click', () => {
        this.updateOutreachModal();
        outreachModal.classList.add('open');
      });
    }

    if (btnCloseOutreach && outreachModal) {
      btnCloseOutreach.addEventListener('click', () => {
        outreachModal.classList.remove('open');
      });
    }

    if (outreachModal) {
      outreachModal.addEventListener('click', (e) => {
        if (e.target === outreachModal) outreachModal.classList.remove('open');
      });
    }

    // 1-Click Kakao Booking Button
    const btnKakaoBook = document.getElementById('btn-kakao-book');
    if (btnKakaoBook) {
      btnKakaoBook.addEventListener('click', () => {
        this.handlePatientBooking();
      });
    }

    // Outreach Language Toggle
    const btnLangKo = document.getElementById('btn-lang-ko');
    const btnLangEn = document.getElementById('btn-lang-en');
    if (btnLangKo && btnLangEn) {
      btnLangKo.addEventListener('click', () => {
        btnLangKo.classList.add('active');
        btnLangEn.classList.remove('active');
        this.outreachLang = 'ko';
        this.updateOutreachModal();
      });
      btnLangEn.addEventListener('click', () => {
        btnLangEn.classList.add('active');
        btnLangKo.classList.remove('active');
        this.outreachLang = 'en';
        this.updateOutreachModal();
      });
    }

    // FHIR Buttons in Standards Dossier
    const fhirBtnDr = document.getElementById('fhir-btn-dr');
    const fhirBtnComm = document.getElementById('fhir-btn-comm');
    if (fhirBtnDr && fhirBtnComm) {
      fhirBtnDr.addEventListener('click', () => {
        fhirBtnDr.classList.add('active');
        fhirBtnComm.classList.remove('active');
        this.renderFhirResource('DiagnosticReport');
      });
      fhirBtnComm.addEventListener('click', () => {
        fhirBtnComm.classList.add('active');
        fhirBtnDr.classList.remove('active');
        this.renderFhirResource('CommunicationRequest');
      });
    }

    // Fast-Forward Preset Pills
    document.querySelectorAll('.preset-pill').forEach(pill => {
      pill.addEventListener('click', (e) => {
        const days = parseInt(e.currentTarget.dataset.days, 10);
        updateScrubDays(days);
      });
    });

    // Triage Filter Buttons
    document.querySelectorAll('.filter-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        e.currentTarget.classList.add('active');
        this.currentFilter = e.currentTarget.dataset.filter;
        this.applyFilters();
      });
    });

    // Search Input
    const searchInput = document.getElementById('patient-search');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        this.searchQuery = e.target.value.toLowerCase().trim();
        this.applyFilters();
      });
    }

    // EMR Comparison Modal
    const btnEmrComp = document.getElementById('btn-emr-comparison');
    const emrModal = document.getElementById('emr-modal');
    const btnCloseEmr = document.getElementById('btn-close-modal');

    if (btnEmrComp && emrModal) {
      btnEmrComp.addEventListener('click', () => {
        this.updateEmrComparisonContent();
        emrModal.classList.add('open');
      });
    }

    if (btnCloseEmr && emrModal) {
      btnCloseEmr.addEventListener('click', () => emrModal.classList.remove('open'));
    }

    if (emrModal) {
      emrModal.addEventListener('click', (e) => {
        if (e.target === emrModal) emrModal.classList.remove('open');
      });
    }

    // Nobility & Hippocratic Charter Modal
    const btnNobility = document.getElementById('btn-nobility-charter');
    const nobilityModal = document.getElementById('nobility-modal');
    const btnCloseNobility = document.getElementById('btn-close-nobility');
    const btnCloseNobilityBottom = document.getElementById('btn-close-nobility-bottom');

    if (btnNobility && nobilityModal) {
      btnNobility.addEventListener('click', () => {
        nobilityModal.classList.add('open');
      });
    }

    if (btnCloseNobility && nobilityModal) {
      btnCloseNobility.addEventListener('click', () => nobilityModal.classList.remove('open'));
    }

    if (btnCloseNobilityBottom && nobilityModal) {
      btnCloseNobilityBottom.addEventListener('click', () => nobilityModal.classList.remove('open'));
    }

    if (nobilityModal) {
      nobilityModal.addEventListener('click', (e) => {
        if (e.target === nobilityModal) nobilityModal.classList.remove('open');
      });
    }

    
    // Summary View One-Click Action Buttons
    const btnSummaryKakao = document.getElementById('summary-btn-kakao');
    if (btnSummaryKakao) {
      btnSummaryKakao.addEventListener('click', () => {
        this.updateOutreachModal();
        const m = document.getElementById('outreach-modal');
        if (m) m.classList.add('open');
      });
    }

    const btnSummaryOrder = document.getElementById('summary-btn-order');
    if (btnSummaryOrder) {
      btnSummaryOrder.addEventListener('click', () => {
        if (!this.currentCase) return;
        this.closedOverrides.add(this.currentCase.scenario_id);
        this.selectCase(this.currentCase.scenario_id);
        this._playTelemetrySound(880, 'sine', 0.15);
      });
    }

    // Light / Dark Theme Toggle Button
    const btnTheme = document.getElementById('btn-theme-toggle');
    const themeText = document.getElementById('theme-btn-text');
    if (btnTheme) {
      const savedTheme = localStorage.getItem('clinloop_theme') || 'light';
      if (savedTheme === 'dark') {
        document.body.classList.add('dark-theme');
        if (themeText) themeText.textContent = 'Dark Mode';
      } else {
        document.body.classList.remove('dark-theme');
        if (themeText) themeText.textContent = 'Light Mode';
      }

      btnTheme.addEventListener('click', () => {
        document.body.classList.toggle('dark-theme');
        const isDark = document.body.classList.contains('dark-theme');
        localStorage.setItem('clinloop_theme', isDark ? 'dark' : 'light');
        if (themeText) themeText.textContent = isDark ? 'Dark Mode' : 'Light Mode';
        btnTheme.innerHTML = isDark ? '🌙 <span id="theme-btn-text">Dark Mode</span>' : '☀️ <span id="theme-btn-text">Light Mode</span>';
      });
    }

    // Sound Toggle
    const soundToggle = document.getElementById('sound-toggle');
    if (soundToggle) {
      soundToggle.addEventListener('click', () => {
        this.soundEnabled = !this.soundEnabled;
        soundToggle.textContent = this.soundEnabled ? '🔊 Audio: On' : '🔇 Audio: Muted';
      });
    }

    // Window Resize
    window.addEventListener('resize', () => {
      if (this.currentCase) {
        const isOverridden = this.closedOverrides.has(this.currentCase.scenario_id);
        this.hypergraph.render(this.currentCase, isOverridden, this.currentScrubDays);
        this.safetyGauge.drawDial();
        this.safetyGauge.drawSigmoidCurve();
      }
    });
  }

  applyFilters() {
    this.filteredCases = this.cases.filter(c => {
      const isClosed = (c.ground_truth_status === 'closed') || this.closedOverrides.has(c.scenario_id);
      const effectiveStatus = isClosed ? 'closed' : c.ground_truth_status;

      // Filter check
      if (this.currentFilter !== 'all' && effectiveStatus !== this.currentFilter) {
        return false;
      }

      // Search check
      if (this.searchQuery) {
        const matchId = c.patient_id.toLowerCase().includes(this.searchQuery);
        const matchName = c.scenario_name.toLowerCase().includes(this.searchQuery);
        const matchRule = c.applicable_rule_id.toLowerCase().includes(this.searchQuery);
        if (!matchId && !matchName && !matchRule) return false;
      }

      return true;
    });

    this.renderCaseTabs();

    if (this.filteredCases.length > 0) {
      if (!this.currentCase || !this.filteredCases.some(c => c.scenario_id === this.currentCase.scenario_id)) {
        this.selectCase(this.filteredCases[0].scenario_id);
    if (!window.location.hash) { this.switchView('summary'); }
      }
    }
  }

  renderCaseTabs() {
    const container = document.getElementById('case-tabs-list');
    if (!container) return;
    container.innerHTML = '';

    if (this.filteredCases.length === 0) {
      container.innerHTML = `<div style="grid-column: 1 / -1; padding: 1.5rem; text-align: center; color: var(--text-dim); font-size: 0.85rem;">No matching patient trajectories found.</div>`;
      return;
    }

    this.filteredCases.forEach(c => {
      const card = document.createElement('div');
      card.className = `case-card ${this.currentCase?.scenario_id === c.scenario_id ? 'active' : ''}`;
      card.id = `tab-${c.scenario_id}`;

      const isClosed = (c.ground_truth_status === 'closed') || this.closedOverrides.has(c.scenario_id);
      const statusClass = isClosed ? 'status-closed' : (c.ground_truth_status === 'delayed' ? 'status-delayed' : 'status-open');
      const statusText = isClosed ? 'Closed' : (c.ground_truth_status === 'delayed' ? 'Delayed' : 'Open Alert');

      card.innerHTML = `
        <div class="case-header">
          <span class="patient-id">${c.patient_id}</span>
          <span class="case-status-badge ${statusClass}">${statusText}</span>
        </div>
        <div class="case-title" title="${c.scenario_name}">${c.scenario_name}</div>
        <div class="case-meta">
          <span>${c.patient_age}y / ${c.patient_sex}</span>
          <span style="font-family: var(--font-mono); color: var(--cyan-neon);">Rule: ${c.applicable_rule_id}</span>
        </div>
      `;

      card.addEventListener('click', () => this.selectCase(c.scenario_id));
      container.appendChild(card);
    });
  }

  selectCase(scenarioId) {
    const selected = this.cases.find(c => c.scenario_id === scenarioId);
    if (!selected) return;

    this.currentCase = selected;
    this._playTelemetrySound(580, 'sine', 0.07);

    document.querySelectorAll('.case-card').forEach(el => el.classList.remove('active'));
    const activeTab = document.getElementById(`tab-${scenarioId}`);
    if (activeTab) activeTab.classList.add('active');

    const isOverridden = this.closedOverrides.has(scenarioId);
    const isClosed = (selected.ground_truth_status === 'closed') || isOverridden;

    // Reset scrubber to 35 days (default)
    const scrubber = document.getElementById('timeline-scrubber');
    const scrubberVal = document.getElementById('scrubber-days-val');
    this.currentScrubDays = 35;
    if (scrubber) scrubber.value = 35;
    if (scrubberVal) scrubberVal.textContent = '35 Days';

    // Render Hypergraph
    this.hypergraph.render(selected, isOverridden, this.currentScrubDays);

    // Update Safety Clock with Sigmoid
    const targetScore = isClosed ? 0.0 : selected.ground_truth_risk_score;
    this.safetyGauge.setScenarioParams(
      targetScore,
      selected.ground_truth_severity,
      selected.applicable_rule_id,
      selected.applicable_rule_id === 'R003' ? 180 : (selected.applicable_rule_id === 'R007' ? 7 : 30),
      this.currentScrubDays
    );

    // Update Details
    this.updateDetailsPanel(selected, isClosed);

    // Update delta pill in mode tab
    const pillDelta = document.getElementById('tab-pill-delta');
    if (pillDelta && selected.counterfactual) {
      pillDelta.textContent = `${selected.counterfactual.delta_5yr_survival} Survival`;
    }

    // Update Counterfactual & Standards views
    this.updateSummaryView();
    this.updateCounterfactualView();
    this.updateStandardsView();
    this.updateOutreachModal();
  }

  updateDetailsPanel(scenario, isClosed) {
    document.getElementById('case-display-title').textContent = scenario.scenario_name;
    document.getElementById('case-display-desc').textContent = scenario.clinical_narrative;

    document.getElementById('stat-rule-id').textContent = scenario.applicable_rule_id;
    document.getElementById('stat-severity').textContent = scenario.ground_truth_severity.toUpperCase();
    
    const actionBox = document.getElementById('action-card');
    const actionTitle = document.getElementById('action-required-title');
    const actionDesc = document.getElementById('action-required-desc');
    const actionBtn = document.getElementById('btn-close-action');

    if (isClosed) {
      actionBox.classList.add('resolved');
      actionTitle.textContent = '✓ Clinical Obligation Fulfilled';
      actionDesc.textContent = 'All mandatory diagnostic reports, notifications, and follow-ups have been verified across the temporal hypergraph.';
      actionBtn.textContent = 'Loop Closed & Verified';
      actionBtn.classList.add('resolved');
    } else {
      actionBox.classList.remove('resolved');
      actionTitle.textContent = '⚠ Mandatory Action Overdue / Missing';
      actionDesc.textContent = scenario.missing_followup || 'Immediate follow-up required to close open trajectory.';
      actionBtn.textContent = '⚡ Simulate Close Loop (Order/Notify)';
      actionBtn.classList.remove('resolved');
    }

    this.renderEvidenceChain(scenario, isClosed);
  }

  renderEvidenceChain(scenario, isClosed) {
    const container = document.getElementById('evidence-chain-list');
    if (!container) return;
    container.innerHTML = '';

    const firstEvent = scenario.events[0];
    const steps = [
      {
        num: '01',
        title: `Ingestion: ${firstEvent.event_type.replace(/_/g, ' ')}`,
        sub: `Timestamp: ${firstEvent.timestamp.split('T')[0]}`
      },
      {
        num: '02',
        title: `Matched Rule: ${scenario.applicable_rule_id} (BioMCP Grounded)`,
        sub: scenario.biomcp_evidence ? `${scenario.biomcp_evidence.guideline_org.split('(')[0].trim()} • PMID: ${scenario.biomcp_evidence.pmid}` : 'Safety Clock Deadline Engine Activated'
      },
      {
        num: '03',
        title: isClosed ? 'Verification: Closed in Graph' : `Identified Gap: ${scenario.missing_followup}`,
        sub: isClosed ? 'Status: 0.00 Risk (Loop Assured)' : 'Status: ACTIVE CLINICAL HAZARD'
      },
      {
        num: '04',
        title: isClosed ? 'EHR Writeback: HL7 FHIR Task Closed' : 'Action Engine: Clinical Alert Dispatched',
        sub: isClosed ? 'Audit Log Synced to Quality Board' : 'Attending & Triage Escalation Active'
      }
    ];

    steps.forEach(s => {
      const el = document.createElement('div');
      el.className = 'evidence-step';
      el.innerHTML = `
        <div class="step-icon">${s.num}</div>
        <div class="step-content">
          <span class="step-title">${s.title}</span>
          <span class="step-sub">${s.sub}</span>
        </div>
      `;
      container.appendChild(el);
    });
  }

  handleCloseLoop() {
    if (!this.currentCase) return;

    this.closedOverrides.add(this.currentCase.scenario_id);
    this._playSuccessChime();

    this.hypergraph.render(this.currentCase, true);
    this.safetyGauge.setScore(0.0);

    this.updateDetailsPanel(this.currentCase, true);
    this.applyFilters();
  }

  updateEmrComparisonContent() {
    if (!this.currentCase) return;
    const c = this.currentCase;
    document.getElementById('emr-view-scenario-name').textContent = `${c.patient_id} — ${c.scenario_name}`;
    document.getElementById('emr-missing-action').textContent = c.missing_followup || 'Clinical follow-up';
  }

  _playTelemetrySound(freq, type = 'sine', duration = 0.08) {
    if (!this.soundEnabled) return;
    try {
      if (!this.audioCtx) {
        this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      }
      if (this.audioCtx.state === 'suspended') {
        this.audioCtx.resume();
      }
      const osc = this.audioCtx.createOscillator();
      const gain = this.audioCtx.createGain();

      osc.type = type;
      osc.frequency.setValueAtTime(freq, this.audioCtx.currentTime);

      gain.gain.setValueAtTime(0.04, this.audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.0001, this.audioCtx.currentTime + duration);

      osc.connect(gain);
      gain.connect(this.audioCtx.destination);

      osc.start();
      osc.stop(this.audioCtx.currentTime + duration);
    } catch (e) {}
  }

  _playSuccessChime() {
    if (!this.soundEnabled) return;
    try {
      if (!this.audioCtx) {
        this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      }
      const now = this.audioCtx.currentTime;
      [523.25, 659.25, 783.99, 1046.50].forEach((freq, i) => {
        const osc = this.audioCtx.createOscillator();
        const gain = this.audioCtx.createGain();

        osc.type = 'sine';
        osc.frequency.setValueAtTime(freq, now + i * 0.09);

        gain.gain.setValueAtTime(0.06, now + i * 0.09);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.09 + 0.45);

        osc.connect(gain);
        gain.connect(this.audioCtx.destination);

        osc.start(now + i * 0.09);
        osc.stop(now + i * 0.09 + 0.45);
      });
    } catch (e) {}
  }

  setupLiveClock() {
    const clockEl = document.getElementById('live-cockpit-clock');
    if (!clockEl) return;
    const update = () => {
      const now = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const timeStr = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())} KST`;
      clockEl.textContent = timeStr;
    };
    update();
    setInterval(update, 1000);
  }

  populateBioMcpModal() {
    if (!this.currentCase || !this.currentCase.biomcp_evidence) return;
    const ev = this.currentCase.biomcp_evidence;

    // JSON-RPC Request
    const reqObj = {
      jsonrpc: "2.0",
      id: `mcp-req-${this.currentCase.scenario_id.toLowerCase()}`,
      method: "tools/call",
      params: {
        server: "biomcp-core-v1",
        tool: ev.mcp_tool,
        arguments: ev.mcp_args
      }
    };
    const reqEl = document.getElementById('biomcp-req-json');
    if (reqEl) reqEl.textContent = JSON.stringify(reqObj, null, 2);

    // JSON-RPC Response
    const resObj = {
      jsonrpc: "2.0",
      id: `mcp-req-${this.currentCase.scenario_id.toLowerCase()}`,
      result: {
        status: "grounded",
        evidence_source: ev.guideline_org,
        guideline: ev.guideline_title,
        pmid: ev.pmid,
        evidence_grade: ev.evidence_grade,
        mandated_action: ev.mandated_action,
        safety_window_days: ev.time_window_days,
        derived_parameters: {
          t_crit_days: ev.derived_t_crit,
          k_factor: ev.derived_k_factor
        },
        liability_assessment: ev.legal_liability,
        token_hash: "0x8f4d92a1c7e2b834..."
      }
    };
    const resEl = document.getElementById('biomcp-res-json');
    if (resEl) resEl.textContent = JSON.stringify(resObj, null, 2);

    // Latency & Grade
    const latEl = document.getElementById('biomcp-latency-tag');
    if (latEl) latEl.textContent = `Latency: ${ev.latency_ms}ms (Cached)`;

    const gradeEl = document.getElementById('biomcp-evidence-grade');
    if (gradeEl) gradeEl.textContent = ev.evidence_grade.split('(')[0].trim();

    // Dossier Card
    const orgEl = document.getElementById('biomcp-org-tag');
    if (orgEl) orgEl.textContent = ev.guideline_org;

    const titleEl = document.getElementById('biomcp-guideline-title');
    if (titleEl) titleEl.textContent = ev.guideline_title;

    const citEl = document.getElementById('biomcp-citation-text');
    if (citEl) citEl.textContent = `Citation: ${ev.citation}`;

    const pmidLink = document.getElementById('biomcp-pmid-link');
    const pmidVal = document.getElementById('biomcp-pmid-val');
    if (pmidLink && pmidVal) {
      pmidVal.textContent = ev.pmid;
      pmidLink.href = `https://pubmed.ncbi.nlm.nih.gov/${ev.pmid}/`;
    }

    const doiVal = document.getElementById('biomcp-doi-val');
    if (doiVal) doiVal.textContent = ev.doi;

    // Derived Parameters
    const actVal = document.getElementById('biomcp-param-action');
    if (actVal) actVal.textContent = ev.mandated_action;

    const tcritVal = document.getElementById('biomcp-param-tcrit');
    if (tcritVal) tcritVal.textContent = `${ev.derived_t_crit} Days`;

    const kVal = document.getElementById('biomcp-param-k');
    if (kVal) kVal.textContent = ev.derived_k_factor;

    const liabVal = document.getElementById('biomcp-param-liability');
    if (liabVal) liabVal.textContent = ev.legal_liability.split('(')[0].trim();
  }

  _getFallbackCases() {
    return [
      {
        scenario_id: 'SC-0004',
        patient_id: 'PT-0004',
        patient_age: 63,
        patient_sex: 'M',
        scenario_name: 'Incidental Lung Nodule 7.8mm — No Follow-up',
        applicable_rule_id: 'R003',
        ground_truth_status: 'open',
        ground_truth_severity: 'high',
        ground_truth_risk_score: 0.85,
        missing_followup: 'FOLLOWUP_CT within 180 days',
        clinical_narrative: 'Male age 63 with 7.8mm right upper lobe lung nodule incidentally noted on abdominal CT. 6-month CT follow-up not scheduled.',
        events: [
          { event_id: 'EVT-01', event_type: 'imaging_order', timestamp: '2025-11-10T10:00:00', details: { scan: 'Abdominal CT' } },
          { event_id: 'EVT-02', event_type: 'radiology_report', timestamp: '2025-11-10T14:30:00', details: { finding: 'Incidental 7.8mm RUL nodule', condition: 'incidental_nodule_ge_6mm' } },
          { event_id: 'EVT-03', event_type: 'patient_notification', timestamp: '2025-11-12T09:00:00', details: { method: 'phone' } }
        ]
      }
    ];
  }

  switchView(viewName) {
    this.currentView = viewName;
    try { window.location.hash = viewName; } catch (e) {}
    document.querySelectorAll('.stage-tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.view === viewName);
    });

    const panels = {
      summary: document.getElementById('view-summary'),
      hypergraph: document.getElementById('view-hypergraph'),
      counterfactual: document.getElementById('view-counterfactual'),
      standards: document.getElementById('view-standards')
    };

    Object.keys(panels).forEach(k => {
      if (panels[k]) {
        panels[k].classList.toggle('hidden', k !== viewName);
      }
    });

    if (viewName === 'hypergraph' && this.currentCase) {
      const isOverridden = this.closedOverrides.has(this.currentCase.scenario_id);
      this.hypergraph.render(this.currentCase, isOverridden, this.currentScrubDays);
    }
  }


  updateSummaryView() {
    if (!this.currentCase) return;
    const c = this.currentCase;
    const isOverridden = this.closedOverrides.has(c.scenario_id);
    const isClosed = (c.ground_truth_status === 'closed') || isOverridden;

    const patientProfiles = {
      'SC-0004': {
        name: '김철수 (Kim, Chul-soo)',
        ageSex: '남성 52세',
        dept: '응급의학과 외상진료 (갈비뼈 골절 치료 후 퇴원)',
        finding: '흉부 CT 판독 결과 우상엽(RUL)에 7.8mm 크기의 침상형 폐 결절 우연 발견 (조기 폐암 의심 소견)',
        missed: '갈비뼈 치료만 완료되고 폐 결절에 대한 외래 예약이나 호흡기내과 협진이 누락된 채 66일 경과',
        guideline: 'Fleischner Society 2017 가이드라인 (90일 이내 저선량 흉부 CT 재검 또는 조직검사 필수)',
        deadline: '24일 남음 (마감일자: 2026-10-15)',
        negRisk: '42.1% (1년 내 Stage IV 전이암 악화)',
        negSurvival: '15.0% (치명적 급락)',
        posCure: '94.8% (조기 흉강경 절제술 완치)',
        posSurvival: '90.0% (+75.0% 생존율 향상!)',
        delta: '+75.0%',
        qaly: '+11.2 QALYs',
        liability: '3.5억 원'
      },
      'SC-0062': {
        name: '박영희 (Park, Young-hee)',
        ageSex: '여성 42세',
        dept: '부인과 정기 건강검진 (자궁경부 세포검사)',
        finding: '자궁경부 세포검사(Pap) 결과 고등급 편평상피내 병변(HSIL) 발견 (자궁경부암 전암 단계)',
        missed: '환자에게 단순 결과지만 우편 발송되고, 30일 이내 필수적인 질확대경 조준생검(Colposcopy) 예약 누락',
        guideline: 'ASCCP 2020 가이드라인 (30일 이내 질확대경 조준생검 필수 시행 권고)',
        deadline: '5일 경과 (즉시 조치 필요)',
        negRisk: '36.5% (24개월 내 침윤성 자궁경부암 진행)',
        negSurvival: '52.0% (광범위 자궁적출 및 항암치료 필요)',
        posCure: '98.0% (조기 원추절제술 LEEP 완치)',
        posSurvival: '98.0% (+46.0% 생존율 향상!)',
        delta: '+46.0%',
        qaly: '+8.4 QALYs',
        liability: '2.8억 원'
      },
      'SC-0105': {
        name: '이정훈 (Lee, Jung-hoon)',
        ageSex: '남성 61세',
        dept: '흉부외과 개심술(CABG) 수술 후 퇴원',
        finding: '관상동맥우회술 및 판막수술 후 와파린(Warfarin) 항응고제 복용 중',
        missed: '퇴원 후 14일 이내 필수적인 혈액응고수치(PT/INR) 추적 모니터링 처방 누락',
        guideline: 'ACC/AHA 2020 가이드라인 (와파린 복용 환자는 퇴원 후 7~14일 내 INR 목표치 2.0~3.0 검증 필수)',
        deadline: '2일 남음 (출혈/혈전 급성 위기)',
        negRisk: '28.0% (치명적 뇌경색 또는 심부출혈 발생)',
        negSurvival: '65.0% (급성 혈전증 사망 위험)',
        posCure: '96.5% (적정 INR 2.5 유지 및 안전)',
        posSurvival: '94.0% (+29.0% 생존율 향상!)',
        delta: '+29.0%',
        qaly: '+6.2 QALYs',
        liability: '2.2억 원'
      },
      'SC-0220': {
        name: '최민숙 (Choi, Min-sook)',
        ageSex: '여성 68세',
        dept: '내분비내과 골다공증 종합검진',
        finding: '혈중 칼슘 농도 12.4 mg/dL로 중증 고칼슘혈증(Hypercalcemia) 측정',
        missed: '부갑상선 호르몬(PTH) 정밀검사 및 수액 치료 오더 누락된 채 귀가',
        guideline: 'Endocrine Society 임상 가이드라인 (칼슘 12.0 mg/dL 초과 시 급성 심부전/부정맥 방지 즉시 조치)',
        deadline: '1일 남음 (급성 심장마비 위기)',
        negRisk: '31.2% (고칼슘혈증성 혼수 및 치명적 부정맥)',
        negSurvival: '58.0% (심정지 및 급성 신부전)',
        posCure: '99.0% (부갑상선 선종 적출 조기 완치)',
        posSurvival: '92.0% (+34.0% 생존율 향상!)',
        delta: '+34.0%',
        qaly: '+7.1 QALYs',
        liability: '2.5억 원'
      },
      'SC-0310': {
        name: '정우성 (Jung, Woo-sung)',
        ageSex: '남성 55세',
        dept: '건강증진센터 갑상선 초음파 검진',
        finding: '갑상선 좌엽 1.3cm 저에코성 미세석회화 결절 (K-TIRADS 4 고위험)',
        missed: '세침흡인세포검사(FNA) 권고되었으나 타과 진료 연계 없이 종결됨',
        guideline: '대한갑상선영상의학회 2021 가이드라인 (K-TIRADS 4 1cm 이상 결절 세침흡인검사 필수)',
        deadline: '12일 남음 (추적검사 유효기간)',
        negRisk: '22.4% (갑상선 유두암 임파선 전이 진행)',
        negSurvival: '75.0% (원격 전이 위험)',
        posCure: '98.5% (조기 미세절제 완치)',
        posSurvival: '99.0% (+24.0% 생존율 향상!)',
        delta: '+24.0%',
        qaly: '+5.5 QALYs',
        liability: '1.8억 원'
      }
    };

    const prof = patientProfiles[c.scenario_id] || {
      name: `환자 (${c.patient_id})`,
      ageSex: `${c.patient_age}세 ${c.patient_sex}`,
      dept: '외래 검사',
      finding: c.scenario_name,
      missed: c.missing_followup,
      guideline: '표준 임상 가이드라인 준수 권고',
      deadline: '추적 조치 필요',
      negRisk: '30.0%',
      negSurvival: '50.0%',
      posCure: '95.0%',
      posSurvival: '92.0%',
      delta: c.counterfactual ? c.counterfactual.delta_5yr_survival : '+40%',
      qaly: '+8.0 QALYs',
      liability: '2.5억 원'
    };

    const nameEl = document.getElementById('summary-patient-name');
    const metaEl = document.getElementById('summary-patient-meta');
    const q1El = document.getElementById('summary-q1-finding');
    const q2El = document.getElementById('summary-q2-problem');
    const q3El = document.getElementById('summary-q3-action');

    if (nameEl) nameEl.textContent = prof.name;
    if (metaEl) metaEl.textContent = `${prof.ageSex} • 등록번호: ${c.patient_id} • 내원: ${prof.dept}`;
    if (q1El) q1El.innerHTML = `<strong>${prof.finding}</strong>`;
    if (q2El) q2El.innerHTML = `<strong>${prof.missed}</strong>`;
    if (q3El) q3El.innerHTML = `<strong>${prof.guideline}</strong>`;

    const timerText = document.getElementById('summary-timer-text');
    const badge = document.getElementById('summary-urgency-badge');
    const orderBtnLabel = document.getElementById('summary-order-btn-label');

    if (isClosed) {
      if (badge) {
        badge.className = 'badge-pill badge-safe';
        badge.textContent = '✓ 진료루프 종결 완료 (외래 예약 확정)';
      }
      if (timerText) {
        timerText.textContent = '✓ 안전 종결됨';
        timerText.style.color = 'var(--emerald-safe)';
      }
      if (orderBtnLabel) orderBtnLabel.textContent = '✓ 외래 추적검사 오더 확정 완료 (EMR 전송됨)';
    } else {
      if (badge) {
        badge.className = 'badge-pill badge-urgent';
        badge.textContent = `🚨 골든타임 임박 (${prof.deadline})`;
      }
      if (timerText) {
        timerText.textContent = `⏳ ${prof.deadline.split('(')[0].trim()}`;
        timerText.style.color = 'var(--crimson-danger)';
      }
      if (orderBtnLabel) orderBtnLabel.textContent = '외래 추적검사 즉시 오더 및 루프 종결';
    }

    const negRiskEl = document.getElementById('summary-neg-risk');
    const negSurvEl = document.getElementById('summary-neg-survival');
    const posCureEl = document.getElementById('summary-pos-cure');
    const posSurvEl = document.getElementById('summary-pos-survival');
    const deltaEl = document.getElementById('summary-delta-badge');

    if (negRiskEl) negRiskEl.textContent = prof.negRisk;
    if (negSurvEl) negSurvEl.textContent = prof.negSurvival;
    if (posCureEl) posCureEl.textContent = prof.posCure;
    if (posSurvEl) posSurvEl.textContent = prof.posSurvival;
    if (deltaEl) deltaEl.textContent = `${prof.delta} 생존율 압승`;
  }

    updateCounterfactualView() {
    if (!this.currentCase || !this.currentCase.counterfactual) return;
    const cf = this.currentCase.counterfactual;
    const c = this.currentCase;

    const conditionTag = document.getElementById('cf-condition-tag');
    if (conditionTag) conditionTag.textContent = cf.condition_name;

    const ptSummary = document.getElementById('cf-patient-summary');
    if (ptSummary) ptSummary.textContent = `${c.patient_id} (${c.patient_age}y / ${c.patient_sex}) — ${c.scenario_name}`;

    const deltaEl = document.getElementById('cf-survival-delta');
    if (deltaEl) deltaEl.textContent = cf.delta_5yr_survival;

    const subEl = document.getElementById('cf-survival-sub');
    if (subEl && cf.neglected_path && cf.intervened_path) {
      const negFinal = cf.neglected_path[cf.neglected_path.length - 1].survival;
      const intFinal = cf.intervened_path[cf.intervened_path.length - 1].survival;
      subEl.textContent = intFinal + " Intervened vs " + negFinal + " Neglected";
    }

    const qalyEl = document.getElementById('cf-qaly-gain');
    if (qalyEl) qalyEl.textContent = `+${cf.qaly_gain} QALYs`;

    const liabEl = document.getElementById('cf-liability-avoided');
    if (liabEl) liabEl.textContent = cf.liability_avoided_krw;

    const guideEl = document.getElementById('cf-guideline-grade');
    if (guideEl && c.biomcp_evidence) {
      guideEl.textContent = c.biomcp_evidence.guideline_org.split('(')[0].trim();
    }

    const evText = document.getElementById('cf-evidence-text');
    if (evText) evText.textContent = cf.evidence_rationale;

    // Render neglected steps
    const negContainer = document.getElementById('cf-neglected-steps');
    if (negContainer && cf.neglected_path) {
      negContainer.innerHTML = '';
      cf.neglected_path.forEach(step => {
        const item = document.createElement('div');
        item.className = 'cf-step';
        item.innerHTML = `
          <div class="cf-step-time">${step.time}</div>
          <div class="cf-step-body">
            <div class="cf-step-title-row">
              <span class="cf-step-state">${step.state}</span>
              <span class="cf-step-stage stage-danger">${step.stage}</span>
            </div>
            <div class="cf-step-desc">${step.desc}</div>
            <div class="cf-step-meta">
              <span>5-Yr Survival: <strong style="color: var(--crimson-danger);">${step.survival}</strong></span>
              <span>Hazard Rate: ${step.hazard}</span>
            </div>
          </div>
        `;
        negContainer.appendChild(item);
      });
    }

    // Render intervened steps
    const intContainer = document.getElementById('cf-intervened-steps');
    if (intContainer && cf.intervened_path) {
      intContainer.innerHTML = '';
      cf.intervened_path.forEach(step => {
        const item = document.createElement('div');
        item.className = 'cf-step';
        item.innerHTML = `
          <div class="cf-step-time">${step.time}</div>
          <div class="cf-step-body">
            <div class="cf-step-title-row">
              <span class="cf-step-state">${step.state}</span>
              <span class="cf-step-stage stage-success">${step.stage}</span>
            </div>
            <div class="cf-step-desc">${step.desc}</div>
            <div class="cf-step-meta">
              <span>5-Yr Survival: <strong style="color: var(--emerald-safe);">${step.survival}</strong></span>
              <span>Hazard Rate: ${step.hazard}</span>
            </div>
          </div>
        `;
        intContainer.appendChild(item);
      });
    }
  }

  updateStandardsView() {
    if (!this.currentCase) return;
    const c = this.currentCase;
    const omop = c.omop_cdm || {};

    const idEl = document.getElementById('omop-val-id');
    if (idEl) idEl.textContent = omop.concept_id || 'N/A';

    const nameEl = document.getElementById('omop-val-name');
    if (nameEl) nameEl.textContent = omop.concept_name || 'N/A';

    const domEl = document.getElementById('omop-val-domain');
    if (domEl) domEl.textContent = omop.domain_id || 'Observation';

    const vocabEl = document.getElementById('omop-val-vocab');
    if (vocabEl) vocabEl.textContent = `${omop.vocabulary_id || 'SNOMED'} (${omop.concept_code || omop.concept_id})`;

    const loincEl = document.getElementById('omop-val-loinc');
    if (loincEl) loincEl.textContent = omop.loinc_code ? `${omop.loinc_code} - ${omop.loinc_name || ''}` : 'N/A';

    const omopRaw = document.getElementById('omop-raw-json');
    if (omopRaw) omopRaw.textContent = JSON.stringify(omop, null, 2);

    this.renderFhirResource('DiagnosticReport');

    // MTL Robustness Invariant
    const isOverridden = this.closedOverrides.has(c.scenario_id);
    const isClosed = (c.ground_truth_status === 'closed') || isOverridden;
    const tCrit = c.biomcp_evidence ? c.biomcp_evidence.derived_t_crit : 30;
    const deltaT = this.currentScrubDays;
    const margin = tCrit - deltaT;

    const formulaEl = document.getElementById('mtl-formula-text');
    if (formulaEl) {
      formulaEl.textContent = `Φ = □ ( IngestEvent(${c.scenario_category}) ⟹ ◇[0, ${tCrit}d] ${c.missing_followup ? c.missing_followup.split(' ')[0] : 'FollowUp'} )`;
    }

    const marginEl = document.getElementById('mtl-margin-calc');
    const statusPill = document.getElementById('mtl-status-pill');

    if (isClosed) {
      if (marginEl) marginEl.innerHTML = `<span style="color: var(--emerald-safe); font-weight: 700;">ρ(Φ, t) = +∞ (Invariant Formally Satisfied via Closed Loop)</span>`;
      if (statusPill) {
        statusPill.textContent = 'Invariant SATISFIED ✓';
        statusPill.style.background = 'rgba(5, 223, 114, 0.15)';
        statusPill.style.color = 'var(--emerald-safe)';
        statusPill.style.borderColor = 'rgba(5, 223, 114, 0.4)';
      }
    } else if (margin >= 0) {
      if (marginEl) marginEl.innerHTML = `ρ(Φ, t) = T_crit - Δt = ${tCrit}d - ${deltaT}d = <span style="color: var(--emerald-safe); font-weight: 700;">+${margin}d (Safe Window Active)</span>`;
      if (statusPill) {
        statusPill.textContent = `Safe Margin: +${margin} Days`;
        statusPill.style.background = 'rgba(5, 223, 114, 0.15)';
        statusPill.style.color = 'var(--emerald-safe)';
        statusPill.style.borderColor = 'rgba(5, 223, 114, 0.4)';
      }
    } else {
      if (marginEl) marginEl.innerHTML = `ρ(Φ, t) = T_crit - Δt = ${tCrit}d - ${deltaT}d = <span style="color: var(--crimson-danger); font-weight: 700;">${margin}d (CRITICAL TEMPORAL BREACH)</span>`;
      if (statusPill) {
        statusPill.textContent = `INVARIANT VIOLATED (${margin}d)`;
        statusPill.style.background = 'rgba(255, 42, 95, 0.15)';
        statusPill.style.color = 'var(--crimson-danger)';
        statusPill.style.borderColor = 'rgba(255, 42, 95, 0.4)';
      }
    }
  }

  renderFhirResource(type) {
    if (!this.currentCase) return;
    const c = this.currentCase;
    const resTypeEl = document.getElementById('fhir-res-type');
    const resRawEl = document.getElementById('fhir-raw-json');

    if (type === 'DiagnosticReport' && c.fhir_r4) {
      if (resTypeEl) resTypeEl.textContent = 'DiagnosticReport (R4)';
      if (resRawEl) resRawEl.textContent = JSON.stringify(c.fhir_r4, null, 2);
    } else {
      const commResource = {
        resourceType: "CommunicationRequest",
        id: c.patient_outreach ? c.patient_outreach.fhir_communication_request_id : `COMM-REQ-${c.scenario_id}`,
        status: this.closedOverrides.has(c.scenario_id) ? "completed" : "active",
        priority: "urgent",
        subject: {
          reference: `Patient/${c.patient_id}`,
          display: c.patient_outreach ? c.patient_outreach.patient_name : `Patient ${c.patient_id}`
        },
        payload: [
          {
            contentString: c.patient_outreach ? c.patient_outreach.plain_language_body : c.clinical_narrative
          }
        ],
        occurrencePeriod: {
          end: "2026-04-12T18:00:00+09:00"
        },
        reasonCode: [
          {
            coding: [
              {
                system: "http://snomed.info/sct",
                code: c.omop_cdm ? String(c.omop_cdm.concept_code) : "416952002",
                display: c.omop_cdm ? c.omop_cdm.concept_name : c.scenario_name
              }
            ]
          }
        ]
      };
      if (resTypeEl) resTypeEl.textContent = 'CommunicationRequest (R4)';
      if (resRawEl) resRawEl.textContent = JSON.stringify(commResource, null, 2);
    }
  }

  updateOutreachModal() {
    if (!this.currentCase) return;
    const c = this.currentCase;
    const outreach = c.patient_outreach || {};
    const isClosed = (c.ground_truth_status === 'closed') || this.closedOverrides.has(c.scenario_id);

    const titleEl = document.getElementById('kakao-outreach-title');
    const jargonEl = document.getElementById('kakao-jargon-text');
    const bodyEl = document.getElementById('kakao-outreach-body');
    const deptEl = document.getElementById('kakao-dept-slot');
    const btnLabel = document.getElementById('kakao-btn-label');
    const btnBook = document.getElementById('btn-kakao-book');
    const toast = document.getElementById('kakao-booked-toast');
    const fhirId = document.getElementById('outreach-fhir-id');
    const statusTag = document.getElementById('outreach-status-tag');

    if (fhirId) fhirId.textContent = outreach.fhir_communication_request_id || `CommunicationRequest/COMM-REQ-${c.scenario_id}`;

    if (this.outreachLang === 'en') {
      if (titleEl) titleEl.textContent = `[Ajou Hospital] Important Clinical Follow-up Notice`;
      if (jargonEl) jargonEl.textContent = outreach.clinical_jargon || c.scenario_name;
      if (bodyEl) bodyEl.textContent = `Dear ${c.patient_id}, your recent diagnostic test results require an expedited specialist review within recommended guidelines to ensure optimal health. Please confirm your reserved appointment slot with one click below.`;
      if (deptEl) deptEl.textContent = outreach.appointment_slot_suggested || 'Outpatient Clinic';
      if (btnLabel) btnLabel.textContent = `📅 1-Click Confirm Booking (${outreach.appointment_slot_suggested ? outreach.appointment_slot_suggested.split('(')[0].trim() : 'Next Available'})`;
    } else {
      if (titleEl) titleEl.textContent = outreach.plain_language_title || `[아주대병원] ${c.scenario_name} 추적진료 안내`;
      if (jargonEl) jargonEl.textContent = outreach.clinical_jargon || c.scenario_name;
      if (bodyEl) bodyEl.textContent = outreach.plain_language_body || c.clinical_narrative;
      if (deptEl) deptEl.textContent = outreach.appointment_slot_suggested || '전문 외래 클리닉';
      if (btnLabel) btnLabel.textContent = outreach.action_button_label || `📅 1초 간편 예약하기`;
    }

    if (isClosed) {
      if (btnBook) {
        btnBook.classList.add('confirmed');
        btnLabel.textContent = this.outreachLang === 'en' ? '✓ Appointment Confirmed & EMR Synced' : '✓ 예약 확정 완료 (EMR 자동 전송됨)';
      }
      if (toast) toast.style.display = 'block';
      if (statusTag) {
        statusTag.textContent = 'Verified Closed (EMR Synced)';
        statusTag.style.color = 'var(--emerald-safe)';
      }
    } else {
      if (btnBook) {
        btnBook.classList.remove('confirmed');
      }
      if (toast) toast.style.display = 'none';
      if (statusTag) {
        statusTag.textContent = 'Pending Patient Action';
        statusTag.style.color = 'var(--amber-warning)';
      }
    }
  }

  handlePatientBooking() {
    if (!this.currentCase) return;
    this.handleCloseLoop();
    this.updateOutreachModal();
    this.updateStandardsView();
  }

}

document.addEventListener('DOMContentLoaded', () => {
  window.app = new ClinLoopApp();
  window.app.init();
});
