"""
pacs_client.py — Read imaging study labels from the hospital PACS (DICOMweb QIDO-RS)

ClinLoop asks the PACS which studies a patient has had: modality, body part,
description, date, number of series and images. It never retrieves pixel
data. Each study becomes a FHIR ImagingStudy, so "was the follow-up CT of the
adrenals done?" is answered from the PACS itself rather than inferred from
report titles.

Works with any DICOMweb server (Orthanc, dcm4chee, Sectra, Infinitt, Google
Cloud Healthcare, …). Read-only.

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
}
STUDY_FIELDS = ["00081030", "00080061", "00201206", "00201208", "00080050", "00080030"]
SERIES_FIELDS = ["0008103E", "00180015", "00080060"]


class PACSError(RuntimeError):
    pass


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

    def studies(self, pacs_patient_id: str) -> List[Dict[str, Any]]:
        """Study labels for one patient (with each study's series body parts), as plain dicts."""
        if not pacs_patient_id or any(c in pacs_patient_id for c in "*?\\"):
            raise PACSError("Patient ID contains DICOM wildcard characters: not queried")
        out = []
        fields = ",".join(STUDY_FIELDS + [TAG["patient_id"]])
        for item in self._get("/studies", {"PatientID": pacs_patient_id, "includefield": fields}):
            uid = _value(item, TAG["study_uid"])
            if not uid:
                continue
            returned = _value(item, TAG["patient_id"])
            if returned is not None and str(returned) != pacs_patient_id:
                logger.error("PACS returned a study of another PatientID for a query: study skipped")
                continue
            study = {
                "study_uid": uid, "accession": _value(item, TAG["accession"]),
                "study_date": _value(item, TAG["study_date"]), "study_time": _value(item, TAG["study_time"]),
                "description": _value(item, TAG["description"]),
                "modalities": _value(item, TAG["modalities"], many=True),
                "n_series": _value(item, TAG["n_series"]), "n_instances": _value(item, TAG["n_instances"]),
                "series": [],
            }
            try:   # body part lives at series level
                for s in self._get(f"/studies/{uid}/series", {"includefield": ",".join(SERIES_FIELDS)}):
                    study["series"].append({"uid": _value(s, TAG["series_uid"]) or "",
                                            "modality": _value(s, TAG["modality"]) or "",
                                            "description": _value(s, TAG["series_description"]),
                                            "body_part": _value(s, TAG["body_part"])})
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
