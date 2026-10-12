"""
guideline_reports.py — Reading lab results, colonoscopy and pathology reports, and echocardiograms
against published follow-up guidelines (R060–R065)

Each reader is transparent: it returns the obligation, the deadline and the words or numbers in
the report that decided it, so a clinician can check every alert. When the report is unclear, the
reader says so (a review note) rather than guessing.

  R060  HIV screening test reactive → supplemental test or HIV care within 30 days
        (CDC/APHL laboratory testing algorithm 2014, updated 2018; linkage within 30 days)
  R061  Hepatitis B surface antigen (HBsAg) positive → HBV DNA or specialist within 30 days
        (AASLD 2018 hepatitis B guidance). Anti-HBs (surface antibody) is immunity, not infection.
  R062  Positive IGRA, or tuberculin skin test ≥ 10 mm → chest radiograph within 30 days
        (ATS/IDSA/CDC 2017 diagnosis of tuberculosis; exclude active TB before treating latent TB)
  R063  Colonoscopy → surveillance colonoscopy at the USMSTF 2020 interval; only intervals of
        three years or less are tracked: inadequate preparation 1 year, piecemeal resection of a
        polyp ≥ 20 mm 6 months, advanced findings 3 years (Gupta S et al., Gastroenterology 2020)
  R064  Severe aortic stenosis on echocardiography → cardiology / heart valve team within 30 days
        (2020 ACC/AHA valvular heart disease guideline: AVA < 1.0 cm², mean gradient ≥ 40 mmHg,
        or peak velocity ≥ 4.0 m/s)
  R065  LVEF ≤ 40 % in a patient without known heart failure → cardiology within 30 days
        (2022 AHA/ACC/HFSA heart failure guideline: HFrEF; start guideline-directed therapy)
"""

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .report_text import NEGATION_AFTER, not_negated

# ── Laboratory results ───────────────────────────────────────────────────────

LOINC_HIV_SCREEN = {"75622-1", "56888-1", "80387-4", "7917-8", "68961-2", "31201-7", "5221-7", "43009-0",
                    "48345-3", "48346-1", "29893-5", "86233-4", "89374-3", "58900-2"}
LOINC_HIV_SUPPLEMENTAL = {"25836-8", "20447-9", "10351-5", "41513-3", "70241-5", "48023-6", "69668-2",
                          "81641-3", "89365-1", "86657-4", "62469-2", "29539-4", "24012-7"}
LOINC_HBSAG = {"5196-1", "5195-3", "7905-3", "10674-0", "75410-1", "63557-3", "65633-0"}
LOINC_HBV_DNA = {"29615-2", "42595-9", "20442-0", "48398-2", "58452-9", "5009-6", "23869-1"}
LOINC_IGRA = {"71774-4", "88517-7", "71773-6", "46217-6", "45323-3", "64084-7", "71776-9"}
LOINC_TST = {"1648-3", "39263-9", "11558-4"}

_HIV = re.compile(r"\bhiv\b|human immunodeficiency|에이즈|인체\s*면역\s*결핍", re.I)
_HIV_SUPPLEMENTAL = re.compile(r"\brna\b|viral load|\bpcr\b|\bnat\b|differentiat|multispot|geenius|western blot|"
                               r"immunoblot|genotyp|quantitativ|정량|바이러스\s*양|확인\s*검사", re.I)
_HBSAG = re.compile(r"hbs\s*-?\s*ag|hepatitis b (?:virus )?surface antigen|b형\s*간염\s*(?:바이러스\s*)?표면\s*항원|"
                    r"표면\s*항원", re.I)
_HBV_ANTIBODY = re.compile(r"anti[- ]?hb|hbs\s*-?\s*ab|surface antibod|core antibod|표면\s*항체|항체", re.I)
_HBV_DNA = re.compile(r"hbv\s*-?\s*dna|hepatitis b (?:virus )?(?:dna|viral load)|b형\s*간염[^,;]{0,15}(?:dna|바이러스\s*양)",
                      re.I)
