"""
radiology.py — Reading radiology reports into follow-up obligations

Two steps, so every decision can use the patient's context:

  1. extract (one report)   findings, categories, recommendations, critical
                            findings and the body regions of the study.
  2. decide  (one patient)  which obligations each report creates, using age,
                            sex, smoking status, cancer history and the
                            patient's earlier reports (stepped follow-up).

Guidelines encoded (all rules remain pending specialist review):
  * Fleischner Society 2017 — incidental lung nodules: solid / part-solid /
    ground-glass, single / multiple, low / high risk, stepped follow-up,
    growth, exclusions (age < 35, known cancer, immunocompromise, screening).
  * ACR Incidental Findings Committee white papers — adrenal (2017), renal
    (2018), pancreatic cyst (2017), thyroid (2015), abdominal aorta (2013).
  * ACR TI-RADS (2017) — FNA and follow-up size criteria on thyroid ultrasound.
  * ACR Practice Parameter for Communication of Diagnostic Imaging Findings —
    critical findings, from a hospital-approved list (config/critical_findings.json).

The report text is read with transparent patterns and every decision writes
a human-readable note into the event's mapping, so a reviewer can see why a
loop exists, or why it does not.
"""

import hashlib
import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .clinical_ontology import EventType, FLEISCHNER_LARGE_NODULE_DAYS, radiology_grace_days
from .report_text import affirmed, first_affirmed, not_negated, previous_sentence, sentence, span
from .safety_clock import normalize_timestamp

MONTH = 30.44
YEAR = 365.25

# ── Anatomy: body regions and organs ─────────────────────────────────────────
#
# A follow-up study closes an imaging loop only if it covers the body region
# the follow-up was asked for: an abdominal CT covers the adrenals; a head CT
# does not.

ORGAN_PARENT = {
    "brain": "head", "thyroid": "neck", "lung": "chest",
    "liver": "abdomen", "adrenal": "abdomen", "kidney": "abdomen", "pancreas": "abdomen",
    "spleen": "abdomen", "biliary": "abdomen", "abdominal_aorta": "abdomen",
    "bladder": "pelvis", "prostate": "pelvis", "uterus": "pelvis", "ovary": "pelvis",
}
REGION_ORGANS: Dict[str, set] = {}
for _organ, _region in ORGAN_PARENT.items():
    REGION_ORGANS.setdefault(_region, set()).add(_organ)

_ANATOMY = [
    ("spine", r"\b(spine|spinal|vertebra\w*|[clt]-spine)\b|척추"),
    ("head", r"\b(head|brain|skull|cranial|intracranial)\b|두부|뇌|머리"),
    ("neck", r"\bneck\b|경부"),
    ("thyroid", r"\bthyroid\b|갑상선"),
    ("chest", r"\b(chest|thorax|thoracic|lungs?|pulmonary|ldct|cxr)\b|흉부|폐"),
    ("abdomen", r"\b(abdomen|abdominal)\b|복부"),
    ("pelvis", r"\b(pelvis|pelvic)\b|골반"),
    ("liver", r"\b(liver|hepatic)\b|간\s*(?:초음파|CT|MRI)|간(?=[의에내])"),
    ("adrenal", r"\badrenals?\b|부신"),
    ("kidney", r"\b(renal|kidneys?|urogra\w*)\b|신장"),
    ("pancreas", r"\b(pancrea\w*|mrcp)\b|췌장"),
    ("breast", r"\b(breasts?|mammo\w*)\b|유방"),
    ("bladder", r"\bbladder\b|방광"),
    ("prostate", r"\bprostat\w*\b|전립선"),
]
_ANATOMY_RE = [(k, re.compile(p, re.I)) for k, p in _ANATOMY]
_SPINE_LEVEL = re.compile(r"\b(cervical|thoracic|lumbar)\s+spine\b", re.I)
_AORTA = re.compile(r"\baort\w*|\baaa\b|대동맥", re.I)
_THORACIC_AORTA = re.compile(r"thoracic|ascending|arch|chest|흉부", re.I)
_WHOLE_BODY = re.compile(r"whole[- ]body|skull base to (?:mid[- ]?)?thigh|\bpet\b", re.I)
_CAP = re.compile(r"\bcap\b|chest[,/ ]+abdomen[,/ ]+(?:and )?pelvis", re.I)


def regions_in(text: str) -> set:
    """Body regions and organs named in a text (unexpanded)."""
    text = text or ""
    found = set()
    plain = _SPINE_LEVEL.sub(" spine ", text)
    for key, rx in _ANATOMY_RE:
        if rx.search(plain):
            found.add(key)
    if _AORTA.search(text) and not _THORACIC_AORTA.search(text):
        found.add("abdominal_aorta")
    if _WHOLE_BODY.search(text):
        found |= {"neck", "chest", "abdomen", "pelvis"}
    if _CAP.search(text):
        found |= {"chest", "abdomen", "pelvis"}
    return found


def expand_regions(keys) -> List[str]:
    """What a study of these regions covers: a region covers its organs; an organ implies its region."""
    out = set(keys)
    for k in keys:
        out |= REGION_ORGANS.get(k, set())
        if k in ORGAN_PARENT:
            out.add(ORGAN_PARENT[k])
    return sorted(out)


def regions_compatible(required, covered) -> bool:
    return bool(set(required) & set(covered))


# ── Shared patterns ─────────────────────────────────────────────────────────

# "14 mm", "1.4 cm", "14 x 11 mm" (Fleischner 2017: average of long and short axis)
_SIZE = (r"(\d+(?:\.\d+)?)(?:\s*[x×]\s*(\d+(?:\.\d+)?))?(?:\s*[x×]\s*\d+(?:\.\d+)?)?\s*"
         r"(mm|cm|밀리미터|밀리|센티미터|센티)(?![a-zA-Z])")
_SIZE_RE = re.compile(_SIZE, re.I)


def _size_mm(a: str, b: Optional[str], unit: str) -> float:
    dims = [float(a)] + ([float(b)] if b else [])
    factor = 10.0 if unit.lower().startswith(("cm", "센티")) else 1.0
    return round(sum(dims) / len(dims) * factor, 1)


def _sizes(text: str) -> List[float]:
    return [_size_mm(m.group(1), m.group(2), m.group(3)) for m in _SIZE_RE.finditer(text)]


def _sentences(text: str) -> List[Tuple[int, str]]:
    out, start = [], 0
    for m in re.finditer(r"(?<=[.;])\s+|\n", text):
        out.append((start, text[start:m.start()]))
        start = m.end()
    out.append((start, text[start:]))
    return [(s, t) for s, t in out if t.strip()]


_LUNG_RADS = re.compile(r"lung-?rads\s*(?:category\s*)?:?\s*(\d[ABXS]?)", re.I)
_BIRADS = re.compile(r"bi-?rads\s*(?:category\s*)?:?\s*(\d[ABC]?)", re.I)
_TIRADS = re.compile(r"(?:ti-?rads\s*(?:category\s*)?:?\s*(?:TR\s*)?|\bTR\s*)(\d)\b", re.I)
_CHEST_CT = re.compile(r"\b(ct|ldct|computed tomography)\b.*\b(chest|thorax|lung)\b|\b(chest|thorax|lung)\b.*\b(ct|ldct)\b"
                       r"|흉부\s*ct|\bpet[/-]?ct\b", re.I)

