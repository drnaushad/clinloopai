/**
 * ClinLoop AI - Interactive Dashboard Controller 2.0
 */


const CLINLOOP_I18N = {
  ko: {
    prototypeLabel: '연구 프로토타입',
    prototypeNotice: '합성 사례만 사용 · 실시간 EHR, 메시징, 가이드라인 연결 없음 · 환자 진료용 아님',
    brandSubtitle: '임상 후속조치 연구 프로토타입 · 합성 데이터',
    hospitalText: '합성 사례 연구 프로토타입',
    pitchDeck: '📊 피치덱 (Pitch Deck)',
    nobilityBtn: '🏛️ 의료 노블리티 & 윤리 헌장',
    outreachBtn: '📱 환자 알림톡',
    biomcpBtn: '🧬 Triple-MCP 의학 근거',
    emrBtn: '기존 EMR과 비교',
    triageTitle: '합성 사례 대기열',
    triageCount: '합성 사례 5건',
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
    guideDesc: 'ClinLoop AI는 후속 조치 업무 흐름을 검토하기 위한 연구 프로토타입입니다. 이 화면은 합성 사례만 사용하며 진단, 치료 권고, 환자 연락 또는 병원 연동을 수행하지 않습니다.',
    guideSteps: '<span class="guide-step">합성 사례 선택</span> <span class="guide-arrow">➔</span> <span class="guide-step">규칙 매칭과 근거를 검토</span> <span class="guide-arrow">➔</span> <span class="guide-step">브라우저에서만 시뮬레이션</span>',
    deadlineLabel: '추적 관리 의무 기한',
    q1Title: '1. 무엇이 발견되었나요? (What was found?)',
    q2Title: '2. 왜 위험한 상황인가요? (The Unclosed Loop)',
    q3Title: '3. 권고되는 조치는 무엇인가요? (Action Plan)',
    compTitle: '가상 시나리오 비교 · 임상 검증되지 않음',
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
    summaryKakaoSub: '합성 사례 기반 예시만 표시합니다. 실제 환자에게 보내지 마십시오.',
    summaryOrderLblDefault: '브라우저 로컬 종결 시뮬레이션 (전송 안 됨)',
    summaryOrderLblClosed: '브라우저에서만 상태 변경 (전송 안 됨)',
    summaryOrderSub: '이 프로토타입은 오더나 환자 메시지를 전송하지 않습니다.',
    clockTelemetryTitle: '시간 모델 예시 · 실시간 감시 아님',
    riskMetricLabel: '연구용 점수 · 임상 검증 안 됨',
    statRuleTitle: '온톨로지 규칙',
    statSeverityTitle: '합성 사례 중증도',
    mathToggleSummary: '🔬 AI 감쇠곡선 수학식 (Technical Math)',
    auditTrailTitle: '설명 가능한 AI 감사 추적 (Audit Trail)',
    dockLblTheme: '테마:',
    dockLblLang: '언어:',
    apiKeysBtn: '🔑 API 설정',
    apiModalTitle: '프로토타입 API 설정 (연결 안 됨)',
    apiModalSub: 'API 자격 증명 입력 기능이 비활성화되어 있습니다. 실제 API 키나 환자 정보를 입력하지 마십시오.',
    apiNobilityTitle: '⚠️ 연결 및 자격 증명 입력 비활성화',
    apiNobilityDesc: '이 프로토타입은 외부 AI, PubMed 또는 병원 EHR에 연결되지 않습니다. API 키는 저장되거나 전송되지 않으며, 임상 데이터나 환자 정보를 입력하지 마십시오.',
    lblGemini: 'Google Gemini / 임상 파운데이션 모델 API',
    descGemini: '자연어 환자 설명문 생성, 다국어 의학 번역, 복합 질환 임상 요약에 활용되는 생성형 AI API 키입니다.',
    lblAnthropic: 'Anthropic Claude (클로드 3.5 소넷 / 오퍼스)',
    descAnthropic: '최고 수준의 임상 의학 추론, 의료 윤리 안전 정렬 및 복합 다빈도 질환 퇴원 요약에 특화된 Anthropic 최상위 모델 API 키입니다.',
    lblOpenAI: 'OpenAI (프로젝트 아스트라 / o1 / GPT-4o 실시간)',
    descOpenAI: '심층 임상 감별진단 추론(o1) 및 실시간 음성/영상 다중모달 환자 공감 소통(Astra / GPT-4o Realtime)에 활용되는 API 키입니다.',
    lblNcbi: 'NCBI / PubMed / BioMCP E-Utilities API',
    descNcbi: 'NCBI API 키를 등록하면 초당 10회 고속 검색이 활성화되어 최신 의학 가이드라인 및 논문 원문을 지연 없이 검증합니다.',
    lblFhir: '원내 EMR / SMART on FHIR OAuth 토큰',
    descFhir: '원내 전자의무기록(EMR/EHR) 시스템(Epic, Cerner, 아주대 OCS)과 실시간 양방향 오더 연동을 위한 FHIR R4 토큰입니다.',
    txtTestPing: '연결 테스트 (Ping)',
    txtResetKeys: '키 초기화 (GPU 전용 복귀)',
    txtSaveKeys: 'API 설정 저장 & 적용 (Save Keys)',
    lblActiveEngine: '🤖 Active Clinical Foundation Model (활성 AI 추론 엔진 선택):',
    descEngineAnthropic: '최고 임상 추론 & 의료 윤리 정렬',
    descEngineOpenai: '실시간 다중모달 & 심층 CoT 추론',
    descEngineGemini: '초고속 다국어 건강 문해력 요약',
    descEngineLocal: '연결 안 됨 · 연구용 표시',
    btnCancelApi: '닫기 (Close)'
  },
  en: {
    prototypeLabel: 'RESEARCH PROTOTYPE',
    prototypeNotice: 'Synthetic cases only · No live EHR, messaging, or guideline connections · Not for patient care.',
    brandSubtitle: 'Clinical follow-up research prototype · synthetic data',
    hospitalText: 'Research prototype · synthetic cases',
    pitchDeck: '📊 Pitch Deck',
    nobilityBtn: '🏛️ Medical Nobility & Ethics',
    outreachBtn: '📱 Patient Outreach',
    biomcpBtn: '🧬 Triple-MCP Evidence',
    emrBtn: 'Compare vs EMR',
    triageTitle: 'Clinical Triage Queue',
    triageCount: '5 synthetic examples',
    searchPlaceholder: 'Search PT-ID, condition, rule, finding...',
    filterAll: 'All (5)',
    filterOpen: 'Open examples (3)',
    filterDelayed: 'Delayed example (1)',
    filterClosed: 'Closed example (1)',
    tabSummary: '🩺 Clinical Overview (Summary)',
    tabSummaryPill: 'Primary / Recommended',
    tabCounterfactual: '⚖️ Illustrative scenarios (not validated)',
    tabStandards: '🏥 Health Standards (OMOP / FHIR)',
    tabHypergraph: '🕸️ Knowledge Hypergraph (AI Graph)',
    tabPrivacy: '🛡️ Privacy Shield',
    guideTitle: '💡 What is ClinLoop AI? (System Purpose & Core Value)',
    guideDesc: 'ClinLoop AI is a research prototype for reviewing clinical follow-up workflows. This interface uses synthetic cases only; it does not diagnose, recommend treatment, contact patients, or connect to a hospital.',
    guideSteps: '<span class="guide-step">Select a synthetic case</span> <span class="guide-arrow">➔</span> <span class="guide-step">Review the rule match and evidence</span> <span class="guide-arrow">➔</span> <span class="guide-step">Run a browser-only simulation</span>',
    deadlineLabel: 'Mandatory Tracking Deadline',
    q1Title: '1. What was clinically detected? (Diagnostic Finding)',
    q2Title: '2. Why is this dangerous? (The Unclosed Loop Failure)',
    q3Title: '3. What is the recommended action? (Clinical Guideline)',
    compTitle: 'Illustrative scenario comparison · not clinically validated',
    compSub: 'No causal survival, treatment, or cost-benefit estimates have been validated.',
    negCardBadge: 'Synthetic scenario · no forecast',
    negMetric1: 'Clinical outcome estimate',
    negMetric2: 'Survival estimate',
    negCardNote: 'No patient-level risk estimate is available.',
    posCardBadge: 'Hypothetical workflow state · not a treatment effect',
    posMetric1: 'Treatment outcome estimate',
    posMetric2: 'Survival estimate',
    posCardNote: 'No QALY, survival, or cost savings have been established.',
    actionSecTitle: '⚡ Two Immediate One-Click Solutions to Close the Loop',
    actionSecDesc: 'These controls run browser-only simulations. No patient message or clinical order is sent.',
    summaryKakaoLbl: 'Preview a sample patient message',
    summaryKakaoSub: 'Illustrative synthetic-case text only. Do not send to a real patient.',
    summaryOrderLblDefault: 'Simulate local resolution (not sent)',
    summaryOrderLblClosed: 'State changed in this browser only (not sent)',
    summaryOrderSub: 'This prototype does not send orders or patient messages.',
    clockTelemetryTitle: 'Research timing preview · not live monitoring',
    riskMetricLabel: 'Research score · not clinically validated',
    statRuleTitle: 'Ontology Rule',
    statSeverityTitle: 'Synthetic case severity',
    mathToggleSummary: '🔬 Exponential Hazard Sigmoid Formula (Math)',
    auditTrailTitle: 'Explainable AI Audit Trail',
    dockLblTheme: 'Theme:',
    dockLblLang: 'Language:',
    apiKeysBtn: '🔑 API Keys',
    apiModalTitle: 'Prototype API settings (disconnected)',
    apiModalSub: 'API credential entry is disabled. Do not enter real API keys or patient information.',
    apiNobilityTitle: '⚠️ Connections and credential entry disabled',
    apiNobilityDesc: 'This prototype is not connected to external AI, PubMed, or a hospital EHR. API keys are not stored or transmitted. Do not enter clinical or patient information.',
    lblGemini: 'Google Gemini / Medical Foundation Model API',
    descGemini: 'Generative clinical LLM API key for plain-language patient explanations, multilingual translation, and complex discharge summaries.',
    lblAnthropic: 'Anthropic Claude (Claude 3.5 Sonnet / Opus)',
    descAnthropic: 'State-of-the-art clinical safety reasoning, medical ethics alignment, and complex multi-morbid discharge summarization.',
    lblOpenAI: 'OpenAI (Project Astra / o1 / GPT-4o Realtime)',
    descOpenAI: 'Deep chain-of-thought clinical diagnosis (o1) and real-time multimodal voice/video empathy interaction (Astra / GPT-4o).',
    lblNcbi: 'NCBI / PubMed / BioMCP E-Utilities API',
    descNcbi: 'Enables 10 requests/sec high-throughput PubMed literature and clinical guideline verification.',
    lblFhir: 'Hospital EHR / SMART on FHIR OAuth Token',
    descFhir: 'HL7 FHIR R4 token for bi-directional live clinical order dispatch into hospital EHR (Epic, Cerner, Ajou OCS).',
    txtTestPing: 'Test Connection',
    txtResetKeys: 'Reset to GPU Only',
    txtSaveKeys: 'Save & Apply Keys',
    lblActiveEngine: '🤖 Active Clinical Foundation Model:',
    descEngineAnthropic: 'State-of-the-Art Reasoning & Ethics',
    descEngineOpenai: 'Real-time Multimodal & Deep CoT',
    descEngineGemini: 'High-speed Multilingual Summarization',
    descEngineLocal: 'Not connected · research display only',
    btnCancelApi: 'Close'
  }
};