_IGRA = re.compile(r"quanti\s*feron|\bqft\b|t[- .]?spot|interferon[- ]gamma release|\bigra\b|결핵\s*감염\s*검사|"
                   r"인터페론\s*감마", re.I)
_TST = re.compile(r"tuberculin|\bppd\b|\btst\b|mantoux|투베르쿨린|결핵\s*피부\s*반응", re.I)
# Parts of a QuantiFERON panel that are numbers, not the result (antigen minus nil, mitogen, nil)
_IGRA_COMPONENT = re.compile(r"minus nil|\bnil\b|mitogen|tb1|tb2|antigen tube|iu/ml", re.I)

_UNCLEAR = re.compile(r"indeterminate|equivocal|borderline|inconclusive|invalid|grey ?zone|gray ?zone|"
                      r"판정\s*(?:불가|보류)|미결정|경계", re.I)
_NEGATIVE = re.compile(r"non[- ]?reactive|\bnegative\b|not detected|undetected|\babsent\b|\bnone\b|음성|비반응", re.I)
_POSITIVE = re.compile(r"\breactive\b|\bpositive\b|\bdetected\b|양성|반응성", re.I)


def _result_sign(value_text: str, flag: Optional[str], interp_codes: Iterable[str]) -> Optional[str]:
    """'positive', 'negative', 'unclear' or None (no result stated)."""
    text = value_text or ""
    if _UNCLEAR.search(text):
        return "unclear"
    if _NEGATIVE.search(text):
        return "negative"
    if _POSITIVE.search(text):
        return "positive"
    codes = {str(c).upper() for c in interp_codes}
    if codes & {"IND", "EQV", "I"}:
        return "unclear"
    if codes & {"NEG", "N", "ND"}:
        return "negative"
    if codes & {"POS", "DET", "A", "AA", "H", "HH"} or flag in ("ABNORMAL", "HIGH", "CRITICAL"):
        return "positive"
    return None


def classify_lab(codes: Iterable[str], code_text: str, value_text: str, flag: Optional[str],
                 value: Any, unit: Optional[str], interp_codes: Iterable[str]) -> Optional[Dict[str, Any]]:
    """
    The guideline meaning of one lab result, or None when it is not one of these tests.

    Returns {"condition": … or None, "followup_event": … or None, "mapping": […], "review_note": …}.
    "followup_event" names the test this result itself is (an HIV RNA closes R060, an HBV DNA R061).
    """
    codes = set(codes)
    text = code_text or ""

    # Supplemental HIV tests and HBV DNA are follow-ups, never screening triggers
    if codes & LOINC_HIV_SUPPLEMENTAL or (_HIV.search(text) and _HIV_SUPPLEMENTAL.search(text)):
        return {"condition": None, "followup_event": "hiv_supplemental_test",
                "mapping": ["HIV supplemental test (RNA / differentiation)→hiv_supplemental_test"]}
    if codes & LOINC_HBV_DNA or _HBV_DNA.search(text):
        return {"condition": None, "followup_event": "hbv_dna_test", "mapping": ["HBV DNA→hbv_dna_test"]}

    sign = _result_sign(value_text, flag, interp_codes)

    if codes & LOINC_HIV_SCREEN or _HIV.search(text):
        out = {"condition": None, "followup_event": None, "mapping": [f"HIV screening test: {sign or 'no result'}"]}
        if sign == "positive":
            out["condition"] = "hiv_screen_reactive"
            out["mapping"].append("reactive→hiv_screen_reactive (R060)")
        elif sign == "unclear":
            out["review_note"] = "HIV screening result is indeterminate: repeat or supplemental testing per the lab algorithm"
        return out

    if (codes & LOINC_HBSAG or _HBSAG.search(text)) and not _HBV_ANTIBODY.search(text):
        out = {"condition": None, "followup_event": None, "mapping": [f"HBsAg: {sign or 'no result'}"]}
        if sign == "positive":
            out["condition"] = "hbsag_positive"
            out["mapping"].append("HBsAg positive→hbsag_positive (R061)")
        return out

    if codes & LOINC_IGRA or _IGRA.search(text):
        if isinstance(value, (int, float)) and not value_text and _IGRA_COMPONENT.search(text + " " + (unit or "")):
            return {"condition": None, "followup_event": None, "mapping": ["IGRA panel component: not the result"]}
        out = {"condition": None, "followup_event": None, "mapping": [f"IGRA: {sign or 'no result'}"]}
        if sign == "positive":
            out["condition"] = "tb_infection_test_positive"
            out["mapping"].append("IGRA positive→tb_infection_test_positive (R062)")
        elif sign == "unclear":
            out["review_note"] = "IGRA indeterminate or borderline: repeat the test, or decide clinically"
        return out

    if codes & LOINC_TST or _TST.search(text):
        mm = value if isinstance(value, (int, float)) else None
        if mm is None:
            m = re.search(r"(\d+(?:\.\d+)?)\s*mm", value_text or "")
            mm = float(m.group(1)) if m else None
        out = {"condition": None, "followup_event": None, "mapping": []}
        if mm is not None:
            out["mapping"].append(f"TST induration {mm:g} mm")
            if mm >= 10:
                out["condition"] = "tb_infection_test_positive"
                out["mapping"].append("≥10 mm→tb_infection_test_positive (R062)")
        elif sign == "positive":
            out["condition"] = "tb_infection_test_positive"
            out["mapping"].append("TST positive (no size stated)→tb_infection_test_positive (R062)")
        return out
    return None


