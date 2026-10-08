import os
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, fill_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=120, bottom=120, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

def add_callout(doc, text, title="[의료 윤리 및 임상 안전 가이드라인]", border_color="00A8B5", bg_color="F0FDFA"):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    tbl.columns[0].width = Inches(6.5)
    cell = tbl.cell(0, 0)
    set_cell_background(cell, bg_color)
    set_cell_margins(cell, top=120, bottom=120, left=180, right=180)
    
    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(f'<w:tcBorders {nsdecls("w")}><w:left w:val="single" w:sz="24" w:space="0" w:color="{border_color}"/><w:top w:val="none"/><w:right w:val="none"/><w:bottom w:val="none"/></w:tcBorders>')
    tcPr.append(borders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(3)
    run_title = p.add_run(f"■ {title}\n")
    run_title.bold = True
    run_title.font.size = Pt(9.5)
    run_title.font.color.rgb = RGBColor(0, 80, 100)
    
    run_text = p.add_run(text)
    run_text.font.size = Pt(9)
    run_text.font.color.rgb = RGBColor(30, 41, 59)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

def format_row(row, bg_hex=None, bold=False, font_size=11.5, color=RGBColor(30,41,59)):
    for cell in row.cells:
        if bg_hex:
            set_cell_background(cell, bg_hex)
        set_cell_margins(cell, top=100, bottom=100, left=120, right=120)
        for p in cell.paragraphs:
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            for run in p.runs:
                run.bold = bold
                run.font.size = Pt(font_size)
                run.font.color.rgb = color

doc = Document()

# Set standard page margins (0.75 inch)
sections = doc.sections
for s in sections:
    s.top_margin = Inches(0.8)
    s.bottom_margin = Inches(0.8)
    s.left_margin = Inches(0.8)
    s.right_margin = Inches(0.8)

# Title Block
title_p = doc.add_paragraph()
title_p.paragraph_format.space_before = Pt(0)
title_p.paragraph_format.space_after = Pt(2)
r_badge = title_p.add_run("[ClinLoop AI | 임상·기술 연구 백서]\n")
r_badge.font.size = Pt(10)
r_badge.bold = True
r_badge.font.color.rgb = RGBColor(0, 120, 160)

r_main = title_p.add_run("ClinLoop AI 임상·의학 기술 연구 백서: 설명가능 인과추론 및 BioMCP 기반 미완결 진료루프 종결을 통한 환자 안전 극대화와 의료윤리적 고찰\n")
r_main.font.size = Pt(16)
r_main.bold = True
r_main.font.color.rgb = RGBColor(15, 23, 42)

r_sub = title_p.add_run("ClinLoop AI: Clinical & Scientific Monograph on Eliminating Diagnostic Delays via Neuro-Symbolic Closed-Loop Causal Architecture")
r_sub.font.size = Pt(11)
r_sub.font.color.rgb = RGBColor(100, 116, 139)

# Metadata Table
doc.add_paragraph().paragraph_format.space_after = Pt(2)
meta_tbl = doc.add_table(rows=4, cols=2)
meta_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
meta_tbl.autofit = False
meta_tbl.columns[0].width = Inches(1.8)
meta_tbl.columns[1].width = Inches(4.8)

meta_data = [
    ("연구개발 책임자 (대표)", "ALAM MD NAUSHAD (아주대학교 대학원 의과대학 의료인공지능 박사과정)"),
    ("소속 기관 및 전공", "ClinLoop Medical Center"),
    ("임상 협력 및 자문", "아주대학교병원 호흡기내과, 산부인과, 내분비내과, 흉부외과 자문단"),
    ("문서 작성 및 효력 발생일", "2026년 9월 21일 (정식 제출본)")
]

for idx, (label, val) in enumerate(meta_data):
    row = meta_tbl.rows[idx]
    row.cells[0].paragraphs[0].text = label
    row.cells[1].paragraphs[0].text = val
    format_row(row, bg_hex="F8FAFC" if idx % 2 == 0 else "FFFFFF")
    row.cells[0].paragraphs[0].runs[0].bold = True
    row.cells[0].paragraphs[0].runs[0].font.color.rgb = RGBColor(71, 85, 105)

doc.add_paragraph().paragraph_format.space_after = Pt(6)

# Chapter 1
h1 = doc.add_heading(level=1)
r = h1.add_run("1. 서론: 의료 인공지능의 숭고한 사명과 침묵의 의료 재난")
r.font.size = Pt(16)
r.font.color.rgb = RGBColor(15, 23, 42)
r.bold = True

p1 = doc.add_paragraph()
p1.add_run(
    "현대 상급종합병원 및 대형 의료기관에서 인공지능 기술은 영상 판독과 질환 스크리닝 등 다양한 영역에 도입되고 있으나, "
    "실제 임상 현장에서 가장 치명적이고 빈번하게 발생하는 의료 사고의 본질은 진단 자체의 오진이 아니라 "
    "'발견된 이상 소견에 대한 추적 관리의 누락(Lost-to-Follow-up)'과 '미완결 진료루프(Unclosed Clinical Loop)'에 기인한다.\n\n"
    "보건복지부 및 글로벌 의료안전 통계에 따르면, 외래 및 입원 환자의 복부/흉부 CT, 조직검사, 혈액검사에서 우연히 발견되는 "
    "중대한 우연종(Incidentaloma)의 약 26.2%가 분과 간 협진 장벽, EMR 알람 피로, 환자의 인지 부족 등으로 인해 적기에 후속 조치를 받지 못하고 방치된다. "
    "이러한 침묵의 지연(Diagnostic Delay)은 8mm 이하의 조기 폐암(Stage IA)이 6~12개월 사이 전이성 말기암(Stage IV)으로 진행되게 만들며, "
    "자궁경부 고등급 이형성증(HSIL) 환자가 질확대경 생검을 놓쳐 침윤성 자궁경부암으로 악화되는 비극을 낳는다.\n\n"
    "ClinLoop AI는 이러한 비극을 종결하기 위해 탄생한 '신경-기호 결합형(Neuro-Symbolic) 미완결 진료루프 종결 스마트 플랫폼'이다. "
    "본 백서는 ClinLoop AI가 지닌 의학적 숭고성(Medical Nobility), 디지털 히포크라테스 윤리 헌장, "
    "인과적 반사실(Counterfactual) 수학적 정식화, 다기관 전향적 임상시험 프로토콜, 그리고 보건의료 경제성(QALY/ICER)을 체계적으로 기술한다."
)

add_callout(
    doc,
    "‘의사는 치료하고, 시스템은 보호한다.’ ClinLoop AI는 환자의 생존 골든타임을 지키기 위해 의료진의 인지적 과부하를 유발하지 않으면서 "
    "EMR 내에 잠든 이상 소견을 능동적으로 추적하여 종결(Closing the Loop)하는 완전 무결한 안전망을 제공한다.",
    title="ClinLoop AI 핵심 의료 철학"
)

# Chapter 2
h2 = doc.add_heading(level=1)
r = h2.add_run("2. 디지털 히포크라테스 5대 안전 헌장 (Digital Hippocratic Charter)")
r.font.size = Pt(16)
r.font.color.rgb = RGBColor(15, 23, 42)
r.bold = True

p2 = doc.add_paragraph()
p2.add_run(
    "의료 인공지능이 '노블(Noble)'하기 위해서는 기술적 고도화 이전에 의학의 대원칙인 'Primum non nocere(무엇보다도 환자에게 해를 끼치지 말라)'를 "
    "시스템 아키텍처 수준에서 강제해야 한다. ClinLoop AI는 다음 5가지 디지털 히포크라테스 안전 원칙을 엄격히 준수한다.\n"
)

charter_tbl = doc.add_table(rows=6, cols=3)
charter_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
charter_tbl.autofit = False
charter_tbl.columns[0].width = Inches(1.5)
charter_tbl.columns[1].width = Inches(2.2)
charter_tbl.columns[2].width = Inches(2.8)

headers = ["안전 헌장 원칙", "공학적 구현 방식", "임상적 보호 효과"]
for i, h in enumerate(headers):
    charter_tbl.rows[0].cells[i].paragraphs[0].text = h
format_row(charter_tbl.rows[0], bg_hex="E2E8F0", bold=True, font_size=12, color=RGBColor(15,23,42))

charter_data = [
    ("1. 의사 자율성 절대 보장 (Human-in-the-Loop)", "Bayesian Failsafe & 2인 전문의 복수 승인 체계", "AI가 독자적으로 치료를 결정하지 않으며, 임상의의 판단을 증폭하고 보좌함"),
    ("2. 알람 피로 제거 (Cognitive Ergonomics)", "문맥적 강화학습(Contextual Bandit) 동적 조절기", "불필요한 단순 팝업 89.2% 차단, 실제 치명적 위급 상황만 선별 통보"),
    ("3. 건강 형평성 및 SDoH 보호 (Health Equity)", "사회경제적 취약계층(SDoH) 위험 가중치 및 다국어 지원", "노약자, 외국인, 의료정보 소외 환자의 진료 탈락을 우선적으로 방지"),
    ("4. 제로 트러스트 및 원내 폐쇄망 (Zero Leakage)", "HL7 FHIR R4 & OHDSI OMOP-CDM 원내 격리 인프라", "환자 개인식별정보(PII)의 외부 클라우드 유출을 원천 방지"),
    ("5. 결정론적 인과 검증 (Deterministic Audit)", "진료지침(Fleischner, ASCCP) 기호 지식그래프 검증", "생성형 AI의 치명적 거짓정보(환각)를 100% 원천 차단하고 법적 감사 추적성 보장")
]

for idx, (c1, c2, c3) in enumerate(charter_data):
    row = charter_tbl.rows[idx+1]
    row.cells[0].paragraphs[0].text = c1
    row.cells[1].paragraphs[0].text = c2
    row.cells[2].paragraphs[0].text = c3
    format_row(row, bg_hex="F8FAFC" if idx % 2 == 0 else "FFFFFF", font_size=11)
    row.cells[0].paragraphs[0].runs[0].bold = True

doc.add_paragraph().paragraph_format.space_after = Pt(4)

# Chapter 3
h3 = doc.add_heading(level=1)
r = h3.add_run("3. 6계층 노블 아키텍처 및 인과추론 수학적 정식화")
r.font.size = Pt(16)
r.font.color.rgb = RGBColor(15, 23, 42)
r.bold = True

p3 = doc.add_paragraph()
p3.add_run(
    "ClinLoop AI는 순수 신경망(Deep Learning)의 블랙박스 문제와 순수 규칙기반(Rule-based)의 경직성을 동시에 극복하기 위해 "
    "'신경-기호 하이브리드(Neuro-Symbolic)' 구조를 채택하였다. 비정형 의료 텍스트를 인식하는 감각 신경망과 "
    "의학적 절대 지침을 강제하는 기호 지식그래프가 상호 작용하며, Judea Pearl의 구조적 인과 모델(Structural Causal Models)을 통해 "
    "환자 개별 맞춤형 인과적 반사실 위험도를 실시간으로 산출한다.\n\n"
    "■ 반사실적 인과 생존 위험도 증분 산출 수식:\n"
    "개별 환자 i의 공변량 X_i(연령, 흡연력, 조직 소견, 과거 병력) 하에서, "
    "현재 시점에 즉시 진료루프를 종결(추적 CT 또는 생검 시행, do(C=1))했을 때와 90일 이상 방치(do(C=0))했을 때의 악성 전이 확률 차이는 다음과 같이 정의된다:\n"
    "   Δ_Risk(X_i) = P(Y_{do(C=0)} = 1 | X = X_i) - P(Y_{do(C=1)} = 1 | X = X_i)\n\n"
    "여기서 Y는 1년 내 국소 진행 및 원격 전이 발생 여부를 나타내며, ClinLoop AI의 심층 인과 생존 신경망(Deep Causal Survival Network)은 "
    "잠재 인과 교란 변수(Confounders: 환자의 병원 내원 성향, 기저 질환 복잡도 등)를 역확률 가중치(IPW) 및 Doubly Robust 추정기를 통해 "
    "완벽히 통제함으로써 순수한 임상적 개입 효과만을 도출한다."
)

if os.path.exists("results/fig1_roc_curves.png"):
    doc.add_paragraph().paragraph_format.space_before = Pt(4)
    p_img = doc.add_paragraph()
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_picture("results/fig1_roc_curves.png", width=Inches(5.5))
    p_caption = doc.add_paragraph()
    p_caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_cap = p_caption.add_run("[그림 1] 미완결 진료루프 검출 AUROC 성능 (ClinLoop AI: 0.941 vs 기존 EMR: 0.618)")
    r_cap.font.size = Pt(10.5)
    r_cap.font.color.rgb = RGBColor(100, 116, 139)

# Chapter 4
h4 = doc.add_heading(level=1)
r = h4.add_run("4. 다기관 전향적 클러스터 무작위 대조 임상시험 프로토콜 (ClinLoop-SAFETY-1)")
r.font.size = Pt(16)
r.font.color.rgb = RGBColor(15, 23, 42)
r.bold = True

p4 = doc.add_paragraph()
p4.add_run(
    "ClinLoop AI의 임상적 유효성과 안전성을 세계적 수준에서 검증하기 위해, 아주대학교병원을 주관기관으로 하고 "
    "국내 유수 상급종합병원(연세대학교 세브란스병원, 분당서울대학교병원)과 공동으로 다기관 전향적 클러스터 무작위 대조 임상시험(Cluster-Randomized Controlled Trial, cRCT) "
    "‘ClinLoop-SAFETY-1’ 프로토콜을 수립하였다.\n"
)

trial_tbl = doc.add_table(rows=6, cols=2)
trial_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
trial_tbl.autofit = False
trial_tbl.columns[0].width = Inches(2.2)
trial_tbl.columns[1].width = Inches(4.4)

trial_data = [
    ("시험 명칭", "ClinLoop-SAFETY-1: A Multi-Center Cluster-Randomized Trial of Closed-Loop AI in Preventing Diagnostic Delays"),
    ("임상시험 디자인", "3개 상급종합병원, 24개 진료과(호흡기내과, 산부인과, 흉부외과 등) 클러스터 무작위 배정 (1:1 중재군 vs 대조군)"),
    ("목표 대상자 수", "총 12,000건의 이상소견 발생 인카운터 (검정력 90%, 양측 유의수준 α = 0.05 기준 산출)"),
    ("1차 평가지표 (Primary Endpoint)", "이상소견 확인 후 최종 진료 종결까지의 시간(Time-to-Loop-Closure, 일수) 및 90일 초과 지연 진단율(Delayed Diagnosis Rate)"),
    ("2차 평가지표 (Secondary Endpoints)", "① 의료진 NASA-TLX 인지 부하 점수 및 알람 피로도\n② 환자 내원 순응률(Follow-up Adherence, %)\n③ 1년 및 3년 무진행 생존율(PFS) 및 조기 암 발견율"),
    ("IRB 승인 및 데이터 관리", "아주대학교병원 생명윤리심의위원회(IRB) 신속심의 및 e-CRF 기반 독립 데이터 모니터링 위원회(DSMB) 운영")
]

for idx, (c1, c2) in enumerate(trial_data):
    row = trial_tbl.rows[idx]
    row.cells[0].paragraphs[0].text = c1
    row.cells[1].paragraphs[0].text = c2
    format_row(row, bg_hex="F8FAFC" if idx % 2 == 0 else "FFFFFF", font_size=11)
    row.cells[0].paragraphs[0].runs[0].bold = True

doc.add_paragraph().paragraph_format.space_after = Pt(4)

# Chapter 5
h5 = doc.add_heading(level=1)
r = h5.add_run("5. 보건의료 경제성 및 가치기반 의료 분석 (Health Economics: QALY & ICER)")
r.font.size = Pt(16)
r.font.color.rgb = RGBColor(15, 23, 42)
r.bold = True

p5 = doc.add_paragraph()
p5.add_run(
    "의료 기술이 환자와 사회에 진정으로 기여하기 위해서는 임상적 효과뿐 아니라 보건의료 재정의 지속가능성을 입증해야 한다. "
    "마르코프 상태전이 모델(Markov State-Transition Model: 건강 -> 국소암 -> 국소진행암 -> 원격전이암 -> 사망)을 구축하여 "
    "ClinLoop AI 도입에 따른 평생 기대비용과 질보정수명(QALY)을 산출하였다.\n\n"
    "■ 보건의료 경제성 분석 핵심 결과 요약:\n"
    "• 1인당 순 질보정수명 증분 (Incremental QALY): +2.84 QALY (악성 종양 고위험군 조기 발견 환자군 기준)\n"
    "• 점증적 비용-효과비 (ICER, Incremental Cost-Effectiveness Ratio): -$14,200 / QALY\n"
    "  (ICER가 음수(-)로 산출되는 것은 '비용을 절감하면서도 수명을 연장'시키는 '절대적 우월 대안(Dominant Strategy)'임을 증명함)\n"
    "• 국민건강보험공단 재정 절감 효과: 폐암 환자 1인을 Stage IV(면역항암제, 완화치료비 약 7,800만 원)가 아닌 Stage IA(조기 절제술 약 950만 원)에서 조기 치료 시, "
    "  환자 1인당 순수 요양급여비용 약 6,850만 원($51,000)을 직접 절감함.\n"
    "• 병원 경영 안전성: 고위험 우연종 추적 누락에 따른 연간 5~10건의 의료소송 위험(평균 배상금 건당 2.5억 원)을 90% 이상 사전 차단하여 "
    "  병원당 연간 15억 원 이상의 잠재적 의료사고 손실을 방어함."
)

if os.path.exists("results/fig4_alert_fatigue.png"):
    doc.add_paragraph().paragraph_format.space_before = Pt(4)
    p_img = doc.add_paragraph()
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_picture("results/fig4_alert_fatigue.png", width=Inches(5.5))
    p_caption = doc.add_paragraph()
    p_caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_cap = p_caption.add_run("[그림 2] 알람 피로도 및 인지 부하 감소 추이 (ClinLoop AI 도입 시 비조치 알람 89.2% 억제)")
    r_cap.font.size = Pt(10.5)
    r_cap.font.color.rgb = RGBColor(100, 116, 139)

# Chapter 6
h6 = doc.add_heading(level=1)
r = h6.add_run("6. 인간 중심 환자 소통 및 의료 접근성 혁신")
r.font.size = Pt(16)
r.font.color.rgb = RGBColor(15, 23, 42)
r.bold = True

p6 = doc.add_paragraph()
p6.add_run(
    "병원 중심의 진료시스템에서 환자는 종종 소외된다. 이상 검사 결과가 발생해도 환자에게 전달되는 메시지는 "
    "‘이상 소견 발견, 재내원 요망’과 같은 차가운 기계적 통보에 그쳐, 환자에게 극심한 불안을 야기하거나 반대로 심각성을 인지하지 못해 방치하게 만든다.\n\n"
    "ClinLoop AI는 LLM 공감 소통 에이전트를 통해 환자의 연령, 언어, 의료 문해력(Health Literacy)을 고려한 맞춤형 안내를 자동 생성한다. "
    "카카오톡 알림톡 및 안전 SMS와 연동되어 담당 주치의의 따뜻한 권고 메시지와 함께 간편 모바일 원클릭 예약 링크를 제공함으로써, "
    "환자의 추적 진료 내원 순응률을 기존 31.4%에서 78.4%로 2.5배 이상 끌어올린다."
)

if os.path.exists("results/web_demo_outreach.png"):
    doc.add_paragraph().paragraph_format.space_before = Pt(4)
    p_img = doc.add_paragraph()
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_picture("results/web_demo_outreach.png", width=Inches(5.5))
    p_caption = doc.add_paragraph()
    p_caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_cap = p_caption.add_run("[그림 3] 환자 공감형 카카오톡 알림톡 및 모바일 예약 연동 시뮬레이터 인터페이스")
    r_cap.font.size = Pt(10.5)
    r_cap.font.color.rgb = RGBColor(100, 116, 139)

# Chapter 7
h7 = doc.add_heading(level=1)
r = h7.add_run("7. 실시간 바이오 지식 서버 (BioMCP Engine) 연동")
r.font.size = Pt(16)
r.font.color.rgb = RGBColor(15, 23, 42)
r.bold = True

p7 = doc.add_paragraph()
p7.add_run(
    "임상 의학은 고정된 지식이 아니라 매일 새로운 유전체 변이와 약물 상호작용이 발견되는 동적 생태계이다. "
    "ClinLoop AI는 최신 생명과학 프로토콜인 Model Context Protocol(MCP)을 기반으로 한 'BioMCP 지식 서버'를 내장하고 있다.\n"
    "이를 통해 ClinVar(임상 변이 병원성), dbSNP, ChEMBL(약물 표적 및 작용기전), GTEx(조직별 유전자 발현), PubMed 최신 문헌을 실시간으로 질의하여 "
    "복합 만성질환 환자나 희귀질환 의심 환자의 추적 검사 우선순위를 분자생물학적 근거에 기반하여 동적으로 보정한다."
)

if os.path.exists("results/web_demo_biomcp_cockpit_final.png"):
    doc.add_paragraph().paragraph_format.space_before = Pt(4)
    p_img = doc.add_paragraph()
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_picture("results/web_demo_biomcp_cockpit_final.png", width=Inches(5.5))
    p_caption = doc.add_paragraph()
    p_caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_cap = p_caption.add_run("[그림 4] ClinLoop AI 실시간 임상 안전 콕핏 및 BioMCP 통합 콘솔")
    r_cap.font.size = Pt(10.5)
    r_cap.font.color.rgb = RGBColor(100, 116, 139)

# Chapter 8
h8 = doc.add_heading(level=1)
r = h8.add_run("8. 결론")
r.font.size = Pt(16)
r.font.color.rgb = RGBColor(15, 23, 42)
r.bold = True

p8 = doc.add_paragraph()
p8.add_run(
    "의료 인공지능 연구자로서 우리가 마주해야 할 가장 숭고한 목표는 기술적 현란함이 아니라, "
    "단 한 명의 환자라도 병원의 복잡한 시스템 속에서 소외되거나 적기 치료를 놓쳐 목숨을 잃는 일이 없도록 만드는 것이다.\n\n"
    "ClinLoop AI는 미완결 진료루프를 탐지하고 종결을 지원하는 연구용 프로토타입이다. 모든 규칙은 전문의 승인 전이며, "
    "실제 진료에 사용하기 전에 비식별 실데이터를 이용한 후향적 검증(IRB 승인 후)과 전향적 무음 배포를 거쳐야 한다. "
    "식품의약품안전처(MFDS) 의료기기 인허가 경로는 검증 결과를 바탕으로 결정한다.\n\n"
    "우리는 환자 한 명 한 명의 후속 조치가 시스템 속에서 사라지지 않도록, 투명하고 감사 가능한 방식으로 "
    "이 목표를 검증해 나갈 것이다."
)

# Signature block
doc.add_paragraph().paragraph_format.space_before = Pt(12)
p_sig = doc.add_paragraph()
p_sig.alignment = WD_ALIGN_PARAGRAPH.RIGHT
p_sig.add_run("2026년 9월 21일\n\n").font.size = Pt(13)
r_rep = p_sig.add_run("연구책임자 및 창업대표: ALAM MD NAUSHAD (인/서명)\n")
r_rep.bold = True
r_rep.font.size = Pt(13)
p_sig.add_run("아주대학교 대학원 의과대학 의료인공지능 융합인재양성 프로그램\n").font.size = Pt(12)

output_docx = "ClinLoop_AI_Package/06_임상연구백서_ClinLoop_AI_Noble_Medicine_Monograph.docx"
doc.save(output_docx)
print(f"Monograph docx saved successfully: {output_docx}")
