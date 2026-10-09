"""
pacs_client.py — Read imaging study labels from the hospital PACS (DICOMweb QIDO-RS)

ClinLoop asks the PACS which studies a patient has had: modality, body part,
description, date, number of series and images. It never retrieves pixel
data. Each study becomes a FHIR ImagingStudy, so "was the follow-up CT of the
adrenals done?" is answered from the PACS itself rather than inferred from
report titles.

Works with any DICOMweb server (Orthanc, dcm4chee, Sectra, Infinitt, Google
Cloud Healthcare, …). Read-only.

Pixel data is retrieved (WADO-RS) only by the automatic image scanner
(imaging_scanner.py), which is off unless the hospital turns it on, and only
for studies an enabled imaging model applies to. Images are analysed in memory
and never stored.

Configuration (environment):
  CLINLOOP_PACS_DICOMWEB     QIDO-RS base URL, e.g. https://pacs.hospital.local/dicom-web
  CLINLOOP_PACS_TOKEN        bearer token (optional)
  CLINLOOP_PACS_ID_SYSTEM    FHIR Patient.identifier system whose value is the PACS PatientID
                             (default: the identifier typed MR)
  CLINLOOP_PACS_MATCH_FHIR_ID=1  also query by the FHIR Patient id when the patient has no MRN
                             (only if the PACS really uses those ids: otherwise another
                             person's studies could match)

Every study returned is checked: its PatientID must equal the one queried.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional

import requests

from .imaging_fhir import imaging_study_resource

logger = logging.getLogger("clinloop.pacs")

# DICOM tags (group+element) read from QIDO-RS JSON
TAG = {
    "study_uid": "0020000D", "accession": "00080050", "study_date": "00080020", "study_time": "00080030",
    "description": "00081030", "modalities": "00080061", "patient_id": "00100020",
    "n_series": "00201206", "n_instances": "00201208",
    "series_uid": "0020000E", "modality": "00080060", "series_description": "0008103E", "body_part": "00180015",
    "sop_uid": "00080018", "instance_number": "00200013",
}
STUDY_FIELDS = ["00081030", "00080061", "00201206", "00201208", "00080050", "00080030"]
SERIES_FIELDS = ["0008103E", "00180015", "00080060"]


class PACSError(RuntimeError):
    pass


_UID = re.compile(r"^[0-9]+(?:\.[0-9]+)*$")


def _uid(value: str) -> str:
    """A DICOM UID (digits and dots, ≤64 characters) before it goes into a URL path."""
    if not isinstance(value, str) or len(value) > 64 or not _UID.match(value):
        raise PACSError("not a valid DICOM UID: not requested")
    return value


def _value(item: Dict[str, Any], tag: str, many: bool = False):
    values = (item.get(tag) or {}).get("Value") or []
    if many:
        return [v for v in values if v not in (None, "")]
    v = values[0] if values else None
    if isinstance(v, dict):                     # PN values: {"Alphabetic": ...}
        return None
    return v


class DICOMwebClient:
    def __init__(self, base_url: str, token: Optional[str] = None, timeout: float = 30.0,
                 session: Optional[requests.Session] = None):
        self.base = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout
        self.headers = {"Accept": "application/dicom+json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def _get(self, path: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        r = self.session.get(f"{self.base}{path}", params=params, headers=self.headers, timeout=self.timeout)
        if r.status_code == 204:
            return []
        if r.status_code != 200:
            raise PACSError(f"QIDO-RS {path} → HTTP {r.status_code}")
        try:
            data = r.json()
        except ValueError as e:
            raise PACSError(f"QIDO-RS {path}: not JSON") from e
        if not isinstance(data, list):
            raise PACSError(f"QIDO-RS {path}: unexpected response (not a list of studies)")
        return data

    def _study(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        uid = _value(item, TAG["study_uid"])
        if not uid:
            return None
        return {
            "study_uid": uid, "accession": _value(item, TAG["accession"]),
            "study_date": _value(item, TAG["study_date"]), "study_time": _value(item, TAG["study_time"]),
            "description": _value(item, TAG["description"]),
            "modalities": _value(item, TAG["modalities"], many=True),
            "n_series": _value(item, TAG["n_series"]), "n_instances": _value(item, TAG["n_instances"]),
            "series": [],
        }

    def series(self, study_uid: str) -> List[Dict[str, Any]]:
        out = []
        for s in self._get(f"/studies/{_uid(study_uid)}/series", {"includefield": list(SERIES_FIELDS)}):
            out.append({"uid": _value(s, TAG["series_uid"]) or "", "modality": _value(s, TAG["modality"]) or "",
                        "description": _value(s, TAG["series_description"]), "body_part": _value(s, TAG["body_part"])})
        return out

    def new_studies(self, date_from: str, date_to: str, modalities: List[str],
                    page: int = 100, max_per_modality: int = 5000, max_pages: int = 200) -> List[Dict[str, Any]]:
        """
        Studies acquired between two dates (YYYYMMDD), any patient, with their PatientID (for the scanner).
        Paging continues until an empty page (a PACS may cap pages below `page`), stops when a page adds
        nothing new (a PACS that ignores `offset`), and each modality has its own cap, so a busy CR list
        can never crowd out CT or MR. Modalities whose list was cut short are left in self.truncated.
        """
        fields = STUDY_FIELDS + [TAG["patient_id"], TAG["study_date"]]   # repeated includefield: widest support
        found: Dict[str, Dict[str, Any]] = {}
        self.truncated: List[str] = []
        for modality in modalities or [""]:
            offset, mine = 0, set()
            for _ in range(max_pages):
                params = {"StudyDate": f"{date_from}-{date_to}", "includefield": fields,
                          "limit": page, "offset": offset}
                if modality:
                    params["ModalitiesInStudy"] = modality
                items = self._get("/studies", params)
                new = 0
                for item in items:
                    study = self._study(item)
                    pid = _value(item, TAG["patient_id"])
                    if study and pid is not None and study["study_uid"] not in mine:
                        study["pacs_patient_id"] = str(pid)
                        found.setdefault(study["study_uid"], study)
                        mine.add(study["study_uid"])
                        new += 1
                if not items or not new:
                    break
                if len(mine) >= max_per_modality:
                    self.truncated.append(modality or "all")
                    break
                offset += len(items)
            else:
                self.truncated.append(modality or "all")
        return list(found.values())

    def instances(self, study_uid: str, series_uid: str) -> List[Dict[str, Any]]:
        """Instance UIDs of one series, in instance-number order."""
        items = self._get(f"/studies/{_uid(study_uid)}/series/{_uid(series_uid)}/instances",
                          {"includefield": TAG["instance_number"]})
        out = []
        for i in items:
            uid = _value(i, TAG["sop_uid"])
            if uid:
                try:
                    num = int(_value(i, TAG["instance_number"]) or 0)
                except (TypeError, ValueError):
                    num = 0
                out.append({"uid": uid, "number": num})
        return sorted(out, key=lambda x: x["number"])

    def instance_header(self, study_uid: str, series_uid: str, instance_uid: str) -> Dict[str, Any]:
        """Body part and descriptions from one image's metadata (WADO-RS JSON, no pixel data). Some PACS
        (e.g. Orthanc) do not return BodyPartExamined in series queries."""
        items = self._get(f"/studies/{_uid(study_uid)}/series/{_uid(series_uid)}/instances/{_uid(instance_uid)}/metadata", {})
        item = items[0] if items else {}
        return {"body_part": _value(item, TAG["body_part"]), "description": _value(item, TAG["series_description"]),
                "study_description": _value(item, TAG["description"]), "modality": _value(item, TAG["modality"])}

    def retrieve_instance(self, study_uid: str, series_uid: str, instance_uid: str,
                          max_bytes: int = 200 * 1024 * 1024) -> bytes:
        """One DICOM instance (WADO-RS). Held in memory only; never written to disk."""
        headers = {k: v for k, v in self.headers.items() if k != "Accept"}
        headers["Accept"] = 'multipart/related; type="application/dicom"; transfer-syntax=*'
        r = self.session.get(f"{self.base}/studies/{_uid(study_uid)}/series/{_uid(series_uid)}/instances/{_uid(instance_uid)}",
                             headers=headers, timeout=self.timeout, stream=True)
        if r.status_code != 200:
            raise PACSError(f"WADO-RS instance → HTTP {r.status_code}")
        body = bytearray()
        for chunk in r.iter_content(1024 * 1024):
            body += chunk
            if len(body) > max_bytes:
                r.close()
                raise PACSError("WADO-RS instance larger than the size limit: not retrieved")
        return _first_dicom_part(bytes(body), r.headers.get("Content-Type", ""))

    def studies(self, pacs_patient_id: str) -> List[Dict[str, Any]]:
        """Study labels for one patient (with each study's series body parts), as plain dicts."""
        if not pacs_patient_id or any(c in pacs_patient_id for c in "*?\\"):
            raise PACSError("Patient ID contains DICOM wildcard characters: not queried")
        out = []
        fields = STUDY_FIELDS + [TAG["patient_id"]]
        for item in self._get("/studies", {"PatientID": pacs_patient_id, "includefield": fields}):
            study = self._study(item)
            if not study:
                continue
            returned = _value(item, TAG["patient_id"])
            if returned is not None and str(returned) != pacs_patient_id:
                logger.error("PACS returned a study of another PatientID for a query: study skipped")
                continue
            try:   # body part lives at series level
                study["series"] = self.series(study["study_uid"])
            except PACSError as e:
                logger.warning("Series query failed for a study: %s", e)
            if not study["modalities"]:
                study["modalities"] = sorted({s["modality"] for s in study["series"] if s["modality"]})
            out.append(study)
        return out

    def ping(self) -> bool:
        try:
            self._get("/studies", {"limit": 1})
            return True
        except (PACSError, requests.RequestException):
            return False


def _first_dicom_part(body: bytes, content_type: str) -> bytes:
    """The DICOM file in a WADO-RS response (multipart/related, or a bare application/dicom body)."""
    if "multipart" not in content_type.lower():
        return body
    m = re.search(r'boundary="?([^";]+)"?', content_type, re.I)
    if not m:
        raise PACSError("WADO-RS multipart response without a boundary")
    delimiter = b"--" + m.group(1).strip().encode("latin-1")
    # Slice the bytes directly: a generic MIME parser copies a 200 MB part many times over
    start = body.find(delimiter)
    while start != -1:
        head_end = body.find(b"\r\n\r\n", start)
        if head_end == -1:
            break
        nxt = body.find(b"\r\n" + delimiter, head_end + 4)
        part = body[head_end + 4: nxt if nxt != -1 else len(body)]
        if part:
            return part
        start = nxt + 2 if nxt != -1 else -1
    raise PACSError("WADO-RS response had no DICOM part")


def dicom_patient_ids(patient: Dict[str, Any], strict: bool = False) -> List[str]:
    """
    What an image's DICOM PatientID may be: the FHIR id and the MRN (or the configured identifier system).
    strict (automatic scanning, no person looking): only the configured system's value, and the FHIR id
    only with CLINLOOP_PACS_MATCH_FHIR_ID=1. Another site's MRN with the same digits never matches.
    """
    system = os.environ.get("CLINLOOP_PACS_ID_SYSTEM")
    match_fhir = os.environ.get("CLINLOOP_PACS_MATCH_FHIR_ID", "").strip().lower() in ("1", "true", "yes", "on")
    ids = [patient["id"]] if (not strict or match_fhir) else []
    for i in patient.get("identifier", []):
        is_mrn = any(c.get("code") == "MR" for c in (i.get("type") or {}).get("coding", []))
        if not i.get("value"):
            continue
        if strict:
            if system and i.get("system") == system:
                ids.append(i["value"])
        elif is_mrn or (system and i.get("system") == system):
            ids.append(i["value"])
    return list(dict.fromkeys(ids))


def pacs_patient_ids(patient_resource: Optional[Dict[str, Any]], fhir_id: str) -> List[str]:
    """Which PatientID(s) to ask the PACS for, from the FHIR Patient's identifiers."""
    system = os.environ.get("CLINLOOP_PACS_ID_SYSTEM")
    ids = (patient_resource or {}).get("identifier", [])
    if system:
        values = [i.get("value") for i in ids if i.get("system") == system and i.get("value")]
    else:
        values = [i.get("value") for i in ids
                  if any(c.get("code") == "MR" for c in (i.get("type") or {}).get("coding", [])) and i.get("value")]
    if not values and os.environ.get("CLINLOOP_PACS_MATCH_FHIR_ID", "").strip().lower() in ("1", "true", "yes", "on"):
        values = [fhir_id]
    return values


def imaging_studies_for(client: DICOMwebClient, fhir_id: str,
                        patient_resource: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """FHIR ImagingStudy resources for a patient, read from the PACS."""
    resources = []
    ids = pacs_patient_ids(patient_resource, fhir_id)
    if not ids:
        raise PACSError("patient has no MRN to look up in the PACS (set CLINLOOP_PACS_ID_SYSTEM, "
                        "or CLINLOOP_PACS_MATCH_FHIR_ID=1 if the PACS uses FHIR ids)")
    for pid in ids:
        for study in client.studies(pid):
            resources.append(imaging_study_resource(study, fhir_id, source="pacs"))
    return resources


def client_from_env() -> Optional[DICOMwebClient]:
    base = os.environ.get("CLINLOOP_PACS_DICOMWEB")
    if not base:
        return None
    return DICOMwebClient(base, token=os.environ.get("CLINLOOP_PACS_TOKEN"))
