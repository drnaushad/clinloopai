"""
document_reader.py — Reports from other hospitals: PDF text and OCR (Korean and English)

A patient brings a CT report from another hospital on paper, as a scanned PDF
or as a phone photo. ClinLoop reads it into text, finds the study, the date
and the impression, and creates a FHIR DiagnosticReport that runs through
the same report-reading logic as the hospital's own reports.

  * PDF with a text layer → text extracted directly (exact)
  * scanned PDF or image  → OCR with Tesseract (kor+eng), with a confidence score

Because OCR and outside formats can be wrong, every loop created from an
outside report asks a human to check the text and date against the original
document. Only the impression (identifiers scrubbed) and the study title are
stored; the uploaded file is not kept, only its SHA-256 hash.
"""

import hashlib
import io
import re
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .imaging_fhir import CLINLOOP_TAG_SYSTEM, OCR_CONFIDENCE_URL

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 20
OCR_LANGS = "kor+eng"


class DocumentError(ValueError):
    pass


def ocr_available() -> bool:
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return shutil.which("tesseract") is not None


def _ocr_image(img) -> Tuple[str, Optional[float]]:
    import pytesseract
    from PIL import ImageOps
    img = ImageOps.grayscale(img)
    if img.width < 1500:                      # small photos/scans read better upscaled
        scale = 1500 / max(1, img.width)
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    img = ImageOps.autocontrast(img)
    text = pytesseract.image_to_string(img, lang=OCR_LANGS, config="--psm 6")
    data = pytesseract.image_to_data(img, lang=OCR_LANGS, config="--psm 6", output_type=pytesseract.Output.DICT)
    conf = [float(c) for c, w in zip(data["conf"], data["text"]) if str(w).strip() and float(c) >= 0]
    return text, (sum(conf) / len(conf) if conf else None)


def extract_text(content: bytes, filename: str = "") -> Dict[str, Any]:
    """Text of a PDF or image: {"text", "method": "pdf-text"|"ocr", "confidence", "pages"}."""
    if not content:
        raise DocumentError("Empty file")
    if len(content) > MAX_BYTES:
        raise DocumentError(f"File larger than {MAX_BYTES // (1024 * 1024)} MB")
    is_pdf = content[:5] == b"%PDF-" or filename.lower().endswith(".pdf")
    if is_pdf:
        import pdfplumber
        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                pages = pdf.pages[:MAX_PAGES]
                texts = [(p.extract_text() or "") for p in pages]
                if sum(len(t.strip()) for t in texts) >= 40 * max(1, len(pages)) * 0.5:
                    return {"text": "\n".join(texts), "method": "pdf-text", "confidence": None, "pages": len(pages)}
                if not ocr_available():
                    raise DocumentError("This PDF is a scan without text; OCR (Tesseract) is not installed on the server")
                results = [_ocr_image(p.to_image(resolution=300).original) for p in pages]
        except DocumentError:
            raise
        except Exception as e:  # malformed PDF
            raise DocumentError(f"Could not read the PDF: {type(e).__name__}") from e
    else:
        if not ocr_available():
            raise DocumentError("OCR (Tesseract) is not installed on the server")
        from PIL import Image, UnidentifiedImageError
        try:
            img = Image.open(io.BytesIO(content))
        except UnidentifiedImageError as e:
            raise DocumentError("Not a PDF or an image file") from e
        results = [_ocr_image(img)]
    confs = [c for _, c in results if c is not None]
    return {"text": "\n".join(t for t, _ in results), "method": "ocr",
            "confidence": round(sum(confs) / len(confs), 1) if confs else None, "pages": len(results)}


# ── Parsing a report ────────────────────────────────────────────────────────

# A heading is the word alone on its line, or followed by ":" ("Comparison with outside CT is
# recommended." and "결과적으로 …" are sentences, not headings)
_SECTION = re.compile(
    r"^\s*(?P<name>impressions?|conclusions?|opinion|findings|technique|comparison|clinical (?:history|information|indication)|"
    r"history|indication|recommendations?|결론|판독\s*결과|판독\s*소견|판독소견|소견|결과|진단|검사\s*소견|임상\s*정보|"
    r"비교|기법|권고|추천)\s*(?:[:：]\s*(?P<rest>.*)|-\s+(?P<rest2>.*)|$)", re.I | re.M)