# ── Lung nodules ─────────────────────────────────────────────────────────────

_NODULE_SIZE_FIRST = re.compile(rf"{_SIZE}[^.;]{{0,40}}?(nodules?|결절)", re.I)
_NODULE_WORD_FIRST = re.compile(rf"(nodules?|결절)[^.;]{{0,40}}?{_SIZE}", re.I)
_LUNG_SITE = re.compile(r"\b(lungs?|pulmonary|(?:upper|middle|lower)\s+lobes?|lingula\w*|perifissural|subpleural)\b"
                        r"|폐|[우좌][상중하]엽|설상엽", re.I)
_OTHER_SITE = re.compile(r"\b(adrenal|thyroid|renal|kidneys?|liver|hepatic|pancrea\w*|splen\w*|breast|ovar\w*|"
                         r"prostat\w*|parotid|lymph\s+nodes?|subcutaneous|skin)\b"
                         r"|부신|갑상선|신장|췌장|유방|비장|전립선|간(?=[\s의에내])", re.I)
_CHEST_STUDY = re.compile(r"chest|thora\w*|lung|ldct|흉부|폐", re.I)
_GGN = re.compile(r"ground[- ]glass|\bggn\b|\bggo\b|non-?solid|간유리", re.I)
_PART_SOLID = re.compile(r"part[- ]solid|semi-?solid|sub-?solid|mixed (?:attenuation|density)|부분\s*고형", re.I)
_SOLID_COMPONENT = re.compile(rf"solid component[^.;]{{0,20}}?{_SIZE}|{_SIZE}\s*solid component|고형\s*성분[^.;]{{0,10}}?{_SIZE}", re.I)
_MULTIPLE = re.compile(r"\b(multiple|numerous|several|nodules)\b|다발성|여러\s*개", re.I)
_BENIGN_NODULE = re.compile(r"(?<!non-)(?<!non )\b(calcified|granulomas?|hamartoma|intrapulmonary lymph node)\b"
                            r"|benign (?:pattern of )?calcification|(?<!비)석회화", re.I)
_PERIFISSURAL = re.compile(r"perifissural", re.I)
_GROWING = re.compile(r"\b(increas\w*|enlarg\w*|grow\w*|grew|larger|new(?:ly)?\s+(?:developed\s+)?solid component)\b"
                      r"|증가|커[졌짐]", re.I)
_STABLE = re.compile(r"\b(stable|unchanged|redemonstrat\w*|again (?:seen|noted|demonstrated)|previously "
                     r"(?:seen|noted|described|reported)|persistent|persists)\b|no\s+(?:significant\s+|interval\s+)*change"
                     r"|변화\s*없|안정", re.I)
_DECREASING = re.compile(r"\b(decreas\w*|smaller|shrink\w*|shrunk|regress\w*)\b|감소", re.I)
_NEW = re.compile(r"\bnew\b|신규|새로", re.I)
_STABLE_FOR = re.compile(r"(?:stable|unchanged)[^.;]{0,30}?\bfor\s+(\d+(?:\.\d+)?)\s*(year|month)s?", re.I)
_SINCE_YEAR = re.compile(r"\bsince\s+(?:\w+\s+)?((?:19|20)\d{2})\b|((?:19|20)\d{2})년\s*이후", re.I)
_COMPARED_DATE = re.compile(r"compar\w*\s+(?:to|with)[^.;]{0,40}?((?:19|20)\d{2})-(\d{2})(?:-(\d{2}))?", re.I)
_RISK_FEATURES = [("spiculation", re.compile(r"spiculat\w*|침상", re.I)),
                  ("upper lobe", re.compile(r"upper lobe|[우좌]상엽", re.I)),
                  ("emphysema", re.compile(r"emphysema|폐기종", re.I)),
                  ("pulmonary fibrosis", re.compile(r"fibrosis|섬유화", re.I))]


def _nodule_site(text: str, m: re.Match, code_text: str) -> str:
    """'lung', another organ, or 'lung' by default (a false alert is safer than a miss)."""
    s = sentence(text, m.start(), m.end())
    if _LUNG_SITE.search(s):
        return "lung"
    other = _OTHER_SITE.search(s)
    if other:
        return other.group(0).lower()
    other = _OTHER_SITE.search(code_text)
    if other and not _CHEST_STUDY.search(code_text):
        return other.group(0).lower()
    return "lung"


def _lung_nodules(text: str, code_text: str) -> List[Dict[str, Any]]:
    found: Dict[int, Dict[str, Any]] = {}
    for pattern, (a, b, unit) in ((_NODULE_SIZE_FIRST, (1, 2, 3)), (_NODULE_WORD_FIRST, (2, 3, 4))):
        for m in pattern.finditer(text):
            if not affirmed(text, m) or _nodule_site(text, m, code_text) != "lung":
                continue
            if re.search(r"component", m.group(0), re.I) or re.match(r"\s*(?:solid\s+)?component", text[m.end():], re.I):
                continue   # "nodule with a 7 mm solid component" is one nodule
            s = sentence(text, m.start(), m.end())
            size = _size_mm(m.group(a), m.group(b), m.group(unit))
            comp = _SOLID_COMPONENT.search(s)
            comp_mm = None
            if comp:
                g = [x for x in comp.groups() if x is not None]
                comp_mm = _size_mm(g[0], g[1] if len(g) > 2 else None, g[-1])
            typ = "part_solid" if (_PART_SOLID.search(s) or comp) else "ggn" if _GGN.search(s) else "solid"
            change = ("growing" if (_GROWING.search(s) and not re.search(r"\bno\s+(?:\w+\s+)?(?:increase|growth|enlargement)", s, re.I))
                      else "decreasing" if _DECREASING.search(s)
                      else "stable" if _STABLE.search(s)
                      else "new" if _NEW.search(s) else None)
            stable_since = None
            sf = _STABLE_FOR.search(s)
            if sf:
                stable_since = ("for", float(sf.group(1)) * (12 if sf.group(2).lower() == "year" else 1))
            else:
                sy = _SINCE_YEAR.search(s) or _SINCE_YEAR.search(text)
                cd = _COMPARED_DATE.search(text)
                if sy:
                    stable_since = ("date", datetime(int(sy.group(1) or sy.group(2)), 7, 1))
                elif cd:
                    stable_since = ("date", datetime(int(cd.group(1)), int(cd.group(2)), int(cd.group(3) or 1)))
            benign = bool(_BENIGN_NODULE.search(s)) or (bool(_PERIFISSURAL.search(s)) and size < 10)
            found[m.start()] = {
                "size_mm": size, "type": typ, "solid_component_mm": comp_mm,
                "multiple": bool(_MULTIPLE.search(s)), "change": change, "stable_since": stable_since,
                "benign": benign, "risk_features": [k for k, rx in _RISK_FEATURES if rx.search(s)],
                "evidence_span": span(text, m), "_start": m.start(),
            }
    if not found:
        return []
    nodules = sorted(found.values(), key=lambda n: n["_start"])
    # Drop overlapping duplicates of the same mention (both patterns can match it)
    unique: List[Dict[str, Any]] = []
    for n in nodules:
        if unique and abs(n["_start"] - unique[-1]["_start"]) < 15 and n["size_mm"] == unique[-1]["size_mm"]:
            continue
        unique.append(n)
    for n in unique:
        n.pop("_start", None)
    if len(unique) > 1:
        for n in unique:
            n["multiple"] = True
    return unique


