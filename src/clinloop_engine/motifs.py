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
  R056  A lung nodule ≥ 2 mm larger than its smallest earlier measurement across the patient's reports
        (lesions linked by lobe and size), when the report does not itself call it growing →
        radiologist review and work-up within 30 days. Fleischner 2017; BTS 2015 (VDT).
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
_UNCERTAIN = re.compile(r"rule[- ]?out|\br/o\b|suspected|possible|probable|\?|의심|배제|가능성", re.I)
_CHA2DS2 = [  # (points, ICD-10 prefixes, text)
    ("chf", 1, ("I50", "I11.0", "I13.0", "I13.2"), r"heart failure|cardiomyopathy|lvef|심부전"),
    ("hypertension", 1, ("I10", "I11", "I12", "I13", "I15"),
     r"(?<!pulmonary )(?<!portal )(?<!intracranial )(?<!ocular )(?<!gestational )hypertension|(?<!폐)(?<!문맥)고혈압"),
    ("diabetes", 1, ("E10", "E11", "E13", "E14"),
     r"(?<!pre)(?<!pre-)(?<!gestational )diabetes(?!\s+insipidus)|\bdiabetic\b|\bt[12]dm\b|(?<!임신성\s)(?<!임신성)당뇨(?!붕증)"),
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
    elif unit in ("mmol/l",):
        v = v * 1.611                                     # mmol/L (Fe4) → g/dL
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

def creatinine_mg_dl(e: Dict[str, Any]) -> Optional[float]:
    """Serum creatinine in mg/dL whatever the unit (µmol/L ÷ 88.4); a unitless value > 20 is taken as µmol/L."""
    v = _num(e["details"].get("value"))
    if v is None:
        return None
    unit = str(e["details"].get("unit") or "").lower().replace("µ", "u").replace("μ", "u")
    if "mol" in unit or (not unit and v > 20):
        return v / 88.4
    return v


def pattern_creatinine(events: List[Dict[str, Any]], ctx: Dict[str, Any], out: List[Dict[str, Any]]) -> None:
    labs = _labs(events, "creatinine")
    labs = [e for e in labs if not re.search(r"urine|소변|egfr|clearance|ratio", e["details"].get("test") or "", re.I)
            and creatinine_mg_dl(e) is not None]
    last: Optional[datetime] = None
    for i, e in enumerate(labs):
        when = _t(e)
        prior = [p for p in labs[:i] if _t(p) < when]
        recent = [creatinine_mg_dl(p) for p in prior if when - _t(p) <= timedelta(days=7)]
        older = [creatinine_mg_dl(p) for p in prior if timedelta(days=7) < when - _t(p) <= timedelta(days=365)]
        if recent:
            baseline, basis = min(recent), "lowest in the previous 7 days"
        elif older:
            baseline, basis = statistics.median(older), "median of the previous 8–365 days"
        else:
            continue
        value = creatinine_mg_dl(e)
        if baseline <= 0 or value < 1.5 * baseline or value - baseline < 0.3:     # KDIGO: ≥ 0.3 mg/dL
            continue
        if last and when - last < timedelta(days=30):
            continue
        ratio = value / baseline
        stage = 3 if ratio >= 3 else 2 if ratio >= 2 else 1
        out.append(_derived(e, "creatinine-rise", "pattern_creatinine_rise", "R053", 3.0,
                            [e] + [p for p in prior if creatinine_mg_dl(p) == baseline][-1:],
                            f"Creatinine {e['details'].get('value')} {e['details'].get('unit') or ''} = {ratio:.1f} × baseline "
                            f"{baseline:.2f} mg/dL "
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
    if ctx.get("sex") == "female" and af_score_variant() == "cha2ds2_vasc":
        score, items = score + 1, items + ["female +1"]
    return {"score": score, "items": items, "age_known": age is not None}


def af_score_variant() -> str:
    """
    'cha2ds2_vasc' (ACC/AHA 2023; ESC 2020): anticoagulate at ≥ 2 (men) / ≥ 3 (women).
    'cha2ds2_va'   (ESC 2024): sex no longer scores; anticoagulate at ≥ 2 for everyone.
    The hospital's cardiologists choose (CLINLOOP_AF_SCORE); the guideline registry flags R054 until they do.
    """
    import os
    v = (os.environ.get("CLINLOOP_AF_SCORE") or "cha2ds2_vasc").strip().lower().replace("-", "_").replace("₂", "2")
    return "cha2ds2_va" if v in ("cha2ds2_va", "cha2ds2va", "va") else "cha2ds2_vasc"


def pattern_af(events: List[Dict[str, Any]], ctx: Dict[str, Any], out: List[Dict[str, Any]]) -> None:
    """
    Judged at every moment the risk could have been reached: the AF diagnosis, each later diagnosis
    (e.g. hypertension added in 2026), and the 65th and 75th birthdays, up to now.
    """
    from .safety_clock import utc_now
    af = sorted((e for e in events if e["event_type"] == EventType.DIAGNOSIS.value
                 and e["details"].get("verification") not in ("unconfirmed", "provisional", "differential", "refuted")
                 and not _UNCERTAIN.search(e["details"].get("diagnosis") or "")
                 and (_AF.search(e["details"].get("diagnosis") or "")
                      or any(str(c).startswith("I48") for c in e["details"].get("codes") or []))), key=_t)
    if not af:
        return
    first = af[0]
    now = utc_now()
    candidates = {_t(first)} | {_t(e) for e in events if e["event_type"] == EventType.DIAGNOSIS.value and _t(e) > _t(first)}
    b = ctx.get("birth_date")
    if b:
        for years in (65, 75):
            try:
                candidates.add(b.replace(year=b.year + years))
            except ValueError:                            # 29 February
                candidates.add(b.replace(year=b.year + years, day=28))
    needed = 3 if (ctx.get("sex") == "female" and af_score_variant() == "cha2ds2_vasc") else 2
    score_name = "CHA₂DS₂-VA" if af_score_variant() == "cha2ds2_va" else "CHA₂DS₂-VASc"
    for when in sorted(t for t in candidates if _t(first) <= t <= now):
        on_oac = [m for m in events if m["event_type"] == EventType.MEDICATION_CHANGE.value
                  and m["details"].get("anticoagulant") and is_fulfilling_status(m.get("status")) and _t(m) <= when]
        if on_oac:
            return
        s = cha2ds2_vasc(events, ctx, when)
        if not s["age_known"] or s["score"] < needed:
            continue
        anchor = {**first, "timestamp": when.isoformat(), "event_id": first["event_id"]}
        out.append(_derived(anchor, "af-oac", "pattern_af_no_anticoagulation", "R054", 30.0, [first],
                            f"Atrial fibrillation with {score_name} {s['score']} ({', '.join(s['items'])}) on "
                            f"{when.date()} and no anticoagulant",
                            [f"pattern: AF, {score_name} {s['score']} (≥ {needed}) and no anticoagulant → anticoagulation "
                             f"decision within 30 days (a documented contraindication closes it)"],
                            {"cha2ds2_vasc": s["score"], "followup_match": {"R054": {"anticoagulant": True}}}))
        return


# ── R055 persistent microscopic haematuria ─────────────────────────────────

def _rbc_positive(e: Dict[str, Any]) -> bool:
    """≥ 3 RBC/hpf on microscopy. Automated counts per µL (other scale) count only when the lab flags them."""
    d = e["details"]
    flagged = d.get("flag") in ("HIGH", "ABNORMAL", "CRITICAL")
    unit = str(d.get("unit") or "").lower().replace("µ", "u").replace("μ", "u")
    if re.search(r"/\s*u?l\b|/\s*ml\b", unit):
        return flagged
    v = _num(d.get("value"))
    if v is None:                                      # text results: "10-20", ">50", "many", "다수"
        text = str(d.get("result") or "")
        m = re.search(r"(\d+(?:\.\d+)?)", text)
        v = float(m.group(1)) if m else (50.0 if re.search(r"many|numerous|tntc|too numerous|다수|많", text, re.I) else None)
    return (v is not None and v >= 3.0) or flagged


def pattern_haematuria(events: List[Dict[str, Any]], ctx: Dict[str, Any], out: List[Dict[str, Any]]) -> None:
    pos = sorted((e for e in events if e["event_type"] == EventType.LAB_RESULT.value
                  and (e["details"] or {}).get("analyte") == "urine_rbc" and is_fulfilling_status(e.get("status"))
                  and _rbc_positive(e)), key=_t)
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


# ── R056 a lung nodule measured larger across reports (lesion tracking) ──────

GROWTH_MM = 2.0          # Fleischner 2017 / Lung-RADS: growth ≥ 2 mm in mean diameter is significant
VDT_SUSPICIOUS_DAYS = 400.0   # BTS 2015: volume-doubling time < 400 days favours malignancy


def _same_lesion(a: Dict[str, Any], b: Dict[str, Any], unique: bool) -> bool:
    """Probably the same nodule: same lobe (or same side when a lobe is missing), compatible size."""
    if a.get("lobe") and b.get("lobe"):
        if a["lobe"] != b["lobe"]:
            return False
    elif a.get("side") and b.get("side"):
        if a["side"] != b["side"]:
            return False
    elif not unique:
        return False            # no location and several nodules: cannot tell which is which
    return 0.5 <= b["size_mm"] / max(a["size_mm"], 0.1) <= 3.0


def volume_doubling_days(d1: float, d2: float, days: float) -> Optional[float]:
    """Volume-doubling time from two diameters (sphere): Δt · ln 2 / (3 · ln(d2/d1))."""
    import math
    if d2 <= d1 or days <= 0:
        return None
    return days * math.log(2) / (3 * math.log(d2 / d1))


def pattern_nodule_growth(events: List[Dict[str, Any]], ctx: Dict[str, Any], out: List[Dict[str, Any]]) -> None:
    """
    Link each lung nodule across the patient's reports (same lobe, compatible size) and do the arithmetic the
    reports may not: a nodule now ≥ 2 mm larger than its smallest earlier measurement, when the report itself
    does not call it growing (e.g. "stable 8 mm nodule", previously 6 mm, or 6 → 7 → 8 mm over three scans).
    """
    reports = sorted((e for e in events if e["event_type"] == EventType.RADIOLOGY_REPORT.value
                      and is_fulfilling_status(e.get("status"))
                      and ((e["details"] or {}).get("radiology") or {}).get("lung_nodules")), key=_t)
    chains: List[List[Dict[str, Any]]] = []          # each: [{"size_mm", "lobe", "side", "time", "event", "nodule"}]
    for rep in reports:
        nods = [n for n in rep["details"]["radiology"]["lung_nodules"] if not n.get("benign")]
        unique = len(nods) == 1 and len(chains) <= 1
        for n in nods:
            m = {"size_mm": float(n["size_mm"]), "lobe": n.get("lobe"), "side": n.get("side"),
                 "time": _t(rep), "event": rep, "nodule": n}
            candidates = [c for c in chains if c[-1]["time"] < m["time"] and _same_lesion(c[-1], m, unique)]
            if candidates:
                chain = min(candidates, key=lambda c: abs(c[-1]["size_mm"] - m["size_mm"]))
                if not m["lobe"]:
                    m["lobe"] = chain[-1]["lobe"]
                if not m["side"]:
                    m["side"] = chain[-1]["side"]
                chain.append(m)
            else:
                chains.append([m])
    for chain in chains:
        for k in range(1, len(chain)):
            cur = chain[k]
            base = min(chain[:k], key=lambda x: x["size_mm"])
            growth = round(cur["size_mm"]) - round(base["size_mm"])
            if growth < GROWTH_MM:
                continue
            stated = cur["nodule"].get("change") == "growing"
            radiology_flagged = "suspicious_lung_nodule" in (cur["event"]["details"].get("extra_conditions") or [])
            if stated or radiology_flagged:
                break                                  # the report (or R046) already deals with the growth
            days = (cur["time"] - base["time"]).days
            vdt = volume_doubling_days(base["size_mm"], cur["size_mm"], days)
            where = cur["lobe"] or (f"{cur['side']} lung" if cur["side"] else "lung")
            history = " → ".join(f"{x['size_mm']:g} mm ({x['time'].date()})" for x in chain[:k + 1])
            said = cur["nodule"].get("change")
            out.append(_derived(cur["event"], "nodule-growth", "pattern_nodule_growth", "R056", 30.0,
                                [x["event"] for x in chain[:k + 1]],
                                f"{where} nodule {history}: +{growth:g} mm"
                                + (f", volume-doubling time ≈ {vdt:.0f} days" if vdt else "")
                                + (f"; the latest report calls it {said}" if said else "; growth not stated in the report"),
                                [f"pattern: probably the same {where} nodule across {k + 1} reports, +{growth:g} mm from "
                                 f"{base['size_mm']:g} mm" + (f" (VDT ≈ {vdt:.0f} days"
                                                              f"{' < 400: suspicious' if vdt < VDT_SUSPICIOUS_DAYS else ''})"
                                                              if vdt else "")
                                 + " → radiologist confirms the match and the growth; work-up within 30 days"],
                                {"nodule_growth_mm": growth, "volume_doubling_days": round(vdt) if vdt else None,
                                 "lesion": {"lobe": cur["lobe"], "side": cur["side"],
                                            "sizes_mm": [x["size_mm"] for x in chain[:k + 1]]},
                                 "review_note_all": "Lesion match is probable, not certain: a radiologist confirms it is "
                                                    "the same nodule before work-up"}))
            break                                      # one review per lesion


PATTERNS = [pattern_ida, pattern_creatinine, pattern_af, pattern_haematuria, pattern_nodule_growth]


def apply_patterns(events: List[Dict[str, Any]], ctx: Dict[str, Any]) -> None:
    """Add a DIAGNOSTIC_PATTERN trigger for each complete pattern (in place)."""
    out: List[Dict[str, Any]] = []
    for fn in PATTERNS:
        fn(events, ctx or {}, out)
    events.extend(out)
