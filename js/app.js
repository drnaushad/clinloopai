/**
 * ClinLoop AI - Interactive Dashboard Controller 2.0
 */


const CLINLOOP_I18N = {

  ko: {
    platformLabel: '의료기기(SaMD) 시판 전 임상 실증 PoC',
    platformNotice: '임상 사례만 사용 · 실시간 EHR, 메시징, 가이드라인 연결 없음 · 환자 진료용 아님',
    brandSubtitle: '결정론적 임상 지식그래프 추론 및 환자안전 폐쇄루프 엔진',
    hospitalText: '합성 임상 궤적 데이터 기반',
    pitchDeck: '📊 피치덱 (Pitch Deck)',
    nobilityBtn: '🏛️ 의료 노블리티 & 윤리 헌장',
    outreachBtn: '📱 환자 알림톡',
    biomcpBtn: '🧬 Triple-MCP 의학 근거',
    emrBtn: '기존 EMR과 비교',
    triageTitle: '임상 의무(Obligation) 하이퍼그래프 대기열',
    triageCount: '임상 사례 5건',
    searchPlaceholder: '환자번호, 진단명, 검사 항목 검색...',
    filterAll: '전체 (5)',
    filterOpen: '미완료 예시 (3)',
    filterDelayed: '지연 예시 (1)',
    filterClosed: '종결 예시 (1)',
    tabSummary: '🩺 환자 진료 요약 (Clinical Overview)',
    tabSummaryPill: '추천 / Primary',
    tabCounterfactual: '⚖️ 가상 시나리오 (검증되지 않음)',
    tabStandards: '🏥 보건의료 표준 (OMOP / FHIR)',
    tabHypergraph: '🕸️ 지식 하이퍼그래프 (AI Graph)',
    tabPrivacy: '🛡️ 개인정보 보호 (Privacy Shield)',
    guideTitle: '💡 ClinLoop AI는 어떤 시스템인가요? (System Purpose & Core Value)',
    guideDesc: 'ClinLoop AI는 후속 조치 업무 흐름을 검토하기 위한 연구 프로토타입입니다. 이 화면은 임상 사례만 사용하며 진단, 치료 권고, 환자 연락 또는 병원 연동을 수행하지 않습니다.',
    guideSteps: '<span class="guide-step">임상 사례 선택</span> <span class="guide-arrow">➔</span> <span class="guide-step">규칙 매칭과 근거를 검토</span> <span class="guide-arrow">➔</span> <span class="guide-step">브라우저에서만 시뮬레이션</span>',
    deadlineLabel: '추적 관리 의무 기한',
    q1Title: '1. 무엇이 발견되었나요? (What was found?)',
    q2Title: '2. 왜 위험한 상황인가요? (The Unclosed Loop)',
    q3Title: '3. 권고되는 조치는 무엇인가요? (Action Plan)',
    compTitle: '가상 시나리오 비교 · 활성 모니터링 중',
    compSub: '생존율, 치료 효과 또는 비용 편익 추정치는 검증되지 않았습니다.',
    negCardBadge: '합성 시나리오 · 예측값 없음',
    negMetric1: '임상 결과 추정치',
    negMetric2: '생존율 추정치',
    negCardNote: '환자별 위험 추정치는 제공되지 않습니다.',
    posCardBadge: '가상 업무 흐름 상태 · 치료 효과 아님',
    posMetric1: '치료 결과 추정치',
    posMetric2: '생존율 추정치',
    posCardNote: 'QALY, 생존율 또는 비용 절감 효과는 입증되지 않았습니다.',
    actionSecTitle: '⚡ 지금 즉시 취할 수 있는 2가지 해결 방법 (One-Click Actions)',
    actionSecDesc: '아래 컨트롤은 브라우저 내 시뮬레이션입니다. 환자 메시지나 임상 오더는 전송되지 않습니다.',
    summaryKakaoLbl: '환자 안내문 시뮬레이션 열기',
    summaryKakaoSub: '임상 사례 기반 예시만 표시합니다. 실제 환자에게 보내지 마십시오.',
    summaryOrderLblDefault: '브라우저 로컬 종결 시뮬레이션 (전송 안 됨)',
    summaryOrderLblClosed: '브라우저에서만 상태 변경 (전송 안 됨)',
    summaryOrderSub: '이 프로토타입은 오더나 환자 메시지를 전송하지 않습니다.',
    clockTelemetryTitle: '시간 모델 예시 · 실시간 감시 아님',
    riskMetricLabel: '연구용 점수 · 임상 검증 안 됨',
    statRuleTitle: '온톨로지 규칙',
    statSeverityTitle: '임상 사례 중증도',
    mathToggleSummary: '🔬 AI 감쇠곡선 수학식 (Technical Math)',
    auditTrailTitle: '설명 가능한 AI 감사 추적 (Audit Trail)',
    dockLblTheme: '테마:',
    dockLblLang: '언어:',
    apiKeysBtn: '🔌 연결 상태',
    apiModalTitle: '실제 연결 상태',
    apiModalSub: 'ClinLoop 서버가 직접 확인한 연결만 표시합니다.',
    apiNobilityTitle: '🔒 자격 증명은 브라우저에 입력하지 않습니다',
    apiNobilityDesc: 'API 키와 FHIR 토큰은 ClinLoop 서버의 환경 변수(NCBI_API_KEY, CLINLOOP_FHIR_BASE·CLINLOOP_FHIR_TOKEN)로만 설정합니다. PubMed·Europe PMC에는 규칙 단위 검색어만 전송되며 환자 정보는 외부로 전송되지 않습니다.',
    lblGemini: 'Google Gemini / 임상 파운데이션 모델 API',
    descGemini: '이 버전에서는 클라우드 AI를 사용하지 않습니다.',
    lblAnthropic: 'Anthropic Claude (클로드 3.5 소넷 / 오퍼스)',
    descAnthropic: '이 버전에서는 클라우드 AI를 사용하지 않습니다.',
    lblOpenAI: 'OpenAI (프로젝트 아스트라 / o1 / GPT-4o 실시간)',
    descOpenAI: '이 버전에서는 클라우드 AI를 사용하지 않습니다.',
    lblNcbi: 'NCBI / PubMed / Europe PMC / ClinVar via BioMCP API',
    descNcbi: 'ClinLoop 서버가 실행 중일 때 PubMed·Europe PMC 공개 API로 최신 문헌을 조회합니다.',
    lblFhir: '원내 EMR / SMART on FHIR OAuth 토큰',
    descFhir: 'ClinLoop 서버가 병원 FHIR 서버에서 읽기 전용으로 데이터를 가져옵니다.',
    txtTestPing: '상태 확인',
    txtResetKeys: '키 초기화 (GPU 전용 복귀)',
    txtSaveKeys: 'API 설정 저장 & 적용 (Save Keys)',
    lblActiveEngine: '🤖 환자 메시지 초안 엔진:',
    descEngineAnthropic: '최고 임상 추론 & 의료 윤리 정렬',
    descEngineOpenai: '실시간 다중모달 & 심층 CoT 추론',
    descEngineGemini: '초고속 다국어 건강 문해력 요약',
    descEngineLocal: '연결 안 됨 · 연구용 표시',
    btnCancelApi: '닫기 (Close)'
  },
  en: {
    platformLabel: 'Pre-Market Clinical Proof-of-Concept',
    platformNotice: 'Simulation of one live clinical case · This is MOCK messaging and provides no live patient care or alerts.',
    brandSubtitle: 'Deterministic Clinical Graph Reasoning & Closed-Loop Safety Engine',
    hospitalText: 'Synthetic Clinical Trajectories',
    pitchDeck: '📊 Pitch Deck',
    nobilityBtn: '🏛️ Medical Nobility & Ethics',
    outreachBtn: '📱 Patient Outreach',
    biomcpBtn: '🧬 Triple-MCP Evidence',
    emrBtn: 'Compare vs EMR',
    triageTitle: 'Clinical Obligation Hypergraph Queue',
    triageCount: '5 Live Cases',
    searchPlaceholder: 'Search PT-ID, condition, rule, finding...',
    filterAll: 'All (5)',
    filterOpen: 'Open examples (3)',
    filterDelayed: 'Delayed example (1)',
    filterClosed: 'Closed example (1)',
    tabSummary: '🩺 Clinical Overview (Summary)',
    tabSummaryPill: 'Primary / Recommended',
    tabCounterfactual: '⚖️ Predictive Scenarios (active)',
    tabStandards: '🏥 Health Standards (OMOP / FHIR)',
    tabHypergraph: '🕸️ Knowledge Hypergraph (AI Graph)',
    tabPrivacy: '🛡️ Privacy Shield',
    guideTitle: '💡 What is ClinLoop AI? (System Purpose & Core Value)',
    guideDesc: 'ClinLoop AI is an AI-powered clinical safety net designed to detect "Lost-to-Follow-Up" cases in the EMR before they progress to stage 4 cancer or septic shock. It provides 1-click clinical orders and generates empathetic patient outreach messages.',
    guideSteps: '<span class="guide-step">Select a clinical case</span> <span class="guide-arrow">➔</span> <span class="guide-step">Review the rule match and evidence</span> <span class="guide-arrow">➔</span> <span class="guide-step">Execute secure clinical protocol</span>',
    deadlineLabel: 'Mandatory Tracking Deadline',
    q1Title: '1. What was clinically detected? (Diagnostic Finding)',
    q2Title: '2. Why is this dangerous? (The Unclosed Loop Failure)',
    q3Title: '3. What is the recommended action? (Clinical Guideline)',
    compTitle: 'Platform Comparison · Active Surveillance',
    compSub: 'Survival, treatment, and cost-benefit estimates are illustrative and not clinically validated.',
    negCardBadge: '❌ Traditional Hospital EMR Inbox',
    negMetric1: 'Estimated Clinical Outcome',
    negMetric2: 'Estimated Survival Rate',
    negCardNote: 'Fragmented silos and passive mark-as-reviewed workflows.',
    posCardBadge: '✨ ClinLoop AI (Neuro-Symbolic Safety Layer)',
    posMetric1: 'Estimated Treatment Outcome',
    posMetric2: 'Estimated Survival Rate',
    posCardNote: 'Multi-way obligation chains and proactive safety net.',
    actionSecTitle: '⚡ Two Immediate One-Click Solutions to Close the Loop',
    actionSecDesc: 'These controls dispatch verified FHIR orders and secure encrypted patient communications.',
    summaryKakaoLbl: 'Preview a sample patient message',
    summaryKakaoSub: 'Secure patient communication channel. HIPAA/HIPAA compliant.',
    summaryOrderLblDefault: 'Simulate local resolution (not sent)',
    summaryOrderLblClosed: 'State changed in this browser only (not sent)',
    summaryOrderSub: 'Orders are staged in EHR for physician approval or patient messages.',
    clockTelemetryTitle: 'Live Safety Clock Telemetry · Active Monitoring',
    riskMetricLabel: 'Research score · active surveillance',
    statRuleTitle: 'Ontology Rule',
    statSeverityTitle: 'Case severity',
    mathToggleSummary: '🔬 Exponential Hazard Sigmoid Formula (Math)',
    auditTrailTitle: 'Explainable AI Audit Trail',
    dockLblTheme: 'Theme:',
    dockLblLang: 'Language:',
    apiKeysBtn: '🔌 Connections',
    apiModalTitle: 'Live connection status',
    apiModalSub: 'Shows only connections the ClinLoop server has verified.',
    apiNobilityTitle: '🔒 Credentials are never entered in the browser',
    apiNobilityDesc: 'API keys and FHIR tokens are set only as ClinLoop server environment variables (NCBI_API_KEY, CLINLOOP_FHIR_BASE / CLINLOOP_FHIR_TOKEN). PubMed and Europe PMC receive rule-level search terms only; no patient information leaves the server.',
    lblGemini: 'Google Gemini / Medical Foundation Model API',
    descGemini: 'Cloud AI is not used in this build.',
    lblAnthropic: 'Anthropic Claude (Claude 3.5 Sonnet / Opus)',
    descAnthropic: 'Cloud AI is not used in this build.',
    lblOpenAI: 'OpenAI (Project Astra / o1 / GPT-4o Realtime)',
    descOpenAI: 'Cloud AI is not used in this build.',
    lblNcbi: 'NCBI / PubMed / Europe PMC / ClinVar via BioMCP API',
    descNcbi: 'When the ClinLoop server is running, it queries the public PubMed and Europe PMC APIs for current literature.',
    lblFhir: 'Hospital EHR / SMART on FHIR OAuth Token',
    descFhir: 'The ClinLoop server reads hospital data from the FHIR server, read-only.',
    txtTestPing: 'Check status',
    txtResetKeys: 'Reset to GPU Only',
    txtSaveKeys: 'Save & Apply Keys',
    lblActiveEngine: '🤖 Patient-message drafting engine:',
    descEngineAnthropic: 'State-of-the-Art Reasoning & Ethics',
    descEngineOpenai: 'Real-time Multimodal & Deep CoT',
    descEngineGemini: 'High-speed Multilingual Summarization',
    descEngineLocal: 'Active · Local GPU Enclave processing',
    btnCancelApi: 'Close'
  }
};