_IMPRESSION = re.compile(r"impression|conclusion|opinion|결론|판독\s*결과|진단", re.I)
_FINDINGS = re.compile(r"findings|판독\s*소견|판독소견|소견|검사\s*소견|결과", re.I)
_RECOMMEND = re.compile(r"recommendation|권고|추천", re.I)
_SIGNATURE = re.compile(r"^\s*(?:electronically signed|signed by|radiologist|reading physician|dictated|판독의|판독\s*전문의|"
                        r"영상의학과\s*전문의|서명)\b.*$", re.I | re.M)
_DATE = re.compile(r"(?P<y>(?:19|20)\d{2})\s*(?:[-./]|년)\s*(?P<m>\d{1,2})\s*(?:[-./]|월)\s*(?P<d>\d{1,2})\s*일?"
                   r"|(?<!\d)(?P<a>\d{1,2})/(?P<b>\d{1,2})/(?P<y2>(?:19|20)\d{2})(?!\d)")
_DATE_LABEL = re.compile(r"(?:exam(?:ination)?|study|procedure|scan|acquisition|service)\s*date|date of (?:exam|study|service)|"
                         r"검사\s*일(?:자|시)?|촬영\s*일(?:자|시)?|시행\s*일", re.I)
_DOB = re.compile(r"birth|dob|생년월일|생일", re.I)
_TITLE_LABEL = re.compile(r"^\s*(?:exam(?:ination)?|study|procedure|검사\s*명|검사|검사\s*항목)\s*(?:name)?\s*[:：]\s*(.+)$", re.I | re.M)
_MODALITY_WORDS = re.compile(r"\b(CT|MRI|MR|PET|US|ultrasound|sonograph\w*|x-?ray|radiograph\w*|mammogra\w*|LDCT)\b|"
                             r"초음파|흉부|복부|자기공명|단순\s*촬영|유방\s*촬영", re.I)
_PATHOLOGY = re.compile(r"patholog|cytolog|biopsy specimen|병리|조직\s*검사\s*결과|세포\s*검사", re.I)


def _date_of(m: re.Match) -> Optional[datetime]:
    try:
        if m.group("y"):
            return datetime(int(m.group("y")), int(m.group("m")), int(m.group("d")))
        a, b, y = int(m.group("a")), int(m.group("b")), int(m.group("y2"))
        if a > 12 and b <= 12:
            return datetime(y, b, a)          # day/month/year
        if b > 12 and a <= 12:
            return datetime(y, a, b)          # month/day/year
        return None                           # 05/06/2026 is ambiguous: never guessed
    except ValueError:
        return None


def _find_date(text: str) -> Optional[str]:
    """
    The exam date: a date labelled as the exam/study date wins; otherwise the latest date
    in the document (comparison dates are earlier). Birth dates are excluded, whether the
    label is on the same line, the line above, or a table header.
    """
    lines = text.splitlines()
    dob_values = set()
    for i, line in enumerate(lines):
        if _DOB.search(line):
            for j in (i, i + 1):
                if j < len(lines):
                    found = [_date_of(m) for m in _DATE.finditer(lines[j])]
                    found = [d for d in found if d]
                    if found and (j == i or not _DATE_LABEL.search(lines[i])):
                        dob_values.add(min(found))          # the earliest date near a DOB label
                    elif found and j == i + 1:
                        dob_values.add(min(found))          # table header with both labels: DOB is the earlier
    labelled, other = [], []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for i, line in enumerate(lines):
        for m in _DATE.finditer(line):
            d = _date_of(m)
            if not d or d in dob_values or d > now.replace(year=now.year + 1):
                continue
            is_label = bool(_DATE_LABEL.search(line)) or (i > 0 and _DATE_LABEL.search(lines[i - 1]) and len(line) < 60)
            (labelled if is_label else other).append(d)
    pool = labelled or other
    return max(pool).date().isoformat() if pool else None


