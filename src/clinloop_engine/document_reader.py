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

_SECTION = re.compile(
    r"^\s*(?P<name>impressions?|conclusions?|opinion|findings|technique|comparison|clinical (?:history|information|indication)|"
    r"history|indication|recommendations?|결론|판독\s*결과|판독\s*소견|판독소견|소견|결과|진단|검사\s*소견|임상\s*정보|"
    r"비교|기법|권고|추천)\s*[:：\-]?\s*(?P<rest>.*)$", re.I | re.M)
_IMPRESSION = re.compile(r"impression|conclusion|opinion|결론|판독\s*결과|진단", re.I)
_FINDINGS = re.compile(r"findings|판독\s*소견|판독소견|소견|검사\s*소견|결과", re.I)
_RECOMMEND = re.compile(r"recommendation|권고|추천", re.I)
_SIGNATURE = re.compile(r"^\s*(?:electronically signed|signed by|radiologist|reading physician|dictated|판독의|판독\s*전문의|"
                        r"영상의학과\s*전문의|서명)\b.*$", re.I | re.M)
_DATE = re.compile(r"(?P<y>(?:19|20)\d{2})\s*(?:[-./]|년)\s*(?P<m>\d{1,2})\s*(?:[-./]|월)\s*(?P<d>\d{1,2})\s*일?")
_DATE_LABEL = re.compile(r"(?:exam(?:ination)?|study|procedure|scan|acquisition|service)\s*date|date of (?:exam|study|service)|"
                         r"검사\s*일(?:자|시)?|촬영\s*일(?:자|시)?|시행\s*일", re.I)
_DOB = re.compile(r"birth|dob|생년월일|생일", re.I)
_TITLE_LABEL = re.compile(r"^\s*(?:exam(?:ination)?|study|procedure|검사\s*명|검사|검사\s*항목)\s*(?:name)?\s*[:：]\s*(.+)$", re.I | re.M)
_MODALITY_WORDS = re.compile(r"\b(CT|MRI|MR|PET|US|ultrasound|sonograph\w*|x-?ray|radiograph\w*|mammogra\w*|LDCT)\b|"
                             r"초음파|흉부|복부|자기공명|단순\s*촬영|유방\s*촬영", re.I)
_PATHOLOGY = re.compile(r"patholog|cytolog|biopsy specimen|병리|조직\s*검사\s*결과|세포\s*검사", re.I)


def _find_date(text: str) -> Optional[str]:
    lines = text.splitlines()
    candidates: List[Tuple[int, str]] = []
    for i, line in enumerate(lines):
        if _DOB.search(line):
            continue
        for m in _DATE.finditer(line):
            try:
                d = datetime(int(m.group("y")), int(m.group("m")), int(m.group("d")))
            except ValueError:
                continue
            labelled = bool(_DATE_LABEL.search(line)) or (i > 0 and _DATE_LABEL.search(lines[i - 1]) and len(line) < 40)
            candidates.append((0 if labelled else 1, d.date().isoformat()))
    return sorted(candidates)[0][1] if candidates else None


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
        body = (sm.group("rest") + "\n" + text[sm.end():end]).strip()
        body = _SIGNATURE.sub("", body).strip()
        name = sm.group("name")
        kind = ("impression" if _IMPRESSION.fullmatch(name.strip()) or _IMPRESSION.match(name) else
                "recommendation" if _RECOMMEND.match(name) else
                "findings" if _FINDINGS.match(name) else "other")
        if body and kind != "other":
            sections.setdefault(kind, body)
    conclusion = sections.get("impression") or sections.get("findings") or _SIGNATURE.sub("", text).strip()
    if sections.get("recommendation") and sections["recommendation"] not in conclusion:
        conclusion += "\n" + sections["recommendation"]
    conclusion = re.sub(r"\s*\n\s*", " ", conclusion).strip()
    return {"title": title, "date": _find_date(text), "conclusion": conclusion[:4000],
            "section": "impression" if "impression" in sections else "findings" if "findings" in sections else "whole text",
            "pathology": bool(_PATHOLOGY.search(text)) and not _MODALITY_WORDS.search(title or "")}


def outside_report_resource(patient_id: str, content: bytes, extracted: Dict[str, Any], parsed: Dict[str, Any],
                            uploaded_at: Optional[str] = None, confirmed_by: Optional[str] = None) -> Dict[str, Any]:
    """
    FHIR DiagnosticReport for an outside report (identifiers scrubbed from the stored text).

    `confirmed_by`: the person who checked the extracted title, date and impression
    against the original at upload. Unconfirmed text keeps a "verify" flag on every loop.
    """
    from .phi_deidentifier import PHIDeidentifier
    sha = hashlib.sha256(content).hexdigest()
    conclusion, _ = PHIDeidentifier()._scrub_text(parsed["conclusion"])
    tags = ["outside-report", "ocr" if extracted["method"] == "ocr" else "pdf-text"]
    if confirmed_by:
        tags.append("human-confirmed")
    when = parsed["date"] + "T00:00:00" if parsed.get("date") else None
    if not when:
        tags.append("date-unknown")
        when = uploaded_at or datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0).isoformat()
    resource: Dict[str, Any] = {
        "resourceType": "DiagnosticReport",
        "id": "ext-" + sha[:32],
        "meta": {"tag": [{"system": CLINLOOP_TAG_SYSTEM, "code": t} for t in tags]},
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                                  "code": "PAT" if parsed.get("pathology") else "RAD"}]}],
        "code": {"text": parsed.get("title") or "Outside report"},
        "subject": {"reference": f"Patient/{patient_id}"},
        "effectiveDateTime": when,
        "conclusion": conclusion,
    }
    if confirmed_by:
        resource["resultsInterpreter"] = [{"display": f"Text confirmed against the original by {confirmed_by}"}]
    if extracted.get("confidence") is not None:
        resource["extension"] = [{"url": OCR_CONFIDENCE_URL, "valueDecimal": float(extracted["confidence"])}]
    return resource
