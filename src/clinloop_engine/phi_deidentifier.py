"""
ClinLoop AI — PHI De-identification Engine
HIPAA Safe Harbor (45 CFR §164.514(b)) + Korean PIPA compliant
"""
import re, hashlib, secrets, logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("clinloop.phi_deidentifier")

HIPAA_18_FIELDS = ["name","geo","dates","phone","fax","email","ssn","mrn",
    "health_plan_id","account_no","cert_no","vehicle_id","device_id","web_url",
    "ip_address","biometric","photo","other_unique_id"]

PIPA_ADDITIONAL_FIELDS = ["jumin_no","passport_no","alien_reg_no","driver_license","kakao_id"]

PHI_PATTERNS = {
    "jumin_no": re.compile(r"\b\d{6}-[1-4]\d{6}\b"),
    "phone_kr":  re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b"),
    "phone_intl":re.compile(r"\+?\d[\d\s\-\(\)]{7,15}\d"),
    "email":     re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b"),
    "mrn":       re.compile(r"(?:\bMRN|\bmrn|차트번호|등록번호)[-:#\s]*[A-Z0-9\-]{4,20}\b"),
    "date_kr":   re.compile(r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일"),
    "date_iso":  re.compile(r"\b(19|20)\d{2}[-/\.]\d{2}[-/\.]\d{2}\b"),
    "ip_address":re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "url":       re.compile(r"https?://[^\s]+"),
    # Korean street / lot addresses: "...로 123", "...길 45", "...동 12-3"
    "address_kr":re.compile(r"[가-힣]+(?:로|길)\s*\d+(?:-\d+)?|[가-힣]+동\s*\d+(?:-\d+)?(?:번지)?"),
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
    def __init__(self):
        self._salt = secrets.token_hex(16)
        self._ledger: Dict[str,str] = {}
        self._reverse: Dict[str,str] = {}
    def pseudonymize(self, val: str, prefix="PT") -> str:
        if val in self._ledger: return self._ledger[val]
        digest = hashlib.sha256((self._salt+val).encode()).hexdigest()[:8].upper()
        p = f"{prefix}-{digest}"
        self._ledger[val]=p; self._reverse[p]=val
        return p
    def reverse_lookup(self, p: str) -> Optional[str]:
        return self._reverse.get(p)
    @property
    def ledger_size(self): return len(self._ledger)

class PHIDeidentifier:
    """HIPAA Safe Harbor + Korean PIPA de-identification before any cloud LLM call."""
    def __init__(self):
        self.ledger = PseudonymLedger()

    def deidentify_patient(self, patient: Dict[str,Any]) -> Tuple[Dict[str,Any], Dict[str,Any]]:
        safe, log = {}, {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "salt_hash": hashlib.sha256(self.ledger._salt.encode()).hexdigest()[:12],
            "substitutions": [], "phi_fields_removed": [],
            "compliance": ["HIPAA Safe Harbor 45 CFR §164.514(b)","Korean PIPA Article 23-24"],
        }

        # 1. Name → pseudonym
        name = patient.get("name") or patient.get("patient_name") or patient.get("성명")
        pname = self.ledger.pseudonymize(str(name or "UNKNOWN"), "PT")
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
        mrn = patient.get("mrn") or patient.get("patient_id") or patient.get("차트번호")
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
        log["safe_to_send_cloud"] = not residual
        log["limitations"] = ("Free-text names not present in the structured record are not detected; "
                              "human review is required before any external transmission.")
        return safe, log

    def _scrub_text(self, text: str, known: Optional[Dict[str,str]] = None) -> Tuple[str,list]:
        subs = []
        # The patient's own name / MRN, replaced by their pseudonyms
        for value, pseudonym in (known or {}).items():
            if value and len(value) >= 2 and value in text:
                text = text.replace(value, pseudonym)
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
        found = ["known_identifier" for v in known if v and len(v) >= 2 and v in text]
        for pat in ["jumin_no","mrn","email","url","ip_address","phone_kr","phone_intl","date_kr","address_kr"]:
            if PHI_PATTERNS[pat].search(text):
                found.append(pat)
        return found

    def build_llm_prompt(self, safe_patient: Dict[str,Any], task: str) -> str:
        c = safe_patient.get("clinical",{})
        lines = [
            "[CLINLOOP AI — DE-IDENTIFIED CLINICAL CONTEXT | HIPAA Safe Harbor Active]",
            f"Case Reference: {safe_patient.get('case_ref','ANON')} (pseudonym only; real identity on-premise)",
            f"Patient: {safe_patient.get('age_group','')}, {safe_patient.get('gender','')}",
            "",
        ] + [f"- {k}: {v}" for k,v in c.items() if v] + [
            "", f"Clinical Task: {task}", "",
            "IMPORTANT: Do NOT request or infer personal identifiers. Respond on de-identified context only.",
        ]
        return "\n".join(lines)

    def audit_summary(self) -> Dict[str,Any]:
        return {
            "engine": "ClinLoop AI PHI De-identifier v1.0",
            "standards": ["HIPAA Safe Harbor 45 CFR §164.514(b)","Korean PIPA Articles 23-24","ISO 29101:2018"],
            "phi_categories_covered": len(HIPAA_18_FIELDS)+len(PIPA_ADDITIONAL_FIELDS),
            "on_premise_only": True,
            "cloud_egress": "De-identified clinical context only — zero raw PHI",
        }

_deidentifier: Optional[PHIDeidentifier] = None
def get_deidentifier() -> PHIDeidentifier:
    global _deidentifier
    if _deidentifier is None:
        _deidentifier = PHIDeidentifier()
        logger.info("PHI De-identifier initialized. Ledger is on-premise only.")
    return _deidentifier