# Identifier removal that never touches clinical content (dates, sizes, intervals, words)
_ID_PATTERNS = [
    (re.compile(r"\b\d{6}\s*-\s*[1-4]\d{6}\b"), "[주민번호 삭제]"),                       # resident registration no.
    (re.compile(r"\b01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}\b|\b0\d{1,2}-\d{3,4}-\d{4}\b"), "[전화 삭제]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[email 삭제]"),
    (re.compile(r"(?i)\b(?:MRN|patient\s*(?:no|number|id)|hospital\s*(?:no|number)|chart\s*no)\s*[:#.]?\s*[A-Z0-9-]{4,}"), "[ID 삭제]"),
    # A bare "ID" only in capitals and followed by a code with a digit ("Refer to ID clinic" is clinical text)
    (re.compile(r"\bID\s*[:#.]?\s*(?=[A-Za-z0-9-]*\d)[A-Za-z0-9-]{4,}"), "[ID 삭제]"),
    (re.compile(r"\+\d{1,3}[\s.-]?\(?\d{1,4}\)?(?:[\s.-]?\d{2,4}){2,4}"), "[전화 삭제]"),     # international
    (re.compile(r"(?i)\b(?:home\s+)?(?:address|addr\.?)\s*[:：][^\n]*|(?:주소|거주지)\s*[:：][^\n]*"), "[주소 삭제]"),
    (re.compile(r"(?i)\b(daughter|son|wife|husband|mother|father|sister|brother|guardian|caregiver|next of kin|nok|"
                r"emergency contact)(\s*(?:[:：]|is|,)?\s*)(?:(?:mr|mrs|ms|dr)\.?\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?"),
     r"\1\2[이름 삭제]"),
    (re.compile(r"(보호자|배우자|남편|아내|딸|아들)(\s*[:：]\s*|\s+)(?=[가-힣]{2,4}(?:\s|님|씨|,|$|\())[가-힣]{2,4}"
                r"(?<!동반)(?<!내원)(?<!면담)(?<!설명)"), r"\1\2[이름 삭제]"),
    (re.compile(r"(?:등록\s*번호|병록\s*번호|환자\s*번호|차트\s*번호)\s*[:：]?\s*[A-Za-z0-9-]{4,}"), "[ID 삭제]"),
    (re.compile(r"(?i)\b(?:patient(?:'s)?\s*name|patient|name)\s*[:：]\s*[^\n,;]{1,40}"), "[이름 삭제]"),
    (re.compile(r"(?:환자\s*명|성\s*명|이\s*름)\s*[:：]\s*[^\s,;]{1,20}"), "[이름 삭제]"),
    (re.compile(r"(?i)\b(?:DOB|D\.O\.B\.?|date of birth|birth\s*date)\s*[:：]?\s*[\d./-]{6,10}"), "[생년월일 삭제]"),
    (re.compile(r"생년월일\s*[:：]?\s*[\d년월일./\s-]{6,16}"), "[생년월일 삭제]"),
]
_HEADER_LINE = re.compile(r"(?i)^\s*(?:patient|name|dob|date of birth|mrn|address|phone|tel|sex|age|"
                          r"환자|성명|이름|생년월일|등록번호|주소|전화|연락처|성별|나이)\b.*$", re.M)
_TITLE_WORDS = re.compile(
    r"\b(?:PET/CT|PET-CT|LDCT|CT|CTA|MRI|MRA|MR|PET|US|ultrasound|sonography|x-?ray|radiograph(?:y)?|mammograph\w*|"
    r"low[- ]dose|chest|thorax|abdomen|abdominal|pelvis|pelvic|head|brain|neck|thyroid|breast|spine|liver|kidney|renal|"
    r"adrenal|pancreas|whole[- ]body|with(?:out)?|and|contrast|enhanced|non-?contrast|PA|AP|lateral)\b"
    r"|흉부|복부|골반|두부|뇌|경부|갑상선|유방|척추|간|신장|부신|췌장|조영|비조영|저선량|초음파|자기공명|단순\s*촬영|촬영", re.I)


def scrub_identifiers(text: str, names: Optional[List[str]] = None) -> str:
    """Remove identifiers (resident no., phone, MRN, labelled names, the patient's own names); keep clinical text."""
    text = text or ""
    for rx, repl in _ID_PATTERNS:
        text = rx.sub(repl, text)
    for n in sorted({n.strip() for n in (names or []) if n and len(n.strip()) >= 2}, key=len, reverse=True):
        # Whole words only: a patient called "Li" must not turn "lipid" or "clinic" into "[이름 삭제]pid".
        # Korean names may carry a particle (홍길동님, 홍길동은), so only the start is bounded for Hangul.
        pattern = re.escape(n).replace(r"\ ", r"\s+")
        if re.search(r"[가-힣]", n):
            text = re.sub(r"(?<![가-힣])" + pattern, "[이름 삭제]", text)
        else:
            text = re.sub(r"(?<![A-Za-z])" + pattern + r"(?![A-Za-z])", "[이름 삭제]", text, flags=re.I)
    return text


