/**
 * ClinLoop AI - Interactive Dashboard Controller 2.0
 */


// Browser storage can be blocked ("block all site data", some private windows): reading it then throws,
// which would stop the whole cockpit. Preferences are a convenience, so a failure just means defaults.
const safeStorage = {
  get(key) { try { return window.localStorage.getItem(key); } catch (e) { return null; } },
  set(key, value) { try { window.localStorage.setItem(key, value); } catch (e) { /* not remembered */ } },
};

function displayCopy(text, lang) {
  return window.ClinLoopUI ? window.ClinLoopUI.display(text, lang) : String(text);
}

const CLINLOOP_I18N = {

  ko: {
    workflowComparison: {"title": "업무 흐름 검토 — 설계 예시", "case": "선택한 합성 예시:", "existing": "기존 업무 흐름에서 확인할 사항", "demonstrated": "ClinLoop에서 보여주는 기능", "existing1": "현재 시스템은 검사 결과와 필요한 후속 조치를 연결합니까?", "existing2": "결과 확인, 예약, 실제 진료 완료를 구분합니까?", "existing3": "담당자와 단계별 보고를 어떻게 기록합니까?", "existing4": "EMR 기능은 기관마다 다릅니다. ClinLoop는 실제 병원 업무 흐름과 비교 검증되지 않았습니다.", "demo1": "합성 사례로 규칙 기반 후속 조치 추적을 보여줍니다.", "demo2": "제안된 기한, 적용 규칙, 근거를 사람이 검토할 수 있도록 표시합니다.", "demo3": "병원 서버는 감사 기록을 지원합니다. 이 공개 페이지의 조치는 브라우저 안에서만 시뮬레이션됩니다.", "demo4": "임상 정확도와 환자에게 주는 이익은 입증되지 않았습니다.", "missing": "이 예시에 기록된 후속 조치:", "limit": "설계 비교 예시입니다. EMR보다 우수하거나 환자 결과를 개선한다는 근거가 아닙니다.", "close": "비교 닫기"},
    platformLabel: '연구 미리보기 · 합성 데이터 전용',
    kpiExamples: '예시', kpiOpen: '미완료', kpiRules: '규칙',
    platformNotice: '이 공개 페이지는 합성(가상) 예시 사례만 사용 · 병원 적용은 현지 검증과 전문의 규칙 승인 후',
    brandSubtitle: '검사·영상 결과의 후속 조치 누락을 찾는 임상 안전 시스템',
    hospitalText: '합성 임상 궤적 데이터 기반',
    nobilityBtn: '윤리·안전 헌장',
    outreachBtn: '환자 안내 메시지',
    biomcpBtn: '근거 문헌',
    emrBtn: '기존 EMR과 비교',
    triageTitle: '사례 목록',
    triageCount: '임상 사례 5건',
    searchPlaceholder: '환자번호, 진단명, 검사 항목 검색...',
    filterAll: '전체',
    filterOpen: '미완료',
    filterDelayed: '지연',
    filterClosed: '종결',
    tabSummary: '임상 요약',
    tabSummaryPill: '',
    tabCounterfactual: '가상 시나리오 (예시)',
    tabStandards: '데이터 표준',
    tabHypergraph: '지식 그래프',
    tabPrivacy: '데이터 보호',
    guideTitle: 'ClinLoop AI는 무엇인가요?',
    guideDesc: 'ClinLoop AI 연구 미리보기는 기록에 남은 후속 조치 의무(이상 검사결과, 영상 소견, 의뢰)를 추적하고, 의료진이 확인할 수 있는 근거와 함께 누락을 알려줍니다. 진단이나 치료 권고는 하지 않습니다. 이 공개 데모는 합성 예시 사례만 사용하며 환자 연락이나 병원 연동을 수행하지 않습니다.',
    guideSteps: '<span class="guide-step">임상 사례 선택</span> <span class="guide-arrow">➔</span> <span class="guide-step">규칙 매칭과 근거를 검토</span> <span class="guide-arrow">➔</span> <span class="guide-step">브라우저에서만 시뮬레이션</span>',
    deadlineLabel: '후속 조치 기한',
    q1Title: '발견 소견',
    q2Title: '왜 중요한가',
    q3Title: '권고 조치 (가이드라인)',
    compTitle: '가상 시나리오 비교',
    compSub: '생존율, 치료 효과 또는 비용 편익 추정치는 검증되지 않았습니다.',
    negCardBadge: '합성 시나리오 · 예측값 없음',
    negMetric1: '임상 결과 추정치',
    negMetric2: '생존율 추정치',
    negCardNote: '환자별 위험 추정치는 제공되지 않습니다.',
    posCardBadge: '가상 업무 흐름 상태 · 치료 효과 아님',
    posMetric1: '치료 결과 추정치',
    posMetric2: '생존율 추정치',
    posCardNote: 'QALY, 생존율 또는 비용 절감 효과는 입증되지 않았습니다.',
    actionSecTitle: '조치 (시뮬레이션)',
    actionSecDesc: '아래 컨트롤은 브라우저 내 시뮬레이션입니다. 환자 메시지나 임상 오더는 전송되지 않습니다.',
    summaryKakaoLbl: '환자 안내문 시뮬레이션 열기',
    summaryKakaoSub: '임상 사례 기반 예시만 표시합니다. 실제 환자에게 보내지 마십시오.',
    summaryOrderLblDefault: '브라우저 로컬 종결 시뮬레이션 (전송 안 됨)',
    summaryOrderLblClosed: '브라우저에서만 상태 변경 (전송 안 됨)',
    summaryOrderSub: '이 프로토타입은 오더나 환자 메시지를 전송하지 않습니다.',
    clockTelemetryTitle: '기한 상태 (예시)',
    riskMetricLabel: '연구용 점수 · 임상 검증 안 됨',
    statRuleTitle: '규칙',
    statSeverityTitle: '중증도',
    mathToggleSummary: '긴급도 점수 계산 방법',
    auditTrailTitle: '감사 기록',
    dockLblTheme: '테마:',
    dockLblLang: '언어:',
    apiKeysBtn: '연결 상태',
    apiModalTitle: '실제 연결 상태',
    apiModalSub: 'ClinLoop 서버가 직접 확인한 연결만 표시합니다.',
    apiCredTitle: '자격 증명은 브라우저에 입력하지 않습니다',
    apiCredDesc: 'API 키와 FHIR 토큰은 ClinLoop 서버의 환경 변수(NCBI_API_KEY, CLINLOOP_FHIR_BASE·CLINLOOP_FHIR_TOKEN)로만 설정합니다. PubMed·Europe PMC에는 규칙 단위 검색어만 전송되며 환자 정보는 외부로 전송되지 않습니다.',
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
    txtResetKeys: '키 초기화 (온프레미스 전용 복귀)',
    txtSaveKeys: 'API 설정 저장 & 적용 (Save Keys)',
    lblActiveEngine: '환자 메시지 초안 엔진:',
    descEngineAnthropic: '최고 임상 추론 & 의료 윤리 정렬',
    descEngineOpenai: '실시간 다중모달 & 심층 CoT 추론',
    descEngineGemini: '초고속 다국어 건강 문해력 요약',
    descEngineLocal: '연결 안 됨 · 연구용 표시',
    btnCancelApi: '닫기'
  },
  en: {
    workflowComparison: {"title": "Workflow review — design only", "case": "Selected synthetic example:", "existing": "Questions for the existing workflow", "demonstrated": "What ClinLoop demonstrates", "existing1": "Does the current system link results to the follow-up actions they require?", "existing2": "Does it distinguish acknowledgement, scheduling and completed care?", "existing3": "How are responsibility and escalation recorded?", "existing4": "EMR features vary. ClinLoop has not been compared with a hospital’s production workflow.", "demo1": "Synthetic cases demonstrate rule-based follow-up tracking.", "demo2": "A proposed deadline, its rule and supporting evidence are displayed for human review.", "demo3": "The hospital backend supports audit events. This public page simulates actions in the browser.", "demo4": "Clinical accuracy and patient benefit have not been established.", "missing": "Follow-up request in this example:", "limit": "This is a design comparison. It does not establish superiority over an EMR or improved patient outcomes.", "close": "Close comparison"},
    platformLabel: 'Research preview · synthetic data only',
    kpiExamples: 'Examples', kpiOpen: 'Open', kpiRules: 'Rules',
    platformNotice: 'Synthetic example cases on this public page · Hospital use after local validation and specialist rule sign-off.',
    brandSubtitle: 'Finds and closes missed follow-up of clinical results',
    hospitalText: 'Synthetic Clinical Trajectories',
    nobilityBtn: 'Ethics & safety charter',
    outreachBtn: 'Patient outreach',
    biomcpBtn: 'Evidence',
    emrBtn: 'Compare vs EMR',
    triageTitle: 'Case queue',
    triageCount: '5 example cases',
    searchPlaceholder: 'Search PT-ID, condition, rule, finding...',
    filterAll: 'All',
    filterOpen: 'Open',
    filterDelayed: 'Delayed',
    filterClosed: 'Closed',
    tabSummary: 'Clinical overview',
    tabSummaryPill: '',
    tabCounterfactual: 'Scenarios (illustration)',
    tabStandards: 'Data standards',
    tabHypergraph: 'Knowledge graph',
    tabPrivacy: 'Data protection',
    guideTitle: 'What is ClinLoop AI?',
    guideDesc: 'ClinLoop AI research preview explores tracking the follow-up obligations already in the record (abnormal results, imaging findings, referrals) and flags missed ones with a basis the clinician can check. It does not diagnose or recommend treatment. This public demo uses synthetic example cases only and does not contact patients or connect to a hospital.',
    guideSteps: '<span class="guide-step">Select a clinical case</span> <span class="guide-arrow">➔</span> <span class="guide-step">Review the rule match and evidence</span> <span class="guide-arrow">➔</span> <span class="guide-step">Simulate in this browser only</span>',
    deadlineLabel: 'Follow-up deadline',
    q1Title: 'Finding',
    q2Title: 'Why it matters',
    q3Title: 'Recommended action (guideline)',
    compTitle: 'Hypothetical scenario comparison',
    compSub: 'Survival, treatment, and cost-benefit estimates are illustrative and not clinically validated.',
    negCardBadge: 'Synthetic scenario · no prediction',
    negMetric1: 'Estimated Clinical Outcome',
    negMetric2: 'Estimated Survival Rate',
    negCardNote: 'No patient-level risk estimate is given.',
    posCardBadge: 'Hypothetical workflow state · not a treatment effect',
    posMetric1: 'Estimated Treatment Outcome',
    posMetric2: 'Estimated Survival Rate',
    posCardNote: 'No QALY, survival or cost benefit has been shown.',
    actionSecTitle: 'Actions (simulation)',
    actionSecDesc: 'These controls are a simulation in your browser. No patient message or clinical order is sent.',
    summaryKakaoLbl: 'Preview a sample patient message',
    summaryKakaoSub: 'Example text from a synthetic case. Never send it to a real patient.',
    summaryOrderLblDefault: 'Simulate local resolution (not sent)',
    summaryOrderLblClosed: 'State changed in this browser only (not sent)',
    summaryOrderSub: 'This demo sends no orders or patient messages.',
    clockTelemetryTitle: 'Deadline status (example)',
    riskMetricLabel: 'Research score · not clinically validated',
    statRuleTitle: 'Rule',
    statSeverityTitle: 'Severity',
    mathToggleSummary: 'How the urgency score is calculated',
    auditTrailTitle: 'Audit trail',
    dockLblTheme: 'Theme:',
    dockLblLang: 'Language:',
    apiKeysBtn: 'Connections',
    apiModalTitle: 'Connection status',
    apiModalSub: 'Shows only connections the ClinLoop server has verified.',
    apiCredTitle: 'Credentials are never entered in the browser',
    apiCredDesc: 'API keys and FHIR tokens are set only as ClinLoop server environment variables (NCBI_API_KEY, CLINLOOP_FHIR_BASE / CLINLOOP_FHIR_TOKEN). PubMed and Europe PMC receive rule-level search terms only; no patient information leaves the server.',
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
    txtResetKeys: 'Reset to on-premise only',
    txtSaveKeys: 'Save & Apply Keys',
    lblActiveEngine: 'Patient-message drafting engine:',
    descEngineAnthropic: 'State-of-the-Art Reasoning & Ethics',
    descEngineOpenai: 'Real-time Multimodal & Deep CoT',
    descEngineGemini: 'High-speed Multilingual Summarization',
    descEngineLocal: 'Not connected · research display',
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
  const lang = document.documentElement.lang.indexOf('ko') === 0 ? 'ko' : 'en';
  const label = '▶ Test Local LLM Now';
  const present = (el,text) => { if (!el) return; if (window.ClinLoopUI) window.ClinLoopUI.set(el,text); else el.textContent=displayCopy(text,lang); };
  const source = text => { if (!output) return; if (window.ClinLoopUI) window.ClinLoopUI.source(output,text); else output.textContent=text; };

  present(btn, '⏳ Generating...');
  btn.disabled = true;
  if (badge) present(badge, 'Calling MedLlama2 via Ollama...');
  if (output) { output.style.display = 'block'; output.textContent = ''; }

  if (!CLINLOOP_API_BASE && !OLLAMA_BASE) {
    if (badge) present(badge, `⚠️ On-premise LLM not available in the public demo`);
    if (output) present(output, 'The local LLM runs only inside the hospital network (ClinLoop API on port 8124 with Ollama). Nothing was generated. Run the cockpit and API locally to try this panel.');
    present(btn, label);
    btn.disabled = false;
    return;
  }

  try {
    if (!CLINLOOP_API_BASE) throw new Error('API not configured');
    // First check engine status
    const statusResp = await fetch(`${CLINLOOP_API_BASE}/api/v1/local-llm/status`);
    const status = statusResp.ok ? await statusResp.json() : null;
    const bestModel = status?.best_model || 'deepseek-r1:32b';

    if (badge) present(badge, `Best model: ${status?.best_model_label || bestModel} · Generating...`);

    const t0 = Date.now();
    const resp = await fetch(`${CLINLOOP_API_BASE}/api/v1/local-llm/generate`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        task: lang === 'ko' ? 'kakao_message_ko' : 'kakao_message_en',
        clinical_context: 'Patient: 40대 남성. CT finding: 14mm ground-glass nodule in right lower lobe. Fleischner 2017: follow-up chest CT at 6-12 months.',
      })
    });

    const latency = Date.now() - t0;

    if (resp.ok) {
      const data = await resp.json();
      if (!data.text) throw new Error(data.error || 'empty response');
      if (output) source(data.text);
      if (badge) present(badge, `✅ ${data.model} · ${data.latency_ms || latency}ms · On-Premise ✓`);
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
          prompt: lang === 'ko' ? '[Synthetic example] 40대 남성 환자, 14mm 간유리음영 결절 발견. 카카오톡 안심 알림 2문장 작성 (의학용어 없이, 환자 이름 없이):' : '[Synthetic example] Man in his 40s, 14 mm ground-glass nodule. Write a two-sentence English patient reminder without medical jargon or patient names:',
          stream: false,
          options: {temperature: 0.3, num_predict: 100}
        })
      });
      const latency = Date.now() - t0;
      const data = await resp.json();
      if (!data.response) throw new Error('empty response');
      if (output) source(data.response);
      if (badge) present(badge, `✅ ${data.model} (direct Ollama) · ${Math.round(latency/1000)}s · On-Premise ✓`);
    } catch (e2) {
      if (badge) present(badge, `⚠️ Local LLM offline (ClinLoop API port 8124 / Ollama port 11434)`);
      if (output) { present(output, 'No message was generated: the on-premise LLM did not respond. Start Ollama and the ClinLoop API, then try again.'); output.style.display = 'block'; }
    }
  }
  present(btn, label);
  btn.disabled = false;
}