# ── Colonoscopy and polyp pathology (USMSTF 2020) ───────────────────────────

INTERVAL_PIECEMEAL_DAYS = 183
INTERVAL_POOR_PREP_DAYS = 365
INTERVAL_ADVANCED_DAYS = 1096

_COLONOSCOPY = re.compile(r"colonoscop|\bcolon(?:ic)?\b.*(?:polyp|endoscop)|대장\s*내시경|결장\s*내시경", re.I)
_COLON_SITE = re.compile(r"colon|colonic|cecum|caecum|rect(?:um|al)|sigmoid|ascending|descending|transverse|"
                         r"hepatic flexure|splenic flexure|대장|결장|직장|맹장", re.I)
_CANCER = re.compile(r"(?:invasive |intramucosal )?adenocarcinoma|carcinoma|malignan\w*|\bcancer\b|선암|암종|대장암", re.I)
_PIECEMEAL = re.compile(r"piece-?meal|분할\s*절제|분할\s*점막\s*절제", re.I)
_VILLOUS = re.compile(r"(?:tubulo)?villous|관\s*융모|융모\s*선종|융모성", re.I)
_HGD = re.compile(r"high[- ]grade dysplasia|\bHGD\b|고도\s*이형성|고등급\s*이형성", re.I)
_TSA = re.compile(r"traditional serrated adenoma|\bTSA\b|전통\s*(?:적\s*)?톱니\s*모양\s*선종", re.I)
_SSL_DYSPLASIA = re.compile(r"(?:sessile serrated (?:lesion|adenoma|polyp)|\bSSL\b|\bSSA/?P?\b|톱니\s*모양)"
                            r"[^.;\n]{0,60}?\bwith\s+(?:[\w-]+\s+){0,2}dysplasia|이형성을?\s*동반한\s*(?:무경성\s*)?톱니", re.I)
_ADENOMA = re.compile(r"adenoma|선종", re.I)
_POLYP_WORD = re.compile(r"polyp|adenoma|lesion|\bSSL\b|\bSSA\b|\bLST\b|용종|선종|병변", re.I)
_PREP_BAD = re.compile(r"(?:poor|inadequate|insufficient|suboptimal)\s+(?:bowel\s+)?prep(?:aration)?|"
                       r"(?:bowel\s+)?prep(?:aration)?\s+(?:was|is)?\s*(?:poor|inadequate|insufficient|suboptimal)|"
                       r"장\s*정결(?:도|\s*상태)?\s*(?:가|는|이)?\s*(?:불량|불충분|부적절|나쁨|불량함)", re.I)
