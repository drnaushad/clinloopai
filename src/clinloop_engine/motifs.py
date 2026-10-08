"""
motifs.py — Diagnostic patterns: dangerous combinations whose next step never happened

Some dangers are visible only across several events. No single result is
alarming, but together they call for a work-up that is easy to miss. Each
pattern is a small graph motif over one patient's events, evaluated at the
moment it became complete (only events up to then count):

  R052  Iron-deficiency anaemia (low haemoglobin + low ferritin within 90 days)
        in a man ≥ 18 or a woman ≥ 50 → GI investigation (colonoscopy or GI
        referral); 14 days at age ≥ 60 (suspected-cancer pathway), else 60 days.
        BSG 2021; NICE NG12.
  R053  Creatinine ≥ 1.5 × baseline (lowest in the previous 7 days, else the
        median of 8–365 days) and ≥ 0.3 mg/dL higher → repeat creatinine within
        3 days. KDIGO 2012 AKI; NICE NG148 AKI algorithm.
  R054  Atrial fibrillation with CHA₂DS₂-VASc ≥ 2 (men) / ≥ 3 (women), computed
        from the problem list and age, and no anticoagulant → anticoagulation
        decision within 30 days. ESC 2020 AF guideline.
  R055  Microscopic haematuria (≥ 3 RBC/hpf) on two tests within 12 months at
        age ≥ 35 → urology referral or CT urography within 90 days. AUA/SUFU 2020.

Every pattern lists the events it was built from (shown on the patient graph),
is skipped when the next step already happened (with the reason), and fires at
most once a year per patient. Like every rule, these start in shadow mode
until a specialist signs them off.
"""

import re
import statistics
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .clinical_ontology import EventType, is_fulfilling_status
from .safety_clock import normalize_timestamp

ANTICOAGULANT_NAMES = re.compile(
    r"warfarin|coumadin|apixaban|eliquis|rivaroxaban|xarelto|edoxaban|lixiana|savaysa|dabigatran|pradaxa|"
    r"와파린|아픽사반|엘리퀴스|리바록사반|자렐토|에독사반|릭시아나|다비가트란|프라닥사", re.I)

_AF = re.compile(r"atrial fibrillation|atrial flutter|\baf(?:ib)?\b|심방\s*세동|심방\s*조동", re.I)
_CHA2DS2 = [  # (points, ICD-10 prefixes, text)
    ("chf", 1, ("I50", "I11.0", "I13.0", "I13.2"), r"heart failure|cardiomyopathy|lvef|심부전"),
    ("hypertension", 1, ("I10", "I11", "I12", "I13", "I15"), r"hypertension|고혈압"),
    ("diabetes", 1, ("E10", "E11", "E13", "E14"), r"diabet|당뇨"),
    ("stroke_tia", 2, ("I63", "I64", "G45", "I69.3", "Z86.73"), r"stroke|cerebral infarct|\btia\b|transient ischaemic|"
                                                               r"transient ischemic|뇌경색|뇌졸중|일과성\s*허혈"),
    ("vascular", 1, ("I21", "I22", "I25.2", "I70", "I73.9"), r"myocardial infarction|peripheral arter|aortic plaque|"
                                                            r"심근경색|말초\s*동맥"),
]

ONCE_PER = timedelta(days=365)


def _t(e: Dict[str, Any]) -> datetime:
    return normalize_timestamp(e["timestamp"])