class ClinLoopApp {
  constructor() {
    this.cases = [];
    this.filteredCases = [];
    this.currentCase = null;
    this.hypergraph = null;
    this.safetyGauge = null;
    this.soundEnabled = false;   // sound off by default: a cockpit in a clinic should be quiet until asked
    this.audioCtx = null;
    this.closedOverrides = new Set();
    this.scheduledOverrides = new Set();
    this.currentFilter = 'all';
    this.searchQuery = '';
    this.currentScrubDays = 35;
    this.currentView = 'hypergraph';
    this.currentLang = safeStorage.get('clinloop_lang') === 'ko' ? 'ko' : 'en';
    this.outreachLang = this.currentLang;
    this.activeEngine = safeStorage.get('clinloop_active_engine') || 'local';
  }

  async init() {
    this.hypergraph = new HypergraphVisualizer('hypergraph-container');
    this.safetyGauge = new SafetyClockGauge('safety-gauge-canvas', 'sigmoid-canvas');

    await this.loadData();
    this.setupEventListeners();

    this.setupDialogs();

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
    } else if (window.location.hash === '#privacy') {
        this.switchView('privacy');
    } else {
        this.switchView('summary');       // any other address (#top-chrome …) opens the clinical overview
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
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const resp = await fetch('data/cases.json', { signal: controller.signal });
      if (!resp.ok) throw new Error('Examples unavailable');
      this.cases = await resp.json();
    } catch (e) {
      console.error('Failed to load cases.json, using fallback data', e);
      this.cases = this._getFallbackCases();
    } finally {
      clearTimeout(timeout);
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

  updateDisplayLabels() {
    const ko = this.currentLang === 'ko';
    const labels = {
      'theme-opt-light': ko ? '라이트' : 'Light', 'theme-opt-dark': ko ? '다크' : 'Dark',
      'dock-btn-light': ko ? '라이트' : 'Light', 'dock-btn-dark': ko ? '다크' : 'Dark',
      'sound-toggle': ko ? (this.soundEnabled ? '소리: 켜짐' : '소리: 꺼짐')
                         : (this.soundEnabled ? 'Sound: on' : 'Sound: off')
    };
    Object.entries(labels).forEach(([id, text]) => {
      const button = document.getElementById(id);
      if (button) button.textContent = text;
    });
    document.getElementById('sound-toggle')?.setAttribute('aria-pressed', String(this.soundEnabled));
  }

  setupEventListeners() {
    // -----------------------------------------------------------------------
    // Compute: the hardware the ClinLoop server really has (CPU or GPU), and what uses it.
    // The rules engine never needs a GPU, so with no server (the public website) the badge
    // is not shown at all rather than reporting a problem that does not exist.
    // -----------------------------------------------------------------------
    // Evidence (BioMCP) button: opens the evidence panel for the selected case
    const btnBiomcp = document.getElementById('btn-biomcp');
    if (btnBiomcp) {
      btnBiomcp.addEventListener('click', () => {
        if (typeof this.populateBioMcpModal === 'function') this.populateBioMcpModal();
        document.getElementById('biomcp-modal')?.classList.add('open');
      });
    }
    // "More" menu: close after choosing an item, on Escape, or on a click elsewhere
    const moreMenu = document.querySelector('details.more-menu');
    if (moreMenu) {
      moreMenu.querySelectorAll('.more-menu-list button').forEach((b) => b.addEventListener('click', () => { moreMenu.open = false; }));
      document.addEventListener('click', (e) => { if (moreMenu.open && !moreMenu.contains(e.target)) moreMenu.open = false; });
      document.addEventListener('keydown', (e) => { if (e.key === 'Escape') moreMenu.open = false; });
    }

    const btnGpuHud = document.getElementById('btn-gpu-hud');
    const gpuModal = document.getElementById('gpu-modal');
    const btnCloseGpuModal = document.getElementById('btn-close-gpu-modal');

    let computeStatus;
    this.renderComputeLocale = () => {
      if (!btnGpuHud || computeStatus === undefined) return;
      const set = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = displayCopy(text, this.currentLang); };
      const label = document.getElementById('gpu-hud-label');
      const dot = document.getElementById('gpu-hud-dot');
      const c = computeStatus;
      const summary = c ? `Compute device: ${c.gpu_available ? c.gpu_name : 'CPU'}` : 'Could not reach the ClinLoop server to check its hardware';
      if (label) label.textContent = c ? (c.gpu_available ? `GPU: ${c.gpu_name}` : this.currentLang === 'ko' ? 'CPU 전용' : 'CPU only') : displayCopy('Compute: unknown', this.currentLang);
      if (dot) dot.style.background = c && c.gpu_available ? 'var(--emerald-safe)' : 'var(--text-dim)';
      btnGpuHud.title = displayCopy(summary, this.currentLang);
      // This tooltip is dynamic; do not let the static attribute presenter restore its initial text.
      btnGpuHud.removeAttribute('data-ui-attributes');
      if (c) {
        set('gpu-val-device', c.gpu_available ? c.gpu_name : `CPU · ${c.cpu_count || '?'} cores`);
        set('gpu-val-vram-total', c.gpu_memory_total_gb ? `${c.gpu_memory_total_gb} GB` : '—');
        const ct = (c.uses || {}).ct_organ_segmentation || {};
        set('gpu-val-ct', ct.installed ? `Installed · runs on ${String(ct.runs_on).toUpperCase()}` : 'Not installed');
      }
      set('compute-sub', summary);
      btnGpuHud.hidden = false;
    };
    this.fetchGpuTelemetry = async () => {
      if (!btnGpuHud || !CLINLOOP_API_BASE) return;
      try {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 8000);
        try {
          const resp = await fetch(`${CLINLOOP_API_BASE}/api/v1/compute/status`, { signal: ctrl.signal });
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          computeStatus = await resp.json();
        } finally { clearTimeout(timer); }
      } catch (_) { computeStatus = null; }
      this.renderComputeLocale();
    };

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