_BBPS = re.compile(r"(?:boston bowel prep\w*(?:\s*scale)?|\bBBPS\b)[^0-9]{0,30}?(\d{1,2})"
                   r"(?:\s*(?:\(|:|\[)?\s*(?:right|R)?\s*(\d)\s*[/,\- ]\s*(?:transverse|T)?\s*(\d)\s*[/,\- ]\s*(?:left|L)?\s*(\d))?",
                   re.I)
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                 "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
_SIZE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:(?:-|–|to|~)\s*(\d+(?:\.\d+)?)\s*)?(mm|cm)\b", re.I)
_DISTANCE = re.compile(r"(?:\bat\s+|\bfrom\s+|insert\w*\s+to\s+|~\s*)$|^\s*(?:cm\s+)?(?:from|proximal|distal|above)\b", re.I)
# "all < 10 mm", "less than 1 cm", "10 mm 미만": a limit, not a measured polyp
_LIMIT = re.compile(r"(?:<|≤|less than|smaller than|under|below)\s*$", re.I)
_INSTRUMENT = re.compile(r"^\s*(?:\w+\s+)?(?:snare|clip|forceps|hood|cap|needle|balloon)", re.I)


def _affirmed(rx: "re.Pattern", text: str) -> Optional["re.Match"]:
    for m in rx.finditer(text):
        after = text[m.end():m.end() + 60]
        if not_negated(text, m.start()) and not NEGATION_AFTER.search(after):
            return m
    return None


def _polyp_sizes(text: str) -> List[float]:
    """Polyp sizes in mm: numbers with mm/cm in a sentence about a polyp, not distances or instruments."""
    sizes: List[float] = []
    for sentence in re.split(r"(?<=[.;\n])\s+|\n", text):
        if not _POLYP_WORD.search(sentence):
            continue
        for m in _SIZE.finditer(sentence):
            before, after = sentence[max(0, m.start() - 25):m.start()], sentence[m.end():m.end() + 25]
            if _DISTANCE.search(before) or re.match(r"\s*(?:from|proximal|distal|above)\b", after, re.I) \
                    or _INSTRUMENT.match(after) or _LIMIT.search(before):
                continue
            hi = float(m.group(2) or m.group(1))
            mm = hi * 10 if m.group(3).lower() == "cm" else hi
            if 1 <= mm <= 100:
                sizes.append(mm)
    return sizes


def _adenoma_count(text: str) -> int:
    best = 0
    for m in re.finditer(r"\b(\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")\s+(?:\(\d+\)\s+)?(?:small\s+|diminutive\s+)?"
                         r"(?:tubular\s+|sessile serrated\s+)?adenomas\b", text, re.I):
        n = m.group(1).lower()
        best = max(best, int(n) if n.isdigit() else _NUMBER_WORDS[n])
    for m in re.finditer(r"(?:선종|관상\s*선종)\s*(\d{1,2})\s*개|(\d{1,2})\s*개의?\s*(?:관상\s*)?선종", text):
        best = max(best, int(m.group(1) or m.group(2)))
    # "Tubular adenomas (x5)", "adenomas x 5", "Tubular adenomas (5 of 5)"
    for m in re.finditer(r"adenomas?\b[^.\n]{0,15}?(?:\(\s*)?(?:x|×)\s*(\d{1,2})|adenomas?\b[^.\n]{0,15}?\(?(\d{1,2})\s+of\s+\d{1,2}",
                         text, re.I):
        best = max(best, int(m.group(1) or m.group(2)))
    # Lettered part ranges: "A-E. Colon polyps: tubular adenomas" (five parts)
    for m in re.finditer(r"(?:^|\n)\s*([A-Z])\s*[-–]\s*([A-Z])[.)]\s+([^\n]*)", text):
        if _affirmed(_ADENOMA, m.group(3)):
            best = max(best, ord(m.group(2)) - ord(m.group(1)) + 1)
    # Korean: "용종 6개: 모두 관상선종"
    for m in re.finditer(r"(\d{1,2})\s*개[^.\n]{0,15}?(?:모두|전부)[^.\n]{0,10}?선종", text):
        best = max(best, int(m.group(1)))
    # Pathology parts: "A. Colon, ascending, polypectomy: Tubular adenoma." Count lettered parts with an adenoma
    parts = re.findall(r"(?:^|\n)\s*([A-Z])[.)]\s+([^\n]*(?:\n(?!\s*[A-Z][.)]\s)[^\n]*)*)", text)
    with_adenoma = {label for label, body in parts if _affirmed(_ADENOMA, body)}
    return max(best, len(with_adenoma))