// ── Global: Test Local LLM Button (Privacy Shield Tab) ──────────────────────
async function testLocalLLM() {
  const btn = document.getElementById('test-local-llm-btn');
  const badge = document.getElementById('local-llm-status-badge');
  const output = document.getElementById('local-llm-test-output');
  if (!btn) return;

  btn.textContent = '⏳ Generating...';
  btn.disabled = true;
  if (badge) badge.textContent = 'Calling MedLlama2 via Ollama...';
  if (output) { output.style.display = 'block'; output.textContent = ''; }

  try {
    // First check engine status
    const statusResp = await fetch('http://localhost:8124/api/v1/local-llm/status', {timeout: 5000});
    const status = statusResp.ok ? await statusResp.json() : null;
    const bestModel = status?.best_model || 'deepseek-r1:32b';

    if (badge) badge.textContent = `Best model: ${status?.best_model_label || bestModel} · Generating...`;

    const t0 = Date.now();
    const resp = await fetch('http://localhost:8124/api/v1/local-llm/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        task: 'kakao_message_ko',
        clinical_context: 'Patient: 40대 남성. CT finding: 14mm ground-glass nodule in right lower lobe. Risk: 42.1% malignant progression (Fleischner 2017 high-risk). Follow-up PET-CT required within 24 days.',
      })
    });

    const latency = Date.now() - t0;

    if (resp.ok) {
      const data = await resp.json();
      if (output) output.textContent = data.text || '(empty response)';
      if (badge) badge.innerHTML = `<span style="color:#10b981">✅ ${data.model} · ${data.latency_ms || latency}ms · On-Premise ✓</span>`;
    } else {
      throw new Error(`HTTP ${resp.status}`);
    }
  } catch (e) {
    // Fallback: call Ollama directly
    try {
      const t0 = Date.now();
      const resp = await fetch('http://localhost:11434/api/generate', {
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
      if (output) output.textContent = data.response || '(empty)';
      if (badge) badge.innerHTML = `<span style="color:#10b981">✅ ${data.model} (direct Ollama) · ${Math.round(latency/1000)}s · On-Premise ✓</span>`;
    } catch (e2) {
      if (badge) badge.innerHTML = `<span style="color:#f59e0b">⚠️ Backend offline. DeepSeek-R1 runs on port 8124 / Ollama port 11434</span>`;
      if (output) { output.textContent = '[Offline prototype: no patient communication was generated.]'; output.style.display = 'block'; }
    }
  }
  btn.textContent = '▶ Test Local LLM Now';
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
    this.currentFilter = 'all';
    this.searchQuery = '';
    this.currentScrubDays = 35;
    this.currentView = 'hypergraph';
    this.currentLang = localStorage.getItem('clinloop_lang') || 'en';
    this.outreachLang = this.currentLang;
    this.activeEngine = localStorage.getItem('clinloop_active_engine') || 'local';
  }

  async init() {
    this.hypergraph = new HypergraphVisualizer('hypergraph-container');
    this.safetyGauge = new SafetyClockGauge('safety-gauge-canvas', 'sigmoid-canvas');

    await this.loadData();
    this.setupEventListeners();
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

  // ── Synthetic sample counts; these are not clinical impact metrics. ───────
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
      if (hudLabel) hudLabel.textContent = 'GPU: Not connected';
      for (const id of ['gpu-val-device', 'gpu-val-vram-total', 'gpu-val-vram-alloc', 'gpu-val-lat']) {
        const element = document.getElementById(id);
        if (element) element.textContent = 'Not connected';
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
    // API Key & Hospital Security Credentials Modal Integration
    // -----------------------------------------------------------------------
    // Active Clinical Foundation Model Switcher (Anthropic Claude 3.5, OpenAI Astra, Gemini 2.5, Local GPU)
    const engineCards = document.querySelectorAll('.engine-opt-card');
    const activeModelBadge = document.getElementById('active-model-badge');

    const updateEngineSelectionUI = (engine) => {
      this.activeEngine = engine;
      localStorage.setItem('clinloop_active_engine', engine);

      engineCards.forEach(card => {
        const isMatch = card.dataset.engine === engine;
        card.classList.toggle('active', isMatch);
        if (isMatch) {
          card.style.borderColor = (engine === 'anthropic') ? '#a78bfa' : (engine === 'openai') ? '#38bdf8' : (engine === 'gemini') ? 'var(--emerald-safe)' : 'var(--amber-warning)';
          card.style.background = (engine === 'anthropic') ? 'rgba(139, 92, 246, 0.18)' : (engine === 'openai') ? 'rgba(56, 189, 248, 0.18)' : (engine === 'gemini') ? 'rgba(5, 150, 105, 0.18)' : 'rgba(245, 158, 11, 0.18)';
        } else {
          card.style.borderColor = 'var(--border-subtle)';
          card.style.background = 'rgba(30, 41, 59, 0.5)';
        }
      });

      if (activeModelBadge) {
        activeModelBadge.textContent = 'Research template · no model connected';
        activeModelBadge.style.color = 'var(--text-muted)';
      }
      if (apiStatusPill) apiStatusPill.textContent = 'NOT CONNECTED';

      // Sync outreach simulator engine buttons if open
      const outreachBtns = document.querySelectorAll('.btn-outreach-engine');
      outreachBtns.forEach(btn => btn.classList.toggle('active', btn.dataset.engine === engine));
      const outreachPill = document.getElementById('outreach-model-pill');
      if (outreachPill) outreachPill.textContent = 'Research template · no AI connected';

      if (this.updateOutreachModal) this.updateOutreachModal();
    };

    engineCards.forEach(card => {
      card.addEventListener('click', () => {
        const engine = card.dataset.engine;
        updateEngineSelectionUI(engine);
        this._playTelemetrySound(880, 'sine', 0.1);
      });
    });

    // Outreach Engine Persona Buttons in #outreach-modal
    const outreachBtns = document.querySelectorAll('.btn-outreach-engine');
    outreachBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        const engine = btn.dataset.engine;
        updateEngineSelectionUI(engine);
        this._playTelemetrySound(920, 'sine', 0.08);
      });
    });

    const btnApiKeys = document.getElementById('btn-api-keys');
    const apiModal = document.getElementById('api-keys-modal');
    const btnCloseApiModal = document.getElementById('btn-close-api-modal');
    const btnCancelApiModal = document.getElementById('btn-cancel-api-modal');
    const btnSaveApiKeys = document.getElementById('btn-save-api-keys');
    const btnResetApiKeys = document.getElementById('btn-reset-api-keys');

    const inputGemini = document.getElementById('input-key-gemini');
    const inputAnthropic = document.getElementById('input-key-anthropic');
    const inputOpenAI = document.getElementById('input-key-openai');
    const inputNcbi = document.getElementById('input-key-ncbi');
    const inputFhir = document.getElementById('input-key-fhir');

    const btnTestGemini = document.getElementById('btn-test-gemini');
    const btnTestAnthropic = document.getElementById('btn-test-anthropic');
    const btnTestOpenAI = document.getElementById('btn-test-openai');
    const btnTestNcbi = document.getElementById('btn-test-ncbi');
    const btnTestFhir = document.getElementById('btn-test-fhir');

    const feedGemini = document.getElementById('feedback-gemini');
    const feedAnthropic = document.getElementById('feedback-anthropic');
    const feedOpenAI = document.getElementById('feedback-openai');
    const feedNcbi = document.getElementById('feedback-ncbi');
    const feedFhir = document.getElementById('feedback-fhir');

    const apiStatusPill = document.getElementById('api-status-pill');

    const loadSavedKeys = () => {
      localStorage.removeItem('clinloop_api_keys');
      for (const input of [inputGemini, inputAnthropic, inputOpenAI, inputNcbi, inputFhir]) {
        if (input) {
          input.value = '';
          input.disabled = true;
        }
      }
      for (const button of [btnTestGemini, btnTestAnthropic, btnTestOpenAI, btnTestNcbi, btnTestFhir, btnSaveApiKeys, btnResetApiKeys]) {
        if (button) button.disabled = true;
      }
      if (apiStatusPill) apiStatusPill.textContent = 'NOT CONNECTED';
    };

    loadSavedKeys();
    setTimeout(() => {
      const storedEngine = localStorage.getItem('clinloop_active_engine') || 'local';
      updateEngineSelectionUI(storedEngine);
    }, 100);

    // Auto-open modal if specified in query string (?modal=api-keys or ?modal=outreach)
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('modal') === 'api-keys' && apiModal) {
      loadSavedKeys();
      apiModal.classList.add('open');
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

    if (btnApiKeys && apiModal) {
      btnApiKeys.addEventListener('click', () => {
        loadSavedKeys();
        apiModal.classList.add('open');
      });
    }

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

    // Ping Test helper
    const testKeyConnection = (provider, inputEl, feedbackEl, btnEl) => {
      inputEl.value = '';
      feedbackEl.className = 'api-feedback-msg error';
      feedbackEl.textContent = this.currentLang === 'en'
        ? 'API testing is disabled in this prototype.'
        : '프로토타입에서 API 연결 테스트는 비활성화되어 있습니다.';
    };

    if (btnTestGemini && inputGemini && feedGemini) {
      btnTestGemini.addEventListener('click', () => testKeyConnection('gemini', inputGemini, feedGemini, btnTestGemini));
    }
    if (btnTestAnthropic && inputAnthropic && feedAnthropic) {
      btnTestAnthropic.addEventListener('click', () => testKeyConnection('anthropic', inputAnthropic, feedAnthropic, btnTestAnthropic));
    }
    if (btnTestOpenAI && inputOpenAI && feedOpenAI) {
      btnTestOpenAI.addEventListener('click', () => testKeyConnection('openai', inputOpenAI, feedOpenAI, btnTestOpenAI));
    }
    if (btnTestNcbi && inputNcbi && feedNcbi) {
      btnTestNcbi.addEventListener('click', () => testKeyConnection('ncbi', inputNcbi, feedNcbi, btnTestNcbi));
    }
    if (btnTestFhir && inputFhir && feedFhir) {
      btnTestFhir.addEventListener('click', () => testKeyConnection('fhir', inputFhir, feedFhir, btnTestFhir));
    }

    if (btnSaveApiKeys) {
      btnSaveApiKeys.addEventListener('click', async () => {
        // ─── BAA Compliance Gate (HIPAA + Korean PIPA) ───
        const _aKey = inputAnthropic ? inputAnthropic.value.trim() : '';
        const _oKey = inputOpenAI ? inputOpenAI.value.trim() : '';
        const _gKey = inputGemini ? inputGemini.value.trim() : '';
        if (_aKey || _oKey || _gKey) {
          const isKo = (this.currentLang !== 'en');
          const baaMsg = isKo
            ? '⚖️ HIPAA BAA 규정 준수 확인 필요\n\n클라우드 API 키 저장 전 반드시 확인하십시오:\n\n✅ 해당 클라우드 제공업체(Anthropic/OpenAI/Google)와 HIPAA 업무위탁계약(BAA)이 체결되었음\n\n✅ 한국 개인정보보호법 제17조에 따른 환자 동의(외부 AI 서비스 이용)가 문서화됨\n\n✅ ClinLoop AI PHI 비식별화 필터가 상시 활성화 상태임\n\n온프레미스 GPU는 언제든지 무위험 기본 엔진으로 즉시 복귀 가능합니다.\n\n확인을 클릭하여 BAA 준수 사실을 인정하고 키를 저장합니다.'
            : '⚖️ HIPAA BAA Compliance Confirmation Required\n\nBefore saving cloud API keys, please confirm:\n\n✅ A HIPAA Business Associate Agreement has been signed with this cloud provider (Anthropic / OpenAI / Google)\n\n✅ Korean PIPA Article 17 patient consent for external AI services is documented\n\n✅ ClinLoop AI PHI De-identification Filter will remain ACTIVE at all times\n\nThe On-Premise GPU remains the zero-risk sovereign default engine at all times.\n\nClick OK to confirm BAA compliance and save keys.';
          const baaOk = confirm(baaMsg);
          if (!baaOk) {
            this.showNotification(
              isKo ? '⚠️ 저장 취소됨. 클라우드 모델 사용을 위해 BAA 확인이 필요합니다.' : '⚠️ Save cancelled. BAA confirmation is required for cloud model access.',
              'warning'
            );
            return;
          }
        }
        // ─────────────────────────────────────────────────
        const keys = {
          gemini: inputGemini ? inputGemini.value.trim() : '',
          anthropic: inputAnthropic ? inputAnthropic.value.trim() : '',
          openai: inputOpenAI ? inputOpenAI.value.trim() : '',
          ncbi: inputNcbi ? inputNcbi.value.trim() : '',
          fhir: inputFhir ? inputFhir.value.trim() : ''
        };

        loadSavedKeys();
        if (apiModal) apiModal.classList.remove('open');
        alert((this.currentLang === 'en') ? 'API credentials are disabled in this prototype.' : '프로토타입에서 API 자격 증명은 비활성화되어 있습니다.');
      });
    }

    if (btnResetApiKeys) {
      btnResetApiKeys.addEventListener('click', () => {
        if (inputGemini) inputGemini.value = '';
        if (inputAnthropic) inputAnthropic.value = '';
        if (inputOpenAI) inputOpenAI.value = '';
        if (inputNcbi) inputNcbi.value = '';
        if (inputFhir) inputFhir.value = '';
        localStorage.removeItem('clinloop_api_keys');

        const badgeGemini = document.getElementById('badge-gemini-status');
        const badgeAnthropic = document.getElementById('badge-anthropic-status');
        const badgeOpenAI = document.getElementById('badge-openai-status');
        const badgeNcbi = document.getElementById('badge-ncbi-status');
        const badgeFhir = document.getElementById('badge-fhir-status');
        if (badgeGemini) badgeGemini.textContent = 'Not connected';
        if (badgeAnthropic) badgeAnthropic.textContent = 'Not connected';
        if (badgeOpenAI) badgeOpenAI.textContent = 'Not connected';
        if (badgeNcbi) badgeNcbi.textContent = 'Not connected';
        if (badgeFhir) badgeFhir.textContent = 'Not connected';

        if (apiStatusPill) {
          apiStatusPill.textContent = 'NOT CONNECTED';
        }
      });
    }

    
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
        this.addAuditEntry('simulation', 'LOCAL SIMULATION', `Case marked resolved in this browser; no order was sent · Case: ${caseName}`, true);
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

      if (btnHeaderLangKo) btnHeaderLangKo.classList.toggle('active', isKo);
      if (btnHeaderLangEn) btnHeaderLangEn.classList.toggle('active', !isKo);
      if (dockBtnKo) dockBtnKo.classList.toggle('active', isKo);
      if (dockBtnEn) dockBtnEn.classList.toggle('active', !isKo);

      localStorage.setItem('clinloop_lang', this.currentLang);

    // Update Pitch Deck link based on language
    const pitchLink = document.getElementById('pitch-deck-link');
    if (pitchLink) {
      pitchLink.href = this.currentLang === 'en' ? 'presentation_en.html' : 'presentation.html';
    }

      this.applyI18nText(this.currentLang);

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
    this.setLanguage(initialLang);

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
    setTxt('prototype-notice-label', t.prototypeLabel);
    setTxt('prototype-notice-copy', t.prototypeNotice);
    setTxt('pitch-deck-link', t.pitchDeck);
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

    const isKo = (this.currentLang !== 'en');

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
      pillDelta.textContent = 'Not validated';
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
    const isKo = (this.currentLang !== 'en');
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
      actionTitle.textContent = isKo ? '합성 사례: 후속조치 규칙 매칭' : 'Synthetic case: follow-up rule match';
      actionDesc.textContent = isKo
        ? `시연 데이터의 예시 항목: ${scenario.missing_followup || '후속조치'}. 실제 환자 우선순위나 임상 권고가 아닙니다.`
        : `Illustrative sample gap: ${scenario.missing_followup || 'follow-up'}. This is not a patient-specific priority or clinical recommendation.`;
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
        sub: scenario.biomcp_evidence ? `Illustrative citation: ${scenario.biomcp_evidence.guideline_org.split('(')[0].trim()} • PMID: ${scenario.biomcp_evidence.pmid}` : 'Static sample metadata; not a live evidence lookup'
      },
      {
        num: '03',
        title: isClosed ? 'Verification: Closed in Graph' : `Identified Gap: ${scenario.missing_followup}`,
        sub: isClosed ? 'Synthetic sample state only; no clinical closure verified' : 'Synthetic sample label; not a clinical hazard determination'
      },
      {
        num: '04',
        title: isClosed ? 'Local sample state changed' : 'No alert was dispatched',
        sub: 'No EHR writeback, messaging, or clinician escalation is connected'
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
    const isKo = (this.currentLang !== 'en');

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
        missed: '갈비뼈 치료만 완료되고 폐 결절에 대한 외래 예약이나 호흡기내과 협진이 누락된 채 66일 경과',
        guideline: 'Fleischner Society 2017 가이드라인 (90일 이내 저선량 흉부 CT 재검 또는 조직검사 필수)',
        deadline: '24일 남음 (마감일자: 2026-10-15)',
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
        missed: 'Rib fracture treated but follow-up CT and Pulmonology referral silently lost in EMR for 66 days post-discharge',
        guideline: 'Fleischner Society 2017 Guidelines (Thin-slice Chest CT repeat within 90 days or tissue biopsy)',
        deadline: '24 Days Remaining (Safety Deadline: 2026-10-15)',
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
        ? '합성 사례 날짜 · 실시간 임상 마감 아님'
        : 'Synthetic scenario date · not a live clinical deadline';
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
        badge.textContent = isKo ? '합성 연구 사례 · 임상 우선순위 아님' : 'Synthetic research sample · not a clinical priority';
      }
      if (timerText) {
        timerText.textContent = isKo ? '시연용 시간 정보' : 'Illustrative timing only';
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

    const outcomePlaceholder = isKo ? '임상 검증되지 않음' : 'Not clinically validated';
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
    if (deltaEl) deltaEl.textContent = 'Not clinically validated';

    const subEl = document.getElementById('cf-survival-sub');
    if (subEl) subEl.textContent = 'No validated clinical outcome model is available.';

    const qalyEl = document.getElementById('cf-qaly-gain');
    if (qalyEl) qalyEl.textContent = 'Not established';

    const liabEl = document.getElementById('cf-liability-avoided');
    if (liabEl) liabEl.textContent = 'Not estimated';

    const guideEl = document.getElementById('cf-guideline-grade');
    if (guideEl && c.biomcp_evidence) {
      guideEl.textContent = 'Static sample citation · not a live evidence lookup';
    }

    const evText = document.getElementById('cf-evidence-text');
    if (evText) evText.textContent = 'Illustrative scenario content only; no causal effect is established.';

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
              <span>Illustrative scenario only</span>
              <span>Survival and hazard estimates not validated</span>
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
              <span>Illustrative scenario only</span>
              <span>Survival and hazard estimates not validated</span>
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
      ? 'Synthetic research text only. This is not a clinical instruction or a message to send. A qualified clinician must review the actual record and decide any patient communication through approved channels.'
      : '합성 데이터 시연용 문구입니다. 임상 지시나 실제 환자에게 보낼 메시지가 아닙니다. 담당 의료진이 실제 기록을 검토하고 승인된 절차로 환자 연락 여부를 결정해야 합니다.';

    const setText = (id, value) => {
      const element = document.getElementById(id);
      if (element) element.textContent = value;
    };
    setText('kakao-outreach-title', isEnglish ? `Synthetic sample message · ${c.scenario_id}` : `합성 사례 안내문 · ${c.scenario_id}`);
    setText('kakao-jargon-text', isEnglish ? 'Synthetic case selected' : '합성 사례 선택됨');
    setText('kakao-outreach-body', message);
    setText('kakao-dept-slot', isEnglish ? 'No appointment reserved' : '예약된 일정 없음');
    setText('kakao-btn-label', isEnglish ? 'Simulate local workflow (not booked)' : '로컬 시뮬레이션 (예약되지 않음)');
    setText('outreach-fhir-id', isEnglish ? 'Not connected · no message request sent' : '연결 안 됨 · 메시지 요청 전송 안 됨');
    setText('outreach-model-pill', isEnglish ? 'Research template · no AI connected' : '연구용 템플릿 · AI 연결 안 됨');
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
    this.handleCloseLoop();
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
      setInterval(updateDpNoise, 2200);
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