# ── ACR incidental findings: adrenal, renal, pancreas, thyroid, aorta ───────

_LESION = r"(?:nodules?|mass(?:es)?|lesions?|adenoma|incidentaloma|cysts?|tumou?r|neoplasm|결절|종괴|종양|병변|낭종)"
_ADRENAL = re.compile(rf"(?:\badrenal|부신)[^.;]{{0,40}}?{_LESION}|{_LESION}[^.;]{{0,60}}?(?:adrenal|부신)", re.I)
_ADRENAL_BENIGN = re.compile(r"\b(adenoma|myelolipoma|macroscopic fat|lipid[- ]rich|cyst|h(?:a)?emorrhage|calcified)\b"
                             r"|선종|골수지방종", re.I)
_UNCERTAIN = re.compile(r"indeterminate|cannot be (?:excluded|characteri[sz]ed)|possibl\w*|versus|\bvs\.?\b|metasta\w*|"
                        r"not characteri[sz]ed|불확정|감별", re.I)
_HU = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:HU|hounsfield)", re.I)
_STABLE_YEAR = re.compile(r"(?:stable|unchanged)[^.;]{0,40}?(?:\b(?:for|over|since)\b[^.;]{0,20}?(?:year|(?:19|20)\d{2}))", re.I)

_RENAL = re.compile(rf"(?:\brenal|\bkidneys?|신장)[^.;]{{0,40}}?{_LESION}|{_LESION}[^.;]{{0,60}}?(?:\brenal|\bkidneys?|신장)", re.I)
_BOSNIAK = re.compile(r"bosniak\s*(?:class(?:ification)?|category|type)?\s*:?\s*(II-?F|2F|IV|III|II|I|[1-4])\b", re.I)
_RENAL_SUSPICIOUS = re.compile(r"\b(?:solid|enhancing)\s+(?:\w+\s+){0,2}(?:mass|lesion|nodule|component)|renal cell carcinoma|\brcc\b|"
                               r"(?:suspicious|concerning) for (?:malignan\w*|neoplasm|carcinoma)|신세포암", re.I)
_RENAL_BENIGN = re.compile(r"simple (?:renal )?cysts?|angiomyolipoma|macroscopic fat|too small to characteri[sz]e|"
                           r"\btstc\b|hyperdense cyst|단순\s*낭종|혈관근지방종", re.I)

_PANCREAS = re.compile(r"(?:pancrea\w*|췌장)[^.;]{0,40}?(?:cyst\w*|ipmn|intraductal papillary|낭종|낭성)|"
                       r"(?:cyst\w*|ipmn|낭종|낭성)[^.;]{0,60}?(?:pancrea\w*|췌장)", re.I)
_PSEUDOCYST = re.compile(r"pseudocyst|가성낭종", re.I)
_MAIN_DUCT = re.compile(rf"main (?:pancreatic )?duct[^.;]{{0,40}}?{_SIZE}|주췌관[^.;]{{0,20}}?{_SIZE}", re.I)
_PANCREAS_WORRISOME = re.compile(r"mural nodule|enhancing (?:solid )?component|solid component|"
                                 r"thick(?:ened)?,? (?:enhancing )?(?:cyst )?wall|obstructive jaundice|벽결절", re.I)

_THYROID = re.compile(rf"(?:thyroid|갑상선)[^.;]{{0,40}}?{_LESION}|{_LESION}[^.;]{{0,60}}?(?:thyroid|갑상선)", re.I)
_THYROID_SUSPICIOUS = re.compile(r"invasi\w*|invad\w*|extrathyroidal|abnormal (?:cervical )?lymph nodes?|suspicious", re.I)
_PET_AVID = re.compile(r"fdg[- ]avid|hypermetabolic|increased (?:fdg )?uptake|\bsuv\b|대사\s*증가", re.I)

_AAA = re.compile(r"aneurysm\w*|ectatic|ectasia|dilat\w*|\baaa\b|대동맥류|확장", re.I)
_RUPTURE = re.compile(r"ruptur\w*|leak\w*|파열", re.I)
_AAA_MEASURE = re.compile(r"\b(measur\w*|diameter|caliber|calibre)\b|직경", re.I)