def clean_title(title: Optional[str]) -> Optional[str]:
    """Only the clinical words of a study title ("CT Chest - Hong Gil-dong" → "CT Chest")."""
    if not title:
        return None
    words = [m.group(0) for m in _TITLE_WORDS.finditer(title)]
    while words and words[-1].lower() in ("and", "with", "without"):
        words.pop()
    return " ".join(words) or None


def parse_report(text: str) -> Dict[str, Any]:
    """Study title, date and impression from report text (English or Korean)."""
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text or "")        # hyphenated line breaks
    text = re.sub(r"[ \t]+", " ", text)
    # Letter-only OCR confusions of units ("1.3 crn"); digit look-alikes are never guessed
    text = re.sub(r"(?<=\d)\s?(?:crn|cn|c m|ern)(?![a-z])", " cm", text)
    text = re.sub(r"(?<=\d)\s?(?:rnm|rn m|m m)(?![a-z])", " mm", text)
    title = None
    m = _TITLE_LABEL.search(text)
    if m and _MODALITY_WORDS.search(m.group(1)):
        title = m.group(1).strip()
    if not title:
        title = next((ln.strip() for ln in text.splitlines()
                      if _MODALITY_WORDS.search(ln) and len(ln.strip()) < 80 and not _SECTION.match(ln)), None)
    sections: Dict[str, str] = {}
    matches = list(_SECTION.finditer(text))
    for i, sm in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = ((sm.group("rest") or sm.group("rest2") or "") + "\n" + text[sm.end():end]).strip()
        body = _SIGNATURE.sub("", body).strip()
        name = sm.group("name")
        kind = ("impression" if _IMPRESSION.fullmatch(name.strip()) or _IMPRESSION.match(name) else
                "recommendation" if _RECOMMEND.match(name) else
                "findings" if _FINDINGS.match(name) else "other")
        if body and kind != "other":
            sections.setdefault(kind, body)
    conclusion = sections.get("impression") or sections.get("findings") \
        or _HEADER_LINE.sub("", _SIGNATURE.sub("", text)).strip()      # no sections: drop header/identity lines
    if sections.get("recommendation") and sections["recommendation"] not in conclusion:
        conclusion += "\n" + sections["recommendation"]
    conclusion = re.sub(r"\s*\n\s*", " ", conclusion).strip()
    return {"title": clean_title(title), "date": _find_date(text), "conclusion": conclusion[:4000],
            "section": "impression" if "impression" in sections else "findings" if "findings" in sections else "whole text",
            "pathology": bool(_PATHOLOGY.search(text)) and not _MODALITY_WORDS.search(title or "")}


def outside_report_resource(patient_id: str, content: bytes, extracted: Dict[str, Any], parsed: Dict[str, Any],
                            uploaded_at: Optional[str] = None, confirmed_by: Optional[str] = None,
                            names: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    FHIR DiagnosticReport for an outside report (identifiers scrubbed from the stored text).

    `confirmed_by`: the person who checked the extracted title, date and impression
    against the original at upload. Unconfirmed text keeps a "verify" flag on every loop.
    """
    sha = hashlib.sha256(content).hexdigest()
    conclusion = scrub_identifiers(parsed["conclusion"], names)
    tags = ["outside-report", "ocr" if extracted["method"] == "ocr" else "pdf-text"]
    if confirmed_by:
        tags.append("human-confirmed")
    when = parsed["date"] + "T00:00:00" if parsed.get("date") else None
    if not when:
        tags.append("date-unknown")
        when = uploaded_at or datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0).isoformat()
    resource: Dict[str, Any] = {
        "resourceType": "DiagnosticReport",
        "id": "ext-" + hashlib.sha256(f"{patient_id}|{sha}".encode()).hexdigest()[:32],
        "meta": {"tag": [{"system": CLINLOOP_TAG_SYSTEM, "code": t} for t in tags]},
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                                  "code": "PAT" if parsed.get("pathology") else "RAD"}]}],
        "code": {"text": clean_title(parsed.get("title")) or "Outside report"},
        "subject": {"reference": f"Patient/{patient_id}"},
        "effectiveDateTime": when,
        "conclusion": conclusion,
    }
    if confirmed_by:
        resource["resultsInterpreter"] = [{"display": f"Text confirmed against the original by {confirmed_by}"}]
    if extracted.get("confidence") is not None:
        resource["extension"] = [{"url": OCR_CONFIDENCE_URL, "valueDecimal": float(extracted["confidence"])}]
    return resource