def _num(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _age(ctx: Dict[str, Any], when: datetime) -> Optional[float]:
    b = ctx.get("birth_date")
    return (when - b).days / 365.25 if b else None


def _derived(anchor: Dict[str, Any], name: str, condition: str, rule: str, days: float, evidence: List[Dict[str, Any]],
             summary: str, mapping: List[str], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    d = {"condition": condition, "pattern": name, "rule_deadline_days": {rule: days},
         "evidence_events": [e["event_id"] for e in evidence], "evidence_span": summary, "mapping": mapping}
    d.update(extra or {})
    return {"event_id": f"pattern:{name}:{anchor['event_id']}", "patient_id": anchor["patient_id"],
            "event_type": EventType.DIAGNOSTIC_PATTERN.value, "timestamp": anchor["timestamp"],
            "status": "completed", "source": anchor.get("source"), "details": d}


def _labs(events: List[Dict[str, Any]], analyte: str) -> List[Dict[str, Any]]:
    return sorted((e for e in events if e["event_type"] == EventType.LAB_RESULT.value
                   and (e["details"] or {}).get("analyte") == analyte and is_fulfilling_status(e.get("status"))
                   and _num((e["details"] or {}).get("value")) is not None), key=_t)


# ── R052 iron-deficiency anaemia ────────────────────────────────────────────

def _hb_low(e: Dict[str, Any], sex: Optional[str]) -> bool:
    d = e["details"]
    if not re.search(r"h(?:a)?emoglobin(?!\s*a1c)|\bhgb\b|\bhb\b(?!\s*a1c)|718-7|혈색소", (d.get("test") or "") + " "
                     + " ".join(d.get("loinc") or []), re.I) or re.search(r"a1c|glyc|stool|urine|분변", d.get("test") or "", re.I):
        return False
    v = _num(d.get("value"))
    unit = str(d.get("unit") or "").lower()
    if unit in ("g/l",):
        v = v / 10.0
    limit = 13.0 if sex == "male" else 12.0           # WHO anaemia thresholds (g/dL)
    return v < limit or d.get("flag") in ("LOW", "CRITICAL")


def _ferritin_low(e: Dict[str, Any]) -> bool:
    v = _num(e["details"].get("value"))
    return v < 30.0 or e["details"].get("flag") == "LOW"   # ng/mL = µg/L; BSG 2021


def pattern_ida(events: List[Dict[str, Any]], ctx: Dict[str, Any], out: List[Dict[str, Any]]) -> None:
    sex = ctx.get("sex")
    hbs = [e for e in _labs(events, "cbc") if _hb_low(e, sex)]
    ferr = [e for e in _labs(events, "ferritin") if _ferritin_low(e)]
    last: Optional[datetime] = None
    for f in ferr:
        for h in hbs:
            if abs((_t(h) - _t(f)).days) > 90:
                continue
            anchor = h if _t(h) >= _t(f) else f
            when = _t(anchor)
            if last and when - last < ONCE_PER:
                continue
            age = _age(ctx, when)
            if age is None or sex not in ("male", "female") or (sex == "male" and age < 18) or (sex == "female" and age < 50):
                continue      # premenopausal women: menstrual loss is the usual cause; men ≥ 18 and women ≥ 50 per BSG
            done = [e for e in events if when - timedelta(days=365) <= _t(e) <= when
                    and (e["event_type"] == EventType.COLONOSCOPY.value
                         or ((e["details"] or {}).get("specialty") == "gastroenterology"
                             and e["event_type"] in (EventType.SPECIALIST_REFERRAL.value, EventType.REFERRAL_VISIT.value)))]
            if done:
                continue
            days = 14.0 if age >= 60 else 60.0
            hb, fe = h["details"], f["details"]
            out.append(_derived(anchor, "ida", "pattern_ida", "R052", days, [h, f],
                                f"Haemoglobin {hb.get('value')} {hb.get('unit') or ''} ({_t(h).date()}) and ferritin "
                                f"{fe.get('value')} {fe.get('unit') or ''} ({_t(f).date()}): iron-deficiency anaemia, "
                                f"{sex}, age {age:.0f}",
                                [f"pattern: iron-deficiency anaemia (Hb + ferritin within 90 days), {sex} age {age:.0f} "
                                 f"→ GI investigation within {days:g} days" + (" (age ≥ 60: suspected-cancer pathway)" if age >= 60 else "")],
                                {"followup_match": {"R052": {"specialty": "gastroenterology",
                                                             "_only_for": [EventType.SPECIALIST_REFERRAL.value,
                                                                           EventType.REFERRAL_VISIT.value]}}}))
            last = when
            break


# ── R053 creatinine rise (AKI warning) ──────────────────────────────────────

def pattern_creatinine(events: List[Dict[str, Any]], ctx: Dict[str, Any], out: List[Dict[str, Any]]) -> None:
    labs = _labs(events, "creatinine")
    labs = [e for e in labs if not re.search(r"urine|소변|egfr|clearance", e["details"].get("test") or "", re.I)]
    last: Optional[datetime] = None
    for i, e in enumerate(labs):
        when = _t(e)
        unit = str(e["details"].get("unit") or "").lower()
        prior = [p for p in labs[:i] if str(p["details"].get("unit") or "").lower() == unit and _t(p) < when]
        recent = [_num(p["details"]["value"]) for p in prior if when - _t(p) <= timedelta(days=7)]
        older = [_num(p["details"]["value"]) for p in prior if timedelta(days=7) < when - _t(p) <= timedelta(days=365)]
        if recent:
            baseline, basis = min(recent), "lowest in the previous 7 days"
        elif older:
            baseline, basis = statistics.median(older), "median of the previous 8–365 days"
        else:
            continue
        value = _num(e["details"]["value"])
        min_rise = 26.5 if "mol" in unit else 0.3          # µmol/L vs mg/dL (KDIGO 0.3 mg/dL)
        if baseline <= 0 or value < 1.5 * baseline or value - baseline < min_rise:
            continue
        if last and when - last < timedelta(days=30):
            continue
        ratio = value / baseline
        stage = 3 if ratio >= 3 else 2 if ratio >= 2 else 1
        out.append(_derived(e, "creatinine-rise", "pattern_creatinine_rise", "R053", 3.0,
                            [e] + [p for p in prior if _num(p["details"]["value"]) == baseline][-1:],
                            f"Creatinine {value:g} {e['details'].get('unit') or ''} = {ratio:.1f} × baseline {baseline:g} "
                            f"({basis}): AKI warning stage {stage}",
                            [f"pattern: creatinine {ratio:.1f} × baseline ({basis}) → AKI stage {stage}: repeat creatinine "
                             f"(and clinical review) within 3 days"],
                            {"followup_match": {"R053": {"analyte": "creatinine",
                                                         "_only_for": [EventType.LAB_RESULT.value]}},
                             "aki_stage": stage}))
        last = when


# ── R054 AF without an anticoagulation decision ─────────────────────────────

def cha2ds2_vasc(events: List[Dict[str, Any]], ctx: Dict[str, Any], when: datetime) -> Dict[str, Any]:
    dx = [e for e in events if e["event_type"] == EventType.DIAGNOSIS.value and _t(e) <= when]
    items, score = [], 0
    for key, pts, prefixes, rx in _CHA2DS2:
        hit = next((e for e in dx if any(str(c).startswith(prefixes) for c in (e["details"].get("codes") or []))
                    or re.search(rx, e["details"].get("diagnosis") or "", re.I)), None)
        if hit:
            score += pts
            items.append(f"{key} +{pts}")
    age = _age(ctx, when)
    if age is not None and age >= 75:
        score, items = score + 2, items + ["age ≥ 75 +2"]
    elif age is not None and age >= 65:
        score, items = score + 1, items + ["age 65–74 +1"]
    if ctx.get("sex") == "female":
        score, items = score + 1, items + ["female +1"]
    return {"score": score, "items": items, "age_known": age is not None}


def pattern_af(events: List[Dict[str, Any]], ctx: Dict[str, Any], out: List[Dict[str, Any]]) -> None:
    af = sorted((e for e in events if e["event_type"] == EventType.DIAGNOSIS.value
                 and (_AF.search(e["details"].get("diagnosis") or "")
                      or any(str(c).startswith("I48") for c in e["details"].get("codes") or []))), key=_t)
    if not af:
        return
    e = af[0]
    when = _t(e)
    on_oac = [m for m in events if m["event_type"] == EventType.MEDICATION_CHANGE.value and m["details"].get("anticoagulant")
              and _t(m) <= when]
    if on_oac:
        return
    s = cha2ds2_vasc(events, ctx, when)
    needed = 3 if ctx.get("sex") == "female" else 2
    if not s["age_known"] or s["score"] < needed:
        return
    out.append(_derived(e, "af-oac", "pattern_af_no_anticoagulation", "R054", 30.0, [e],
                        f"Atrial fibrillation with CHA₂DS₂-VASc {s['score']} ({', '.join(s['items'])}) and no anticoagulant",
                        [f"pattern: AF, CHA₂DS₂-VASc {s['score']} (≥ {needed}) and no anticoagulant → anticoagulation decision "
                         f"within 30 days (a documented contraindication closes it)"],
                        {"cha2ds2_vasc": s["score"],
                         "followup_match": {"R054": {"anticoagulant": True}}}))


# ── R055 persistent microscopic haematuria ─────────────────────────────────

def _rbc_positive(e: Dict[str, Any]) -> bool:
    d = e["details"]
    v = _num(d.get("value"))
    return (v is not None and v >= 3.0) or d.get("flag") in ("HIGH", "ABNORMAL", "CRITICAL")


def pattern_haematuria(events: List[Dict[str, Any]], ctx: Dict[str, Any], out: List[Dict[str, Any]]) -> None:
    pos = [e for e in _labs(events, "urine_rbc") if _rbc_positive(e)]
    last: Optional[datetime] = None
    for i, e in enumerate(pos):
        when = _t(e)
        earlier = [p for p in pos[:i] if timedelta(days=1) <= when - _t(p) <= timedelta(days=365)]
        if not earlier or (last and when - last < ONCE_PER):
            continue
        age = _age(ctx, when)
        if age is None or age < 35:
            continue
        done = [x for x in events if when - timedelta(days=365) <= _t(x) <= when
                and (x["details"] or {}).get("specialty") == "urology"]
        if done:
            continue
        out.append(_derived(e, "haematuria", "pattern_haematuria", "R055", 90.0, [earlier[0], e],
                            f"Microscopic haematuria on {_t(earlier[0]).date()} and {when.date()} "
                            f"({e['details'].get('value')} RBC/hpf), age {age:.0f}",
                            [f"pattern: haematuria ≥ 3 RBC/hpf twice within 12 months, age {age:.0f} → urology referral or "
                             f"CT urography within 90 days"],
                            {"followup_match": {"R055": {"specialty": "urology",
                                                         "_only_for": [EventType.SPECIALIST_REFERRAL.value,
                                                                       EventType.REFERRAL_VISIT.value,
                                                                       EventType.FOLLOWUP_APPOINTMENT.value]}},
                             "followup_regions": {"R055": ["kidney", "bladder"]}}))
        last = when


PATTERNS = [pattern_ida, pattern_creatinine, pattern_af, pattern_haematuria]


def apply_patterns(events: List[Dict[str, Any]], ctx: Dict[str, Any]) -> None:
    """Add a DIAGNOSTIC_PATTERN trigger for each complete pattern (in place)."""
    out: List[Dict[str, Any]] = []
    for fn in PATTERNS:
        fn(events, ctx or {}, out)
    events.extend(out)