def _incidental_findings(text: str, code_text: str, study_modality: Optional[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    thyroid_us = study_modality == "ultrasound" and "thyroid" in regions_in(code_text)
    for start, s in _sentences(text):
        sizes = _sizes(s)
        # Adrenal
        m = _ADRENAL.search(s)
        if m and affirmed(s, m) and sizes:
            hu = [float(x) for x in _HU.findall(s)]
            benign = (bool(_ADRENAL_BENIGN.search(s)) and not _UNCERTAIN.search(s)) or (hu and min(hu) <= 10) \
                or bool(_STABLE_YEAR.search(s))
            out.append({"kind": "adrenal", "organ": "adrenal", "size_mm": max(sizes), "benign": bool(benign),
                        "evidence_span": s.strip()})
        # Kidney
        m = _RENAL.search(s)
        if m and affirmed(s, m):
            b = _BOSNIAK.search(s)
            bos = None
            if b:
                bos = {"I": "I", "1": "I", "II": "II", "2": "II", "IIF": "IIF", "II-F": "IIF", "2F": "IIF",
                       "III": "III", "3": "III", "IV": "IV", "4": "IV"}.get(b.group(1).upper())
            out.append({"kind": "renal", "organ": "kidney", "size_mm": max(sizes) if sizes else None,
                        "bosniak": bos,
                        "suspicious": bos in ("III", "IV") or bool(_RENAL_SUSPICIOUS.search(s)),
                        "benign": bos in ("I", "II") or bool(_RENAL_BENIGN.search(s)),
                        "indeterminate": bool(re.search(r"indeterminate|불확정", s, re.I)),
                        "evidence_span": s.strip()})
        # Pancreas
        m = _PANCREAS.search(s)
        if m and affirmed(s, m) and not _PSEUDOCYST.search(s) and sizes:
            worrisome = []
            duct = _MAIN_DUCT.search(text)
            if duct:
                g = [x for x in duct.groups() if x is not None]
                if _size_mm(g[0], g[1] if len(g) > 2 else None, g[-1]) >= 7:
                    worrisome.append("main pancreatic duct ≥7 mm")
            w = first_affirmed(_PANCREAS_WORRISOME, text)
            if w:
                worrisome.append(w.group(0).lower())
            out.append({"kind": "pancreatic_cyst", "organ": "pancreas", "size_mm": max(sizes),
                        "worrisome": worrisome, "evidence_span": s.strip()})
        # Thyroid
        m = _THYROID.search(s)
        if not m and thyroid_us:
            m = re.search(r"nodules?|결절", s, re.I)
        if m and affirmed(s, m) and (sizes or _PET_AVID.search(s)):
            t = _TIRADS.search(s) or _TIRADS.search(text)
            out.append({"kind": "thyroid_us" if thyroid_us else "thyroid_incidental", "organ": "thyroid",
                        "size_mm": max(sizes) if sizes else None,
                        "tirads": int(t.group(1)) if t else None,
                        "suspicious": bool(_THYROID_SUSPICIOUS.search(s)),
                        "pet_avid": bool(_PET_AVID.search(s)), "evidence_span": s.strip()})
        # Abdominal aorta
        rupture = first_affirmed(_RUPTURE, s)      # a ruptured aneurysm is a critical finding (R035)
        if _AORTA.search(s) and not _THORACIC_AORTA.search(s) and (_AAA.search(s) or _AAA_MEASURE.search(s)) \
                and sizes and not rupture:
            m = _AAA.search(s) or _AAA_MEASURE.search(s)
            if affirmed(s, m) and max(sizes) >= 25:
                out.append({"kind": "aaa", "organ": "abdominal_aorta", "diameter_mm": max(sizes),
                            "evidence_span": s.strip()})
    return out


# ── Recommendations ─────────────────────────────────────────────────────────

_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "six": 6, "twelve": 12}
_UNIT_DAYS = {"day": 1, "week": 7, "month": MONTH, "year": YEAR, "일": 1, "주": 7, "개월": MONTH, "년": YEAR}
_NUM = r"(\d+(?:\.\d+)?|one|two|three|four|six|twelve)"
# Bare "MR" is excluded: "recommend Mr Kim return in 2 weeks" is not an MRI
_MOD = r"(cta|ct|mri|(?-i:US)|ultrasound|ultrasonograph\w*|sonograph\w*|radiographs?|x-?rays?|cxr)"
_INTERVAL = rf"(?:in|within|at|after)\s+(?:{_NUM}\s*(?:-|–|to)\s*)?{_NUM}\s*(day|week|month|year)s?"
_REC_PATTERNS = [
    re.compile(rf"recommend\w*[^.;]{{0,40}}?\b{_MOD}\b[^.;]{{0,50}}?\b{_INTERVAL}", re.I),
    re.compile(rf"\b{_MOD}\b[^.;]{{0,40}}?\b{_INTERVAL}[^.;]{{0,30}}?\brecommend", re.I),
]
_KO_MOD = r"(CT|MRI|초음파|X선|엑스레이)"
_REC_KO = re.compile(rf"(\d+)\s*(?:[-~]\s*(\d+))?\s*(개월|주|일|년)\s*(?:후|뒤|이내|내)?\s*(?:에\s*)?(?:추적\s*)?(?:검사\s*)?"
                     rf"{_KO_MOD}[^.]{{0,20}}?(?:권고|권장|필요)", re.I)
_NOT_GUIDED = r"(?![\s-]*guided)"
_REC_NO_INTERVAL = [
    re.compile(rf"recommend\w*[^.;]{{0,40}}?\b{_MOD}\b{_NOT_GUIDED}", re.I),
    re.compile(rf"\b{_MOD}\b{_NOT_GUIDED}[^.;]{{0,40}}?\b(?:recommend\w*|advised|suggested|warranted)", re.I),
]
_REC_KO_NO_INTERVAL = re.compile(rf"(?:추가|추적|정밀)\s*(?:검사\s*)?(?:로\s*)?{_KO_MOD}[^.]{{0,15}}?(?:권고|권장)", re.I)
DEFAULT_REC_INTERVAL_DAYS = 30.0
_BIOPSY = r"(biops(?:y|ies)|tissue sampling|fine[-\s]needle aspiration|\bFNA\b|core[-\s]needle|조직검사|세침\s*흡인)"
_BIOPSY_REC = [
    re.compile(rf"recommend\w*[^.;]{{0,40}}?{_BIOPSY}", re.I),
    re.compile(rf"{_BIOPSY}[^.;]{{0,40}}?\b(?:recommend\w*|advised|suggested|warranted|indicated)", re.I),
    re.compile(rf"{_BIOPSY}[^.]{{0,15}}?(?:권고|권장|필요)", re.I),
]
_HEDGE = re.compile(r"if clinically|as clinically indicated|if (?:desired|needed|warranted)|could be considered|"
                    r"may be considered|can be considered|\boptional", re.I)
_NOT_A_REC = re.compile(r"\b(no|not|without|prior|previous|outside|comparison|compared)\b", re.I)
REC_RULE = {"ct": "R030", "mri": "R031", "ultrasound": "R032", "xray": "R033"}


def _norm_modality(text: str) -> Optional[str]:
    t = text.lower()
    if t in ("ct", "cta"):
        return "ct"
    if t in ("mri", "mr"):
        return "mri"
    if t == "us" or "sonograph" in t or "ultrasound" in t or t == "초음파":
        return "ultrasound"
    if "radiograph" in t or t.replace("-", "").rstrip("s") in ("xray", "cxr") or t in ("x선", "엑스레이"):
        return "xray"
    return None


def _usable_rec(text: str, m: re.Match) -> bool:
    """Affirmed, not hedged, and not about a prior study."""
    return (affirmed(text, m) and not _HEDGE.search(sentence(text, m.start(), m.end()))
            and not _NOT_A_REC.search(m.group(0)))


def _rec_regions(text: str, m: re.Match, code_text: str) -> List[str]:
    """Where the follow-up is for: the recommendation itself, its sentence, the sentence before, or the study."""
    for source in (m.group(0), sentence(text, m.start(), m.end()), previous_sentence(text, m.start()), code_text):
        found = regions_in(source)
        if found:
            return sorted(found)
    return []


def _extract_recommendation(text: str, code_text: str = "") -> Optional[Dict[str, Any]]:
    """Radiologist follow-up recommendation: modality, interval (upper bound of a range), regions, evidence span.

    A recommendation that names a modality but no interval gets a 30-day default
    (``recommended_interval_stated`` False), so "CT for further evaluation" is not lost.
    """
    def result(m, modality, days, stated):
        return {"recommended_modality": modality, "recommended_interval_days": days,
                "recommended_interval_stated": stated, "regions": _rec_regions(text, m, code_text),
                "evidence_span": span(text, m)}

    for pattern in _REC_PATTERNS:
        for m in pattern.finditer(text):
            if not not_negated(text, m.start()):
                continue
            modality = _norm_modality(m.group(1))
            low, high, unit = m.group(2), m.group(3), m.group(4).lower()
            value = high if high else low
            number = float(_WORD_NUM.get(value.lower(), value)) if value else None
            if modality and number:
                return result(m, modality, round(number * _UNIT_DAYS[unit], 1), True)
    m = _REC_KO.search(text)
    if m:
        number = float(m.group(2) or m.group(1))
        return result(m, _norm_modality(m.group(4)), round(number * _UNIT_DAYS[m.group(3)], 1), True)
    for pattern in _REC_NO_INTERVAL + [_REC_KO_NO_INTERVAL]:
        for m in pattern.finditer(text):
            modality = _norm_modality(m.group(1))
            if modality and _usable_rec(text, m):
                return result(m, modality, DEFAULT_REC_INTERVAL_DAYS, False)
    return None


def _biopsy_recommendation(text: str) -> Optional[Dict[str, Any]]:
    for pattern in _BIOPSY_REC:
        for m in pattern.finditer(text):
            if _usable_rec(text, m):
                s = sentence(text, m.start(), m.end())
                return {"evidence_span": span(text, m),
                        "regions": sorted(regions_in(s) or regions_in(previous_sentence(text, m.start())))}
    return None


# ── Critical findings (hospital-approved list) ──────────────────────────────

DEFAULT_CRITICAL_FINDINGS = os.path.join(os.path.dirname(__file__), "config", "critical_findings.json")
# Not a new emergent finding: chronic/known/resolving, or only the indication for the study
_NOT_NEW = re.compile(r"\b(chronic|old|known|previously|prior|stable|resolv\w*|improv\w*|decreas\w*|residual|"
                      r"evaluat\w*|assess\w*|protocol|rule out|r/o|exclude)\b[^.;]{0,30}$", re.I)
_COMMUNICATED = re.compile(r"(discussed with|communicated (?:to|with)|called to|telephoned|notified|conveyed to|"
                           r"relayed to|read back|에게\s*(?:전화로?\s*|구두로?\s*)?(?:통보|보고|전달))", re.I)
_critical_cache: Dict[str, Any] = {}


def critical_findings_path() -> str:
    return os.environ.get("CLINLOOP_CRITICAL_FINDINGS") or DEFAULT_CRITICAL_FINDINGS


def load_critical_findings() -> Dict[str, Any]:
    """The active critical-finding list, its content hash, and compiled patterns (reloaded when the file changes)."""
    path = critical_findings_path()
    mtime = os.path.getmtime(path)
    cached = _critical_cache.get(path)
    if cached and cached["mtime"] == mtime:
        return cached
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    canonical = json.dumps(data.get("findings", []), sort_keys=True, ensure_ascii=False)
    compiled = []
    for item in data.get("findings", []):
        compiled.append((item, re.compile("(" + "|".join(item["patterns"]) + ")", re.I)))
    entry = {"path": path, "mtime": mtime, "data": data, "compiled": compiled,
             "hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}
    _critical_cache[path] = entry
    return entry


def _critical_findings(text: str) -> List[Dict[str, Any]]:
    found = []
    for item, rx in load_critical_findings()["compiled"]:
        for m in rx.finditer(text):
            if affirmed(text, m) and not _NOT_NEW.search(text[max(0, m.start() - 60):m.start()]):
                found.append({"id": item["id"], "label": item.get("label", {}).get("en", item["id"]),
                              "category": item.get("category", 1), "window_minutes": float(item.get("window_minutes", 60)),
                              "match": m.group(0), "evidence_span": span(text, m)})
                break
    return found


# ── Study modality ──────────────────────────────────────────────────────────

_MOD_PET = re.compile(r"\bpet\b", re.I)
_MOD_CT = re.compile(r"\b(ct|cta|ldct|computed tomography)\b", re.I)
_MOD_MRI = re.compile(r"\b(mri|mr|mrcp|magnetic resonance)\b", re.I)
_MOD_US = re.compile(r"\b(?-i:US)\b|ultrasound|sonograph|초음파", re.I)
_MOD_XRAY = re.compile(r"radiograph|\bx-?rays?\b|\bcxr\b|\bxr\b|x선|엑스레이|단순\s*촬영", re.I)
_LIVER = re.compile(r"liver|hepat|abdom|간|복부", re.I)


def study_modality(code_text: str) -> Optional[str]:
    if _MOD_CT.search(code_text):
        return "ct"
    if _MOD_MRI.search(code_text):
        return "mri"
    if _MOD_US.search(code_text):
        return "ultrasound"
    if _MOD_XRAY.search(code_text):
        return "xray"
    return None


# ── Step 1: one report ───────────────────────────────────────────────────────

def map_radiology_report(ts: Optional[str], code_text: str, conclusion: str,
                         details: Dict[str, Any]) -> List[Tuple[str, Optional[str], Dict]]:
    """Events for one radiology report. Obligations are decided later, per patient (decide_obligations)."""
    mapping = ["DiagnosticReport(RAD)→radiology_report"]
    events: List[Tuple[str, Optional[str], Dict]] = []
    modality = study_modality(code_text)
    covered = expand_regions(regions_in(code_text))
    rad: Dict[str, Any] = {"study_regions": covered, "modality": modality}

    for key, pattern, label in (("lung_rads", _LUNG_RADS, "Lung-RADS"), ("birads", _BIRADS, "BI-RADS"),
                                ("tirads", _TIRADS, "TI-RADS TR")):
        m = pattern.search(conclusion)
        if m:
            details[key] = m.group(1).upper()
            mapping.append(f"{label} {m.group(1).upper()}")
    nodules = _lung_nodules(conclusion, code_text)
    if nodules:
        dominant = max(nodules, key=lambda n: (n["size_mm"], n["type"] != "ggn"))
        dominant["multiple"] = dominant["multiple"] or len(nodules) > 1
        rad["lung_nodule"] = dominant
        details["nodule_size_mm"] = dominant["size_mm"]
        details["finding"] = "lung_nodule"
        mapping.append(f"lung nodule {dominant['size_mm']:g} mm, {dominant['type'].replace('_', '-')}"
                       f"{', multiple' if dominant['multiple'] else ''}"
                       f"{', ' + dominant['change'] if dominant['change'] else ''}")
    rad["incidental"] = _incidental_findings(conclusion, code_text, modality)
    for f in rad["incidental"]:
        size = f.get("size_mm") or f.get("diameter_mm")
        mapping.append(f"{f['kind'].replace('_', ' ')}" + (f" {size:g} mm" if size else ""))
    rec = _extract_recommendation(conclusion, code_text)
    if rec and rec["recommended_modality"]:
        rad["recommendation"] = rec
        mapping.append(f"radiologist recommends {rec['recommended_modality']} in "
                       f"{rec['recommended_interval_days']:g} days"
                       + ("" if rec["recommended_interval_stated"] else " (no interval stated: 30-day default)")
                       + (f" [{', '.join(rec['regions'])}]" if rec["regions"] else ""))
    biopsy = _biopsy_recommendation(conclusion)
    if biopsy:
        rad["biopsy_recommendation"] = biopsy
    critical = _critical_findings(conclusion)
    if critical:
        rad["critical"] = critical
    m = first_affirmed(_COMMUNICATED, conclusion)
    if m:
        # Follow-ups must come after their trigger, so the documented call is placed one
        # minute after the report time (the report text rarely gives a parseable time)
        try:
            notified = (datetime.fromisoformat(str(ts).replace("Z", "+00:00")) + timedelta(minutes=1)).isoformat()
        except ValueError:
            notified = ts
        events.append((EventType.CRITICAL_VALUE_NOTIFICATION.value, notified,
                       {"evidence_span": span(conclusion, m),
                        "mapping": ["communication documented in the radiology report→critical_value_notification",
                                    "time: report time + 1 minute"]}))
        mapping.append("communication to clinician documented in report")

    details["radiology"] = rad
    details["mapping"] = mapping
    events.insert(0, (EventType.RADIOLOGY_REPORT.value, ts, details))
    # A completed study fulfils outstanding follow-up imaging obligations
    if _CHEST_CT.search(code_text):
        events.append((EventType.FOLLOWUP_CT.value, ts, {"mapping": ["chest CT report→followup_ct"],
                                                         "body_regions": covered}))
    if _MOD_PET.search(code_text):
        events.append((EventType.IMAGING_PET.value, ts, {"mapping": ["PET report→imaging_pet"], "body_regions": covered}))
    if modality:
        etype = {"ct": EventType.IMAGING_CT, "mri": EventType.IMAGING_MRI,
                 "ultrasound": EventType.IMAGING_ULTRASOUND, "xray": EventType.IMAGING_XRAY}[modality].value
        events.append((etype, ts, {"mapping": [f"{modality} report→{etype} [{', '.join(covered) or 'region unknown'}]"],
                                   "body_regions": covered}))
        if modality != "xray" and _LIVER.search(code_text):
            events.append((EventType.LIVER_IMAGING.value, ts, {"mapping": [f"{modality} liver/abdomen→liver_imaging"]}))
    return events


# ── Step 2: decisions with the patient's context ─────────────────────────────

def _months(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 86400 / MONTH


def nodule_risk(n: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[str, str]:
    """Fleischner low/high risk. Unknown is managed as high risk (the safer choice)."""
    features = list(n.get("risk_features", []))
    if ctx.get("emphysema"):
        features.append("emphysema")
    smoking = ctx.get("smoking")
    if smoking in ("current", "former"):
        features.append(f"{smoking} smoker")
    if features:
        return "high", "high risk (" + ", ".join(dict.fromkeys(features)) + ")"
    if smoking == "never":
        return "low", "low risk (never smoker, no high-risk features in the report)"
    return "high", "risk unknown (no smoking status): managed as high risk"


def fleischner(n: Dict[str, Any], ctx: Dict[str, Any], prior: List[Dict[str, Any]], when: datetime) -> Dict[str, Any]:
    """
    Fleischner Society 2017 decision for one lung nodule.

    Returns {"action": "followup"|"workup"|"none", "days": float|None, "notes": [...], "review": str|None}.
    Intervals use the upper bound of the guideline range plus the radiology grace
    period (a CT at 10 months for a "6–12 month" nodule is on time).
    """
    notes: List[str] = []
    size = round(n["size_mm"])
    typ, multiple = n["type"], n["multiple"]
    label = f"{'multiple ' if multiple else ''}{typ.replace('_', '-')} nodule {size} mm"

    review = None
    exclusions = []
    if ctx.get("age") is not None and ctx["age"] < 35:
        exclusions.append("patient under 35")
    if ctx.get("malignancy"):
        exclusions.append("known malignancy")
    if ctx.get("immunocompromised"):
        exclusions.append("immunocompromised")
    if exclusions:
        review = (f"Fleischner 2017 does not apply ({', '.join(exclusions)}): confirm the follow-up plan "
                  f"with the treating team.")
        notes.append(f"Fleischner exclusion: {', '.join(exclusions)} → human review")

    if n.get("benign"):
        notes.append(f"{label}: benign features (calcification / granuloma / perifissural) → no follow-up (Fleischner 2017)")
        return {"action": "none", "days": None, "notes": notes, "review": None}

    risk, basis = nodule_risk(n, ctx)
    notes.append(f"Fleischner: {basis}")

    # Is this a known nodule? Earlier lung-nodule reports for this patient set the baseline.
    change = n.get("change")
    baseline: Optional[datetime] = None
    earlier = [p for p in prior if p["time"] < when]
    if change != "new" and earlier:
        baseline = earlier[0]["time"]
        last = earlier[-1]
        if change is None:
            change = "growing" if size - round(last["size_mm"]) >= 2 else "stable"
            notes.append(f"compared with {last['time'].date()} ({last['size_mm']:g} mm): {change}")
    elif change in ("stable", "decreasing") and n.get("stable_since"):
        kind, value = n["stable_since"]
        baseline = when - timedelta(days=value * MONTH) if kind == "for" else value

    if change == "growing":
        notes.append(f"{label}: growth → work-up (PET/CT, tissue sampling or referral) within 30 days")
        return {"action": "workup", "days": 30.0, "notes": notes, "review": review}

    if change in ("stable", "decreasing"):
        return _fleischner_stepped(n, size, typ, multiple, risk, baseline, when, label, notes, review)

    # Initial management
    if typ == "solid":
        if size < 6:
            notes.append(f"{label}: no routine follow-up" + (" (optional CT at 12 months in high risk: not tracked)"
                                                              if risk == "high" else ""))
            return {"action": "none", "days": None, "notes": notes, "review": None}
        if size <= 8:
            days, rng = (6 * MONTH, "3–6 months") if multiple else (12 * MONTH, "6–12 months")
        else:
            days, rng = (6 * MONTH, "3–6 months") if multiple else (FLEISCHNER_LARGE_NODULE_DAYS, "3 months, PET/CT or tissue sampling")
    elif typ == "ggn":
        if not multiple and size < 6:
            notes.append(f"{label}: no routine follow-up")
            return {"action": "none", "days": None, "notes": notes, "review": None}
        days, rng = (6 * MONTH, "3–6 months") if multiple else (12 * MONTH, "6–12 months")
    else:  # part-solid
        if not multiple and size < 6:
            notes.append(f"{label}: no routine follow-up")
            return {"action": "none", "days": None, "notes": notes, "review": None}
        if not multiple and (n.get("solid_component_mm") or 0) >= 6:
            days, rng = FLEISCHNER_LARGE_NODULE_DAYS, "3 months (solid component ≥6 mm: highly suspicious)"
        else:
            days, rng = 6 * MONTH, "3–6 months"
    days += radiology_grace_days(days)
    notes.append(f"{label}: CT at {rng} → due within {days:.0f} days (incl. grace)")
    return {"action": "followup", "days": round(days, 1), "notes": notes, "review": review}


def _fleischner_stepped(n, size, typ, multiple, risk, baseline, when, label, notes, review):
    elapsed = _months(baseline, when) if baseline else None
    since = f"{elapsed:.0f} months since baseline" if elapsed is not None else "baseline date unknown"
    if typ == "solid":
        if size < 6:
            notes.append(f"stable {label}: no routine follow-up")
            return {"action": "none", "days": None, "notes": notes, "review": None}
        if elapsed is not None and elapsed >= 23:
            notes.append(f"stable {label}, {since}: solid nodule stable ≥2 years → no further routine follow-up")
            return {"action": "none", "days": None, "notes": notes, "review": None}
        if size <= 8 and risk == "low":
            notes.append(f"stable {label}, low risk: optional CT at 18–24 months (not tracked)")
            return {"action": "none", "days": None, "notes": notes, "review": None}
        if size > 8 and not multiple and elapsed is not None and elapsed < 9:
            target, step = baseline + timedelta(days=12 * MONTH), "next CT at ~12 months (proposed)"
        elif baseline:
            target, step = baseline + timedelta(days=24 * MONTH), "next CT at 18–24 months"
        else:
            target, step = when + timedelta(days=12 * MONTH), "next CT within 12 months (baseline unknown)"
    elif typ == "ggn":
        if size < 6:
            notes.append(f"stable {label}: CT at 2 and 4 years may be considered (optional, not tracked)")
            return {"action": "none", "days": None, "notes": notes, "review": None}
        if elapsed is not None and elapsed >= 59:
            notes.append(f"stable {label}, {since}: 5 years of stability → surveillance complete")
            return {"action": "none", "days": None, "notes": notes, "review": None}
        target, step = when + timedelta(days=24 * MONTH), "CT every 2 years until 5 years"
    else:
        if (n.get("solid_component_mm") or 0) >= 6:
            notes.append(f"persistent {label} with solid component ≥6 mm: highly suspicious → work-up within 30 days")
            return {"action": "workup", "days": 30.0, "notes": notes, "review": review}
        if size < 6:
            notes.append(f"stable {label}: CT at 2 and 4 years may be considered (optional, not tracked)")
            return {"action": "none", "days": None, "notes": notes, "review": None}
        if elapsed is not None and elapsed >= 59:
            notes.append(f"stable {label}, {since}: 5 years of stability → surveillance complete")
            return {"action": "none", "days": None, "notes": notes, "review": None}
        target, step = when + timedelta(days=12 * MONTH), "annual CT for 5 years"
    days = max(30.0, (target - when).total_seconds() / 86400)
    days = round(days + radiology_grace_days(days), 1)
    notes.append(f"stable {label} ({since}): {step} → due within {days:.0f} days (incl. grace)")
    return {"action": "followup", "days": days, "notes": notes, "review": review}


def acr_incidental(f: Dict[str, Any], ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """ACR white-paper management for one incidental finding: rule, deadline, region and a note, or None."""
    kind = f["kind"]
    size = f.get("size_mm")

    def plan(rule_id, condition, days, note, regions=None, grace=False):
        if grace:
            days = days + radiology_grace_days(days)
        return {"rule_id": rule_id, "condition": condition, "days": round(days, 1),
                "regions": regions or [f["organ"]], "note": note}

    if kind == "adrenal":
        if f["benign"]:
            return {"none": "adrenal: benign features (adenoma ≤10 HU, myelolipoma, cyst, or stable ≥1 year) → no follow-up (ACR 2017)"}
        if size < 10:
            return {"none": "adrenal nodule <1 cm → no follow-up (ACR 2017)"}
        if ctx.get("malignancy"):
            return plan("R038", "adrenal_mass_workup", 30, "adrenal nodule ≥1 cm with known cancer → PET/CT, biopsy or specialist review (ACR 2017)")
        if size >= 40:
            return plan("R038", "adrenal_mass_workup", 30, "adrenal mass ≥4 cm → endocrine surgery referral (ACR 2017)")
        if size >= 20:
            return plan("R037", "adrenal_nodule_followup", 90, "indeterminate adrenal nodule 2–4 cm → adrenal protocol CT or MRI (ACR 2017; 90 days proposed)")
        return plan("R037", "adrenal_nodule_followup", 12 * MONTH, "indeterminate adrenal nodule 1–2 cm → adrenal CT or MRI at 12 months (ACR 2017)", grace=True)

    if kind == "renal":
        if f["suspicious"]:
            return plan("R039", "suspicious_renal_mass", 30,
                        f"renal mass{' Bosniak ' + f['bosniak'] if f['bosniak'] else ''}: solid/enhancing or Bosniak III–IV → urology referral (ACR 2018)")
        if f["bosniak"] == "IIF":
            return plan("R040", "renal_lesion_followup", 6 * MONTH, "Bosniak IIF cyst → CT or MRI at 6 months (Bosniak v2019)", grace=True)
        if f["benign"]:
            return {"none": "renal: simple cyst, Bosniak I–II, angiomyolipoma or too small to characterise → no follow-up (ACR 2018)"}
        if f["indeterminate"] and (size or 0) >= 10:
            return plan("R040", "renal_lesion_followup", 90, "indeterminate renal lesion ≥1 cm → renal mass protocol CT or MRI (ACR 2018; 90 days proposed)")
        return None

    if kind == "pancreatic_cyst":
        if f["worrisome"]:
            return plan("R042", "pancreatic_cyst_worrisome", 30,
                        f"pancreatic cyst with worrisome features ({', '.join(f['worrisome'])}) → EUS / pancreas specialist (ACR 2017)")
        if size < 15:
            return plan("R041", "pancreatic_cyst_followup", 24 * MONTH, "pancreatic cyst <1.5 cm → MRI/MRCP in 2 years (ACR 2017)", grace=True)
        if size <= 25:
            return plan("R041", "pancreatic_cyst_followup", 12 * MONTH, "pancreatic cyst 1.5–2.5 cm → MRI/MRCP in 1 year (ACR 2017)", grace=True)
        return plan("R041", "pancreatic_cyst_followup", 6 * MONTH, "pancreatic cyst >2.5 cm → MRI/MRCP in 6 months or EUS-FNA (ACR 2017)", grace=True)

    if kind == "thyroid_incidental":
        age = ctx.get("age")
        threshold = 10 if age is None or age < 35 else 15
        if f["suspicious"] or f["pet_avid"]:
            return plan("R043", "incidental_thyroid_nodule", 90,
                        "thyroid nodule with " + ("FDG uptake" if f["pet_avid"] else "suspicious features") + " → thyroid ultrasound (ACR 2015)")
        if size and size >= threshold:
            basis = "age unknown" if age is None else f"age {age}"
            return plan("R043", "incidental_thyroid_nodule", 90,
                        f"incidental thyroid nodule ≥{threshold / 10:g} cm ({basis}) → thyroid ultrasound (ACR 2015; 90 days proposed)")
        return {"none": f"incidental thyroid nodule <{threshold / 10:g} cm → no ultrasound (ACR 2015)"}

    if kind == "thyroid_us":
        tr = f.get("tirads")
        if not tr or not size:
            return None
        fna = {5: 10, 4: 15, 3: 25}.get(tr)
        follow = {5: 5, 4: 10, 3: 15}.get(tr)
        if fna and size >= fna:
            return {"biopsy": f"TI-RADS TR{tr} nodule {size / 10:g} cm meets FNA criteria (≥{fna / 10:g} cm, ACR TI-RADS 2017)"}
        if follow and size >= follow:
            return {"ultrasound_followup": 12 * MONTH,
                    "note": f"TI-RADS TR{tr} nodule {size / 10:g} cm → follow-up ultrasound at 1 year (ACR TI-RADS 2017)"}
        return {"none": f"TI-RADS TR{tr} nodule {size / 10:g} cm → no FNA or follow-up (ACR TI-RADS 2017)"}

    if kind == "aaa":
        d = f["diameter_mm"]
        repair = 50 if ctx.get("sex") == "female" else 55
        if d >= repair:
            return plan("R045", "aaa_repair_threshold", 14,
                        f"abdominal aorta {d / 10:g} cm ≥{repair / 10:g} cm → vascular surgery referral (SVS 2018 / ACR 2013)")
        for upper, years, label in ((30, 5, "2.5–2.9 cm"), (35, 3, "3.0–3.4 cm"), (40, 2, "3.5–3.9 cm"),
                                    (45, 1, "4.0–4.4 cm"), (10_000, 0.5, "≥4.5 cm")):
            if d < upper:
                return plan("R044", "aaa_surveillance", years * YEAR,
                            f"abdominal aorta {d / 10:g} cm ({label}) → imaging in {years:g} year(s) (ACR 2013)", grace=True)
    return None


def _overlaps(a, b) -> bool:
    return regions_compatible(expand_regions(a), expand_regions(b))


def decide_obligations(events: List[Dict[str, Any]], ctx_base: Dict[str, Any]) -> None:
    """
    Decide the obligations of each radiology report of one patient, in time order.

    Writes to each report's details:
      extra_conditions   trigger conditions for the engine
      rule_deadline_days per-rule deadline (days from the report)
      followup_regions   per-rule body regions a follow-up study must cover
      review_notes       per-rule reason a human must confirm the loop
    """
    def ts(e):
        return normalize_timestamp(e["timestamp"])

    def context_at(when: datetime) -> Dict[str, Any]:
        ctx = dict(ctx_base)
        birth = ctx_base.get("birth_date")
        if birth:
            ctx["age"] = when.year - birth.year - ((when.month, when.day) < (birth.month, birth.day))
        for e in events:
            if ts(e) > when:
                continue
            d = e["details"]
            if e["event_type"] == EventType.RISK_FACTOR.value and d.get("smoking"):
                ctx["smoking"] = d["smoking"]      # latest wins (events are in time order)
            if e["event_type"] == EventType.DIAGNOSIS.value:
                ctx["malignancy"] = ctx.get("malignancy") or bool(d.get("malignancy"))
                ctx["immunocompromised"] = ctx.get("immunocompromised") or bool(d.get("immunocompromised"))
        return ctx

    reports = sorted((e for e in events if e["event_type"] == EventType.RADIOLOGY_REPORT.value
                      and "radiology" in e["details"]), key=ts)
    events.sort(key=ts)
    nodule_history: List[Dict[str, Any]] = []

    for e in reports:
        d = e["details"]
        rad = d["radiology"]
        when = ts(e)
        ctx = context_at(when)
        ctx["emphysema"] = bool(re.search(r"emphysema|폐기종", d.get("conclusion") or "", re.I))
        mapping: List[str] = d["mapping"]
        conds: List[str] = []
        deadlines: Dict[str, float] = {}
        regions: Dict[str, List[str]] = {}
        reviews: Dict[str, str] = {}
        spans: List[str] = []
        covered_organs: List[Tuple[str, List[str]]] = []   # (rule, regions) to de-duplicate biopsy advice

        def add(rule_id, condition, days=None, regs=None, review=None, evidence=None):
            conds.append(condition)
            if days is not None:
                deadlines[rule_id] = days
            if regs:
                regions[rule_id] = regs
            if review:
                reviews[rule_id] = review
            if evidence:
                spans.append(evidence)

        rec = rad.get("recommendation")
        rec_tracked = rec is not None
        if rec and d.get("lung_rads") and rec["recommended_modality"] == "ct":
            rec_tracked = False
            mapping.append("Lung-RADS rule tracks this CT: recommendation not tracked separately")

        # 1. Lung nodule (Fleischner) — not for screening LDCT with a Lung-RADS category
        n = rad.get("lung_nodule")
        if n and d.get("lung_rads"):
            mapping.append("screening LDCT: Lung-RADS governs follow-up, Fleischner not applied")
        elif n:
            decision = fleischner(n, ctx, nodule_history, when)
            mapping.extend(decision["notes"])
            nodule_history.append({"time": when, "size_mm": n["size_mm"], "type": n["type"]})
            if decision["action"] == "workup":
                add("R046", "suspicious_lung_nodule", 30.0, review=decision["review"], evidence=n["evidence_span"])
                covered_organs.append(("R046", ["lung"]))
                if rec_tracked and rec["recommended_modality"] == "ct":
                    rec_tracked = False
                    mapping.append("nodule work-up (R046) covers the CT recommendation")
            elif decision["action"] == "followup":
                rec_ct = rec_tracked and rec["recommended_modality"] == "ct"
                rec_deadline = (rec["recommended_interval_days"] + radiology_grace_days(rec["recommended_interval_days"])
                                if rec_ct else None)
                if rec_ct and rec["recommended_interval_stated"] and rec_deadline < decision["days"]:
                    mapping.append("radiologist interval is tighter than Fleischner: tracked as R030")
                else:
                    add("R003", "incidental_nodule_ge_6mm", decision["days"], review=decision["review"],
                        evidence=n["evidence_span"])
                    covered_organs.append(("R003", ["lung"]))
                    if rec_ct:
                        rec_tracked = False
                        mapping.append("Fleischner window (R003) governs: recommendation not tracked separately")

        # 2. Incidental findings (ACR white papers); the radiologist's own recommendation wins
        tirads_followup = None
        for f in rad.get("incidental", []):
            decision = acr_incidental(f, ctx)
            if not decision:
                continue
            if "none" in decision:
                mapping.append(decision["none"])
                continue
            if "biopsy" in decision:
                mapping.append(decision["biopsy"])
                if not rad.get("biopsy_recommendation"):
                    rad["biopsy_recommendation"] = {"evidence_span": f["evidence_span"], "regions": ["thyroid"],
                                                    "source": "TI-RADS criteria"}
                continue
            if "ultrasound_followup" in decision:
                mapping.append(decision["note"])
                if not rec_tracked:
                    tirads_followup = decision
                continue
            if rec_tracked and _overlaps(rec["regions"], [f["organ"]]):
                mapping.append(f"{decision['note']} — radiologist's recommendation tracked instead "
                               f"({REC_RULE[rec['recommended_modality']]})")
                continue
            mapping.append(decision["note"])
            add(decision["rule_id"], decision["condition"], decision["days"], decision["regions"],
                evidence=f["evidence_span"])
            covered_organs.append((decision["rule_id"], decision["regions"]))

        # 3. Radiologist's recommendation (R030–R033), or the TI-RADS follow-up ultrasound
        if rec_tracked:
            d.update({k: rec[k] for k in ("recommended_modality", "recommended_interval_days",
                                          "recommended_interval_stated")})
            if rec["regions"]:
                regions[REC_RULE[rec["recommended_modality"]]] = rec["regions"]
            spans.append(rec["evidence_span"])
        elif tirads_followup:
            d.update(recommended_modality="ultrasound", recommended_interval_days=round(tirads_followup["ultrasound_followup"], 1),
                     recommended_interval_stated=False)
            regions["R032"] = ["thyroid"]

        # 4. Tissue sampling advised (R036), unless another rule already covers that finding
        biopsy = rad.get("biopsy_recommendation")
        if biopsy:
            b_regions = biopsy.get("regions") or []
            governed = ("R018" if str(d.get("birads", ""))[:1] in ("4", "5") else
                        "R020" if d.get("lung_rads") in ("4B", "4X") else None)
            if not governed:
                governed = next((rule for rule, regs in covered_organs
                                 if not b_regions or _overlaps(b_regions, regs)), None)
            if governed:
                mapping.append(f"tissue sampling recommended: covered by {governed}")
            else:
                d["biopsy_recommended"] = True
                if b_regions:
                    regions["R036"] = b_regions
                spans.append(biopsy["evidence_span"])
                mapping.append("tissue sampling recommended" + (f" ({biopsy['source']})" if biopsy.get("source") else ""))

        # 5. Critical findings (hospital-approved list)
        critical = rad.get("critical")
        if critical:
            shortest = min(critical, key=lambda c: c["window_minutes"])
            d.update(critical_imaging=True, critical_finding=shortest["label"])
            add("R035", "critical_imaging_finding", shortest["window_minutes"] / 1440.0, evidence=shortest["evidence_span"])
            mapping.append(f"critical finding: {', '.join(c['label'] for c in critical)} "
                           f"(ACR category {shortest['category']}, communicate within {shortest['window_minutes']:g} min)")

        if conds:
            d["extra_conditions"] = list(dict.fromkeys(conds))
        if deadlines:
            d["rule_deadline_days"] = deadlines
        if regions:
            d["followup_regions"] = regions
        if reviews:
            d["review_notes"] = reviews
        if spans:
            d["evidence_span"] = " … ".join(dict.fromkeys(spans))