def colonoscopy_interval(text: str) -> Dict[str, Any]:
    """
    The USMSTF 2020 surveillance interval for one colonoscopy (endoscopy and/or pathology report text).

    Returns {"days": int or None, "reasons": [...], "review_note": str or None, "cancer": bool}.
    Only intervals of three years or less are tracked; longer ones (small adenomas: 3–10 years) are not.
    """
    reasons: List[Tuple[int, str]] = []
    note = None
    cancer = _affirmed(_CANCER, text)
    if cancer:
        return {"days": None, "reasons": [f"'{cancer.group(0)}': cancer pathway (pathology rules), not surveillance"],
                "review_note": None, "cancer": True}

    m = _affirmed(_PREP_BAD, text)
    if m:
        reasons.append((INTERVAL_POOR_PREP_DAYS, f"'{m.group(0)}': inadequate preparation → repeat within 1 year"))
    for b in _BBPS.finditer(text):
        total = int(b.group(1))
        segments = [int(x) for x in b.group(2, 3, 4) if x is not None]
        if total <= 9 and (total < 6 or any(s < 2 for s in segments)):
            reasons.append((INTERVAL_POOR_PREP_DAYS, f"BBPS {total}{' (' + '/'.join(map(str, segments)) + ')' if segments else ''}"
                                                     ": inadequate preparation (needs ≥ 6 with every segment ≥ 2)"))
            break

    sizes = _polyp_sizes(text)
    largest = max(sizes, default=None)
    pm = _affirmed(_PIECEMEAL, text)
    if pm:
        sentence = re.split(r"(?<=[.;\n])", text[:pm.start()])[-1] + text[pm.start():pm.end() + 120].split(".")[0]
        local = _polyp_sizes(sentence)
        size = max(local, default=largest)
        if size is None:
            reasons.append((INTERVAL_PIECEMEAL_DAYS, "piecemeal resection (size not stated) → 6 months"))
            note = "Piecemeal resection without a stated size: check that the polyp was ≥ 20 mm"
        elif size >= 20:
            reasons.append((INTERVAL_PIECEMEAL_DAYS, f"piecemeal resection of a {size:g} mm polyp → 6 months"))

    if largest is not None and largest >= 10:
        reasons.append((INTERVAL_ADVANCED_DAYS, f"polyp {largest:g} mm (≥ 10 mm) → 3 years"))
    for rx, label in ((_VILLOUS, "villous histology"), (_HGD, "high-grade dysplasia"),
                      (_TSA, "traditional serrated adenoma"), (_SSL_DYSPLASIA, "sessile serrated lesion with dysplasia")):
        hit = _affirmed(rx, text)
        if hit:
            reasons.append((INTERVAL_ADVANCED_DAYS, f"'{hit.group(0)}': {label} → 3 years"))
    count = _adenoma_count(text)
    if count >= 5:
        reasons.append((INTERVAL_ADVANCED_DAYS, f"{count} adenomas (≥ 5) → 3 years"))

    if not reasons:
        return {"days": None, "reasons": ["no finding with an interval of 3 years or less"], "review_note": None,
                "cancer": False}
    days = min(d for d, _ in reasons)
    return {"days": days, "reasons": [r for _, r in sorted(reasons)], "review_note": note, "cancer": False}