    // Action button
    const btnAction = document.getElementById('btn-close-action');
    const orderModal = document.getElementById('order-modal');
    const btnConfirmOrder = document.getElementById('btn-confirm-order');
    const btnCancelOrder = document.getElementById('btn-cancel-order');

    if (btnAction && orderModal) {
      btnAction.addEventListener('click', () => {
        if (!this.currentCase || this.closedOverrides.has(this.currentCase.scenario_id)) return;
        this.updateOrderPreview();
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
      if (scrubberVal) scrubberVal.textContent = displayCopy(`${days} Days`, this.currentLang);
      
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
    // Only the case-queue filters: other buttons share the .filter-btn look but are not filters
    document.querySelectorAll('.filter-btn[data-filter]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.filter-btn[data-filter]').forEach(b => b.classList.remove('active'));
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

    // Ethics & safety charter modal
    const btnCharter = document.getElementById('btn-nobility-charter');
    const nobilityModal = document.getElementById('nobility-modal');
    const btnCloseCharter = document.getElementById('btn-close-nobility');
    const btnCloseCharterBottom = document.getElementById('btn-close-nobility-bottom');

    if (btnCharter && nobilityModal) {
      btnCharter.addEventListener('click', () => {
        nobilityModal.classList.add('open');
      });
    }

    if (btnCloseCharter && nobilityModal) {
      btnCloseCharter.addEventListener('click', () => nobilityModal.classList.remove('open'));
    }

    if (btnCloseCharterBottom && nobilityModal) {
      btnCloseCharterBottom.addEventListener('click', () => nobilityModal.classList.remove('open'));
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
    safeStorage.set('clinloop_active_engine', 'local');

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
        this.addAuditEntry('simulation', 'LOCAL SIMULATION', `Browser-only example marked resolved; no order was sent · Case: ${caseName}`, true);
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
      document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
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
      safeStorage.set('clinloop_theme', isDark ? 'dark' : 'light');

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
    // A choice made on any ClinLoop page is kept; otherwise follow the device (as the clinical pages do)
    const deviceDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    const initialTheme = urlParamsTheme || safeStorage.get('clinloop_theme') || (deviceDark ? 'dark' : 'light');
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

      safeStorage.set('clinloop_lang', this.currentLang);
      document.documentElement.lang = this.currentLang;   // the shared page navigation follows it (appnav.js)

    


      this.applyI18nText(this.currentLang);
      this.updateDisplayLabels();
      if (this.renderPrivacyLocale) this.renderPrivacyLocale();
      if (this.renderComputeLocale) this.renderComputeLocale();
      const scrubberLabel=document.getElementById('scrubber-days-val');
      if (scrubberLabel) scrubberLabel.textContent=displayCopy(`${this.currentScrubDays} Days`,this.currentLang);
      if (this.currentCase) this.populateBioMcpModal();
      if (this.renderConnections) this.renderConnections();

      this.outreachLang = this.currentLang;
      const btnOutreachKo = document.getElementById('btn-lang-ko');
      const btnOutreachEn = document.getElementById('btn-lang-en');
      if (btnOutreachKo && btnOutreachEn) {
        btnOutreachKo.classList.toggle('active', isKo);
        btnOutreachEn.classList.toggle('active', !isKo);
      }
      this.updateOutreachModal();
      this.updateEmrComparisonContent();
      this.updateOrderPreview();

      this.renderCaseTabs();
      this.updateSummaryView();
      this.updateLivesCounter();

      if (this.currentCase) {
        const isOverridden = this.closedOverrides.has(this.currentCase.scenario_id);
        const isClosed = (this.currentCase.ground_truth_status === 'closed') || isOverridden;
        this.updateDetailsPanel(this.currentCase, isClosed);
      }
      this.updateCounterfactualView();
      this.updateStandardsView();
      if (this.currentCase) this.hypergraph.render(this.currentCase, this.closedOverrides.has(this.currentCase.scenario_id), this.currentScrubDays);
    };

    const initialLang = (typeof urlParams !== 'undefined' ? urlParams.get('lang') : new URLSearchParams(window.location.search).get('lang')) || safeStorage.get('clinloop_lang') || 'en';
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
        this.updateDisplayLabels();
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
    document.querySelectorAll('[data-workflow-copy]').forEach(el => {
      el.textContent = t.workflowComparison[el.dataset.workflowCopy] || '';
    });
    document.querySelectorAll('.modal-overlay button').forEach(button => {
      if (/^[✕×✖]$/.test(button.textContent.trim())) button.setAttribute('aria-label', lang === 'ko' ? '대화상자 닫기' : 'Close dialog');
    });
    
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
    setTxt('kpi-lbl-examples', t.kpiExamples);
    setTxt('kpi-lbl-open', t.kpiOpen);
    setTxt('kpi-lbl-rules', t.kpiRules);
    setTxt('txt-nobility-btn', t.nobilityBtn);
    setTxt('txt-outreach-btn', t.outreachBtn);
    setTxt('txt-biomcp-btn', t.biomcpBtn);
    setTxt('txt-more-btn', this.currentLang === 'ko' ? '더보기' : 'More');
    setTxt('txt-emr-btn', t.emrBtn);
    setTxt('triage-title', t.triageTitle);
    setTxt('triage-count', t.triageCount);

    const searchInput = document.getElementById('patient-search');
    if (searchInput) searchInput.placeholder = t.searchPlaceholder;

    if (this.cases) this.updateFilterCounts();

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
    setTxt('modal-api-nobility-title', t.apiCredTitle);
    setHtml('modal-api-nobility-desc', t.apiCredDesc);
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


  /** Filter labels with live counts (cases change state when one is marked closed in this browser). */
  updateFilterCounts() {
    const t = CLINLOOP_I18N[this.currentLang] || CLINLOOP_I18N.en;
    const status = (c) => ((c.ground_truth_status === 'closed') || this.closedOverrides.has(c.scenario_id)) ? 'closed' : c.ground_truth_status;
    const n = (s) => this.cases.filter(c => status(c) === s).length;
    const set = (id, label, count) => { const el = document.getElementById(id); if (el) el.textContent = `${label} (${count})`; };
    set('filter-btn-all', t.filterAll, this.cases.length);
    set('filter-btn-open', t.filterOpen, n('open'));
    set('filter-btn-delayed', t.filterDelayed, n('delayed'));
    set('filter-btn-closed', t.filterClosed, n('closed'));
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
    this.updateFilterCounts();
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
      
      // A worklist row: patient, status chip, finding, then severity · rule · department · ID
      const statusText = isClosed ? (isKo ? '종결' : 'Closed')
        : c.ground_truth_status === 'delayed' ? (isKo ? '지연' : 'Delayed') : (isKo ? '미완료' : 'Open');
      const sev = c.ground_truth_severity || 'moderate';
      const sevText = isKo ? ({ critical: '위급', high: '높음', moderate: '중간', low: '낮음' })[sev] || sev : sev;
      card.classList.add(`sev-${sev}`);

      const ptName = isKo
        ? (c.patient_name_kr ? `${c.patient_name_kr} (${c.patient_sex === 'M' ? '남' : '여'} ${c.patient_age}세)` : `${c.patient_id}`)
        : (c.patient_name_en ? `${c.patient_name_en} (${c.patient_sex === 'M' ? 'M' : 'F'}, ${c.patient_age}y)` : `${c.patient_id}`);
      const ptCondition = isKo ? (c.title_kr || c.scenario_name) : c.scenario_name;
      const ptDept = isKo ? (c.dept_kr || '외래 진료') : (c.dept_en || 'Outpatient Clinic');

      card.innerHTML = `
        <div class="case-header">
          <span class="case-name">${ptName}</span>
          <span class="case-status-badge ${statusClass}">${statusText}</span>
        </div>
        <div class="case-title" title="${ptCondition}">${ptCondition}</div>
        <div class="case-meta">
          <span class="case-sev">${sevText}</span>
          <span>${c.applicable_rule_id || ''}</span>
          <span class="case-dept">${ptDept}</span>
          <span class="case-pid">${c.patient_id}</span>
        </div>
      `;

      card.addEventListener('click', () => this.selectCase(c.scenario_id));
      // Keyboard: each case is a button (Tab to it, Enter or Space to open)
      card.tabIndex = 0;
      card.setAttribute('role', 'button');
      card.setAttribute('aria-pressed', this.currentCase?.scenario_id === c.scenario_id ? 'true' : 'false');
      card.setAttribute('aria-label', `${ptName}: ${ptCondition}`);
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.selectCase(c.scenario_id); }
      });
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
    if (scrubberVal) scrubberVal.textContent = displayCopy('35 Days', this.currentLang);

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
    document.getElementById('case-display-desc').textContent = displayCopy(scenario.clinical_narrative, this.currentLang);

    document.getElementById('stat-rule-id').textContent = scenario.applicable_rule_id;
    const sevKo = { critical: '위급', high: '높음', moderate: '중간', low: '낮음' };
    document.getElementById('stat-severity').textContent = isKo ? (sevKo[scenario.ground_truth_severity] || scenario.ground_truth_severity) : scenario.ground_truth_severity;
    
    const actionBox = document.getElementById('action-card');
    const actionTitle = document.getElementById('action-required-title');
    const actionDesc = document.getElementById('action-required-desc');
    const actionBtn = document.getElementById('btn-close-action');

    if (isClosed) {
      actionBox.classList.add('resolved');
      actionTitle.textContent = isKo ? '종결됨 (예시 · 이 브라우저)' : 'Closed (example · this browser)';
      actionDesc.textContent = isKo ? '이 브라우저에서만 표시가 바뀌었습니다. 오더나 환자 메시지는 전송되지 않았습니다.' : 'Changed in this browser only. No order or patient message was sent.';
      actionBtn.textContent = isKo ? '종결로 표시됨' : 'Marked closed';
      actionBtn.classList.add('resolved');
    } else {
      actionBox.classList.remove('resolved');
      // "COLPOSCOPY_REFERRAL within 30 days" → "Colposcopy referral within 30 days"
      const missing = (scenario.missing_followup || '').replace(/\b[A-Z][A-Z0-9_]{2,}\b/g, (w) => w.replace(/_/g, ' ').toLowerCase())
        .replace(/^./, (ch) => ch.toUpperCase());
      actionTitle.textContent = isKo ? '누락된 후속 조치' : 'Missing follow-up';
      actionDesc.textContent = isKo
        ? `${scenario.action_kr || scenario.title_kr || '후속 조치'} (예시 사례)`
        : `${missing || 'Follow-up'} (example case)`;
      actionBtn.textContent = isKo ? '이 브라우저에서 종결로 표시 (예시)' : 'Mark closed in this browser (example)';
      actionBtn.classList.remove('resolved');
    }

    this.renderEvidenceChain(scenario, isClosed);
  }

