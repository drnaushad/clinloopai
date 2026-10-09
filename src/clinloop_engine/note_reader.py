"""
note_reader.py — Plans written in clinical notes become tracked follow-ups

Many missed follow-ups are promises written in a note and never ordered:
"Repeat potassium in 1 week", "Refer to cardiology", "CT chest in 3 months",
"6주 후 외래 재방문", "심장내과 협진 의뢰". ClinLoop reads the plan part of a
clinician's note (English and Korean) and turns each concrete plan into an
obligation that closes when the matching event happens:

  kind       closes when                                       rule
  lab        a result of the same test (potassium, HbA1c, …)    R048
  imaging    a study of the same modality covering the region   R049
  referral   a referral or visit to the same specialty          R050
  visit      a follow-up appointment                            R051

What is deliberately NOT tracked (with the reason shown):
  * negated or cancelled plans   "no need to repeat CT", "협진 불필요"
  * conditional plans            "repeat CBC if fever recurs", "필요시 재검"
  * things already done          "CT was repeated", "was referred"
  * history sections             (HPI, past history, 현병력, 과거력)

Every plan carries the exact sentence it came from. Rules only: no model
decides what a note says. An optional on-premise LLM can SUGGEST plans the
rules missed; suggestions are shown to a person and never open a loop.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from .clinical_ontology import radiology_grace_days

DAY = 1.0
WEEK = 7.0
MONTH = 30.44
YEAR = 365.25

# Without a stated interval a plan still has to happen: these defaults are conservative
DEFAULT_DAYS = {"lab": 30.0, "imaging": 90.0, "referral": 30.0, "visit": 30.0}
RULE_FOR = {"lab": "R048", "imaging": "R049", "referral": "R050", "visit": "R051"}

# ── Vocabularies ────────────────────────────────────────────────────────────

ANALYTES: List[Tuple[str, str]] = [
    ("urine_rbc", r"(?:\brbcs?\b|red (?:blood )?cells?|erythrocytes?)\W+(?:\S+\W+){0,3}(?:urine|urinary|sediment)|"
                  r"(?:urine|urinary|sediment)\W+(?:\S+\W+){0,3}(?:\brbcs?\b|red (?:blood )?cells?|erythrocytes?)|"
                  r"13945-1|5821-4|소변\s*적혈구|요\s*적혈구"),
    ("hba1c", r"hb\s?a1c|\ba1c\b|glycated h(?:a)?emoglobin|당화혈색소|4548-4"),
    ("potassium", r"potassium|\bk\+|(?:(?<=check )|(?<=repeat )|(?<=rpt )|(?<=recheck ))k\b|"
                  r"\bk\b(?=\s*(?:level|recheck|in\b|tomorrow|today|next|on\b|q\d))|칼륨|2823-3|6298-4"),
    ("sodium", r"sodium|(?:(?<=check )|(?<=repeat )|(?<=recheck ))na\b|"
               r"\bna\+?\b(?=\s*(?:level|recheck|in\b|tomorrow|next))|나트륨|2951-2"),
    ("magnesium", r"magnesium|(?:(?<=check )|(?<=repeat )|(?<=recheck ))mg\b|\bmg\b(?=\s*(?:level|in\s+\d|tomorrow))|"
                  r"마그네슘|19123-9|2601-3"),
    ("calcium", r"calcium|칼슘|17861-6"),
    ("phosphate", r"phosphate|phosphorus|인산|2777-1"),
    ("creatinine", r"creatinine|renal function|kidney function|\begfr\b|\bbmp\b|\bcmp\b|신기능|크레아티닌|2160-0"),
    ("inr", r"\binr\b|prothrombin time|\bpt/inr\b|6301-6|34714-6"),
    ("tsh", r"\btsh\b|thyroid function|\btfts?\b|갑상선\s*기능|3016-3"),
    ("liver", r"\blfts?\b|liver function|liver enzymes|\balt\b|\bast\b|간기능|간\s*수치|1742-6|1920-8"),
    ("lipids", r"lipid panel|lipids|cholesterol|\bldl\b|지질|콜레스테롤|2093-3|13457-7"),
    ("psa", r"\bpsa\b|prostate[- ]specific antigen|2857-1"),
    ("glucose", r"fasting glucose|blood sugar|glucose|공복\s*혈당|혈당|2345-7|1558-6"),
    ("cbc", r"\bcbc\b|complete blood count|blood count|h(?:a)?emoglobin\b|\bhgb\b|\bhb\b|platelets?|\bwbc\b|white (?:blood )?cell count|leukocytes|"
            r"일반혈액|혈색소|718-7|26515-7|6690-2"),
    ("ferritin", r"ferritin|iron studies|페리틴|2276-4"),
    ("b12", r"\bb12\b|cobalamin|2132-9"),
    ("vitamin_d", r"vitamin d|25-?oh|비타민\s*d|1989-3"),
    ("urinalysis", r"urinalysis|\bua\b|urine test|소변\s*검사|5767-9"),
    ("crp", r"\bcrp\b|c-reactive|1988-5"),
    ("troponin", r"troponin|트로포닌"),
    ("drug_level", r"tacrolimus|cyclosporin|ciclosporin|sirolimus|everolimus|타크로리무스"),
    ("hcv_rna", r"(?:hcv|hepatitis c)\W+(?:\S+\W+){0,3}(?:rna|viral load|pcr|quant\w*)|11011-4|20416-4"),
]
GENERIC_LAB = r"labs?\b|blood ?work|bloods\b|blood tests?|혈액\s*검사|피검사|검사실\s*검사|재검(?:사)?"

MODALITIES: List[Tuple[str, str]] = [
    ("echo", r"echocardiogra\w*|\becho\b|\btte\b|심초음파"),
    ("ct", r"\bct\b|\bcta\b|\bctap\b|computed tomography|\bldct\b|씨티"),
    ("mri", r"\bmri\b|\bmra\b|magnetic resonance|자기공명"),
    ("ultrasound", r"ultrasound|ultrasonograph\w*|\bus\b|\busg\b|sonograph\w*|초음파"),
    ("xray", r"x-?ray|\bcxr\b|radiograph\w*|엑스레이|x선|흉부\s*사진"),
    ("pet", r"\bpet\b|pet-ct|pet/ct"),
    ("mammogram", r"mammogra\w*|유방\s*촬영"),
]
# Follow-up event types that count as each modality
MODALITY_EVENTS = {
    "ct": ["imaging_ct", "followup_ct"], "mri": ["imaging_mri"], "ultrasound": ["imaging_ultrasound", "liver_imaging"],
    "xray": ["imaging_xray"], "pet": ["imaging_pet"], "echo": ["echocardiogram"],
    "mammogram": ["imaging_xray"],
}

SPECIALTIES: List[Tuple[str, str]] = [
    ("cardiology", r"cardiolog\w*|cardiac clinic|heart clinic|심장\s*내과|순환기\s*내과"),
    ("gastroenterology", r"gastroenterolog\w*|\bgi\b(?=\s*(?:clinic|referral|consult|for|team|\.|,|$))|"
                         r"(?:(?<=to )|(?<=with ))gi\b|소화기\s*내과"),
    ("hepatology", r"hepatolog\w*|간\s*클리닉|간\s*내과"),
    ("nephrology", r"nephrolog\w*|renal clinic|신장\s*내과"),
    ("oncology", r"oncolog\w*|종양\s*내과|혈액\s*종양\s*내과"),
    ("hematology", r"h(?:a)?ematolog\w*|혈액\s*내과"),
    ("neurology", r"neurolog\w*|신경과"),
    ("pulmonology", r"pulmonolog\w*|respiratory clinic|chest clinic|호흡기\s*내과"),
    ("endocrinology", r"endocrinolog\w*|diabetes clinic|내분비\s*내과"),
    ("urology", r"urolog\w*|비뇨\s*(?:의학과|기과)"),
    ("dermatology", r"dermatolog\w*|피부과"),
    ("orthopedics", r"orthop(?:a)?edic\w*|\bortho\b|정형외과"),
    ("rheumatology", r"rheumatolog\w*|류마티스\s*내과"),
    ("surgery", r"general surgery|surgical (?:clinic|consult|review)|surgeon|\bsurgery\b|외과"),
    ("gynecology", r"gyn(?:a)?ecolog\w*|\bob/?gyn\b|산부인과"),
    ("ophthalmology", r"ophthalmolog\w*|eye clinic|안과"),
    ("ent", r"\bent\b|otolaryngolog\w*|이비인후과"),
    ("psychiatry", r"psychiatr\w*|mental health|정신\s*건강\s*의학과|정신과"),
    ("infectious_disease", r"infectious disease|\bid\b(?=\s*(?:clinic|consult|referral))|감염\s*내과"),
]


def _first_key(table: List[Tuple[str, str]], text: str) -> Optional[str]:
    for key, rx in table:
        if re.search(rx, text or "", re.I):
            return key
    return None


_SPECIMEN = re.compile(r"\burin\w*|\bstool\b|\bf(?:a)?ec\w*|\bcsf\b|cerebrospinal|pleural|ascit\w*|synovial|"
                       r"소변|분변|뇌척수|흉수|복수", re.I)
SPECIMEN_OWN = {"urine_rbc", "urinalysis"}


def _specimen(text: str) -> Optional[str]:
    m = _SPECIMEN.search(text or "")
    if not m:
        return None
    w = m.group(0).lower()
    return "urine" if w.startswith("urin") or w == "소변" else "stool" if w in ("stool", "분변") or w.startswith("f") \
        else "csf" if w in ("csf", "cerebrospinal", "뇌척수") else "fluid"


def analyte_of(text: str, codes: Optional[List[str]] = None) -> Optional[str]:
    """
    Normalised lab test ('potassium', 'hba1c', …) from a test name or LOINC codes; None if unknown.
    A test on another specimen keeps it ('urine:potassium'), so a urine potassium never closes a blood potassium plan.
    """
    key = _first_key(ANALYTES, " ".join([text or ""] + list(codes or [])))
    spec = _specimen(text)
    if key and spec and key not in SPECIMEN_OWN:
        return f"{spec}:{key}"
    return key


def specialty_of(text: str) -> Optional[str]:
    return _first_key(SPECIALTIES, text or "")


# ── Sections and sentences ──────────────────────────────────────────────────

_PLAN_HEAD = re.compile(r"^\s*(?:#+\s*)?(?:assessment\s*(?:and|&|/)\s*plan|a\s*/\s*p|a&p|plan|recommendations?|"
                        r"계획|치료\s*계획|추적\s*계획|권고)\s*[:：]?\s*", re.I)
# Weak plan headings: read as plan text, but never taken as THE plan section (the plans may be under "Assessment")
_WEAK_HEAD = re.compile(r"^\s*(?:#+\s*)?(?:follow[- ]?up|disposition|추적\s*관찰)\s*[:：]\s*", re.I)
_PLAN_LINE = re.compile(r"^\s*(?:[-•*·]|\d+[.)])?\s*(?:repeat|recheck|re-check|rpt|refer|rtc|f/u|follow[- ]?up|order|"
                        r"schedule|arrange|obtain|check|plan)\b|(?:재검|의뢰|협진|예정|추적|재방문)\s*[.。]?\s*$", re.I)
_HISTORY_HEAD = re.compile(r"^\s*(?:#+\s*)?(?:hpi|history of present illness|history|past (?:medical )?history|pmh|"
                           r"interval history|subjective|현병력|과거력|병력|주호소|chief complaint|cc)\s*[:：]", re.I)
_OTHER_HEAD = re.compile(r"^\s*(?:#+\s*)?(?:objective|exam(?:ination)?|physical exam|vitals?|labs?|results?|"
                         r"medications?|allergies|assessment|impression|진찰\s*소견|검사\s*결과|투약|평가)\s*[:：]", re.I)


def plan_text(note: str) -> Tuple[str, str]:
    """
    The part of the note to read for plans, and how it was chosen.
    With a Plan / A&P section: that section. Otherwise the whole note minus history sections.
    """
    lines = (note or "").splitlines()
    is_plan_head = lambda ln: bool(_PLAN_HEAD.match(ln)) and (":" in ln or "：" in ln or len(ln.strip()) < 30)  # noqa: E731
    if any(is_plan_head(ln) for ln in lines):
        # Every plan section (and follow-up/disposition sections), each up to the next heading of another kind
        out, inside = [], False
        for line in lines:
            if is_plan_head(line) or _WEAK_HEAD.match(line):
                inside = True
                rest = _WEAK_HEAD.sub("", _PLAN_HEAD.sub("", line, count=1), count=1)
                out.append(rest)
                continue
            if _HISTORY_HEAD.match(line) or _OTHER_HEAD.match(line):
                inside = False
            if inside:
                out.append(line)
        return "\n".join(out), "plan section"
    out, skipping = [], False
    for line in lines:
        if _HISTORY_HEAD.match(line):
            skipping = True
            continue
        # A history section ends at the next heading, a blank line, or a line that starts a plan
        if _OTHER_HEAD.match(line) or _WEAK_HEAD.match(line) or not line.strip() or _PLAN_LINE.search(line):
            skipping = False
        if not skipping:
            out.append(_WEAK_HEAD.sub("", line, count=1))
    return "\n".join(out), "whole note (history sections skipped)"


def sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z가-힣0-9(])|\n+|;\s*|(?<=다)\.\s*|^\s*[-•*·]\s+|\s+[-•·]\s+(?=[A-Za-z가-힣])",
                     text or "", flags=re.M)
    out = []
    for p in parts:
        p = re.sub(r"^\s*(?:\d+[.)]|[-•*·])\s*", "", (p or "").strip())
        if len(p) >= 3:
            out.append(p)
    return out


# ── Intervals ───────────────────────────────────────────────────────────────

_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "eight": 8, "ten": 10, "twelve": 12,
              "a": 1, "an": 1, "few": 3, "several": 3, "couple": 2, "a few": 3, "a couple of": 2, "couple of": 2}
_UNIT = {"h": DAY / 24, "hr": DAY / 24, "hrs": DAY / 24, "hour": DAY / 24, "hours": DAY / 24, "시간": DAY / 24,
         "d": DAY, "day": DAY, "days": DAY, "w": WEEK, "wk": WEEK, "wks": WEEK, "week": WEEK, "weeks": WEEK,
         "mo": MONTH, "mos": MONTH, "month": MONTH, "months": MONTH, "y": YEAR, "yr": YEAR, "yrs": YEAR,
         "year": YEAR, "years": YEAR, "일": DAY, "주": WEEK, "주일": WEEK, "개월": MONTH, "달": MONTH, "년": YEAR}
# A number (digits right after a space, start, 'q' or punctuation — never inside a word like "today" or "and"),
# or a number word followed by a full unit word. Single-letter units only directly after digits; never "… ago".
_INTERVAL = re.compile(
    r"(?:(?<=q)|(?<![A-Za-z0-9.]))(?P<n>\d+(?:\.\d+)?)(?:\s*(?:-|–|to|~)\s*(?P<n2>\d+(?:\.\d+)?))?\s*"
    r"(?P<u>hours?|hrs?|days?|weeks?|wks?|months?|mos?|years?|yrs?|시간|개월|주일|주|일|달|년|(?<=\d)[hdwy])(?![A-Za-z])"
    r"|(?<![A-Za-z])(?P<w>a\s+few|a\s+couple\s+of|couple\s+of|one|two|three|four|five|six|eight|ten|twelve|an|a|few|several)"
    r"\s+(?P<u2>hours?|days?|weeks?|months?|years?)\b", re.I)
_AGO = re.compile(r"^\s*(?:ago|before|prior|earlier|전)", re.I)
_LEAD = re.compile(r"^(?:in|within|after|for)\s+", re.I)
_NEXT = re.compile(r"\bnext (week|month|year)\b|다음\s*(주|달)|\btomorrow\b|내일|\bin\s+(?:the\s+)?(?:am|morning)\b|"
                   r"\bnext\s+(?:am|morning)\b|아침", re.I)


def interval_days(s: str) -> Tuple[Optional[float], Optional[str]]:
    """(days, the words it came from), taking the upper bound of a range ('4-6 weeks' → 42)."""
    for m in _INTERVAL.finditer(s):
        if _AGO.match(s[m.end():]):
            continue                              # "3 months ago" / "3개월 전" is history, not a plan
        if m.group("n"):
            n = float(m.group("n"))
            if m.group("n2"):
                n = max(n, float(m.group("n2")))
            u = m.group("u")
        else:
            n = float(_NUM_WORDS.get(re.sub(r"\s+", " ", m.group("w").lower()), 1))
            u = m.group("u2")
        unit = _UNIT.get(u.lower()) or _UNIT.get(u)
        if unit and 0 < n * unit <= 3 * YEAR:
            return round(n * unit, 2 if n * unit < 1 else 1), m.group(0).strip()
    m = _NEXT.search(s)
    if m:
        word = m.group(0).lower()
        days = DAY if (word in ("tomorrow", "내일", "아침") or re.search(r"\b(?:am|morning)\b", word)) else WEEK if ("week" in word or "주" in word) else \
            MONTH if ("month" in word or "달" in word) else YEAR
        return days, m.group(0)
    return None, None


# ── Plan detection ──────────────────────────────────────────────────────────

_FUTURE = re.compile(
    r"\b(?:will|plan(?:ned|s)?\s+(?:to|for)?|to\s+(?:be\s+)?(?:repeat|recheck|check|obtain|order|arrange|schedule|refer|see|have|get)|"
    r"should|needs?|need to|recommend\w*|repeat\w*|rpt|re-?check\w*|check\w*|obtain|order(?:ed)?|request(?:ed)?|arrange[d]?|"
    r"schedul\w*|book(?:ed)?|tomorrow|tonight|in\s+(?:the\s+)?(?:am|morning)|q\d+\s*(?:h|d|wk?s?|mo?s?|y)|"
    r"refer(?:ral)?\b|consult\b|f/u|follow[- ]?up|fu\b|rtc|return(?:\s+to\s+clinic)?|see\s+(?:her|him|them|patient|pt)|"
    r"r/v|review)\b|예정|계획|권고|권유|재검|확인\s*요망|f/u|추적|재방문|의뢰|협진|예약|시행\s*(?:예정|요망)|검사\s*요망|하기로", re.I)
# Cues are judged per clause ("No further imaging needed, repeat CBC in 2 weeks" has two plans).
# English cues may stand anywhere in the clause; Korean verb-final cues (취소, 보류, 시행함) only after the plan.
_NEGATED = re.compile(
    r"\bno\s+(?:need|indication|further|plans?|follow[- ]?up|repeat|referral)\b|\bnot\s+(?:needed|necessary|required|indicated)\b|"
    r"\bwill\s+not\b|\bwon't\b|\bdo(?:es)?\s+not\s+need\b|\bdon't\s+need\b|\bdeclin\w*|\bdecided\s+against\b|\bcancel\w*|"
    r"\bdefer(?:red)?\s+indefinitely\b|\bdiscontinu\w*\s+(?:follow|surveillance)|\bno\s+longer\b|불필요|필요\s*없|하지\s*않|안\s*하기로", re.I)
_NEGATED_AFTER_KO = re.compile(r"취소|보류|중단")
_CONDITIONAL = re.compile(
    r"\bif\b|\bunless\b|\bshould\s+(?:symptoms?|it|pain|fever|he|she|they)\b|\bprn\b|\bas needed\b|\bwhen\s+(?:needed|necessary)\b|"
    r"\bin case\b|필요\s*시|필요하면|악화\s*시|지속\s*시|경우|고려|하면|되면|있으면", re.I)
_CONDITIONAL_BEFORE = re.compile(r"\bconsider\w*\b|\bmay\b|\bmight\b|\bpossibly\b|\bperhaps\b", re.I)
_SOONER = re.compile(r"(?:,?\s*(?:or\s+)?(?:sooner|earlier)(?:\s+(?:if|as)\b[^,;]*)?)", re.I)
_DONE = re.compile(
    r"\b(?:was|were|has been|have been|had)\s+(?:\w+\s+)?(?:repeated|rechecked|checked|done|performed|obtained|referred|seen|completed)\b|"
    r"\balready\s+(?:been\s+)?(?:done|completed|performed|repeated|rechecked|obtained|seen)\b|\b(?:done|completed|performed) on\b", re.I)
_DONE_AFTER_KO = re.compile(r"시행함|시행하였|시행\s*완료|완료|했음|하였음|이미\s*시행")
_CLAUSE = re.compile(r",\s*|\s+but\s+|\s+however\s+|\s+although\s+|，")


def _clause(s: str, at: int, previous: bool = False):
    """The clause of s that contains position `at`, and `at` relative to it (parentheses blanked out)."""
    plain = re.sub(r"\([^)]*\)", lambda m: " " * len(m.group(0)), s)
    start, prev = 0, ""
    for m in _CLAUSE.finditer(plain):
        if m.start() >= at:
            return (plain[start:m.start()], at - start, prev) if previous else (plain[start:m.start()], at - start)
        prev = plain[start:m.start()]
        start = m.end()
    return (plain[start:], at - start, prev) if previous else (plain[start:], at - start)


_IF_CLAUSE = re.compile(r"^\s*(?:if|unless|should|in case|when(?:ever)?|만약|만일)\b|(?:면|시|경우)\s*$", re.I)


def _reason(s: str, at: int) -> Optional[str]:
    """Why the plan at position `at` is not tracked, or None."""
    c, pos, prev = _clause(s, at, previous=True)
    if _IF_CLAUSE.search(prev):                   # "If fever recurs, repeat CBC"
        return "conditional: only if something happens"
    c = _SOONER.sub(" ", c) if _SOONER.search(c) and re.search(r"sooner|earlier", c, re.I) else c
    after = c[pos:]
    if _NEGATED.search(c) or _NEGATED_AFTER_KO.search(after):
        return "negated or cancelled"
    if _DONE.search(c) or _DONE_AFTER_KO.search(after):
        return "already done (past tense)"
    if _CONDITIONAL.search(c) or _CONDITIONAL_BEFORE.search(c[:pos]):
        return "conditional: only if something happens"
    return None
_VISIT = re.compile(
    r"follow[- ]?up\s+(?:visit|appointment|in\s+(?:the\s+)?clinic|with\s+(?:me|us|pcp|gp|primary care)|in\s+\d)|"
    r"\bf/u\s+(?:in\s+)?\d|\bfu\s+(?:in\s+)?\d|\brtc\b|return\s+(?:to\s+(?:the\s+)?clinic|visit|in\s+\d)|"
    r"see\s+(?:her|him|them|the patient|patient|pt)\s+(?:again|back)|next\s+(?:visit|appointment)|clinic\s+review|"
    r"외래\s*(?:재방문|추적|예약|f/u|방문)|재방문|다음\s*외래|외래에서\s*(?:확인|추적)|추적\s*관찰\s*외래", re.I)
_VISIT_WITH = re.compile(r"(?:f/u|fu|follow[- ]?up|see)\s+(?:with|in|at)\s+(?:the\s+)?[A-Za-z가-힣/ ]{2,30}?"
                         r"(?=\s+(?:in|within|clinic|after|on)\b|[,.;]|$)", re.I)
_ABBREV = [(re.compile(r"\bc/?a/?p\b", re.I), "chest abdomen pelvis"), (re.compile(r"\bctap\b", re.I), "CT abdomen pelvis"),
           (re.compile(r"(?<=ct )a/?p\b|(?<=ct )abd/pelvis\b", re.I), "abdomen pelvis"),
           (re.compile(r"\babd\b", re.I), "abdomen"), (re.compile(r"\bhead/neck\b", re.I), "head neck")]


def _expand_abbrev(s: str) -> str:
    for rx, full in _ABBREV:
        s = rx.sub(full, s)
    return s


_REFERRAL = re.compile(r"refer(?:ral|red)?\s+(?:to|for)?|consult(?:ation)?\b|\bto\s+see\b|의뢰|협진|진료\s*요청|전원", re.I)


def _plan(kind: str, target: Optional[str], s: str, extra: Optional[Dict[str, Any]] = None,
          at: int = 0) -> Dict[str, Any]:
    # The interval nearest after the plan's own words ("labs in 4-6 weeks and RTC 3 months"), else anywhere
    clause, pos = _clause(s, at)
    days, words = interval_days(clause[pos:])
    if days is None:
        days, words = interval_days(clause)
    if days is None:
        days, words = interval_days(s[at:])
    stated = days is not None
    if not stated:
        days = DEFAULT_DAYS[kind]
    due = round(days + (radiology_grace_days(days) if kind == "imaging" else max(3.0, 0.15 * days)), 1)
    plan = {"kind": kind, "target": target, "interval_days": days, "interval_stated": stated,
            "interval_text": words, "due_days": due, "rule_id": RULE_FOR[kind], "evidence": s.strip()[:300],
            "tracked": True, "reason": None, "_at": at}
    plan.update(extra or {})
    return plan


def find_plans(note: str) -> Dict[str, Any]:
    """All plans in one note: tracked ones, and ones deliberately not tracked with the reason."""
    from .radiology import regions_in
    text, source = plan_text(note)
    plans: List[Dict[str, Any]] = []
    for s in sentences(text):
        if not (_FUTURE.search(s) or interval_days(s)[0] or _VISIT.search(s) or _CONDITIONAL.search(s)
                or _NEGATED.search(s) or _NEGATED_AFTER_KO.search(s) or _DONE.search(s)):
            continue
        found: List[Dict[str, Any]] = []
        ref = _REFERRAL.search(s)
        spec = specialty_of(s) if ref else None
        if spec:
            found.append(_plan("referral", spec, s, at=ref.start()))
        visit_with = _VISIT_WITH.search(s)
        if visit_with and not spec and specialty_of(visit_with.group(0)):   # "f/u with cardiology in 3 months"
            spec = specialty_of(visit_with.group(0))
            found.append(_plan("visit", spec, s, at=visit_with.start()))
        modality = _first_key(MODALITIES, s)
        if modality:
            regions = sorted(regions_in(_expand_abbrev(s)))
            mpos = re.search(dict(MODALITIES)[modality], s, re.I).start()
            if modality == "mammogram" and not regions:
                regions = ["breast"]
            found.append(_plan("imaging", modality, s, {"regions": regions}, at=mpos))
        analytes = [(k, m.start()) for k, rx in ANALYTES for m in [re.search(rx, s, re.I)] if m]
        if modality:          # "CT" sentences mention contrast/creatinine incidentally: only explicit lab verbs count
            analytes = [a for a in analytes if re.search(r"\b(?:repeat|recheck|check|labs?)\b|재검|혈액", s, re.I)]
        for a, pos in analytes:
            spec_word = _specimen(s[max(0, pos - 20):pos + 30])
            found.append(_plan("lab", f"{spec_word}:{a}" if spec_word and a not in SPECIMEN_OWN else a, s, at=pos))
        generic = re.search(GENERIC_LAB, s, re.I)
        if not analytes and not modality and generic and re.search(
                r"\b(?:repeat|rpt|recheck|check|obtain|draw|order(?:ed)?)\b|\bq\d|재검|검사\s*(?:예정|요망)|f/u|추적", s, re.I):
            found.append(_plan("lab", None, s, at=generic.start()))
        visit = _VISIT.search(s)
        if visit and not spec and not (modality and visit.start() < mpos):
            found.append(_plan("visit", None, s, at=visit.start()))
        if not found:
            continue
        for p in found:
            reason = _reason(s, p.pop("_at"))
            if reason:
                p.update(tracked=False, reason=reason)
            plans.append(p)
    # One plan per kind and target (the first statement wins; repeats add nothing)
    seen, unique = set(), []
    for p in plans:
        k = (p["kind"], p["target"], tuple(p.get("regions") or []), p["tracked"])
        if k not in seen:
            seen.add(k)
            unique.append(p)
    return {"source": source, "plans": unique,
            "tracked": sum(1 for p in unique if p["tracked"]), "not_tracked": sum(1 for p in unique if not p["tracked"])}


_TARGET_NAMES = {"ct": "CT", "mri": "MRI", "pet": "PET", "xray": "X-ray", "echo": "echocardiogram", "hba1c": "HbA1c",
                 "inr": "INR", "tsh": "TSH", "psa": "PSA", "cbc": "CBC", "crp": "CRP", "b12": "vitamin B12",
                 "liver": "liver function tests", "hcv_rna": "HCV RNA", "ent": "ENT",
                 "ultrasound": "Ultrasound", "mammogram": "Mammogram"}


def plan_label(p: Dict[str, Any]) -> str:
    raw = p.get("target") or {"lab": "labs", "visit": "follow-up visit"}.get(p["kind"], p["kind"])
    spec, _, base = raw.rpartition(":")
    target = ((spec + " ") if spec else "") + _TARGET_NAMES.get(base, base.replace("_", " "))
    where = f" {', '.join(p['regions'])}" if p.get("regions") else ""
    words = p.get("interval_text")
    when = (" (no interval stated)" if not words else
            f" ({words})" if re.search(r"[가-힣]", words) else
            f" in {words}" if re.match(r"\d|(?:a|an|one|two|three|four|five|six|eight|ten|twelve|few|several|couple)\b", words, re.I)
            else f" {words}")
    noun = {"lab": "Repeat", "imaging": "", "referral": "Referral to", "visit": "Follow-up visit"}[p["kind"]]
    if p["kind"] == "visit":
        return f"{noun}{(' with ' + target) if p.get('target') else ''}{when}"
    return f"{noun} {target}{where}{when}".strip()


# ── Optional: an on-premise LLM suggests plans the rules missed (never opens a loop) ──

def llm_suggestions(note: str, found: List[Dict[str, Any]], names: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Ask the hospital's local LLM (Ollama) which follow-up plans the note contains, and return
    those the rules did not find, for a person to review. The note is de-identified first; the
    model never decides anything: its suggestions are shown, not filed.
    """
    import json as _json
    from .document_reader import scrub_identifiers
    from .local_llm_engine import generate_clinical_text
    text = scrub_identifiers(plan_text(note)[0], names)[:4000]
    prompt = ("List every concrete follow-up the clinician plans in this note (tests to repeat, imaging, referrals, "
              "follow-up visits). Ignore plans that are conditional, cancelled or already done. Answer with JSON only: "
              '{"plans": [{"kind": "lab|imaging|referral|visit", "target": "...", "interval": "...", "quote": "exact words"}]}'
              "\n\nNOTE:\n" + text)
    out = generate_clinical_text(prompt, temperature=0.0, max_tokens=500,
                                 system_prompt="You extract follow-up plans from clinical notes. Quote the note exactly. "
                                               "Never invent plans that are not written.")
    if out.get("error") or not out.get("text"):
        return {"available": False, "reason": out.get("error") or "no answer", "suggestions": []}
    from .imaging_ai import _json_object
    parsed = _json_object(out["text"])
    have = {(p["kind"], p.get("target")) for p in found}
    suggestions = []
    for p in parsed.get("plans") or []:
        if not isinstance(p, dict) or p.get("kind") not in RULE_FOR:
            continue
        quote = str(p.get("quote") or "").strip()
        if not quote or quote.lower() not in text.lower():
            continue                          # a suggestion must quote the note: no invented plans
        target = (analyte_of(str(p.get("target"))) if p["kind"] == "lab" else
                  _first_key(MODALITIES, str(p.get("target"))) if p["kind"] == "imaging" else
                  specialty_of(str(p.get("target"))) if p["kind"] == "referral" else None)
        if (p["kind"], target) in have:
            continue
        suggestions.append({"kind": p["kind"], "target": target or p.get("target"), "interval": p.get("interval"),
                            "quote": quote[:300]})
    return {"available": True, "model": out.get("model"), "suggestions": suggestions,
            "note": "AI suggestions for review: not tracked unless a person adds them to the plan"}