def is_colonoscopy_report(code_text: str, category: str, text: str) -> bool:
    head = f"{code_text} {category}"
    if _COLONOSCOPY.search(head):
        return True
    return bool(re.search(r"endoscop|내시경|\bgi\b", head, re.I) and _COLONOSCOPY.search(text[:400]))


_OTHER_GI_SITE = re.compile(r"stomach|gastric|duoden\w*|esophag\w*|oesophag\w*|small bowel|ampull\w*|\b위\b|위\s*(?:체부|전정부|각)|"
                            r"십이지장|식도", re.I)


def is_colon_pathology(text: str) -> bool:
    """Polyp histology from the colon: named as colon, or polyps/adenomas with no other site named."""
    polyp = _ADENOMA.search(text) or re.search(r"polyp|serrated|용종|톱니", text, re.I)
    return bool(polyp and (_COLON_SITE.search(text) or not _OTHER_GI_SITE.search(text)))


# ── Echocardiography (ACC/AHA 2020 valve; AHA/ACC/HFSA 2022 heart failure) ────

_ECHO = re.compile(r"echocardiog|\bTTE\b|\bTEE\b|transthoracic echo|transesophageal echo|심장\s*초음파|심초음파", re.I)
_PROSTHETIC_AV = re.compile(r"\bTAVR\b|\bTAVI\b|\bs/p\s+(?:surgical\s+)?AVR\b|aortic valve replacement|"
                            r"(?:bio)?prosthe\w*\s+(?:aortic\s+)?valve[^.]{0,30}aortic|(?:bio)?prosthe\w*\s+aortic|"
                            r"mechanical aortic|bioprosthetic AV|대동맥판\s*치환|인공\s*대동맥판|경피적\s*대동맥판", re.I)
_SEVERE_AS = re.compile(r"(?<!moderate to )(?<!moderate-to-)(?<!moderate-)(?<!moderate/)"
                        r"(?:severe|critical)\s+(?:calcific\s+|degenerative\s+|valvular\s+|low[- ]flow,?\s+low[- ]gradient\s+)?"
                        r"(?:aortic\s+(?:valve\s+)?stenosis|\bAS\b)|"
                        r"(?<!중등도\s)(?<!중등도~)(?:중증|심한|고도)\s*(?:의\s*)?대동맥\s*판막?\s*협착", re.I)
_AORTIC_CONTEXT = re.compile(r"aortic|\bAV\b|\bAS\b|\bAVA\b|대동맥", re.I)
_OTHER_VALVE = re.compile(r"mitral|\bMV\b|\bMS\b|\bMR\b|tricuspid|\bTV\b|\bTR\b|pulmon|\bPV\b|LVOT|승모판|삼첨판|폐동맥", re.I)
_AVA = re.compile(r"(?:\bAVA\b|aortic valve area|valve area|판막\s*면적)(?!\s*(?:i\b|index))[^0-9\n]{0,25}?"
                  r"(\d+(?:\.\d+)?)\s*(?:cm\s*(?:2|²|\^2)|cm2|㎠)", re.I)
_MEAN_GRAD = re.compile(r"(?:mean\s+(?:pressure\s+)?gradient|mean\s+PG|\bMG\b|mean\s+grad|평균\s*압력\s*차)"
                        r"[^0-9\n]{0,25}?(\d+(?:\.\d+)?)\s*mm\s*hg", re.I)
_VMAX = re.compile(r"(?:peak\s+(?:aortic\s+)?(?:jet\s+)?velocity|\bV\s?max\b|peak\s+AV\s+velocity|최대\s*(?:혈류\s*)?속도)"
                   r"[^0-9\n]{0,25}?(\d+(?:\.\d+)?)\s*(m/s|cm/s|m/sec|cm/sec)", re.I)
_EF = re.compile(r"(?<!RV)(?<!RV )(?:LVEF|LV\s*EF|LV ejection fraction|left ventricular ejection fraction|ejection fraction|"
                 r"\bEF\b|좌심실\s*(?:구혈률|박출률)|구혈률|박출률)(?:\s*\([^)]{0,20}\))?[^0-9%\n]{0,30}?"
                 r"(\d{1,2}(?:\.\d)?)(?:\s*%)?(?:\s*(?:-|–|to|~)\s*(\d{1,2}(?:\.\d)?))?\s*%", re.I)