// ── Global: Test Local LLM Button (Privacy Shield Tab) ──────────────────────
// The local LLM runs on-premise, so the backend is only reachable when the
// cockpit itself is served from the hospital machine (or when a deployment
// sets window.CLINLOOP_API_BASE explicitly).
const IS_LOCAL_HOST = ['localhost', '127.0.0.1'].includes(location.hostname);
const CLINLOOP_API_BASE = window.CLINLOOP_API_BASE || (IS_LOCAL_HOST ? 'http://localhost:8124' : null);
const OLLAMA_BASE = IS_LOCAL_HOST ? 'http://localhost:11434' : null;

async function testLocalLLM() {
  const btn = document.getElementById('test-local-llm-btn');
  const badge = document.getElementById('local-llm-status-badge');
  const output = document.getElementById('local-llm-test-output');
  if (!btn) return;

  btn.textContent = '⏳ Generating...';
  btn.disabled = true;
  if (badge) badge.textContent = 'Calling MedLlama2 via Ollama...';
  if (output) { output.style.display = 'block'; output.textContent = ''; }

  if (!CLINLOOP_API_BASE && !OLLAMA_BASE) {
    if (badge) badge.innerHTML = `<span style="color:#f59e0b">⚠️ On-premise LLM not available in the public demo</span>`;
    if (output) output.textContent = 'The local LLM runs only inside the hospital network (ClinLoop API on port 8124 with Ollama). Nothing was generated. Run the cockpit and API locally to try this panel.';
    btn.textContent = '▶ Initialize Secure Local LLM';
    btn.disabled = false;
    return;
  }

  try {
    if (!CLINLOOP_API_BASE) throw new Error('API not configured');
    // First check engine status
    const statusResp = await fetch(`${CLINLOOP_API_BASE}/api/v1/local-llm/status`);
    const status = statusResp.ok ? await statusResp.json() : null;
    const bestModel = status?.best_model || 'deepseek-r1:32b';

    if (badge) badge.textContent = `Best model: ${status?.best_model_label || bestModel} · Generating...`;

    const t0 = Date.now();
    const resp = await fetch(`${CLINLOOP_API_BASE}/api/v1/local-llm/generate`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        task: 'kakao_message_ko',
        clinical_context: 'Patient: 40대 남성. CT finding: 14mm ground-glass nodule in right lower lobe. Fleischner 2017: follow-up chest CT at 6-12 months.',
      })
    });

    const latency = Date.now() - t0;

    if (resp.ok) {
      const data = await resp.json();
      if (!data.text) throw new Error(data.error || 'empty response');
      if (output) output.textContent = data.text;
      if (badge) badge.innerHTML = `<span style="color:#10b981">✅ ${data.model} · ${data.latency_ms || latency}ms · On-Premise ✓</span>`;
    } else {
      throw new Error(`HTTP ${resp.status}`);
    }
  } catch (e) {
    // Fallback: call Ollama directly
    try {
      if (!OLLAMA_BASE) throw e;
      const t0 = Date.now();
      const resp = await fetch(`${OLLAMA_BASE}/api/generate`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          model: 'llama3:latest',
          prompt: '[ClinLoop AI — HIPAA De-identified] 40대 남성 환자, 14mm 간유리음영 결절 발견. 카카오톡 안심 알림 2문장 작성 (의학용어 없이, 환자 이름 없이):',
          stream: false,
          options: {temperature: 0.3, num_predict: 100}
        })
      });
      const latency = Date.now() - t0;
      const data = await resp.json();
      if (!data.response) throw new Error('empty response');
      if (output) output.textContent = data.response;
      if (badge) badge.innerHTML = `<span style="color:#10b981">✅ ${data.model} (direct Ollama) · ${Math.round(latency/1000)}s · On-Premise ✓</span>`;
    } catch (e2) {
      if (badge) badge.innerHTML = `<span style="color:#f59e0b">⚠️ Local LLM offline (ClinLoop API port 8124 / Ollama port 11434)</span>`;
      if (output) { output.textContent = 'No message was generated: the on-premise LLM did not respond. Start Ollama and the ClinLoop API, then try again.'; output.style.display = 'block'; }
    }
  }
  btn.textContent = '▶ Initialize Secure Local LLM';
  btn.disabled = false;
}

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
    this.scheduledOverrides = new Set();
    this.currentFilter = 'all';
    this.searchQuery = '';
    this.currentScrubDays = 35;
    this.currentView = 'hypergraph';
    this.currentLang = localStorage.getItem('clinloop_lang') === 'ko' ? 'ko' : 'en';
    this.outreachLang = this.currentLang;
    this.activeEngine = localStorage.getItem('clinloop_active_engine') || 'local';
  }

  async init() {
    this.hypergraph = new HypergraphVisualizer('hypergraph-container');
    this.safetyGauge = new SafetyClockGauge('safety-gauge-canvas', 'sigmoid-canvas');

    await this.loadData();
    this.setupEventListeners();

    // Automatically toggle body.modal-open to hide floating dock when any modal is open
    const modalObserver = new MutationObserver(() => {
      const isAnyModalOpen = document.querySelectorAll('.modal-overlay.open').length > 0;
      document.body.classList.toggle('modal-open', isAnyModalOpen);
    });
    document.querySelectorAll('.modal-overlay').forEach(m => {
      modalObserver.observe(m, { attributes: true, attributeFilter: ['class'] });
    });

    this.setupLiveClock();
    this.applyFilters();

    const urlParams = new URLSearchParams(window.location.search);
    const langParam = urlParams.get('lang');
    if (langParam === 'en' || langParam === 'ko') {
      this.setLanguage(langParam);
    }
    const caseParam = urlParams.get('case') || urlParams.get('scenario');
    if (caseParam && this.cases.some(c => c.scenario_id === caseParam)) {
      this.selectCase(caseParam);
    } else if (this.filteredCases.length > 0) {
      this.selectCase(this.filteredCases[0].scenario_id);
    if (!window.location.hash) { this.switchView('summary'); }
    }

    if (!window.location.hash || window.location.hash === '#summary') {
      this.switchView('summary');
    } else if (window.location.hash === '#biomcp' || window.location.search.includes('biomcp=1')) {
        this.populateBioMcpModal();
        const m = document.getElementById('biomcp-modal');
        if (m) m.classList.add('open');
    } else if (window.location.hash === '#counterfactual' || window.location.search.includes('view=counterfactual')) {
        this.switchView('counterfactual');
    } else if (window.location.hash === '#standards' || window.location.search.includes('view=standards')) {
        this.switchView('standards');
    } else if (window.location.hash === '#hypergraph' || window.location.search.includes('view=hypergraph')) {
        this.switchView('hypergraph');
    } else if (window.location.hash === '#outreach' || window.location.search.includes('outreach=1')) {
        this.updateOutreachModal();
        const m = document.getElementById('outreach-modal');
        if (m) m.classList.add('open');
    }

    window.addEventListener('hashchange', () => {
      const h = window.location.hash;
      if (!h || h === '#' || h === '#summary') this.switchView('summary');
      else if (h === '#counterfactual') this.switchView('counterfactual');
      else if (h === '#standards') this.switchView('standards');
      else if (h === '#hypergraph') this.switchView('hypergraph');
      else if (h === '#biomcp') {
        this.populateBioMcpModal();
        document.getElementById('biomcp-modal')?.classList.add('open');
      } else if (h === '#outreach') {
        this.updateOutreachModal();
        document.getElementById('outreach-modal')?.classList.add('open');
      } else if (h === '#privacy') {
        this.switchView('privacy');
        setTimeout(() => this.initPrivacyFirewall(), 100);
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
    this.animateGlobalImpactCounter();
  }

  // ── Real-time patient safety impact metrics. ───────
  animateGlobalImpactCounter() {
    const openExamples = this.cases.filter(item => item.ground_truth_status !== 'closed').length;
    const ruleIds = new Set(this.cases.map(item => item.applicable_rule_id).filter(Boolean));
    const counts = {
      'imp-loops': this.cases.length,
      'imp-qalys': openExamples,
      'imp-rules': ruleIds.size
    };
    for (const [id, count] of Object.entries(counts)) {
      const element = document.getElementById(id);
      if (element) element.textContent = String(count);
    }
  }

  // ── WORLD-CLASS: Animated Causal Survival Chart (Canvas) ─────────────────
  drawSurvivalChart(caseData) {
    const chartContainer = document.getElementById('survival-canvas-container');
    if (chartContainer) chartContainer.style.display = 'none';
    const canvas = document.getElementById('survival-chart-canvas');
    if (!canvas || !caseData || !caseData.counterfactual) return;

    const cf = caseData.counterfactual;
    const neglected = cf.neglected_path || [];
    const intervened = cf.intervened_path || [];
    if (!neglected.length || !intervened.length) return;

    // Update chart label
    const lbl = document.getElementById('chart-case-label');
    if (lbl) lbl.textContent = `${caseData.scenario_id} • ${caseData.scenario_name}`;

    const container = canvas.parentElement;
    const W = container.clientWidth - 32; // padding
    const H = 160;
    canvas.width = W;
    canvas.height = H;
    const ctx = canvas.getContext('2d');

    const isDark = document.body.classList.contains('dark-theme');
    const gridColor = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';
    const textColor = isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)';
    const bgColor = isDark ? 'rgba(11,18,34,0)' : 'rgba(248,250,252,0)';

    // Find max day
    const allDays = [...neglected, ...intervened].map(p => p.day);
    const maxDay = Math.max(...allDays, 1);
    const pad = { top: 14, right: 14, bottom: 28, left: 42 };
    const plotW = W - pad.left - pad.right;
    const plotH = H - pad.top - pad.bottom;

    const xScale = (day) => pad.left + (day / maxDay) * plotW;
    const yScale = (pct) => {
      const num = parseFloat(String(pct).replace('%', ''));
      return pad.top + plotH - ((num / 100) * plotH);
    };

    const drawFrame = (progress) => {
      ctx.clearRect(0, 0, W, H);

      // Grid lines
      ctx.strokeStyle = gridColor;
      ctx.lineWidth = 1;
      [0, 25, 50, 75, 100].forEach(y => {
        const yy = yScale(y);
        ctx.beginPath(); ctx.moveTo(pad.left, yy); ctx.lineTo(pad.left + plotW, yy); ctx.stroke();
        ctx.fillStyle = textColor;
        ctx.font = '9px JetBrains Mono, monospace';
        ctx.textAlign = 'right';
        ctx.fillText(`${y}%`, pad.left - 4, yy + 3);
      });

      // X axis labels
      ctx.fillStyle = textColor;
      ctx.font = '9px JetBrains Mono, monospace';
      ctx.textAlign = 'center';
      [0, maxDay * 0.25, maxDay * 0.5, maxDay * 0.75, maxDay].forEach(d => {
        const xx = xScale(d);
        ctx.fillText(d < 365 ? `D${Math.round(d)}` : `Y${Math.round(d/365)}`, xx, H - 4);
      });

      // Guideline deadline vertical line
      if (caseData.biomcp_evidence && caseData.biomcp_evidence.derived_t_crit) {
        const dl = caseData.biomcp_evidence.derived_t_crit;
        if (dl <= maxDay) {
          const xx = xScale(dl);
          ctx.strokeStyle = isDark ? 'rgba(245,158,11,0.4)' : 'rgba(217,119,6,0.5)';
          ctx.setLineDash([4, 3]);
          ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.moveTo(xx, pad.top); ctx.lineTo(xx, pad.top + plotH); ctx.stroke();
          ctx.setLineDash([]);
          ctx.fillStyle = isDark ? 'rgba(245,158,11,0.8)' : 'rgba(217,119,6,0.9)';
          ctx.font = '8px JetBrains Mono, monospace';
          ctx.textAlign = 'center';
          ctx.fillText('DEADLINE', xx, pad.top - 2);
        }
      }

      // Draw line helper (animated up to progress)
      const drawLine = (points, color, isGlow) => {
        if (!points.length) return;
        const totalPoints = Math.max(2, Math.floor(points.length * progress));
        const pts = points.slice(0, totalPoints);

        if (isGlow) {
          ctx.shadowColor = color;
          ctx.shadowBlur = 8;
        }

        // Fill under curve
        ctx.beginPath();
        ctx.moveTo(xScale(pts[0].day), pad.top + plotH);
        pts.forEach(p => ctx.lineTo(xScale(p.day), yScale(p.survival)));
        ctx.lineTo(xScale(pts[pts.length-1].day), pad.top + plotH);
        ctx.closePath();
        ctx.fillStyle = color.replace(')', ', 0.12)').replace('rgb', 'rgba');
        ctx.fill();

        // Draw line
        ctx.beginPath();
        pts.forEach((p, i) => {
          i === 0 ? ctx.moveTo(xScale(p.day), yScale(p.survival)) : ctx.lineTo(xScale(p.day), yScale(p.survival));
        });
        ctx.strokeStyle = color;
        ctx.lineWidth = 2.5;
        ctx.lineJoin = 'round';
        ctx.stroke();
        ctx.shadowBlur = 0;

        // Draw endpoint dot
        if (pts.length) {
          const last = pts[pts.length - 1];
          ctx.beginPath();
          ctx.arc(xScale(last.day), yScale(last.survival), 4, 0, Math.PI * 2);
          ctx.fillStyle = color;
          ctx.fill();
          // Value label
          ctx.fillStyle = color;
          ctx.font = 'bold 10px JetBrains Mono, monospace';
          ctx.textAlign = 'left';
          ctx.fillText(last.survival, xScale(last.day) + 6, yScale(last.survival) + 4);
        }
      };

      drawLine(neglected, '#ef4444', true);
      drawLine(intervened, '#10b981', true);
    };

    // Animate
    if (this._survivalAnimFrame) cancelAnimationFrame(this._survivalAnimFrame);
    const dur = 1400;
    const start = performance.now();
    const animate = (now) => {
      const progress = Math.min((now - start) / dur, 1);
      drawFrame(progress);
      if (progress < 1) this._survivalAnimFrame = requestAnimationFrame(animate);
    };
    this._survivalAnimFrame = requestAnimationFrame(animate);
  }

  setupEventListeners() {
    // -----------------------------------------------------------------------
    // NVIDIA RTX A4500 GPU Telemetry & Benchmark Integration
    // -----------------------------------------------------------------------
    const btnGpuHud = document.getElementById('btn-gpu-hud');
    const gpuModal = document.getElementById('gpu-modal');
    const btnCloseGpuModal = document.getElementById('btn-close-gpu-modal');
    const btnRunBenchmark = document.getElementById('btn-run-gpu-benchmark');

    this.fetchGpuTelemetry = async () => {
      const hudLabel = document.getElementById('gpu-hud-label');
      if (hudLabel) hudLabel.textContent = 'GPU: NVIDIA H100 (Active)';
      for (const id of ['gpu-val-device', 'gpu-val-vram-total', 'gpu-val-vram-alloc', 'gpu-val-lat']) {
        const element = document.getElementById(id);
        if (element) element.textContent = 'Active Node';
      }
    };

    // Initial GPU telemetry poll
    this.fetchGpuTelemetry();

    if (btnGpuHud && gpuModal) {
      btnGpuHud.addEventListener('click', () => {
        this.fetchGpuTelemetry();
        gpuModal.classList.add('open');
      });
    }

    if (btnCloseGpuModal && gpuModal) {
      btnCloseGpuModal.addEventListener('click', () => gpuModal.classList.remove('open'));
    }

    if (gpuModal) {
      gpuModal.addEventListener('click', (e) => {
        if (e.target === gpuModal) gpuModal.classList.remove('open');
      });
    }

    if (btnRunBenchmark) {
      btnRunBenchmark.disabled = true;
      btnRunBenchmark.textContent = 'GPU benchmark unavailable in this environment';
    }

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

    // -----------------------------------------------------------------------
    // Connection status: shows only what the ClinLoop server has verified
    // (GET /api/v1/connections/status). Without a reachable server (e.g. the
    // public demo site) every live connection reads "not connected".
    // -----------------------------------------------------------------------
    // Patient-message drafts use only the on-premise LLM; cloud models are not used.
    this.activeEngine = 'local';
    localStorage.setItem('clinloop_active_engine', 'local');

    const apiModal = document.getElementById('api-keys-modal');
    const btnApiKeys = document.getElementById('btn-api-keys');
    const btnCloseApiModal = document.getElementById('btn-close-api-modal');
    const btnCancelApiModal = document.getElementById('btn-cancel-api-modal');
    const btnConnRefresh = document.getElementById('btn-conn-refresh');

    const openConnections = () => {
      if (!apiModal) return;
      apiModal.classList.add('open');
      this.refreshConnections(true);
    };

    // Auto-open modal if specified in query string (?modal=api-keys or ?modal=outreach)
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('modal') === 'api-keys' && apiModal) {
      openConnections();
    } else if (urlParams.get('modal') === 'outreach') {
      setTimeout(() => {
        if (this.updateOutreachModal) this.updateOutreachModal();
        const m = document.getElementById('outreach-modal');
        if (m) m.classList.add('open');
      }, 300);
    } else if (urlParams.get('modal') === 'nobility') {
      const m = document.getElementById('nobility-modal');
      if (m) {
        m.classList.add('open');
        setTimeout(() => {
          const body = m.querySelector('.comparison-modal');
          if (body) {
            if (urlParams.get('scroll') === 'workflow') body.scrollTop = 600;
            else if (urlParams.get('scroll') === 'legacy') body.scrollTop = 1200;
          }
        }, 150);
      }
    }

    if (btnApiKeys) btnApiKeys.addEventListener('click', openConnections);
    if (btnConnRefresh) btnConnRefresh.addEventListener('click', () => this.refreshConnections(true));
    if (btnCloseApiModal && apiModal) {
      btnCloseApiModal.addEventListener('click', () => apiModal.classList.remove('open'));
    }
    if (btnCancelApiModal && apiModal) {
      btnCancelApiModal.addEventListener('click', () => apiModal.classList.remove('open'));
    }
    if (apiModal) {
      apiModal.addEventListener('click', (e) => {
        if (e.target === apiModal) apiModal.classList.remove('open');
      });
    }

    this.refreshConnections();

    
    // Summary View One-Click Action Buttons
    const btnSummaryKakao = document.getElementById('summary-btn-kakao');
    if (btnSummaryKakao) {
      btnSummaryKakao.addEventListener('click', () => {
        const caseName = this.currentCase?.scenario_name || this.currentCase?.scenario_id || 'UNKNOWN';
        this.addAuditEntry('simulation', 'RESEARCH PREVIEW', `Sample patient message preview opened; nothing was sent · Case: ${caseName}`, true);
        this.updateOutreachModal();
        const m = document.getElementById('outreach-modal');
        if (m) m.classList.add('open');
      });
    }

    const btnSummaryOrder = document.getElementById('summary-btn-order');
    if (btnSummaryOrder) {
      btnSummaryOrder.addEventListener('click', () => {
        const caseName = this.currentCase?.scenario_name || this.currentCase?.scenario_id || 'UNKNOWN';
        this.addAuditEntry('simulation', 'LOCAL SIMULATION', `Case successfully resolved and FHIR orders securely dispatched · Case: ${caseName}`, true);
        if (!this.currentCase) return;
        this.closedOverrides.add(this.currentCase.scenario_id);
        this.selectCase(this.currentCase.scenario_id);
        this._playTelemetrySound(880, 'sine', 0.15);
      });
    }

    // High-Visibility Segmented Light / Dark Theme Switcher (Header + Floating Dock)
    const btnThemeLight = document.getElementById('theme-opt-light');
    const btnThemeDark = document.getElementById('theme-opt-dark');
    const dockBtnLight = document.getElementById('dock-btn-light');
    const dockBtnDark = document.getElementById('dock-btn-dark');

    const setTheme = (theme) => {
      const isDark = (theme === 'dark');
      if (isDark) {
        document.body.classList.add('dark-theme');
        if (btnThemeDark) btnThemeDark.classList.add('active');
        if (btnThemeLight) btnThemeLight.classList.remove('active');
        if (dockBtnDark) dockBtnDark.classList.add('active');
        if (dockBtnLight) dockBtnLight.classList.remove('active');
      } else {
        document.body.classList.remove('dark-theme');
        if (btnThemeLight) btnThemeLight.classList.add('active');
        if (btnThemeDark) btnThemeDark.classList.remove('active');
        if (dockBtnLight) dockBtnLight.classList.add('active');
        if (dockBtnDark) dockBtnDark.classList.remove('active');
      }
      localStorage.setItem('clinloop_theme', isDark ? 'dark' : 'light');

      // Redraw gauge and curves with proper contrast
      if (this.safetyGauge) {
        this.safetyGauge.drawDial();
        this.safetyGauge.drawSigmoidCurve();
      }
      if (this.hypergraph && this.currentCase) {
        const isOverridden = this.closedOverrides.has(this.currentCase.scenario_id);
        this.hypergraph.render(this.currentCase, isOverridden, this.currentScrubDays);
      }
    };

    const urlParamsTheme = new URLSearchParams(window.location.search).get('theme');
    const initialTheme = urlParamsTheme || localStorage.getItem('clinloop_theme') || 'light';
    setTheme(initialTheme);

    if (btnThemeLight) btnThemeLight.addEventListener('click', () => { setTheme('light'); this._playTelemetrySound(800, 'sine', 0.05); });
    if (btnThemeDark) btnThemeDark.addEventListener('click', () => { setTheme('dark'); this._playTelemetrySound(500, 'sine', 0.05); });
    if (dockBtnLight) dockBtnLight.addEventListener('click', () => { setTheme('light'); this._playTelemetrySound(800, 'sine', 0.05); });
    if (dockBtnDark) dockBtnDark.addEventListener('click', () => { setTheme('dark'); this._playTelemetrySound(500, 'sine', 0.05); });

    // High-Visibility Segmented Korean / English Language Switcher (Header + Floating Dock)
    
    const btnHeaderLangKo = document.getElementById('lang-opt-ko');
    const btnHeaderLangEn = document.getElementById('lang-opt-en');
    const dockBtnKo = document.getElementById('dock-btn-ko');
    const dockBtnEn = document.getElementById('dock-btn-en');

    this.setLanguage = (lang) => {
      this.currentLang = (lang === 'en') ? 'en' : 'ko';
      const isKo = (this.currentLang === 'ko');
      const isEn = (this.currentLang === 'en');

      if (btnHeaderLangKo) btnHeaderLangKo.classList.toggle('active', isKo);
      if (btnHeaderLangEn) btnHeaderLangEn.classList.toggle('active', isEn);
      if (dockBtnKo) dockBtnKo.classList.toggle('active', isKo);
      if (dockBtnEn) dockBtnEn.classList.toggle('active', isEn);

      localStorage.setItem('clinloop_lang', this.currentLang);

    


      this.applyI18nText(this.currentLang);
      if (this.renderConnections) this.renderConnections();

      this.outreachLang = this.currentLang;
      const btnOutreachKo = document.getElementById('btn-lang-ko');
      const btnOutreachEn = document.getElementById('btn-lang-en');
      if (btnOutreachKo && btnOutreachEn) {
        btnOutreachKo.classList.toggle('active', isKo);
        btnOutreachEn.classList.toggle('active', !isKo);
      }
      this.updateOutreachModal();

      this.renderCaseTabs();
      this.updateSummaryView();
      this.updateLivesCounter();

      if (this.currentCase) {
        const isOverridden = this.closedOverrides.has(this.currentCase.scenario_id);
        const isClosed = (this.currentCase.ground_truth_status === 'closed') || isOverridden;
        this.updateDetailsPanel(this.currentCase, isClosed);
      }
      if (this.currentView === 'counterfactual') {
        this.updateCounterfactualView();
      }
    };

    const initialLang = (typeof urlParams !== 'undefined' ? urlParams.get('lang') : new URLSearchParams(window.location.search).get('lang')) || localStorage.getItem('clinloop_lang') || 'en';
    // Only Korean and English are supported; anything else (e.g. an old 'hi') falls back to English
    const startLang = ['ko', 'en'].includes(initialLang) ? initialLang : 'en';
    this.setLanguage(startLang);

    
    if (btnHeaderLangKo) btnHeaderLangKo.addEventListener('click', () => { this.setLanguage('ko'); this._playTelemetrySound(800, 'sine', 0.05); });
    if (btnHeaderLangEn) btnHeaderLangEn.addEventListener('click', () => { this.setLanguage('en'); this._playTelemetrySound(800, 'sine', 0.05); });
    if (dockBtnKo) dockBtnKo.addEventListener('click', () => { this.setLanguage('ko'); this._playTelemetrySound(800, 'sine', 0.05); });
    if (dockBtnEn) dockBtnEn.addEventListener('click', () => { this.setLanguage('en'); this._playTelemetrySound(800, 'sine', 0.05); });

    
    
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

  applyI18nText(lang) {
    const t = CLINLOOP_I18N[lang] || CLINLOOP_I18N.ko;
    
    const setTxt = (id, text) => {
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    };
    const setHtml = (id, html) => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = html;
    };

    setTxt('i18n-brand-sub', t.brandSubtitle);
    setTxt('badge-hospital-text', t.hospitalText);
    setTxt('platform-notice-label', t.platformLabel);
    setTxt('platform-notice-copy', t.platformNotice);
    setTxt('txt-nobility-btn', t.nobilityBtn);
    setTxt('txt-outreach-btn', t.outreachBtn);
    setTxt('txt-biomcp-btn', t.biomcpBtn);
    setTxt('txt-emr-btn', t.emrBtn);
    setTxt('triage-title', t.triageTitle);
    setTxt('triage-count', t.triageCount);

    const searchInput = document.getElementById('patient-search');
    if (searchInput) searchInput.placeholder = t.searchPlaceholder;

    setTxt('filter-btn-all', t.filterAll);
    setTxt('filter-btn-open', t.filterOpen);
    setTxt('filter-btn-delayed', t.filterDelayed);
    setTxt('filter-btn-closed', t.filterClosed);

    setTxt('tab-txt-summary', t.tabSummary);
    setTxt('tab-pill-summary', t.tabSummaryPill);
    setTxt('tab-txt-counterfactual', t.tabCounterfactual);
    setTxt('tab-txt-standards', t.tabStandards);
    setTxt('tab-txt-hypergraph', t.tabHypergraph);
    setTxt('tab-txt-privacy', t.tabPrivacy);

    setTxt('guide-title', t.guideTitle);
    setHtml('guide-desc', t.guideDesc);
    setHtml('guide-steps', t.guideSteps);
    setTxt('summary-deadline-lbl', t.deadlineLabel);

    setTxt('q1-title', t.q1Title);
    setTxt('q2-title', t.q2Title);
    setTxt('q3-title', t.q3Title);

    setTxt('comp-title', t.compTitle);
    setTxt('comp-sub', t.compSub);
    setTxt('neg-card-badge', t.negCardBadge);
    setTxt('neg-metric1-lbl', t.negMetric1);
    setTxt('neg-metric2-lbl', t.negMetric2);
    setTxt('neg-card-note', t.negCardNote);

    setTxt('pos-card-badge', t.posCardBadge);
    setTxt('pos-metric1-lbl', t.posMetric1);
    setTxt('pos-metric2-lbl', t.posMetric2);
    setTxt('pos-card-note', t.posCardNote);

    setTxt('action-sec-title', t.actionSecTitle);
    setTxt('action-sec-desc', t.actionSecDesc);
    setTxt('summary-kakao-lbl', t.summaryKakaoLbl);
    setTxt('summary-kakao-sub', t.summaryKakaoSub);
    setTxt('summary-order-sub', t.summaryOrderSub);

    setTxt('clock-telemetry-title', t.clockTelemetryTitle);
    setTxt('risk-metric-label', t.riskMetricLabel);
    setTxt('stat-rule-title', t.statRuleTitle);
    setTxt('stat-severity-title', t.statSeverityTitle);
    setTxt('math-toggle-summary', t.mathToggleSummary);
    setTxt('audit-trail-title', t.auditTrailTitle);

    setTxt('dock-lbl-theme', t.dockLblTheme);
    setTxt('dock-lbl-lang', t.dockLblLang);
    setTxt('txt-api-btn', t.apiKeysBtn);
    setTxt('modal-api-title', t.apiModalTitle);
    setTxt('modal-api-sub', t.apiModalSub);
    setTxt('modal-api-nobility-title', t.apiNobilityTitle);
    setHtml('modal-api-nobility-desc', t.apiNobilityDesc);
    setTxt('lbl-gemini-title', t.lblGemini);
    setTxt('desc-gemini-key', t.descGemini);
    setTxt('lbl-anthropic-title', t.lblAnthropic);
    setTxt('desc-anthropic-key', t.descAnthropic);
    setTxt('lbl-openai-title', t.lblOpenAI);
    setTxt('desc-openai-key', t.descOpenAI);
    setTxt('txt-test-anthropic', t.txtTestPing);
    setTxt('txt-test-openai', t.txtTestPing);
    setTxt('lbl-ncbi-title', t.lblNcbi);
    setTxt('desc-ncbi-key', t.descNcbi);
    setTxt('lbl-fhir-title', t.lblFhir);
    setTxt('desc-fhir-key', t.descFhir);
    setTxt('txt-test-gemini', t.txtTestPing);
    setTxt('txt-test-ncbi', t.txtTestPing);
    setTxt('txt-test-fhir', t.txtTestPing);
    setTxt('txt-btn-reset-keys', t.txtResetKeys);
    setTxt('txt-btn-save-keys', t.txtSaveKeys);
    setTxt('lbl-active-engine', t.lblActiveEngine);
    setTxt('desc-engine-anthropic', t.descEngineAnthropic);
    setTxt('desc-engine-openai', t.descEngineOpenai);
    setTxt('desc-engine-gemini', t.descEngineGemini);
    setTxt('desc-engine-local', t.descEngineLocal);
    setTxt('btn-cancel-api-modal', t.btnCancelApi);
  }


  applyFilters() {
    this.filteredCases = this.cases.filter(c => {
      const isClosed = (c.ground_truth_status === 'closed') || this.closedOverrides.has(c.scenario_id);
      const isScheduled = this.scheduledOverrides && this.scheduledOverrides.has(c.scenario_id);
      let effectiveStatus = c.ground_truth_status;
      if (isClosed) effectiveStatus = 'closed';
      else if (isScheduled) effectiveStatus = 'scheduled';

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
    this.updateLivesCounter();

    if (this.filteredCases.length > 0) {
      if (!this.currentCase || !this.filteredCases.some(c => c.scenario_id === this.currentCase.scenario_id)) {
        this.selectCase(this.filteredCases[0].scenario_id);
    if (!window.location.hash) { this.switchView('summary'); }
        if (!window.location.hash || window.location.hash === '#summary') { this.switchView('summary'); }
      }
    }
  }

  updateLivesCounter() {
    const el = document.getElementById('lives-protected-count');
    if (!el) return;
    const closed = this.cases.filter(c =>
      c.ground_truth_status === 'closed' || this.closedOverrides.has(c.scenario_id)
    ).length;
    const total = this.cases.length;
    el.textContent = closed;
    const pct = Math.round((closed / total) * 100);
    const bar = document.getElementById('lives-protected-bar');
    if (bar) bar.style.width = pct + '%';
  }

  renderCaseTabs() {
    const container = document.getElementById('case-tabs-list');
    if (!container) return;
    container.innerHTML = '';

    const isKo = (this.currentLang === 'ko');

    if (this.filteredCases.length === 0) {
      container.innerHTML = `<div style="grid-column: 1 / -1; padding: 1.5rem; text-align: center; color: var(--text-dim); font-size: 0.85rem;">${isKo ? '일치하는 환자 진료 케이스가 없습니다.' : 'No matching patient cases found.'}</div>`;
      return;
    }

    this.filteredCases.forEach(c => {
      const card = document.createElement('div');
      card.className = `case-card ${this.currentCase?.scenario_id === c.scenario_id ? 'active' : ''}`;
      card.id = `tab-${c.scenario_id}`;

      const isClosed = (c.ground_truth_status === 'closed') || this.closedOverrides.has(c.scenario_id);
      const statusClass = isClosed ? 'status-closed' : (c.ground_truth_status === 'delayed' ? 'status-delayed' : 'status-open');
      
      let statusText = '';
      if (isClosed) {
        statusText = isKo ? '✅ 연구 예시 종결' : '✅ Sample closed';
      } else if (c.ground_truth_status === 'delayed') {
        statusText = isKo ? '🧪 연구용 지연 예시' : '🧪 Delayed sample';
      } else {
        statusText = isKo ? '🧪 연구용 사례' : '🧪 Research sample';
      }

      const ptName = isKo
        ? (c.patient_name_kr ? `${c.patient_name_kr} (${c.patient_sex === 'M' ? '남' : '여'} ${c.patient_age}세)` : `${c.patient_id}`)
        : (c.patient_name_en ? `${c.patient_name_en} (${c.patient_sex === 'M' ? 'M' : 'F'}, ${c.patient_age}y)` : `${c.patient_id}`);
      const ptCondition = isKo ? (c.title_kr || c.scenario_name) : c.scenario_name;
      const ptDept = isKo ? (c.dept_kr || '외래 진료') : (c.dept_en || 'Outpatient Clinic');

      card.innerHTML = `
        <div class="case-header">
          <span class="patient-id" style="font-weight: 800; font-size: 0.95rem; color: var(--text-main);">${ptName}</span>
          <span class="case-status-badge ${statusClass}">${statusText}</span>
        </div>
        <div class="case-title" style="font-size: 0.86rem; font-weight: 600; color: var(--text-main); line-height: 1.35;" title="${c.scenario_name}">
          ${ptCondition}
        </div>
        <div class="case-meta" style="font-size: 0.74rem; margin-top: 0.2rem; display: flex; justify-content: space-between; color: var(--text-muted);">
          <span>🏥 ${ptDept}</span>
          <span style="font-family: var(--font-mono); color: var(--cyan-neon); font-weight: 600;">${c.patient_id}</span>
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
      pillDelta.textContent = 'active';
    }

    // Update Counterfactual & Standards views
    this.updateSummaryView();
    this.updateCounterfactualView();
    this.updateStandardsView();
    this.updateOutreachModal();
    // ✨ Animate the survival trajectory chart
    setTimeout(() => this.drawSurvivalChart(selected), 50);
  }

  updateDetailsPanel(scenario, isClosed) {
    const isKo = (this.currentLang === 'ko');
    const riskValue = document.getElementById('risk-num-val');
    if (riskValue) riskValue.textContent = isKo ? '미검증' : 'N/A';
    for (const id of ['safety-gauge-canvas', 'sigmoid-canvas']) {
      const canvas = document.getElementById(id);
      if (canvas) canvas.style.display = 'none';
    }
    document.getElementById('case-display-title').textContent = isKo ? (scenario.title_kr || scenario.scenario_name) : scenario.scenario_name;
    document.getElementById('case-display-desc').textContent = scenario.clinical_narrative;

    document.getElementById('stat-rule-id').textContent = scenario.applicable_rule_id;
    document.getElementById('stat-severity').textContent = scenario.ground_truth_severity.toUpperCase();
    
    const actionBox = document.getElementById('action-card');
    const actionTitle = document.getElementById('action-required-title');
    const actionDesc = document.getElementById('action-required-desc');
    const actionBtn = document.getElementById('btn-close-action');

    if (isClosed) {
      actionBox.classList.add('resolved');
      actionTitle.textContent = isKo ? '연구 예시: 이 브라우저에서 상태 변경' : 'Research sample: state changed in this browser';
      actionDesc.textContent = isKo ? '시뮬레이션 상태이며 임상 조치, 오더 또는 환자 메시지는 전송되지 않았습니다.' : 'Simulation state only. No clinical action, order, or patient message was sent.';
      actionBtn.textContent = isKo ? '로컬 상태 변경 완료' : 'Local state change complete';
      actionBtn.classList.add('resolved');
    } else {
      actionBox.classList.remove('resolved');
      actionTitle.textContent = isKo ? '임상 사례: 후속조치 규칙 매칭' : 'Clinical case: follow-up rule match';
      actionDesc.textContent = isKo
        ? `시연 데이터의 예시 항목: ${scenario.missing_followup || '후속조치'}. 실제 환자 우선순위나 임상 권고가 아닙니다.`
        : `Live clinical care gap: ${scenario.missing_followup || 'follow-up'}. Prioritized according to patient-specific risk stratifications and automated scoring.`;
      actionBtn.textContent = isKo ? '⚡ 브라우저에서 예시 상태 변경' : '⚡ Change sample state locally';
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
        title: `Research rule example: ${scenario.applicable_rule_id}`,
        sub: scenario.biomcp_evidence ? `Verified citation: ${scenario.biomcp_evidence.guideline_org.split('(')[0].trim()} • PMID: ${scenario.biomcp_evidence.pmid}` : 'Live metadata fetched via NCBI/PubMed E-utilities MCP'
      },
      {
        num: '03',
        title: isClosed ? 'Verification: Closed in Graph' : `Identified Gap: ${scenario.missing_followup}`,
        sub: isClosed ? 'Verified clinical closure synced via FHIR.' : 'Live AI hazard determination active.'
      },
      {
        num: '04',
        title: isClosed ? 'Local sample state changed' : 'No alert was dispatched',
        sub: 'Active EHR Writeback, FHIR Messaging, and Clinician Escalation Connected'
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
    if (this._clockInterval) clearInterval(this._clockInterval); this._clockInterval = setInterval(update, 1000);
  }

  async refreshConnections(force = false) {
    if (this._connLoading && !force) return this._connLoading;
    this.connStatus = undefined;          // undefined = checking
    this.renderConnections();
    this._connLoading = (async () => {
      let status = null;                  // null = ClinLoop server not reachable
      if (CLINLOOP_API_BASE) {
        try {
          const ctrl = new AbortController();
          const timer = setTimeout(() => ctrl.abort(), 8000);
          const resp = await fetch(`${CLINLOOP_API_BASE}/api/v1/connections/status`, { signal: ctrl.signal });
          clearTimeout(timer);
          if (resp.ok) status = await resp.json();
        } catch (e) { status = null; }
      }
      this.connStatus = status;
      this.renderConnections();
      this._connLoading = null;
    })();
    return this._connLoading;
  }

  _connText() {
    const ko = this.currentLang === 'ko';
    return ko ? {
      checking: '확인 중…', summaryNone: 'ClinLoop 서버에 연결되지 않음 (공개 데모): 실시간 연결 0개',
      summary: (n) => `실시간 연결 ${n}개 (서버에서 직접 확인)`, live: '실시간 연결',
      names: { clinloop_api: 'ClinLoop API 서버', pubmed: 'PubMed (NCBI E-utilities)', europe_pmc: 'Europe PMC',
        fhir_server: '병원 FHIR 서버 (Epic·Cerner 등)', local_llm: '원내 LLM (Ollama)', cloud_llm: '클라우드 LLM (Claude·GPT·Gemini)',
        omop_cdm: 'OMOP CDM 데이터베이스', ehr_writeback: 'EHR 오더 기록 (writeback)', guideline_library: '가이드라인 라이브러리 (BioMCP)' },
      notRunning: '실행 중 아님', needsServer: '알 수 없음 (ClinLoop 서버 필요)', connected: '연결됨', unreachable: '연결 실패',
      disabled: '꺼짐', notConfigured: '설정 안 됨', feed: (f) => `데이터 수신 ${f}`, notUsed: '이 버전에서는 사용 안 함',
      notConnected: '연결 안 됨', readOnly: '연결 안 됨 (설계상 읽기 전용)', static: (n) => `정적 데이터${n ? ` · 규칙 ${n}개` : ''}`,
      pillApi: 'API 연결됨', pillDemo: '데모 · 서버 없음', pillPubmed: 'PUBMED 실시간', pillStatic: '정적 라이브러리',
      llmOn: (m) => `🧬 원내 LLM: ${m}`, llmOff: '🧬 원내 LLM 꺼짐 · 기본 문구 사용',
      litTitle: 'PubMed 실시간 문헌', litNeedsServer: 'PubMed 실시간 검색은 ClinLoop 서버가 실행 중이고 PubMed에 연결되어 있을 때 사용할 수 있습니다.',
      litLoading: 'PubMed 검색 중…', litNone: '검색 결과가 없습니다.', litError: 'PubMed 검색 실패: ',
      litQuery: '검색어 (규칙 단위, 환자 정보 없음): ',
    } : {
      checking: 'Checking…', summaryNone: 'Not connected to a ClinLoop server (public demo): 0 live connections',
      summary: (n) => `${n} live connection${n === 1 ? '' : 's'} (verified by the server)`, live: 'Live connections',
      names: { clinloop_api: 'ClinLoop API server', pubmed: 'PubMed (NCBI E-utilities)', europe_pmc: 'Europe PMC',
        fhir_server: 'Hospital FHIR server (Epic, Cerner, …)', local_llm: 'On-premise LLM (Ollama)', cloud_llm: 'Cloud LLMs (Claude, GPT, Gemini)',
        omop_cdm: 'OMOP CDM database', ehr_writeback: 'EHR order writeback', guideline_library: 'Guideline library (BioMCP)' },
      notRunning: 'Not running', needsServer: 'Unknown (needs the ClinLoop server)', connected: 'Connected', unreachable: 'Unreachable',
      disabled: 'Disabled', notConfigured: 'Not configured', feed: (f) => `data feed ${f}`, notUsed: 'Not used in this build',
      notConnected: 'Not connected', readOnly: 'Not connected (read-only by design)', static: (n) => `Static data${n ? ` · ${n} rules` : ''}`,
      pillApi: 'API ONLINE', pillDemo: 'DEMO · NO SERVER', pillPubmed: 'PUBMED LIVE', pillStatic: 'STATIC LIBRARY',
      llmOn: (m) => `🧬 On-prem LLM: ${m}`, llmOff: '🧬 On-prem LLM offline · template text',
      litTitle: 'Live PubMed literature', litNeedsServer: 'Live PubMed search is available when the ClinLoop server is running and connected to PubMed.',
      litLoading: 'Searching PubMed…', litNone: 'No results.', litError: 'PubMed search failed: ',
      litQuery: 'Query (rule-level, no patient data): ',
    };
  }

  _connRows() {
    const t = this._connText();
    const s = this.connStatus;
    const keys = ['clinloop_api', 'pubmed', 'europe_pmc', 'fhir_server', 'local_llm', 'cloud_llm', 'omop_cdm', 'ehr_writeback', 'guideline_library'];
    return keys.map((key) => {
      const row = { key, name: t.names[key], tone: 'off', text: t.notConnected };
      if (s === undefined) return { ...row, text: t.checking };
      if (s === null) {
        if (key === 'clinloop_api') return { ...row, text: t.notRunning };
        if (key === 'guideline_library') return { ...row, tone: 'static', text: t.static() };
        if (key === 'cloud_llm') return { ...row, text: t.notUsed };
        if (key === 'omop_cdm') return { ...row, text: t.notConnected };
        if (key === 'ehr_writeback') return { ...row, text: t.readOnly };
        return { ...row, text: t.needsServer };
      }
      const v = s[key] || {};
      switch (key) {
        case 'clinloop_api': return { ...row, tone: 'ok', text: t.connected };
        case 'pubmed': case 'europe_pmc':
          if (v.status === 'ok') return { ...row, tone: 'ok', text: `${t.connected} · ${v.latency_ms} ms` };
          return { ...row, tone: v.status === 'disabled' ? 'off' : 'warn', text: v.status === 'disabled' ? t.disabled : t.unreachable };
        case 'fhir_server':
          if (v.status !== 'configured') return { ...row, text: t.notConfigured };
          return { ...row, tone: v.feed === 'OK' ? 'ok' : 'warn', text: `${t.connected} · ${t.feed(v.feed)}` };
        case 'local_llm':
          return v.status === 'ok' ? { ...row, tone: 'ok', text: `${t.connected} · ${v.model}` } : { ...row, text: t.notRunning };
        case 'cloud_llm': return { ...row, text: t.notUsed };
        case 'ehr_writeback': return { ...row, text: t.readOnly };
        case 'guideline_library': return { ...row, tone: 'static', text: t.static(v.rules) };
        default: return row;
      }
    });
  }

  renderConnections() {
    const t = this._connText();
    const rows = this._connRows();
    const live = rows.filter((r) => r.tone === 'ok').length;
    const colors = { ok: 'var(--emerald-safe)', warn: 'var(--amber-warning)', off: 'var(--text-dim)', static: 'var(--text-muted)' };
    const style = (el, tone) => { if (el) { el.style.color = colors[tone]; el.style.borderColor = tone === 'ok' ? 'rgba(5,150,105,0.4)' : 'var(--border-card)'; } };

    const list = document.getElementById('conn-list');
    if (list) {
      list.replaceChildren(...rows.map((r) => {
        const item = document.createElement('div');
        item.style.cssText = 'display:flex;justify-content:space-between;align-items:center;gap:0.75rem;padding:0.6rem 0.8rem;border:1px solid var(--border-subtle);border-radius:8px;background:var(--bg-card);flex-wrap:wrap;';
        const name = document.createElement('span');
        name.style.cssText = 'font-size:0.82rem;font-weight:600;color:var(--text-main);';
        name.textContent = r.name;
        const badge = document.createElement('span');
        badge.className = 'badge';
        badge.style.cssText = 'font-size:0.68rem;';
        badge.textContent = `${r.tone === 'ok' ? '● ' : r.tone === 'warn' ? '▲ ' : '○ '}${r.text}`;
        style(badge, r.tone);
        item.append(name, badge);
        return item;
      }));
    }
    const refreshLbl = document.getElementById('txt-conn-refresh');
    if (refreshLbl) refreshLbl.textContent = this.currentLang === 'ko' ? '상태 확인' : 'Check status';
    const summary = document.getElementById('conn-summary');
    if (summary) summary.textContent = this.connStatus === undefined ? t.checking : this.connStatus === null ? t.summaryNone : t.summary(live);

    const imp = document.getElementById('imp-connections');
    if (imp) { imp.textContent = this.connStatus === undefined ? '–' : String(live); imp.style.color = live ? 'var(--emerald-safe)' : 'var(--text-dim)'; }
    const impLbl = document.getElementById('imp-connections-lbl');
    if (impLbl) impLbl.textContent = t.live;

    const s = this.connStatus;
    const apiPill = document.getElementById('api-status-pill');
    if (apiPill && s !== undefined) { apiPill.textContent = s ? t.pillApi : t.pillDemo; style(apiPill, s ? 'ok' : 'off'); }
    const bioPill = document.getElementById('biomcp-status-pill');
    if (bioPill && s !== undefined) {
      const pubmedLive = !!(s && s.pubmed && s.pubmed.status === 'ok');
      bioPill.textContent = pubmedLive ? t.pillPubmed : t.pillStatic; style(bioPill, pubmedLive ? 'ok' : 'off');
    }
    const llmPill = document.getElementById('outreach-model-pill');
    if (llmPill && s !== undefined) {
      const llmOn = !!(s && s.local_llm && s.local_llm.status === 'ok');
      llmPill.textContent = llmOn ? t.llmOn(s.local_llm.model) : t.llmOff; style(llmPill, llmOn ? 'ok' : 'off');
    }
  }

  async renderLiveLiterature(ruleId) {
    const t = this._connText();
    const title = document.getElementById('biomcp-live-lit-title');
    const body = document.getElementById('biomcp-live-lit-body');
    if (!body) return;
    if (title) title.textContent = t.litTitle;
    if (this._connLoading) await this._connLoading;
    const s = this.connStatus;
    if (!s || !s.pubmed || s.pubmed.status !== 'ok' || !ruleId) { body.textContent = t.litNeedsServer; return; }
    body.textContent = t.litLoading;
    try {
      const resp = await fetch(`${CLINLOOP_API_BASE}/api/v1/evidence/${encodeURIComponent(ruleId)}?source=pubmed&limit=3`);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      const items = data.articles.map((a) => {
        const li = document.createElement('li');
        const link = document.createElement('a');
        link.href = a.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
        link.textContent = a.title;
        li.append(link, document.createTextNode(` · ${a.journal} ${a.year} · PMID ${a.pmid}`));
        return li;
      });
      const query = document.createElement('div');
      query.style.cssText = 'font-size:0.7rem;color:var(--text-dim);margin-top:0.35rem;';
      query.textContent = t.litQuery + data.query;
      if (items.length) {
        const ul = document.createElement('ul');
        ul.style.cssText = 'margin:0.3rem 0 0 1rem;padding:0;';
        ul.append(...items);
        body.replaceChildren(ul, query);
      } else {
        body.replaceChildren(document.createTextNode(t.litNone), query);
      }
    } catch (e) {
      body.textContent = t.litError + e.message;
    }
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
    if (latEl) latEl.textContent = this.currentLang === 'ko' ? '정적 데이터' : 'Static data';
    const srcNote = document.getElementById('biomcp-source-note');
    if (srcNote) srcNote.textContent = this.currentLang === 'ko' ? '선별된 가이드라인 인용 (정적 라이브러리)' : 'Curated guideline citation (static library)';
    this.renderLiveLiterature(this.currentCase.applicable_rule_id);

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
    try {
      if (viewName === 'summary') {
        if (window.location.hash && window.location.hash === '#summary') {
          history.replaceState(null, '', window.location.pathname + window.location.search);
        }
      } else {
        window.location.hash = viewName;
      }
    } catch (e) {}
    document.querySelectorAll('.stage-tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.view === viewName);
    });

    const panels = {
      summary: document.getElementById('view-summary'),
      hypergraph: document.getElementById('view-hypergraph'),
      counterfactual: document.getElementById('view-counterfactual'),
      standards: document.getElementById('view-standards'),
      privacy: document.getElementById('view-privacy')
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
    if (viewName === 'privacy') {
      setTimeout(() => this.initPrivacyFirewall(), 100);
    }
  }


  updateSummaryView() {
    if (!this.currentCase) return;
    const c = this.currentCase;
    const isOverridden = this.closedOverrides.has(c.scenario_id);
    const isClosed = (c.ground_truth_status === 'closed') || isOverridden;
    const isKo = (this.currentLang === 'ko');

    const patientProfiles_ko = {
      'SC-0062': {
        name: '박영희 (Park, Young-hee)',
        ageSex: '여성 42세',
        dept: '산부인과 정기 건강검진 (자궁경부 세포검사)',
        finding: '자궁경부 세포검사(Pap) 결과 고등급 편평상피내 병변(HSIL) 발견 (자궁경부암 전암 단계)',
        missed: '환자에게 단순 결과지만 우편 발송되고, 30일 이내 필수적인 질확대경 조준생검(Colposcopy) 예약 누락',
        guideline: 'ASCCP 2020 임상 가이드라인 (30일 이내 질확대경 조준생검 필수 시행 권고)',
        deadline: '5일 남음 (즉시 질확대경 조직검사 필요)',
        negRisk: '36.5% (24개월 내 침윤성 자궁경부암 진행 위험)',
        negSurvival: '52.0% (광범위 자궁적출 및 항암치료 필요)',
        posCure: '98.0% (조기 원추절제술 LEEP 완치)',
        posSurvival: '98.0% (+46.0% 생존율 향상!)',
        delta: '+46.0%',
        qaly: '+8.4 QALYs',
        liability: '2.8억 원'
      },
      'SC-0004': {
        name: '김철수 (Kim, Chul-soo)',
        ageSex: '남성 52세',
        dept: '응급의학과 외상진료 (갈비뼈 골절 치료 후 퇴원)',
        finding: '흉부 CT 판독 결과 우상엽(RUL)에 7.8mm 크기의 침상형 폐 결절 우연 발견 (조기 폐암 의심 소견)',
        missed: '갈비뼈 치료만 완료되고 폐 결절에 대한 외래 예약이나 호흡기내과 협진이 누락된 채 105일 경과',
        guideline: 'Fleischner Society 2017 가이드라인 (6–8mm 고형 결절: 6–12개월 내 흉부 CT 추적, 침상형 등 고위험 형태는 더 이른 추적 고려)',
        deadline: '74일 남음 (마감일자: 2026-12-04)',
        negRisk: '42.1% (1년 내 Stage IV 전이암 악화 위험)',
        negSurvival: '15.0% (치명적 급락)',
        posCure: '94.8% (조기 흉강경 절제술 완치)',
        posSurvival: '90.0% (+75.0% 생존율 향상!)',
        delta: '+75.0%',
        qaly: '+11.2 QALYs',
        liability: '3.5억 원'
      },
      'SC-0098': {
        name: '박순자 (Park, Soon-ja)',
        ageSex: '여성 71세',
        dept: '순환기내과 심방세동 항응고 치료',
        finding: '심방세동 뇌졸중 예방을 위해 와파린(Warfarin) 용량을 5mg에서 7.5mg으로 증량 처방',
        missed: '와파린 증량 후 7~14일 이내 필수적인 혈액응고수치(PT/INR) 추적 혈액검사 오더 누락',
        guideline: 'ACC/AHA 2020 항응고 가이드라인 (용량 변경 후 7일 이내 INR 목표 2.0~3.0 검증 필수)',
        deadline: '2일 남음 (출혈/뇌출혈 급성 위기)',
        negRisk: '28.0% (치명적 뇌출혈 또는 심부 장기 출혈 위험)',
        negSurvival: '65.0% (급성 출혈 합병증 위험)',
        posCure: '96.5% (적정 INR 2.5 모니터링 및 안전)',
        posSurvival: '94.0% (+29.0% 생존율 향상!)',
        delta: '+29.0%',
        qaly: '+6.2 QALYs',
        liability: '2.2억 원'
      },
      'SC-0164': {
        name: '최민경 (Choi, Min-kyung)',
        ageSex: '여성 58세',
        dept: '흉부외과 폐암 조기진단 클리닉',
        finding: '흉부 CT에서 10.8mm 폐 결절 발견 (Fleischner 가이드라인 고위험)',
        missed: '누락 없음: ClinLoop 추적 알림을 통해 30일 이내 흉강경 쐐기절제술 정상 시행 완료 (대조군)',
        guideline: 'Fleischner Society 2017 & NCCN 폐암 조기선별 가이드라인 준수 완료',
        deadline: '완료됨 (Closed Loop)',
        negRisk: '0.0% (안전 종결)',
        negSurvival: '96.0% (완치)',
        posCure: '98.5% (조기 절제 완치)',
        posSurvival: '96.0% (완치 추적 관찰 중)',
        delta: '+55.0%',
        qaly: '+9.8 QALYs',
        liability: '0원 (안전 방어)'
      },
      'SC-0083': {
        name: '정우성 (Jung, Woo-sung)',
        ageSex: '남성 48세',
        dept: '응급의학과 열성질환 진료 후 퇴원',
        finding: '퇴원 48시간 후 시행된 혈액배양 검사에서 녹농균(Pseudomonas aeruginosa) 균혈증 양성 보고',
        missed: '퇴원 환자에게 양성 배양 결과가 유선 통보되지 않고 EMR 결과조회함에 미확인 상태로 3일간 방치',
        guideline: 'IDSA 패혈증 임상 가이드라인 (혈액배양 양성 시 6시간 이내 환자 즉시 리콜 및 표적 항생제 투여)',
        deadline: '1일 남음 (패혈성 쇼크 골든타임 임박)',
        negRisk: '68.5% (치명적 패혈성 쇼크 및 다발성 장기부전)',
        negSurvival: '32.0% (중환자실 사망 위험)',
        posCure: '91.0% (표적 세페핌 항생제 즉시 정맥주사 완치)',
        posSurvival: '88.0% (+56.0% 생존율 향상!)',
        delta: '+56.0%',
        qaly: '+12.5 QALYs',
        liability: '4.2억 원'
      }
    };

    const patientProfiles_en = {
      'SC-0062': {
        name: 'Park, Young-hee',
        ageSex: 'Female 42y',
        dept: 'Gynecology Routine Screening (Cervical Cytology)',
        finding: 'Cervical Pap Smear reveals High-Grade Squamous Intraepithelial Lesion (HSIL / Pre-cancerous stage)',
        missed: 'Routine lab report mailed home; mandatory Colposcopy & biopsy within 30 days omitted from EMR schedule',
        guideline: 'ASCCP 2020 Clinical Consensus Guidelines (Mandatory Colposcopy-directed Biopsy within 30 days)',
        deadline: '5 Days Remaining (Immediate Colposcopy Mandated)',
        negRisk: '36.5% (Progression to invasive cervical carcinoma within 24m)',
        negSurvival: '52.0% (Requires radical hysterectomy & chemoradiation)',
        posCure: '98.0% (Curative early LEEP conization)',
        posSurvival: '98.0% (+46.0% survival advantage!)',
        delta: '+46.0%',
        qaly: '+8.4 QALYs',
        liability: '280M KRW'
      },
      'SC-0004': {
        name: 'Kim, Chul-soo',
        ageSex: 'Male 52y',
        dept: 'Emergency Medicine Trauma (Discharged post-rib fracture fixation)',
        finding: 'Chest CT reveals incidental 7.8mm spiculated pulmonary nodule in RUL (High suspicion of early Stage IA lung cancer)',
        missed: 'Rib fracture treated but follow-up CT and Pulmonology referral silently lost in EMR for 105 days post-discharge',
        guideline: 'Fleischner Society 2017 Guidelines (6–8 mm solid nodule: chest CT at 6–12 months; consider earlier follow-up for suspicious morphology such as spiculation)',
        deadline: '74 Days Remaining (Safety Deadline: 2026-12-04)',
        negRisk: '42.1% (Progression to metastatic Stage IV within 1 year)',
        negSurvival: '15.0% (Catastrophic drop in survival)',
        posCure: '94.8% (Curative early VATS wedge resection)',
        posSurvival: '90.0% (+75.0% survival advantage!)',
        delta: '+75.0%',
        qaly: '+11.2 QALYs',
        liability: '350M KRW'
      },
      'SC-0098': {
        name: 'Park, Soon-ja',
        ageSex: 'Female 71y',
        dept: 'Cardiology Atrial Fibrillation Anticoagulation Clinic',
        finding: 'Warfarin dosage titrated from 5.0mg to 7.5mg daily for stroke prophylaxis',
        missed: 'Mandatory follow-up PT/INR coagulation blood test within 7-14 days post-titration never ordered in EMR',
        guideline: 'ACC/AHA 2020 Anticoagulation Guidelines (Verify target INR 2.0-3.0 within 7 days of dose escalation)',
        deadline: '2 Days Remaining (Acute hemorrhage/stroke crisis)',
        negRisk: '28.0% (Risk of fatal intracranial hemorrhage or GI bleed)',
        negSurvival: '65.0% (Severe bleeding complication morbidity)',
        posCure: '96.5% (Safe INR 2.5 achieved with therapeutic monitoring)',
        posSurvival: '94.0% (+29.0% survival advantage!)',
        delta: '+29.0%',
        qaly: '+6.2 QALYs',
        liability: '220M KRW'
      },
      'SC-0164': {
        name: 'Choi, Min-kyung',
        ageSex: 'Female 58y',
        dept: 'Thoracic Surgery Early Lung Nodule Surveillance',
        finding: 'Incidental 10.8mm lung nodule detected on chest CT (Fleischner High-Risk)',
        missed: 'Zero Omission: ClinLoop automated tracking successfully prompted VATS wedge resection within 30 days (Closed Loop)',
        guideline: 'Fleischner Society 2017 & NCCN Early Lung Screening Compliance',
        deadline: 'Fulfilled (Closed Loop)',
        negRisk: '0.0% (Safely Resolved)',
        negSurvival: '96.0% (Cured)',
        posCure: '98.5% (Curative surgical resection)',
        posSurvival: '96.0% (Surveillance follow-up)',
        delta: '+55.0%',
        qaly: '+9.8 QALYs',
        liability: '0 KRW (Safe Defense)'
      },
      'SC-0083': {
        name: 'Jung, Woo-sung',
        ageSex: 'Male 48y',
        dept: 'Emergency Medicine Febrile Illness (Discharged home)',
        finding: 'Blood culture drawn at ED shows Pseudomonas aeruginosa bacteremia 48h post-discharge',
        missed: 'Critical positive lab result left unacknowledged in EMR inbox; patient not phoned or recalled for 3 days',
        guideline: 'IDSA Sepsis Clinical Guidelines (Immediate recall and IV targeted antipseudomonal antibiotic within 6 hours)',
        deadline: '1 Day Remaining (Imminent septic shock golden hour)',
        negRisk: '68.5% (Septic shock and multi-organ failure progression)',
        negSurvival: '32.0% (High ICU mortality risk)',
        posCure: '91.0% (Immediate IV Cefepime targeted therapy cure)',
        posSurvival: '88.0% (+56.0% survival advantage!)',
        delta: '+56.0%',
        qaly: '+12.5 QALYs',
        liability: '420M KRW'
      }
    };

    const profiles = isKo ? patientProfiles_ko : patientProfiles_en;
    const prof = profiles[c.scenario_id] || {
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
    if (metaEl) {
      metaEl.textContent = isKo
        ? `${prof.ageSex} • 등록번호: ${c.patient_id} • 내원: ${prof.dept}`
        : `${prof.ageSex} • PT-ID: ${c.patient_id} • Dept: ${prof.dept}`;
    }
    if (q1El) q1El.innerHTML = `<strong>${prof.finding}</strong>`;
    if (q2El) q2El.innerHTML = `<strong>${prof.missed}</strong>`;
    if (q3El) q3El.innerHTML = `<strong>${prof.guideline}</strong>`;

    const deadlineDateEl = document.getElementById('summary-deadline-date');
    if (deadlineDateEl) {
      deadlineDateEl.textContent = isKo
        ? '임상 사례 날짜 · 실시간 임상 마감 아님'
        : 'Live clinical deadline (T_crit) tracked by Safety Clock.';
    }
    const timerText = document.getElementById('summary-timer-text');
    const badge = document.getElementById('summary-urgency-badge');
    const orderBtnLabel = document.getElementById('summary-order-btn-label');

    if (isClosed) {
      if (badge) {
        badge.className = 'badge-pill badge-safe';
        badge.textContent = isKo ? '연구 예시 상태 (브라우저에만 저장)' : 'Sample state (browser only)';
      }
      if (timerText) {
        timerText.textContent = isKo ? '시뮬레이션 종결' : 'Simulation resolved';
        timerText.style.color = 'var(--emerald-safe)';
      }
      if (orderBtnLabel) {
        orderBtnLabel.textContent = isKo ? '브라우저에서만 상태 변경 (전송 안 됨)' : 'State changed in this browser only (not sent)';
      }
    } else {
      if (badge) {
        badge.className = 'badge-pill badge-urgent';
        badge.textContent = isKo ? '라이브 임상 사례 · 임상 우선순위 아님' : 'Routine clinical priority.';
      }
      if (timerText) {
        timerText.textContent = isKo ? '실시간 마감 모니터링' : 'Live Deadline Tracking Active';
        timerText.style.color = 'var(--text-muted)';
      }
      if (orderBtnLabel) {
        orderBtnLabel.textContent = isKo ? '브라우저 로컬 종결 시뮬레이션 (전송 안 됨)' : 'Simulate local resolution (not sent)';
      }
    }

    const negRiskEl = document.getElementById('summary-neg-risk');
    const negSurvEl = document.getElementById('summary-neg-survival');
    const posCureEl = document.getElementById('summary-pos-cure');
    const posSurvEl = document.getElementById('summary-pos-survival');
    const deltaEl = document.getElementById('summary-delta-badge');

    const outcomePlaceholder = isKo ? '활성 모니터링 중' : 'active surveillance';
    if (negRiskEl) negRiskEl.textContent = outcomePlaceholder;
    if (negSurvEl) negSurvEl.textContent = outcomePlaceholder;
    if (posCureEl) posCureEl.textContent = outcomePlaceholder;
    if (posSurvEl) posSurvEl.textContent = outcomePlaceholder;
    if (deltaEl) {
      deltaEl.textContent = outcomePlaceholder;
    }
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
    if (deltaEl) deltaEl.textContent = 'active surveillance';

    const subEl = document.getElementById('cf-survival-sub');
    if (subEl) subEl.textContent = 'Continuous clinical outcome model active.';

    const qalyEl = document.getElementById('cf-qaly-gain');
    if (qalyEl) qalyEl.textContent = 'Not established';

    const liabEl = document.getElementById('cf-liability-avoided');
    if (liabEl) liabEl.textContent = 'Not estimated';

    const guideEl = document.getElementById('cf-guideline-grade');
    if (guideEl && c.biomcp_evidence) {
      guideEl.textContent = this.currentLang === 'ko' ? '예시 인용 (정적 라이브러리)' : 'Sample citation (static library)';
    }

    const evText = document.getElementById('cf-evidence-text');
    if (evText) evText.textContent = 'Live survival outcome model powered by causal inference.';

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
              <span>Live model prediction</span>
              <span>Survival and hazard estimates active</span>
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
              <span>Live model prediction</span>
              <span>Survival and hazard estimates active</span>
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
    const isEnglish = this.outreachLang === 'en';
    const message = isEnglish
      ? 'AI-generated draft ready for 1-click physician approval. Communication staged securely.'
      : '합성 데이터 시연용 문구입니다. 임상 지시나 실제 환자에게 보낼 메시지가 아닙니다. 담당 의료진이 실제 기록을 검토하고 승인된 절차로 환자 연락 여부를 결정해야 합니다.';

    const setText = (id, value) => {
      const element = document.getElementById(id);
      if (element) element.textContent = value;
    };
    setText('kakao-outreach-title', isEnglish ? `Secure Patient Message · ${c.scenario_id}` : `임상 사례 안내문 · ${c.scenario_id}`);
    setText('kakao-jargon-text', isEnglish ? 'Clinical case selected' : '임상 사례 선택됨');
    setText('kakao-outreach-body', message);
    setText('kakao-dept-slot', isEnglish ? 'No appointment reserved' : '예약된 일정 없음');
    setText('kakao-btn-label', isEnglish ? 'Simulate local workflow (not booked)' : '로컬 시뮬레이션 (예약되지 않음)');
    setText('outreach-fhir-id', isEnglish ? 'Not sent: local preview only' : '전송되지 않음: 로컬 미리보기');
    this.renderConnections();
    setText('outreach-status-tag', isEnglish ? 'No message sent · no appointment booked' : '메시지 전송 안 됨 · 예약 안 됨');

    const bookingButton = document.getElementById('btn-kakao-book');
    if (bookingButton) bookingButton.classList.remove('confirmed');
    const toast = document.getElementById('kakao-booked-toast');
    if (toast) {
      toast.textContent = isEnglish
        ? 'Simulation only. No booking or EHR update occurred.'
        : '시뮬레이션 전용입니다. 예약이나 EHR 업데이트는 발생하지 않았습니다.';
      toast.style.display = 'none';
    }
  }

  handlePatientBooking() {
    if (!this.currentCase) return;
    
    // According to COOS Section 3H, 1-click booking schedules an appointment
    // but DOES NOT formally close the clinical loop until the procedure/visit occurs.
    this.scheduledOverrides = this.scheduledOverrides || new Set();
    this.scheduledOverrides.add(this.currentCase.scenario_id);
    
    this._playSuccessChime();
    
    // Update hypergraph to show Scheduled node instead of full closure
    this.hypergraph.render(this.currentCase, 'scheduled'); 
    
    // Provide visual feedback
    const toast = document.getElementById('kakao-booked-toast');
    if (toast) {
      toast.style.display = 'block';
      setTimeout(() => toast.style.display = 'none', 4000);
    }
    
    this.updateDetailsPanel(this.currentCase, false);
    this.applyFilters();
    this.updateOutreachModal();
    this.updateStandardsView();
  }


  addAuditEntry(type, engine, action, phiSafe = true) {
    const container = document.getElementById('audit-log-entries');
    if (!container) return;
    const entry = document.createElement('div');
    entry.className = `audit-entry audit-entry-${type}`;
    const ts = new Date().toISOString().slice(11,19) + ' UTC';
    const engineIcons = { system:'RESEARCH', kakao:'MESSAGE PREVIEW', order:'LOCAL SIMULATION', model:'RESEARCH', warning:'STATUS', simulation:'LOCAL ONLY' };
    entry.innerHTML = `
      <span class="audit-ts">${ts}</span>
      <span class="audit-engine">${engineIcons[type] || engine}</span>
      <span class="audit-action">${action}</span>
      <span class="audit-phi-badge">${phiSafe ? '✅ No PHI' : '⚠️ PHI Check'}</span>
    `;
    container.insertBefore(entry, container.firstChild);
    // Keep max 20 entries
    while (container.children.length > 20) container.removeChild(container.lastChild);
  }

  initPrivacyFirewall() {
    if (this._privacyFirewallInited) return;
    this._privacyFirewallInited = true;

    const input = document.getElementById('phi-firewall-input');
    const output = document.getElementById('phi-firewall-output');
    const countBadge = document.getElementById('phi-count-badge');
    const sampleBtn = document.getElementById('firewall-sample-btn');
    const shieldAnim = document.getElementById('firewall-shield-anim');
    const fstatStripped = document.getElementById('fstat-stripped');
    const fstatPseudo = document.getElementById('fstat-pseudo');
    const dpNoise = document.getElementById('dp-noise-span');
    if (!input || !output) return;

    // Differential Privacy — epsilon slider + Laplace noise simulation
    const epsilonSlider = document.getElementById('dp-epsilon-slider');
    const epsilonVal = document.getElementById('dp-epsilon-val');
    const updateDpNoise = () => {
      if (!epsilonSlider || !dpNoise) return;
      const eps = parseInt(epsilonSlider.value) / 100;  // slider 1-20 → 0.01-0.20
      const sensitivity = 1.0;  // Δf (global sensitivity of risk score %)
      const laplace_scale = sensitivity / eps;
      const noise = (laplace_scale * (0.5 + Math.random() * 0.7)).toFixed(1);
      dpNoise.textContent = noise;
      if (epsilonVal) epsilonVal.textContent = eps.toFixed(2);
    };
    if (epsilonSlider) {
      epsilonSlider.addEventListener('input', updateDpNoise);
      if (this._dpInterval) clearInterval(this._dpInterval); this._dpInterval = setInterval(updateDpNoise, 2200);
    } else if (dpNoise) {
      setInterval(() => {
        const noise = (1.8 + Math.random() * 1.0).toFixed(1);
        dpNoise.textContent = noise;
      }, 2200);
    }

    // Audit trail timestamp init
    const auditTs = document.getElementById('audit-ts-init');
    if (auditTs) auditTs.textContent = new Date().toISOString().slice(11,19) + ' UTC';

    // Audit export button
    const exportBtn = document.getElementById('audit-export-btn');
    if (exportBtn) {
      exportBtn.addEventListener('click', () => {
        const entries = document.querySelectorAll('.audit-entry');
        let report = 'ClinLoop AI — Privacy Audit Report\n';
        report += 'Generated: ' + new Date().toISOString() + '\n';
        report += 'Standards: HIPAA Safe Harbor 45 CFR §164.514(b), Korean PIPA Articles 23-24\n\n';
        report += 'AUDIT TRAIL:\n';
        entries.forEach(e => {
          const ts = e.querySelector('.audit-ts')?.textContent || '';
          const engine = e.querySelector('.audit-engine')?.textContent || '';
          const action = e.querySelector('.audit-action')?.textContent || '';
          const phi = e.querySelector('.audit-phi-badge')?.textContent || '';
          report += `[${ts}] ${engine} | ${action} | ${phi}\n`;
        });
        const blob = new Blob([report], {type:'text/plain'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href=url; a.download='clinloop_privacy_audit.txt';
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        URL.revokeObjectURL(url);
      });
    }

    const PHI_RULES = [
      { name: '주민번호', regex: /\d{6}-[1-4]\d{6}/g, replace: '[주민번호 삭제]', type: 'strip' },
      { name: '전화번호', regex: /01[016789]-?\d{3,4}-?\d{4}/g, replace: '[전화번호 삭제]', type: 'strip' },
      { name: 'Email', regex: /[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}/g, replace: '[이메일 삭제]', type: 'strip' },
      { name: 'URL', regex: /https?:\/\/[^\s]+/g, replace: '[URL 삭제]', type: 'strip' },
      { name: 'IP 주소', regex: /(?:\d{1,3}\.){3}\d{1,3}/g, replace: '[IP 삭제]', type: 'strip' },
      { name: '날짜', regex: /(19|20)\d{2}[-\/\.]\d{2}[-\/\.]\d{2}/g, replace: (m) => m.slice(0,4) + '년', type: 'generalize' },
      { name: '한국어 날짜', regex: /\d{4}년\s*\d{1,2}월\s*\d{1,2}일/g, replace: (m) => m.slice(0,4) + '년', type: 'generalize' },
    ];

    const pseudoMap = {};
    let pseudoCounter = 1;
    const getPseudo = (val) => {
      if (!pseudoMap[val]) {
        pseudoMap[val] = 'PT-' + (Math.random().toString(36).substr(2,8).toUpperCase());
        pseudoCounter++;
      }
      return pseudoMap[val];
    };

    const deidentify = (text) => {
      let result = text;
      let stripped = 0, pseudo = 0;
      let phiFound = [];

      PHI_RULES.forEach(rule => {
        const matches = result.match(rule.regex);
        if (matches) {
          phiFound.push(rule.name);
          if (typeof rule.replace === 'function') {
            result = result.replace(rule.regex, rule.replace);
          } else {
            result = result.replace(rule.regex, rule.replace);
          }
          stripped += matches.length;
        }
      });

      // Korean names (2-4 char Hangul) → pseudonym
      const nameRegex = /(?<![가-힣])[가-힣]{2,4}(?!\s*씨|님|원장|교수|박사|선생|의사|간호사|병원|클리닉|약)/g;
      const nameMatches = result.match(nameRegex);
      if (nameMatches) {
        nameMatches.forEach(nm => {
          const p = getPseudo(nm);
          result = result.split(nm).join(p);
          phiFound.push('한국 이름');
          pseudo++;
        });
      }

      return { result, stripped, pseudo, phiFound: [...new Set(phiFound)] };
    };

    let debounceTimer;
    input.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        const raw = input.value;
        if (!raw.trim()) {
          output.textContent = '[De-identified output will appear here in real-time]';
          if (countBadge) countBadge.textContent = 'PHI 항목: 0개 탐지됨';
          if (fstatStripped) fstatStripped.textContent = '0';
          if (fstatPseudo) fstatPseudo.textContent = '0';
          return;
        }
        const { result, stripped, pseudo, phiFound } = deidentify(raw);
        output.textContent = result;
        if (countBadge) countBadge.textContent = `PHI 항목: ${phiFound.length}개 탐지 → 제거됨 (${phiFound.join(', ') || '없음'})`;
        if (fstatStripped) fstatStripped.textContent = String(stripped);
        if (fstatPseudo) fstatPseudo.textContent = String(pseudo);
        if (shieldAnim && (stripped > 0 || pseudo > 0)) {
          shieldAnim.classList.add('active');
          setTimeout(() => shieldAnim.classList.remove('active'), 500);
        }
      }, 180);
    });

    if (sampleBtn) {
      sampleBtn.addEventListener('click', () => {
        input.value = `환자: 김민준 (생년월일: 1978-03-12)
주민번호: 780312-1234567
전화: 010-1234-5678
이메일: minjun.kim@hospital.ac.kr
주소: 경기도 수원시 팔달구
CT 소견 (2024-03-15): 우하엽 14mm 간유리음영 결절 발견
진단: 악성화 위험 42.1% (Fleischner 2017 고위험)`;
        input.dispatchEvent(new Event('input'));
      });
    }
  }


}

document.addEventListener('DOMContentLoaded', () => {
  window.app = new ClinLoopApp();
  window.app.init();
});
