"""
basis.py — Why a loop exists, in plain words a clinician can check against the record

Non-device clinical decision support rests on one condition (REGULATORY_ASSESSMENT.md §2, criterion 4):
the professional can independently review the basis of what the software shows, so they need not rely
on it. The evidence chain and the risk-score breakdown are complete but written for engineers. This
module states the same facts the way a clinician reads a chart:

    Finding    what started it, with the value or the report's own sentence, and when
    Rule       which rule, what it expects, and by when
    Reasoning  how the deadline or the obligation was worked out (e.g. the Fleischner category)
    Found      which follow-up the record holds so far, or that none is recorded
    Reference  the guideline the rule cites

Only facts already in the record and the rule are used: nothing is inferred or scored here.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

_EVENT_NAMES = {
    "lab_result": "lab result", "radiology_report": "radiology report", "pathology_result": "pathology result",
    "culture_result": "culture result", "medication_change": "medication change", "discharge": "discharge",
    "specialist_referral": "referral", "clinical_note_plan": "plan in a clinical note", "ecg": "ECG",
    "echocardiogram": "echocardiogram", "diagnosis": "diagnosis", "diagnostic_pattern": "pattern across results",
    "colonoscopy_finding": "colonoscopy finding", "liver_imaging": "liver imaging",
}
# Follow-up steps as clinicians say them (also used for the EHR cards, cds_hooks.py)
FOLLOWUP_NAMES = {
    "critical_value_notification": "documented call to the treating clinician",
    "followup_ct": "follow-up CT", "followup_lab": "monitoring lab", "followup_appointment": "clinic visit",
    "referral_visit": "specialist visit", "specialist_referral": "specialist referral", "bp_check": "blood-pressure check",
    "inr_recheck": "INR recheck", "hba1c_recheck": "HbA1c recheck", "hcv_rna_test": "HCV RNA test",
    "imaging_ct": "CT", "imaging_mri": "MRI", "imaging_ultrasound": "ultrasound", "imaging_xray": "X-ray",
    "imaging_pet": "PET-CT", "lab_result": "repeat test", "culture_result": "repeat culture",
    "patient_notification": "patient notified", "provider_review": "clinician review",
    "colonoscopy": "colonoscopy", "breast_biopsy": "breast biopsy", "biopsy_order": "biopsy order",
    "biopsy_result": "biopsy result", "colposcopy_referral": "colposcopy referral", "colposcopy_visit": "colposcopy visit",
    "endoscopic_ultrasound": "endoscopic ultrasound", "echocardiogram": "echocardiogram", "liver_imaging": "liver imaging",
    "mental_health_followup": "mental-health follow-up", "postpartum_glucose_test": "postpartum glucose test",
    "hbv_dna_test": "HBV DNA test", "hiv_supplemental_test": "HIV supplemental test", "callback": "patient callback",
    "imaging_order": "imaging order", "ecg": "ECG", "pathology_result": "pathology result",
    "medication_change": "medication adjustment", "ai_finding_reviewed": "AI finding reviewed",
}
_QUOTE_KEYS = ("evidence_span", "plan_text", "conclusion", "interpretation")
_MAX_QUOTE = 240


def _name(event_type: str) -> str:
    return _EVENT_NAMES.get(event_type, event_type.replace("_", " "))


def _step(event_type: str) -> str:
    return FOLLOWUP_NAMES.get(event_type, event_type.replace("_", " "))


def _when(ts: Optional[datetime]) -> str:
    return ts.strftime("%Y-%m-%d %H:%M") if ts else "unknown time"


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _MAX_QUOTE else text[:_MAX_QUOTE].rsplit(" ", 1)[0] + " …"


def _quote(details: Dict[str, Any]) -> Optional[str]:
    """The record's own words. The evidence span is a character window and can start or end inside a
    word ('…grade dysplasia' for 'High-grade dysplasia', '…mm adrenal nodule' without its size), which
    can change the meaning. When the span comes from the report text, the whole sentence(s) around it
    are quoted instead."""
    from .report_text import sentence
    span = details.get("evidence_span")
    for key in ("conclusion", "plan_text", "interpretation"):
        text = details.get(key)
        if isinstance(span, str) and span.strip() and isinstance(text, str):
            at = text.find(span.strip())
            if at >= 0:
                return _short(sentence(text, at, at + len(span.strip())).strip(" ;."))
    for key in _QUOTE_KEYS:
        text = details.get(key)
        if isinstance(text, str) and text.strip():
            return _short(text)
    return None


def _value(details: Dict[str, Any]) -> Optional[str]:
    value = details.get("value")
    if value is None or isinstance(value, (dict, list)):
        return None
    test = details.get("analyte") or details.get("test") or "result"
    unit = details.get("unit") or ""
    flag = details.get("flag")
    text = f"{test} {value}{(' ' + unit) if unit else ''}"
    return text + (f" (flagged {str(flag).lower()})" if flag else "")


def _what(event_type: str, details: Dict[str, Any]) -> str:
    for key in ("report", "test", "medication", "drug", "diagnosis", "primary_diagnosis", "order", "specialty",
                "organism", "specimen"):
        v = details.get(key)
        if isinstance(v, str) and v.strip():
            return f"{_name(event_type)}: {v.strip().replace('_', ' ')}"
    return _name(event_type)


def _reasoning(details: Dict[str, Any]) -> List[str]:
    """The mapping notes that explain a decision; plain resource-type routing ('Observation→lab_result')
    is technical detail and left out."""
    out = []
    for line in details.get("mapping") or []:
        if not isinstance(line, str) or "code/text" in line:
            continue
        head, _, tail = (part.strip() for part in line.partition("→"))
        if tail and (re.fullmatch(r"[a-z_]+", tail)
                     or re.fullmatch(r"[A-Z][A-Za-z]*(\([^)]*\))?( (start|end))?", head)):
            continue       # routing to an event type: "Observation→lab_result", "Encounter(IMP) end→discharge"
        out.append(line)
    return out


# Korean (the hospital's language). Clinical terms that Korean staff use in English (CT, INR, PET-CT)
# stay in English; quotes stay in the record's own language.
_EVENT_NAMES_KO = {
    "lab_result": "검사 결과", "radiology_report": "영상 판독", "pathology_result": "병리 결과",
    "culture_result": "배양 결과", "medication_change": "약물 변경", "discharge": "퇴원",
    "specialist_referral": "전문의 의뢰", "clinical_note_plan": "진료 기록의 계획", "ecg": "심전도",
    "echocardiogram": "심장초음파", "diagnosis": "진단", "diagnostic_pattern": "여러 결과에 걸친 패턴",
    "colonoscopy_finding": "대장내시경 소견", "liver_imaging": "간 영상검사",
}
FOLLOWUP_NAMES_KO = {
    "critical_value_notification": "담당 의료진 통보 기록", "followup_ct": "추적 CT", "followup_lab": "모니터링 검사",
    "followup_appointment": "외래 방문", "referral_visit": "전문과 진료", "specialist_referral": "전문의 의뢰",
    "bp_check": "혈압 확인", "inr_recheck": "INR 재검", "hba1c_recheck": "HbA1c 재검", "hcv_rna_test": "HCV RNA 검사",
    "hbv_dna_test": "HBV DNA 검사", "hiv_supplemental_test": "HIV 확인 검사", "imaging_ct": "CT", "imaging_mri": "MRI",
    "imaging_ultrasound": "초음파", "imaging_xray": "X선 촬영", "imaging_pet": "PET-CT", "imaging_order": "영상검사 오더",
    "lab_result": "재검사", "culture_result": "배양 재검", "patient_notification": "환자 통보",
    "provider_review": "의료진 검토", "biopsy_order": "조직검사 오더", "biopsy_result": "조직검사 결과",
    "breast_biopsy": "유방 조직검사", "callback": "환자 연락", "colonoscopy": "대장내시경",
    "colposcopy_referral": "질확대경검사 의뢰", "colposcopy_visit": "질확대경검사", "ecg": "심전도",
    "echocardiogram": "심장초음파", "endoscopic_ultrasound": "내시경 초음파", "liver_imaging": "간 영상검사",
    "pathology_result": "병리 결과", "medication_change": "약물 조정", "mental_health_followup": "정신건강 추적 진료",
    "postpartum_glucose_test": "산후 혈당 검사", "ai_finding_reviewed": "AI 소견 검토",
}
_FLAG_KO = {"critical": "위급", "high": "높음", "low": "낮음", "abnormal": "비정상", "positive": "양성"}


def _window_ko(days: float) -> str:
    if days < 1:
        return f"{round(days * 24)}시간"
    return f"{int(days) if days >= 2 else round(days, 1):g}일"


def _deadline_note_ko(line: str) -> str:
    """Translate the new deadline provenance notes, retaining source quotes elsewhere."""
    if line == "Deadline source: report-stated interval; no scheduling grace added":
        return "기한 출처: 판독문에 명시된 간격이며 추가 유예 기간을 더하지 않음"
    if line.startswith("Deadline source: proposed default or guideline interval"):
        return "기한 출처: 제안된 기본값 또는 지침 간격이며 판독문에 명시된 기한이 아님. 의료진 검토 필요"
    match = re.fullmatch(r"Report interval: ([\d.]+) calendar months; due ([\d-]+) without scheduling grace", line)
    if match:
        return f"판독문 간격: 달력 기준 {match[1]}개월, 기한 {match[2]}, 추가 유예 기간 없음"
    if line in {"same three-month nodule follow-up: earlier report or rule deadline retained",
                "alternative nodule follow-up: earlier report or rule deadline retained"}:
        return "동일 폐결절 추적: 판독문 또는 규칙 중 더 이른 기한을 유지하고 허용된 대체 조치를 보존함"
    match = re.fullmatch(r"Lung-RADS interval: (\d+) calendar months; no scheduling grace added", line)
    if match:
        return f"Lung-RADS 간격: 달력 기준 {match[1]}개월, 추가 유예 기간 없음"
    return line


def build_ko(trigger, rule, deadline: Optional[datetime], deadline_days: float, followups, status: str,
             expected: List[str], logic: str) -> List[str]:
    """The same basis in Korean, built from the same facts as build()."""
    from .clinical_ontology import RULE_NAMES_KO
    details = trigger.details or {}
    step = lambda t: FOLLOWUP_NAMES_KO.get(t, t.replace("_", " "))  # noqa: E731
    lines = []
    value = details.get("value")
    if value is not None and not isinstance(value, (dict, list)):
        test = details.get("analyte") or details.get("test") or "결과"
        unit = details.get("unit") or ""
        flag = details.get("flag")
        finding = f"{test} {value}{(' ' + unit) if unit else ''}"
        if flag:
            finding += f" ({_FLAG_KO.get(str(flag).lower(), str(flag).lower())})"
    else:
        name = _EVENT_NAMES_KO.get(trigger.event_type, _name(trigger.event_type))
        what = next((str(details[k]).strip().replace("_", " ") for k in
                     ("report", "test", "medication", "drug", "diagnosis", "primary_diagnosis", "order", "specialty",
                      "organism", "specimen") if isinstance(details.get(k), str) and details[k].strip()), None)
        finding = f"{name}: {what}" if what else name
    lines.append(f"소견: {finding}, {_when(trigger.timestamp)}.")
    quote = _quote(details)
    if quote:
        lines.append(f"기록 원문: \u201c{quote}\u201d")
    joiner = " 또는 " if logic == "any" else " 및 "
    wanted = joiner.join(step(t) for t in expected) or "후속 조치"
    long_window = bool(deadline and trigger.timestamp and (deadline - trigger.timestamp).days >= 2)
    by = deadline.strftime("%Y-%m-%d") if long_window else _when(deadline)
    name_ko = RULE_NAMES_KO.get(rule.rule_id, rule.name)
    lines.append(f"규칙 {rule.rule_id} ({name_ko}): {by}까지 {wanted} 필요 ({_window_ko(deadline_days)}).")
    if rule.rule_id == "R005":
        lines.append("30일은 제안된 기관별 추적 목표이며 ASCCP의 일률적인 기한이 아닙니다. HPV, 나이, 임신 여부 및 검사 이력을 확인하여 의료진이 후속 계획을 결정해야 합니다.")
    for line in _reasoning(details):
        lines.append(f"판단 근거: {_deadline_note_ko(line)}.")
    if followups:
        found = "; ".join(f"{step(f.event_type)} ({_when(f.timestamp)})" for f in followups)
        lines.append(f"기록에서 확인: {found}.")
    else:
        lines.append("기록에서 확인: 아직 해당 후속 조치 없음.")
    if followups and logic != "any" and status != "closed":
        done = {f.event_type for f in followups}
        missing = [t for t in expected if t not in done]
        if missing:
            lines.append(f"아직 없음: {', '.join(step(t) for t in missing)}.")
    if status == "delayed":
        lines.append("후속 조치가 기한 이후에 이루어졌습니다.")
    if any(f.event_type in {"biopsy_order", "imaging_order", "lab_order", "specialist_referral", "colposcopy_referral"} for f in followups):
        lines.append("주문·의뢰 근거: 오더 또는 의뢰가 기록되었습니다. 실제 검사·시술 시행이나 결과 검토를 입증하지 않습니다.")
    if status in ("closed", "delayed"):
        lines.append("완료 범위: 이 규칙이 추적하는 조치만 확인되었습니다. 의뢰나 검사 처방만으로 진료·치료 전체의 완료를 입증하지 않습니다.")
    refs = [r for r in (rule.references or []) if isinstance(r, str) and r.strip()]
    if refs:
        lines.append(f"참고 문헌: {refs[0]}")
    return lines


REVIEW_SPARSE_KO = ("의료진 검토 필요: ClinLoop이 볼 수 있는 기록만으로는 이 후속 조치가 이루어졌는지 판단할 수 없습니다. "
                    "차트를 확인하세요.")


def build(trigger, rule, deadline: Optional[datetime], window: str, followups, status: str,
          expected: List[str], logic: str) -> List[str]:
    """Plain-language basis for one loop. ``trigger`` and ``followups`` are graph nodes (event_type,
    timestamp, details, status); ``expected`` the follow-up types the rule asks for."""
    details = trigger.details or {}
    lines = []
    finding = _value(details) or _what(trigger.event_type, details)
    lines.append(f"Finding: {finding}, {_when(trigger.timestamp)}.")
    quote = _quote(details)
    if quote:
        lines.append(f"The record says: “{quote}”")
    joiner = " or " if logic == "any" else " and "
    wanted = joiner.join(_step(t) for t in expected) or "follow-up"
    # A clock time on a deadline weeks away is false precision: the date is what matters
    long_window = bool(deadline and trigger.timestamp and (deadline - trigger.timestamp).days >= 2)
    by = deadline.strftime("%Y-%m-%d") if long_window else _when(deadline)
    lines.append(f"Rule {rule.rule_id} ({rule.name}) expects: {wanted} by {by} ({window}).")
    if rule.rule_id == "R005":
        lines.append(rule.evidence_note)
    for line in _reasoning(details):
        lines.append(f"How this was worked out: {line}.")
    if followups:
        found = "; ".join(f"{_step(f.event_type)} on {_when(f.timestamp)}" for f in followups)
        lines.append(f"Found in the record: {found}.")
    else:
        lines.append("Found in the record: no matching follow-up yet.")
    if followups and logic != "any" and status != "closed":
        done = {f.event_type for f in followups}
        missing = [t for t in expected if t not in done]
        if missing:                 # e.g. patient told, but no referral yet: say which part is outstanding
            lines.append(f"Still missing: {', '.join(_step(t) for t in missing)}.")
    if status == "delayed":
        lines.append("The follow-up came after the deadline.")
    if any(f.event_type in {"biopsy_order", "imaging_order", "lab_order", "specialist_referral", "colposcopy_referral"} for f in followups):
        lines.append("Order/referral evidence only: a request was recorded; performance of care and review of its result are not established.")
    if status in ("closed", "delayed"):
        lines.append("Completion scope: only the step(s) tracked by this rule are established. A referral or order does not prove that the visit, procedure or overall care was completed.")
    refs = [r for r in (rule.references or []) if isinstance(r, str) and r.strip()]
    if refs:
        lines.append(f"Reference: {refs[0]}")
    return lines