_PRIOR = re.compile(r"\b(?:prior|previous|previously|was|baseline|last|old|in 20\d\d|compared (?:to|with))\b|이전|과거|지난", re.I)
_SEVERE_LV = re.compile(r"severe(?:ly)?\s+(?:reduced|depressed|impaired|decreased)\s+(?:global\s+)?(?:LV|left ventricular)?\s*"
                        r"(?:systolic\s+)?function|severe\s+(?:LV|left ventricular)\s+(?:systolic\s+)?dysfunction|"
                        r"좌심실\s*수축\s*기능\s*(?:의\s*)?(?:심한|중증)\s*(?:저하|감소)|(?:심한|중증)\s*좌심실\s*수축\s*기능\s*저하", re.I)


def _line_of(text: str, pos: int) -> str:
    start = max(text.rfind("\n", 0, pos), text.rfind(". ", 0, pos)) + 1
    ends = [i for i in (text.find("\n", pos), text.find(". ", pos)) if i != -1]
    return text[start:min(ends) if ends else len(text)]


def echo_findings(text: str) -> Dict[str, Any]:
    """Severe aortic stenosis (R064) and reduced ejection fraction (R065) from one echocardiogram report."""
    out: Dict[str, Any] = {"severe_as": False, "as_evidence": [], "lvef": None, "reduced_ef": False,
                           "ef_evidence": None, "prosthetic_av": False}
    prosthetic = _affirmed(_PROSTHETIC_AV, text)
    if prosthetic:
        out["prosthetic_av"] = True
        out["as_evidence"].append(f"prosthetic aortic valve ('{prosthetic.group(0)}'): native-valve criteria do not apply")
    else:
        m = _affirmed(_SEVERE_AS, text)
        if m:
            out["as_evidence"].append(f"'{m.group(0)}'")
        for rx, test, label in ((_AVA, lambda v, u: v < 1.0, "AVA {v:g} cm² (< 1.0)"),
                                (_MEAN_GRAD, lambda v, u: v >= 40, "mean gradient {v:g} mmHg (≥ 40)"),
                                (_VMAX, lambda v, u: (v / 100 if u.lower().startswith("cm") else v) >= 4.0,
                                 "peak velocity {v:g} {u} (≥ 4.0 m/s)")):
            for hit in rx.finditer(text):
                line = _line_of(text, hit.start())
                if rx is not _AVA and (not _AORTIC_CONTEXT.search(line) or _OTHER_VALVE.search(line)):
                    continue
                if rx is _AVA and _OTHER_VALVE.search(line) and not _AORTIC_CONTEXT.search(line):
                    continue
                v = float(hit.group(1))
                u = hit.group(2) if rx is _VMAX else ""
                if test(v, u):
                    out["as_evidence"].append(label.format(v=v, u=u))
                break
        out["severe_as"] = bool(out["as_evidence"])

    current: List[float] = []
    for hit in _EF.finditer(text):
        line = _line_of(text, hit.start())
        if _PRIOR.search(text[max(0, hit.start() - 40):hit.start()]) or re.search(r"\bRV\b|우심실", line[:20]):
            continue
        current.append(float(hit.group(2) or hit.group(1)))
    if current:
        out["lvef"] = current[0]
        if current[0] <= 40:
            out["reduced_ef"] = True
            out["ef_evidence"] = f"LVEF {current[0]:g}% (≤ 40%)"
    elif _affirmed(_SEVERE_LV, text):
        out["reduced_ef"] = True
        out["ef_evidence"] = "severely reduced LV systolic function (no number stated)"
    return out


def is_echo_report(code_text: str, category: str) -> bool:
    return bool(_ECHO.search(code_text or "")) or bool(re.search(r"(?:^|\s)cus(?:\s|$)", (category or "").lower()))