  renderEvidenceChain(scenario, isClosed) {
    const container = document.getElementById('evidence-chain-list');
    if (!container) return;
    container.innerHTML = '';

    const firstEvent = scenario.events[0];
    const isKo = this.currentLang === 'ko';
    // Codes such as COLPOSCOPY_REFERRAL read as words
    const words = (text) => (text || '').replace(/\b[A-Z][A-Z0-9_]{2,}\b/g, (w) => w.replace(/_/g, ' ').toLowerCase());
    const ev = scenario.biomcp_evidence;
    const steps = [
      {
        num: '1',
        title: isKo ? `결과 수신: ${({ lab_result: '검사 결과', imaging_order: '영상 검사', radiology_report: '영상 판독', pathology_result: '병리 결과',
          medication_change: '약물 변경', discharge: '퇴원' })[firstEvent.event_type] || firstEvent.event_type.replace(/_/g, ' ')}`
          : `Result received: ${firstEvent.event_type.replace(/_/g, ' ')}`,
        sub: firstEvent.timestamp.split('T')[0]
      },
      {
        num: '2',
        title: isKo ? `규칙 ${scenario.applicable_rule_id} 해당` : `Rule ${scenario.applicable_rule_id} matched`,
        sub: ev ? `${isKo ? '가이드라인' : 'Guideline'}: ${ev.guideline_org.split('(')[0].trim()} · PMID ${ev.pmid}` : (isKo ? '저장된 인용 없음' : 'No citation stored for this example')
      },
      {
        num: '3',
        title: isClosed ? (isKo ? '종결로 표시 (이 브라우저)' : 'Marked closed (this browser)')
          : isKo ? (scenario.title_kr || `누락: ${words(scenario.missing_followup)}`) : `Missing: ${words(scenario.missing_followup)}`,
        sub: isClosed ? (isKo ? '전송된 내용 없음' : 'Nothing was sent') : (isKo ? '규칙 기반 · AI 판단 아님' : 'Rule-based · no AI judgement')
      },
      {
        num: '4',
        title: isKo ? '알림 발송 안 함' : 'No alert sent',
        sub: isKo ? '데모: EHR·메시지·에스컬레이션 연결 없음' : 'Demo: no EHR, messaging or escalation connected'
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

  updateOrderPreview() {
    const c=this.currentCase;
    if (!c) return;
    const name=document.getElementById('modal-pt-name'), action=document.getElementById('modal-order-desc');
    if (name) name.textContent=`${c.patient_id} (${this.currentLang === 'ko' ? c.title_kr || displayCopy(c.scenario_name,'ko') : c.scenario_name})`;
    if (action) action.textContent=displayCopy(c.missing_followup || 'Clinical follow-up for review',this.currentLang);
  }

  updateEmrComparisonContent() {
    if (!this.currentCase) return;
    const c = this.currentCase;
    document.getElementById('emr-view-scenario-name').textContent = `${c.patient_id} — ${this.currentLang === 'ko' ? c.title_kr || displayCopy(c.scenario_name, 'ko') : c.scenario_name}`;
    document.getElementById('emr-missing-action').textContent = displayCopy(c.missing_followup || 'Clinical follow-up', this.currentLang);
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

  /**
   * One behaviour for every pop-up window (.modal-overlay): it opens as a labelled dialog with the
   * keyboard focus inside it, and closes with its ✕ or Close button, the Escape key, or a click
   * outside it; focus then returns to the button that opened it. Before this, Escape closed nothing
   * and the Evidence window's ✕ had no handler, so a reader could be stuck in it.
   */
  setupDialogs() {
    const overlays = [...document.querySelectorAll('.modal-overlay')];
    const openOnes = () => overlays.filter((m) => m.classList.contains('open'));
    const openers = new WeakMap();
    let lastControl = null;     // the More menu closes as its item is clicked, which drops the focus
    document.addEventListener('click', (e) => { lastControl = e.target.closest('button, summary, a') || lastControl; }, true);
    const focusable = (m) => [...m.querySelectorAll('a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])')]
      .filter((el) => !el.disabled && el.offsetParent !== null);
    const close = (m) => {
      m.classList.remove('open');
      // A window opened from a link (#biomcp, #outreach) can then be opened again by the same link
      if (['#biomcp', '#outreach'].includes(window.location.hash)) {
        history.replaceState(null, '', window.location.pathname + window.location.search);
      }
    };
    overlays.forEach((m) => {
      const box = m.firstElementChild;
      if (box) {
        box.setAttribute('role', 'dialog');
        box.setAttribute('aria-modal', 'true');
        box.tabIndex = -1;
        const heading = box.querySelector('h1, h2, h3');
        if (heading) {
          heading.id = heading.id || `${m.id}-title`;
          box.setAttribute('aria-labelledby', heading.id);
        }
      }
      new MutationObserver(() => {
        const isOpen = m.classList.contains('open');
        document.body.classList.toggle('modal-open', openOnes().length > 0);
        if (isOpen && !openers.has(m)) {
          const active = document.activeElement;
          openers.set(m, active && active !== document.body ? active : lastControl);
          requestAnimationFrame(() => (box || m).focus({ preventScroll: true }));
        } else if (!isOpen && openers.has(m)) {
          let back = openers.get(m);
          openers.delete(m);
          if (back && back.focus && document.contains(back)) back.focus({ preventScroll: true });
          // Opened from the (now closed) More menu, whose items cannot take focus: return to the menu's button
          if (back && document.activeElement !== back) back.closest('details')?.querySelector('summary')?.focus({ preventScroll: true });
        }
      }).observe(m, { attributes: true, attributeFilter: ['class'] });
      m.addEventListener('click', (e) => {
        if (e.target === m) { close(m); return; }                       // click outside the window
        const btn = e.target.closest('button');
        if (btn && (/^btn-(close|cancel)/.test(btn.id) || btn.matches('[data-close-dialog]'))) close(m);
      });
    });
    document.addEventListener('keydown', (e) => {
      const top = openOnes().pop();
      if (!top) return;
      if (e.key === 'Escape') { e.preventDefault(); close(top); return; }
      if (e.key !== 'Tab') return;
      const items = focusable(top);                                    // keep Tab inside the window
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && (document.activeElement === first || !top.contains(document.activeElement))) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });
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
      checking: '확인 중…', summaryNone: '공개 데모: 서버 없음. 실시간 연결(병원 EMR, PACS, 문헌 검색)은 병원에 설치된 ClinLoop 서버가 만듭니다.',
      summary: (n) => `실시간 연결 ${n}개 (서버에서 직접 확인)`, live: '실시간 연결', demoValue: '데모', liveNone: '서버 없음 (공개 데모)',
      sourcesDown: (n) => `실행 중 · 도구 ${n}개 · 문헌 출처 연결 안 됨`,
      names: { clinloop_api: 'ClinLoop API 서버', biomcp: 'BioMCP 서버 (MCP)', pubmed: 'PubMed (NCBI E-utilities)', europe_pmc: 'Europe PMC',
        fhir_server: '병원 FHIR 서버 (Epic·Cerner 등)', local_llm: '원내 LLM (Ollama)', cloud_llm: '클라우드 LLM (Claude·GPT·Gemini)',
        omop_cdm: 'OMOP CDM 데이터베이스', ehr_writeback: 'EHR 오더 기록 (writeback)', guideline_library: '내장 가이드라인 라이브러리' },
      notRunning: '실행 중 아님', needsServer: '알 수 없음 (ClinLoop 서버 필요)', connected: '연결됨', unreachable: '연결 실패',
      disabled: '꺼짐', notConfigured: '설정 안 됨', feed: (f) => `데이터 수신 ${f}`, notUsed: '이 버전에서는 사용 안 함',
      notConnected: '연결 안 됨', readOnly: '연결 안 됨 (설계상 읽기 전용)', static: (n) => `정적 데이터${n ? ` · 규칙 ${n}개` : ''}`,
      pillApi: 'API 연결됨', pillDemo: '데모 · 서버 없음', pillPubmed: 'PUBMED 실시간', pillStatic: '정적 라이브러리',
      llmOn: (m) => `🧬 원내 LLM: ${m}`, llmOff: '🧬 원내 LLM 꺼짐 · 기본 문구 사용',
      litTitle: 'PubMed 실시간 문헌', litNeedsServer: 'PubMed 실시간 검색은 ClinLoop 서버가 실행 중이고 PubMed에 연결되어 있을 때 사용할 수 있습니다.',
      litLoading: 'PubMed 검색 중…', litNone: '검색 결과가 없습니다.', litError: 'PubMed 검색 실패: ',
      litQuery: '검색어 (규칙 단위, 환자 정보 없음): ',
      tools: (n) => `도구 ${n}개`, notInstalled: '설치 안 됨', pillBiomcp: 'BIOMCP 실시간', bioTitle: 'BioMCP 실시간 검색',
    } : {
      checking: 'Checking…', summaryNone: 'Public demo, no server. Live connections (hospital records, PACS, literature search) are made by a ClinLoop server installed at a hospital.',
      summary: (n) => `${n} live connection${n === 1 ? '' : 's'} (verified by the server)`, live: 'Live connections', demoValue: 'Demo', liveNone: 'No server (public demo)',
      sourcesDown: (n) => `Running · ${n} tools · literature sources unreachable`,
      names: { clinloop_api: 'ClinLoop API server', biomcp: 'BioMCP server (MCP)', pubmed: 'PubMed (NCBI E-utilities)', europe_pmc: 'Europe PMC',
        fhir_server: 'Hospital FHIR server (Epic, Cerner, …)', local_llm: 'On-premise LLM (Ollama)', cloud_llm: 'Cloud LLMs (Claude, GPT, Gemini)',
        omop_cdm: 'OMOP CDM database', ehr_writeback: 'EHR order writeback', guideline_library: 'Built-in guideline library' },
      notRunning: 'Not running', needsServer: 'Unknown (needs the ClinLoop server)', connected: 'Connected', unreachable: 'Unreachable',
      disabled: 'Disabled', notConfigured: 'Not configured', feed: (f) => `data feed ${f}`, notUsed: 'Not used in this build',
      notConnected: 'Not connected', readOnly: 'Not connected (read-only by design)', static: (n) => `Static data${n ? ` · ${n} rules` : ''}`,
      pillApi: 'API ONLINE', pillDemo: 'DEMO · NO SERVER', pillPubmed: 'PUBMED LIVE', pillStatic: 'STATIC LIBRARY',
      llmOn: (m) => `🧬 On-prem LLM: ${m}`, llmOff: '🧬 On-prem LLM offline · template text',
      litTitle: 'Live PubMed literature', litNeedsServer: 'Live PubMed search is available when the ClinLoop server is running and connected to PubMed.',
      litLoading: 'Searching PubMed…', litNone: 'No results.', litError: 'PubMed search failed: ',
      litQuery: 'Query (rule-level, no patient data): ',
      tools: (n) => `${n} tools`, notInstalled: 'Not installed', pillBiomcp: 'BIOMCP LIVE', bioTitle: 'BioMCP live search',
    };
  }

  _connRows() {
    const t = this._connText();
    const s = this.connStatus;
    const keys = ['clinloop_api', 'biomcp', 'pubmed', 'europe_pmc', 'fhir_server', 'local_llm', 'cloud_llm', 'omop_cdm', 'ehr_writeback', 'guideline_library'];
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
        case 'biomcp':
          if (v.status === 'ok') return { ...row, tone: 'ok', text: `${t.connected} · ${t.tools(v.tools)}` };
          // BioMCP started but its test search found nothing: PubMed etc. cannot be reached from the server
          if (v.status === 'sources_unreachable') return { ...row, tone: 'warn', text: t.sourcesDown(v.tools) };
          if (v.status === 'disabled') return { ...row, tone: 'off', text: t.disabled };
          return { ...row, tone: v.status === 'unreachable' ? 'warn' : 'off', text: v.status === 'unreachable' ? t.unreachable : t.notInstalled };
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
        badge.style.cssText = 'font-size:0.72rem;';
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
    // No server (the public website): say so, rather than a bare 0 that reads as a fault
    const noServer = this.connStatus === null;
    if (imp) { imp.textContent = this.connStatus === undefined ? '–' : noServer ? t.demoValue : String(live); imp.style.color = live ? 'var(--emerald-safe)' : 'var(--text-dim)'; }
    const impLbl = document.getElementById('imp-connections-lbl');
    if (impLbl) { impLbl.textContent = noServer ? t.liveNone : t.live; impLbl.title = noServer ? t.summaryNone : ''; }

    const s = this.connStatus;
    const apiPill = document.getElementById('api-status-pill');
    if (apiPill && s === undefined) apiPill.textContent = t.checking;
    if (apiPill && s !== undefined) { apiPill.textContent = s ? t.pillApi : t.pillDemo; style(apiPill, s ? 'ok' : 'off'); }
    const bioPill = document.getElementById('biomcp-status-pill');
    if (bioPill && s === undefined) bioPill.textContent = t.checking;
    if (bioPill && s !== undefined) {
      const biomcpLive = !!(s && s.biomcp && s.biomcp.status === 'ok');
      const pubmedLive = !!(s && s.pubmed && s.pubmed.status === 'ok');
      bioPill.textContent = biomcpLive ? t.pillBiomcp : pubmedLive ? t.pillPubmed : t.pillStatic;
      style(bioPill, biomcpLive || pubmedLive ? 'ok' : 'off');
    }
    const llmPill = document.getElementById('outreach-model-pill');
    if (llmPill && s === undefined) llmPill.textContent = t.checking;
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
    const biomcpLive = !!(s && s.biomcp && s.biomcp.status === 'ok');
    const pubmedLive = !!(s && s.pubmed && s.pubmed.status === 'ok');
    if (!ruleId || (!biomcpLive && !pubmedLive)) { body.textContent = t.litNeedsServer; return; }
    body.textContent = t.litLoading;
    let bioNote = null;
    if (biomcpLive) {
      try {
        const resp = await fetch(`${CLINLOOP_API_BASE}/api/v1/evidence/${encodeURIComponent(ruleId)}?source=biomcp`);
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
        const text = typeof data.result === 'string' ? data.result : (Array.isArray(data.result) && data.result.length ? JSON.stringify(data.result, null, 2) : '');
        if (text) {
          if (title) title.textContent = t.bioTitle;
          const pre = document.createElement('pre');
          pre.style.cssText = 'white-space:pre-wrap;word-break:break-word;max-height:260px;overflow:auto;margin:0.3rem 0 0;font-size:0.72rem;';
          pre.textContent = text.slice(0, 4000);
          const query = document.createElement('div');
          query.style.cssText = 'font-size:0.7rem;color:var(--text-dim);margin-top:0.35rem;';
          query.textContent = t.litQuery + data.query;
          body.replaceChildren(pre, query);
          return;
        }
        bioNote = data.note || null;
      } catch (e) { bioNote = 'BioMCP: ' + e.message; }
    }
    if (!pubmedLive) {
      if (title) title.textContent = t.bioTitle;
      body.textContent = bioNote || t.litNone;
      return;
    }
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
    if (gradeEl) gradeEl.textContent = displayCopy('Evidence grade not established', this.currentLang);

    // Dossier Card
    const orgEl = document.getElementById('biomcp-org-tag');
    if (orgEl) orgEl.textContent = ev.guideline_org;

    const titleEl = document.getElementById('biomcp-guideline-title');
    if (titleEl) titleEl.textContent = ev.guideline_title;

    const citEl = document.getElementById('biomcp-citation-text');
    if (citEl) citEl.textContent = `${ev.citation}`;

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
    if (actVal) actVal.textContent = displayCopy(ev.mandated_action, this.currentLang);

    const tcritVal = document.getElementById('biomcp-param-tcrit');
    if (tcritVal) tcritVal.textContent = displayCopy(`${ev.derived_t_crit} Days`, this.currentLang);

    const kVal = document.getElementById('biomcp-param-k');
    if (kVal) kVal.textContent = ev.derived_k_factor;

    const liabVal = document.getElementById('biomcp-param-liability');
    if (liabVal) liabVal.textContent = displayCopy('Not estimated', this.currentLang);
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
        // Leave no other view's name in the address: a reload would open that view instead
        if (window.location.hash) {
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
        name: '박영희',
        ageSex: '여성 42세',
        dept: '산부인과 정기 건강검진 (자궁경부 세포검사)',
        finding: '자궁경부 세포검사(Pap) 결과 고등급 편평상피내 병변(HSIL) 발견 (자궁경부암 전암 단계)',
        missed: '결과 우편 발송은 기록되어 있지만 위험도 평가와 적절한 후속 진료 계획은 확인되지 않음',
        guideline: 'ASCCP 2019 위험도 기반 관리: HPV, 나이, 임신 여부 및 검사 이력을 확인. 30일은 제안된 기관별 추적 목표이며 지침의 일률적인 기한이 아님',
        deadline: '예시 추적 목표 · 의료진 검토 필요',
      },
      'SC-0004': {
        name: '김철수',
        ageSex: '남성 52세',
        dept: '응급의학과 외상진료 (갈비뼈 골절 치료 후 퇴원)',
        finding: '흉부 CT에서 우상엽(RUL) 7.8mm 침상형 폐 결절이 우연히 보고됨 · 진단 및 관리 계획은 의료진 평가 필요',
        missed: '갈비뼈 치료만 완료되고 폐 결절에 대한 외래 예약이나 호흡기내과 협진이 누락된 채 105일 경과',
        guideline: 'Fleischner Society 2017 가이드라인 (6–8mm 고형 결절: 6–12개월 내 흉부 CT 추적, 침상형 등 고위험 형태는 더 이른 추적 고려)',
        deadline: '74일 남음 (마감일자: 2026-12-04)',
      },
      'SC-0098': {
        name: '박순자',
        ageSex: '여성 71세',
        dept: '순환기내과 심방세동 항응고 치료',
        finding: '심방세동 뇌졸중 예방을 위해 와파린(Warfarin) 용량을 5mg에서 7.5mg으로 증량 처방',
        missed: '와파린 용량 변경 후 계획된 INR 재검이 합성 기록에서 확인되지 않음',
        guideline: '용량 변경 후 INR 모니터링은 의료진이 결정 · 적응증, 목표 범위 및 재검 시점을 확인',
        deadline: '예시 추적 목표 · 의료진 검토 필요',
      },
      'SC-0164': {
        name: '최민경',
        ageSex: '여성 58세',
        dept: '흉부외과 폐암 조기진단 클리닉',
        finding: '흉부 CT에서 10.8mm 폐 결절 발견 (Fleischner 가이드라인 고위험)',
        missed: '합성 기록에서 해당 추적 조치의 근거 확인 · 완치나 ClinLoop로 인한 환자 이익을 입증하지 않음',
        guideline: '합성 기록의 추적 조치 예시 · 적용 지침과 완료 범위는 의료진 검토 필요',
        deadline: '완료됨 (Closed Loop)',
      },
      'SC-0083': {
        name: '정우성',
        ageSex: '남성 48세',
        dept: '응급의학과 열성질환 진료 후 퇴원',
        finding: '퇴원 48시간 후 시행된 혈액배양 검사에서 녹농균(Pseudomonas aeruginosa) 균혈증 양성 보고',
        missed: '퇴원 환자에게 양성 배양 결과가 유선 통보되지 않고 EMR 결과조회함에 미확인 상태로 3일간 방치',
        guideline: '병원 위급 결과 통보 절차에 따른 긴급 의료진 검토와 의사소통 · 치료는 담당 의료진이 결정',
        deadline: '예시 추적 목표 · 의료진 검토 필요',
      }
    };

    const patientProfiles_en = {
      'SC-0062': {
        name: 'Park, Young-hee',
        ageSex: 'Female 42y',
        dept: 'Gynecology Routine Screening (Cervical Cytology)',
        finding: 'Cervical Pap Smear reveals High-Grade Squamous Intraepithelial Lesion (HSIL / Pre-cancerous stage)',
        missed: 'Result mailing is recorded; clinician risk assessment and an appropriate follow-up plan are not confirmed',
        guideline: 'ASCCP 2019 risk-based management: verify HPV, age, pregnancy and screening history. The proposed 30-day tracking target is local policy, not a universal guideline deadline',
        deadline: 'Example tracking target; clinician review required',
      },
      'SC-0004': {
        name: 'Kim, Chul-soo',
        ageSex: 'Male 52y',
        dept: 'Emergency Medicine Trauma (Discharged post-rib fracture fixation)',
        finding: 'Chest CT reports an incidental 7.8 mm spiculated right upper lobe pulmonary nodule; diagnosis and management need clinician assessment',
        missed: 'Rib fracture treated but follow-up CT and Pulmonology referral silently lost in EMR for 105 days post-discharge',
        guideline: 'Fleischner Society 2017 Guidelines (6–8 mm solid nodule: chest CT at 6–12 months; consider earlier follow-up for suspicious morphology such as spiculation)',
        deadline: '74 Days Remaining (Safety Deadline: 2026-12-04)',
      },
      'SC-0098': {
        name: 'Park, Soon-ja',
        ageSex: 'Female 71y',
        dept: 'Cardiology Atrial Fibrillation Anticoagulation Clinic',
        finding: 'Warfarin dosage titrated from 5.0mg to 7.5mg daily for stroke prophylaxis',
        missed: 'The synthetic record does not show the planned INR recheck after a warfarin dose change',
        guideline: 'Clinician-directed INR monitoring after a dose change; confirm the indication, target range and recheck timing',
        deadline: 'Example tracking target; clinician review required',
      },
      'SC-0164': {
        name: 'Choi, Min-kyung',
        ageSex: 'Female 58y',
        dept: 'Thoracic Surgery Early Lung Nodule Surveillance',
        finding: 'Incidental 10.8mm lung nodule detected on chest CT (Fleischner High-Risk)',
        missed: 'The synthetic record contains follow-up evidence for this tracked step; this does not establish cure or a benefit caused by ClinLoop',
        guideline: 'Synthetic follow-up example; applicable guidance and completion scope require clinician review',
        deadline: 'Fulfilled (Closed Loop)',
      },
      'SC-0083': {
        name: 'Jung, Woo-sung',
        ageSex: 'Male 48y',
        dept: 'Emergency Medicine Febrile Illness (Discharged home)',
        finding: 'Blood culture drawn at ED shows Pseudomonas aeruginosa bacteremia 48h post-discharge',
        missed: 'Critical positive lab result left unacknowledged in EMR inbox; patient not phoned or recalled for 3 days',
        guideline: 'Urgent clinician review and communication under the hospital critical-result protocol; management is decided by the treating team',
        deadline: 'Example tracking target; clinician review required',
      }
    };

    const profiles = isKo ? patientProfiles_ko : patientProfiles_en;
    const prof = profiles[c.scenario_id] || {
      name: isKo ? `환자 (${c.patient_id})` : `Patient (${c.patient_id})`,
      ageSex: isKo ? `${c.patient_age}세 ${c.patient_sex === 'M' ? '남성' : c.patient_sex === 'F' ? '여성' : '성별 미상'}` : `${c.patient_age}y ${c.patient_sex}`,
      dept: isKo ? '외래 검사' : 'Outpatient testing',
      finding: c.scenario_name,
      missed: c.missing_followup,
      guideline: isKo ? '의료진이 적용 가능한 지침과 후속 계획을 검토해야 함' : 'Clinician review of the applicable guideline and follow-up plan is required',
      deadline: isKo ? '추적 조치 필요' : 'Follow-up review required',
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
    if (q1El) q1El.textContent = prof.finding;
    if (q2El) q2El.textContent = prof.missed;
    if (q3El) q3El.textContent = prof.guideline;

    const deadlineDateEl = document.getElementById('summary-deadline-date');
    if (deadlineDateEl) {
      deadlineDateEl.textContent = isKo
        ? '임상 사례 날짜 · 실시간 임상 마감 아님'
        : 'Example case date · not a live clinical deadline';
    }
    const timerText = document.getElementById('summary-timer-text');
    const badge = document.getElementById('summary-urgency-badge');
    const orderBtnLabel = document.getElementById('summary-order-btn-label');

    if (isClosed) {
      if (badge) {
        badge.className = 'badge-pill badge-safe';
        badge.textContent = isKo ? '종결 (예시 · 이 브라우저)' : 'Closed (example · this browser)';
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
        badge.className = 'badge-pill badge-open';
        badge.textContent = isKo ? '미완료 (예시)' : 'Open (example)';
      }
      if (timerText) {
        timerText.textContent = isKo ? '예시 기한 (실시간 아님)' : 'Example deadline (not live)';
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

    const outcomePlaceholder = isKo ? '추정하지 않음' : 'Not estimated';
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
    if (conditionTag) conditionTag.textContent = displayCopy(cf.condition_name, this.currentLang);

    const ptSummary = document.getElementById('cf-patient-summary');
    if (ptSummary) ptSummary.textContent = this.currentLang === 'ko' ? `${c.patient_id} (${c.patient_age}세) — ${c.title_kr || displayCopy(c.scenario_name, 'ko')}` : `${c.patient_id} (${c.patient_age}y / ${c.patient_sex}) — ${c.scenario_name}`;

    const deltaEl = document.getElementById('cf-survival-delta');
    if (deltaEl) deltaEl.textContent = displayCopy('Not estimated', this.currentLang);

    const subEl = document.getElementById('cf-survival-sub');
    if (subEl) subEl.textContent = displayCopy('No outcome model exists.', this.currentLang);

    const qalyEl = document.getElementById('cf-qaly-gain');
    if (qalyEl) qalyEl.textContent = displayCopy('Not established', this.currentLang);

    const liabEl = document.getElementById('cf-liability-avoided');
    if (liabEl) liabEl.textContent = displayCopy('Not estimated', this.currentLang);

    const guideEl = document.getElementById('cf-guideline-grade');
    if (guideEl && c.biomcp_evidence) {
      guideEl.textContent = this.currentLang === 'ko' ? '예시 인용 (정적 라이브러리)' : 'Sample citation (static library)';
    }

    const evText = document.getElementById('cf-evidence-text');
    if (evText) evText.textContent = displayCopy('No survival outcome model exists; nothing is estimated.', this.currentLang);

    for (const [id, steps, danger] of [
      ['cf-neglected-steps', cf.neglected_path, true],
      ['cf-intervened-steps', cf.intervened_path, false]
    ]) {
      const container = document.getElementById(id);
      if (!container || !Array.isArray(steps)) continue;
      container.replaceChildren(...steps.map(step => this.renderCounterfactualStep(step, danger)));
    }
  }

  renderCounterfactualStep(step, danger) {
    const make = (tag, cls, text) => {
      const node = document.createElement(tag); node.className = cls;
      if (text != null) node.textContent = String(text);
      return node;
    };
    const item = make('div', 'cf-step');
    const body = make('div', 'cf-step-body');
    const title = make('div', 'cf-step-title-row');
    title.append(make('span', 'cf-step-state', displayCopy(step.state, this.currentLang)),
      make('span', 'cf-step-stage ' + (danger ? 'stage-danger' : 'stage-success'), displayCopy(step.stage, this.currentLang)));
    const meta = make('div', 'cf-step-meta');
    meta.append(make('span', '', this.currentLang === 'ko' ? '예시 · 모델 예측 아님' : 'Illustration only · not a model prediction'));
    body.append(title, make('div', 'cf-step-desc', displayCopy(/survival|malpractice|mortality|risk was/i.test(step.desc) ? 'This is an unvalidated hypothetical outcome; no survival, harm-reduction or legal-risk estimate is established.' : step.desc, this.currentLang)), meta);
    item.append(make('div', 'cf-step-time', displayCopy(step.time, this.currentLang)), body);
    return item;
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
      if (marginEl) marginEl.innerHTML = `<span style="color: var(--emerald-safe); font-weight: 700;">ρ(Φ, t) = +∞ (${displayCopy('Invariant Formally Satisfied via Closed Loop', this.currentLang)})</span>`;
      if (statusPill) {
        statusPill.textContent = displayCopy('Invariant SATISFIED ✓', this.currentLang);
        statusPill.style.background = 'rgba(5, 223, 114, 0.15)';
        statusPill.style.color = 'var(--emerald-safe)';
        statusPill.style.borderColor = 'rgba(5, 223, 114, 0.4)';
      }
    } else if (margin >= 0) {
      if (marginEl) marginEl.innerHTML = `ρ(Φ, t) = T_crit - Δt = ${tCrit}d - ${deltaT}d = <span style="color: var(--emerald-safe); font-weight: 700;">+${margin}d (${displayCopy('Safe Window Active', this.currentLang)})</span>`;
      if (statusPill) {
        statusPill.textContent = displayCopy(`Safe Margin: +${margin} Days`, this.currentLang);
        statusPill.style.background = 'rgba(5, 223, 114, 0.15)';
        statusPill.style.color = 'var(--emerald-safe)';
        statusPill.style.borderColor = 'rgba(5, 223, 114, 0.4)';
      }
    } else {
      if (marginEl) marginEl.innerHTML = `ρ(Φ, t) = T_crit - Δt = ${tCrit}d - ${deltaT}d = <span style="color: var(--crimson-danger); font-weight: 700;">${margin}d (${displayCopy('CRITICAL TEMPORAL BREACH', this.currentLang)})</span>`;
      if (statusPill) {
        statusPill.textContent = displayCopy(`INVARIANT VIOLATED (${margin}d)`, this.currentLang);
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
      ? 'Synthetic demonstration text. This is not a clinical instruction or a message for a real patient. A clinician must review actual records and use an approved contact process.'
      : '합성 데이터 시연용 문구입니다. 임상 지시나 실제 환자에게 보낼 메시지가 아닙니다. 담당 의료진이 실제 기록을 검토하고 승인된 절차로 환자 연락 여부를 결정해야 합니다.';

    const setText = (id, value) => {
      const element = document.getElementById(id);
      if (element) element.textContent = value;
    };
    setText('kakao-outreach-title', isEnglish ? `Sample Patient Message · ${c.scenario_id}` : `임상 사례 안내문 · ${c.scenario_id}`);
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
    for (const [className, text, translate] of [
      ['audit-ts',ts,false], ['audit-engine',engineIcons[type] || engine,true],
      ['audit-action',action,true], ['audit-phi-badge',phiSafe ? '✅ No PHI' : '⚠️ PHI Check',true]
    ]) {
      const node=document.createElement('span');node.className=className;
      if (translate && window.ClinLoopUI) window.ClinLoopUI.set(node,text); else node.textContent=text;
      entry.appendChild(node);
    }
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
    // Recomputed only when the reader moves the slider: a number that changes by itself every few
    // seconds looks like live data, and it is not
    if (epsilonSlider) {
      epsilonSlider.addEventListener('input', updateDpNoise);
      updateDpNoise();
    }

    // Audit trail timestamp init
    const auditTs = document.getElementById('audit-ts-init');
    if (auditTs) auditTs.textContent = new Date().toISOString().slice(11,19) + ' UTC';

    // Audit export button
    const exportBtn = document.getElementById('audit-export-btn');
    if (exportBtn) {
      exportBtn.addEventListener('click', () => {
        const entries = document.querySelectorAll('.audit-entry');
        let report = displayCopy('ClinLoop AI — Privacy Audit Report',this.currentLang) + '\n';
        report += displayCopy('Generated: ' + new Date().toISOString(),this.currentLang) + '\n';
        report += displayCopy('Reference standards (design target, not certified): HIPAA Safe Harbor 45 CFR §164.514(b), Korean PIPA Articles 23-24',this.currentLang) + '\n\n';
        report += displayCopy('AUDIT TRAIL:',this.currentLang) + '\n';
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
      { name: 'IP 주소', regex: /\b(?:\d{1,3}\.){3}\d{1,3}\b/g, replace: '[IP 삭제]', type: 'strip' },
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

      // Korean names first, before any "[… 삭제]" tag exists to be mistaken for one. Only where the text
      // marks a name (after "환자:", "성명:", "이름:", "보호자:", or before 님 / 씨 / 환자): guessing from
      // the letters alone also replaces words such as "경기도" or "위험". This is a demo, not a de-identifier.
      const labelled = /((?:환자|성명|이름|보호자|patient|name)\s*[:：]?\s*)([가-힣]{2,4})(?![가-힣])/gi;
      const honorific = /(?<![가-힣])([가-힣]{2,4})(\s*(?:님|씨|환자))/g;
      const names = new Set();
      result = result.replace(labelled, (m, lead, nm) => { names.add(nm); return lead + getPseudo(nm); });
      result = result.replace(honorific, (m, nm, tail) => { names.add(nm); return getPseudo(nm) + tail; });
      if (names.size) {
        phiFound.push('한국 이름');
        pseudo += names.size;
      }

      PHI_RULES.forEach(rule => {
        const matches = result.match(rule.regex);
        if (matches) {
          phiFound.push(rule.name);
          const englishReplacement = {주민번호:'[National ID removed]',전화번호:'[Phone removed]',Email:'[Email removed]',URL:'[URL removed]','IP 주소':'[IP removed]',날짜:match=>match.slice(0,4),'한국어 날짜':match=>match.slice(0,4)};
          result = result.replace(rule.regex, this.currentLang === 'en' ? englishReplacement[rule.name] || rule.replace : rule.replace);
          stripped += matches.length;
        }
      });

      return { result, stripped, pseudo, phiFound: [...new Set(phiFound)] };
    };

    const sampleText = {
      en: `Patient: SAMPLE-01 (date of birth: 1978-03-12)
National ID: 780312-1234567
Phone: 010-1234-5678
Email: sample@example.invalid
Fictional address: Example City
CT finding (2024-03-15): 14 mm right lower lobe ground-glass nodule
Synthetic finding: lung nodule. Malignancy risk is not estimated; clinician review required.`,
      ko: `환자: 가상환자 (생년월일: 1978-03-12)
주민번호: 780312-1234567
전화: 010-1234-5678
이메일: sample@example.invalid
가상 주소: 예시 도시
CT 소견 (2024-03-15): 우하엽 14mm 간유리음영 결절 발견
합성 소견: 폐 결절 · 악성 위험은 추정하지 않음; 의료진 검토 필요`
    };
    let activeSample = null;
    const renderPrivacy = () => {
        if (activeSample && input.value === activeSample) { activeSample=sampleText[this.currentLang]; input.value=activeSample; }
        else activeSample=null; // Never rewrite a user-edited source.
        const raw = input.value;
        if (!raw.trim()) {
          output.textContent = this.currentLang === 'ko' ? '[예시 처리 결과가 여기에 표시됩니다]' : '[Demonstration output appears here]';
          if (countBadge) countBadge.textContent = this.currentLang === 'ko' ? '개인정보 항목: 0개 표시됨' : 'Personal-data items: 0 flagged';
          if (fstatStripped) fstatStripped.textContent = '0';
          if (fstatPseudo) fstatPseudo.textContent = '0';
          return;
        }
        const { result, stripped, pseudo, phiFound } = deidentify(raw);
        output.textContent = result;
        if (countBadge) {
          const names = {주민번호:'National ID',전화번호:'Phone',Email:'Email',URL:'URL','IP 주소':'IP address',날짜:'Date','한국어 날짜':'Korean date','한국 이름':'Korean name'};
          countBadge.textContent = this.currentLang === 'ko' ? `개인정보 항목: ${phiFound.length}개 표시됨 (${phiFound.map(value=>value==='Email'?'이메일':value).join(', ') || '없음'})` : `Personal-data items: ${phiFound.length} flagged (${phiFound.map(value=>names[value] || value).join(', ') || 'none'})`;
        }
        if (fstatStripped) fstatStripped.textContent = String(stripped);
        if (fstatPseudo) fstatPseudo.textContent = String(pseudo);
        if (shieldAnim && (stripped > 0 || pseudo > 0)) {
          shieldAnim.classList.add('active');
          setTimeout(() => shieldAnim.classList.remove('active'), 500);
        }
    };
    this.renderPrivacyLocale = renderPrivacy;
    let debounceTimer;
    input.addEventListener('input', () => { clearTimeout(debounceTimer); debounceTimer = setTimeout(renderPrivacy, 180); });
    renderPrivacy();

    if (sampleBtn) {
      sampleBtn.addEventListener('click', () => {
        activeSample = sampleText[this.currentLang];
        input.value = activeSample;
        input.dispatchEvent(new Event('input'));
      });
    }
  }


}

document.addEventListener('DOMContentLoaded', async () => {
  try {
    window.app = new ClinLoopApp();
    await window.app.init();
    document.body.classList.remove('cockpit-loading');
    const status = document.getElementById('cockpit-load-status');
    if (status) status.hidden = true;
  } catch (error) {
    const status = document.getElementById('cockpit-load-status');
    if (status) {
      status.setAttribute('data-demo-copy', 'loadFailed');
      status.textContent = document.documentElement.lang.startsWith('ko')
        ? '예시를 불러오지 못했습니다. 새로고침해 주세요.'
        : 'The examples could not be loaded. Refresh to try again.';
    }
  }
});
