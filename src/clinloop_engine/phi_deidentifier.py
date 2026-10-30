"""
ClinLoop AI — PHI de-identification (pattern-based)

Removes or generalises the identifier types listed in the HIPAA Safe Harbor method
(45 CFR §164.514(b)) and in Korea's PIPA, by regular expressions. Pattern matching misses
identifiers it has no pattern for (for example names in free text), so its output is not
de-identified in the legal sense until reviewed; it has not been independently validated.
Not used by the clinical pipeline (ClinLoop sends no patient data to external AI services).
"""
import re, hashlib, secrets, logging, threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("clinloop.phi_deidentifier")

HIPAA_18_FIELDS = ["name","geo","dates","phone","fax","email","ssn","mrn",
    "health_plan_id","account_no","cert_no","vehicle_id","device_id","web_url",
    "ip_address","biometric","photo","other_unique_id"]

PIPA_ADDITIONAL_FIELDS = ["jumin_no","passport_no","alien_reg_no","driver_license","kakao_id"]

PHI_PATTERNS = {
    "jumin_no": re.compile(r"(?<!\d)\d{6}\s*[-‐‑–]?\s*[1-8]\d{6}(?!\d)"),
    "phone_kr":  re.compile(r"\b01[016789][ .-]?\d{3,4}[ .-]?\d{4}\b"),
    "phone_intl":re.compile(r"\+\d{1,3}[ .-]?\(?\d{1,4}\)?(?:[ .-]?\d{2,4}){2,3}\b|"
                             r"\(\d{3}\)[ .-]?\d{3}[ .-]?\d{4}\b|"
                             r"\b\d{3}[.-]\d{3}[.-]\d{4}\b|\b0\d{1,2}[ .-]\d{3,4}[ .-]\d{4}\b"),
    "email":     re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b"),
    "mrn":       re.compile(r"(?:\bMRN|차트번호|등록번호)[-:#\s]*[A-Z0-9\-]{4,64}\b", re.I),
    "date_kr":   re.compile(r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일"),
    "date_iso":  re.compile(r"\b(19|20)\d{2}[-/\.]\d{1,2}[-/\.]\d{1,2}\b"),
    "date_mdy": re.compile(r"\b\d{1,2}[/.]\d{1,2}[/.]((?:19|20)\d{2})\b"),
    "ip_address":re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "url":       re.compile(r"https?://[^\s]+"),
    # Korean street / lot addresses: "...로 123", "...길 45", "...동 12-3"
    "address_kr":re.compile(r"(?:(?:[가-힣]+(?:특별자치시|특별시|광역시|특별자치도|도|시|군|구|읍|면))\s+){0,5}"
                             r"(?:[가-힣0-9·]+(?:로|길)\s*\d+(?:-\d+)?|[가-힣]+동\s*\d+(?:-\d+)?(?:번지)?)"
                             r"(?:\s+\d+(?:동|층|호)){0,3}"),
}

def _generalize_age(age: int) -> str:
    if age >= 90: return "90세 이상 (90+)"
    d = (age // 10) * 10
    return f"{d}대 ({d}~{d+9}세)"

def _generalize_date(s: str) -> str:
    for fmt in ["%Y-%m-%d","%Y/%m/%d","%Y.%m.%d"]:
        try: return f"{datetime.strptime(s.strip(),fmt).year}년"
        except: pass
    return "[날짜 삭제]"

class PseudonymLedger:
    """One in-memory linkage context, not anonymisation or a persistent key service.

    Raw identifiers and the reverse map remain sensitive on this local process.
    Different ledgers deliberately produce different pseudonyms. A prefix is part
    of the identity namespace; a name and an MRN must never collide by value alone.
    """
    def __init__(self):
        self._salt = secrets.token_hex(32)
        self._ledger: Dict[Tuple[str, str], str] = {}
        self._reverse: Dict[str, str] = {}
        self._lock = threading.RLock()

    def pseudonymize(self, val: str, prefix: str = "PT") -> str:
        key = (prefix, val)
        with self._lock:
            if key not in self._ledger:
                digest = hashlib.sha256((self._salt + "|" + prefix + "|" + val).encode()).hexdigest()[:24].upper()
                pseudonym = f"{prefix}-{digest}"
                self._ledger[key] = pseudonym
                self._reverse[pseudonym] = val
            return self._ledger[key]

    def reverse_lookup(self, pseudonym: str) -> Optional[str]:
        with self._lock:
            return self._reverse.get(pseudonym)

    @property
    def ledger_size(self) -> int:
        with self._lock:
            return len(self._ledger)

class PHIDeidentifier:
    """Pattern-only research helper for flat records; never authorizes cloud egress."""
    def __init__(self):
        self.ledger = PseudonymLedger()

    def deidentify_patient(self, patient: Dict[str,Any]) -> Tuple[Dict[str,Any], Dict[str,Any]]:
        if not isinstance(patient, dict) or "resourceType" in patient or "entry" in patient:
            raise ValueError("FHIR bundles/resources are not supported by the flat-record privacy helper")
        safe, log = {}, {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "salt_hash": hashlib.sha256(self.ledger._salt.encode()).hexdigest()[:12],
            "substitutions": [], "phi_fields_removed": [],
            "reference_frameworks": ["HIPAA Safe Harbor 45 CFR §164.514(b)","Korean PIPA Article 23-24"],
        }

        # 1. Name → pseudonym
        name = patient.get("name") or patient.get("patient_name") or patient.get("성명")
        mrn = patient.get("mrn") or patient.get("patient_id") or patient.get("차트번호")
        # Names are not unique patient identifiers. Missing identity creates a
        # record-local reference, never one shared UNKNOWN patient.
        stable_identity = bool(mrn)
        identity = str(mrn) if stable_identity else secrets.token_hex(24)
        pname = self.ledger.pseudonymize(identity, "PT")
        log["stable_identity_available"] = stable_identity
        safe["patient_ref"] = pname
        if name: log["phi_fields_removed"].append("name"); log["substitutions"].append({"field":"name","pseudonym":pname})

        # 2. Age → decade group
        age = patient.get("age") or patient.get("나이")
        if age is not None:
            try: safe["age_group"] = _generalize_age(int(age))
            except: safe["age_group"] = "[나이 불명]"
            log["substitutions"].append({"field":"age","value":safe["age_group"]})

        # 3. DOB → year only
        dob = patient.get("dob") or patient.get("birth_date") or patient.get("생년월일")
        if dob: safe["birth_year"]=_generalize_date(str(dob)); log["phi_fields_removed"].append("dob")

        # 4. Gender — safe
        if patient.get("gender"): safe["gender"]=patient["gender"]

        # 5. 주민번호 — REMOVE
        if patient.get("jumin_no") or patient.get("주민번호"):
            log["phi_fields_removed"].append("jumin_no"); log["substitutions"].append({"field":"jumin_no","action":"removed"})

        # 6. MRN → pseudonym
        if mrn:
            pmrtn = self.ledger.pseudonymize(str(mrn),"MRN")
            safe["case_ref"] = pmrtn; log["phi_fields_removed"].append("mrn")

        # 7. Clinical text — scrub embedded PHI, including the patient's own
        #    known identifiers wherever they reappear in free text
        known = {}
        if name: known[str(name)] = pname
        if mrn: known[str(mrn)] = safe["case_ref"]
        clinical_fields = ["diagnosis","진단","finding","소견","medication","약물",
            "icd_code","imaging_summary","clinical_context","risk_score","guidelines_triggered","nodule_size"]
        safe["clinical"] = {}
        residual: List[str] = []
        for f in clinical_fields:
            if patient.get(f):
                cleaned, subs = self._scrub_text(str(patient[f]), known)
                safe["clinical"][f] = cleaned
                log["substitutions"].extend(subs)
                residual.extend(self._residual_identifiers(cleaned, known))

        # 8. Hard-remove direct identifiers
        for f in ["phone","전화번호","email","이메일","address","주소","fax","팩스",
                  "ip_address","passport_no","driver_license","kakao_id","insurance_id"]:
            if patient.get(f): log["phi_fields_removed"].append(f)

        log["ledger_size"] = self.ledger.ledger_size
        log["phi_fields_removed_total"] = len(log["phi_fields_removed"])
        # Regex scrubbing cannot find names of people who are not in the
        # structured record (relatives, other patients) or unusual address
        # formats, so this is only a gate against *known* identifier patterns.
        log["residual_identifiers"] = residual
        log["known_pattern_check_passed"] = not residual
        log["human_review_required"] = True
        log["safe_to_send_cloud"] = False
        log["limitations"] = ("Free-text names not present in the structured record are not detected; "
                              "human review is required before any external transmission.")
        return safe, log

    @staticmethod
    def _known_pattern(value: str):
        if re.search(r"[가-힣]", value):
            return re.compile(r"(?<!\w)" + re.escape(value) +
                              r"(?=$|[^\w]|(?:님|씨)?(?:은|는|이|가|의|을|를)?(?=$|[^\w]))")
        return re.compile(r"(?<!\w)" + re.escape(value) + r"(?!\w)")

    def _scrub_text(self, text: str, known: Optional[Dict[str,str]] = None) -> Tuple[str,list]:
        subs = []
        # The patient's own name / MRN, replaced by their pseudonyms
        for value, pseudonym in sorted((known or {}).items(), key=lambda item: len(item[0]), reverse=True):
            if value and len(value) >= 2:
                pattern = self._known_pattern(value)
                text, count = pattern.subn(lambda _: pseudonym, text)
                if count:
                    subs.append({"field":"embedded_known_identifier","action":"pseudonymized_in_text"})
        # Order matters: structured patterns (dates, MRNs) before the broad
        # international-phone pattern, which would otherwise swallow them.
        for name, pat in [("jumin","jumin_no"),("mrn","mrn"),("email","email"),("url","url"),
                          ("ip","ip_address"),("phone_kr","phone_kr")]:
            if PHI_PATTERNS[pat].search(text):
                text = PHI_PATTERNS[pat].sub(f"[{name} 삭제]", text)
                subs.append({"field":f"embedded_{name}","action":"removed_in_text"})
        if PHI_PATTERNS["date_iso"].search(text):
            text = PHI_PATTERNS["date_iso"].sub(lambda m: _generalize_date(m.group(0)), text)
            subs.append({"field":"embedded_date","action":"year_only_in_text"})
        if PHI_PATTERNS["date_mdy"].search(text):
            text = PHI_PATTERNS["date_mdy"].sub(lambda m: m.group(1) + "년", text)
            subs.append({"field":"embedded_date","action":"year_only_in_text"})
        if PHI_PATTERNS["date_kr"].search(text):
            text = PHI_PATTERNS["date_kr"].sub(lambda m: m.group(0).split("년")[0] + "년", text)
            subs.append({"field":"embedded_date_kr","action":"year_only_in_text"})
        for name, pat in [("phone","phone_intl"),("address","address_kr")]:
            if PHI_PATTERNS[pat].search(text):
                text = PHI_PATTERNS[pat].sub(f"[{name} 삭제]", text)
                subs.append({"field":f"embedded_{name}","action":"removed_in_text"})
        return text, subs

    def _residual_identifiers(self, text: str, known: Dict[str,str]) -> List[str]:
        """Identifier patterns still present after scrubbing (should be empty)."""
        found = ["known_identifier" for v in known if v and len(v) >= 2 and self._known_pattern(v).search(text)]
        for pat in ["jumin_no","mrn","email","url","ip_address","phone_kr","phone_intl","date_kr","address_kr"]:
            if PHI_PATTERNS[pat].search(text):
                found.append(pat)
        return found

    def build_llm_prompt(self, safe_patient: Dict[str,Any], task: str) -> str:
        c = safe_patient.get("clinical",{})
        lines = [
            "[CLINLOOP AI — PATTERN-SCRUBBED RESEARCH CONTEXT | HUMAN PRIVACY REVIEW REQUIRED]",
            f"Case Reference: {safe_patient.get('case_ref','ANON')} (pseudonym only; real identity on-premise)",
            f"Patient: {safe_patient.get('age_group','')}, {safe_patient.get('gender','')}",
            "",
        ] + [f"- {k}: {v}" for k,v in c.items() if v] + [
            "", f"Clinical Task: {task}", "",
            "IMPORTANT: Do NOT request or infer personal identifiers. This pattern-scrubbed context is unverified; human privacy review is required.",
        ]
        return "\n".join(lines)

    def audit_summary(self) -> Dict[str,Any]:
        return {
            "engine": "ClinLoop AI PHI De-identifier v1.0",
            "reference_frameworks": ["HIPAA Safe Harbor 45 CFR §164.514(b)","Korean PIPA Articles 23-24","ISO 29101:2018"],
            "listed_identifier_categories": len(HIPAA_18_FIELDS)+len(PIPA_ADDITIONAL_FIELDS),
            "pattern_categories": len(PHI_PATTERNS),
            "independently_validated": False,
            "human_review_required": True,
            "ledger_storage": "In-process sensitive linkage; not an encrypted or persistent identity service",
            "external_transmission_authorized": False,
            "cloud_egress": "Not authorized by this helper; independent human privacy review required",
        }

_deidentifier: Optional[PHIDeidentifier] = None
def get_deidentifier() -> PHIDeidentifier:
    global _deidentifier
    if _deidentifier is None:
        _deidentifier = PHIDeidentifier()
        logger.info("PHI De-identifier initialized. Ledger is on-premise only.")
    return _deidentifier
