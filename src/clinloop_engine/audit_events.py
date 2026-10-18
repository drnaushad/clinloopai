"""
audit_events.py — The access log as FHIR R4 AuditEvent resources

A hospital's security team and a regulatory reviewer expect access records in the standard shape
(FHIR AuditEvent, following the IHE Basic Audit Log Patterns). ClinLoop's own access log
(`loop_store.access_log`, hash-chained) stays the record; this module only presents each entry as an
AuditEvent, keeping the entry's chain hashes in an extension so a copy can still be checked against
the database (`GET /api/v1/access-log/verify`).

Mapping:
  type      DICOM 110110 "Patient Record"; subtype = ClinLoop's action (view_worklist, ingest, …)
  action    R (read) for views; E (execute) for ingest, uploads and filing
  recorded  the entry's time (UTC)
  purpose   TREAT for care; HRESCH for pilot review; HOPERAT for log and quality reviews
  agent     the person (user name, role, client address), requestor = true
  source    ClinLoop, application server
  entity    one per patient whose data was shown or processed (Patient/<id>)
"""

from typing import Dict, Iterable, List

ACTION_SYSTEM = "https://clinloopai.app/fhir/CodeSystem/access-action"
HASH_EXTENSION = "https://clinloopai.app/fhir/StructureDefinition/hash-chain"
_PURPOSE_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ActReason"
_RESEARCH = {"view_pilot_queue", "view_safety_referrals"}
_OPERATIONS = {"view_access_log", "view_documentation_audit"}


def _instant(ts: str) -> str:
    """FHIR instants need a time zone; the log stores UTC without one."""
    return ts if ts.endswith("Z") or "+" in ts[10:] else ts + "Z"


def _purpose(action: str) -> Dict:
    code, display = (("HRESCH", "healthcare research") if action in _RESEARCH
                     else ("HOPERAT", "healthcare operations") if action in _OPERATIONS
                     else ("TREAT", "treatment"))
    return {"coding": [{"system": _PURPOSE_SYSTEM, "code": code, "display": display}]}


def to_audit_event(entry: Dict) -> Dict:
    """One access-log entry (as returned by LoopStore.access_log(..., with_hash=True)) as an AuditEvent."""
    action = entry["action"]
    agent = {"type": {"coding": [{"system": "http://dicom.nema.org/resources/ontology/DCM", "code": "110153",
                                  "display": "Source Role ID"}]},
             "who": {"identifier": {"system": "https://clinloopai.app/fhir/NamingSystem/user", "value": entry["actor"]}},
             "requestor": True,
             "role": [{"text": entry.get("role") or "unknown"}]}
    if entry.get("client"):
        agent["network"] = {"address": entry["client"], "type": "2"}        # 2 = IP address
    event = {
        "resourceType": "AuditEvent",
        "id": f"access-{entry['id']}",
        "type": {"system": "http://dicom.nema.org/resources/ontology/DCM", "code": "110110", "display": "Patient Record"},
        "subtype": [{"system": ACTION_SYSTEM, "code": action}],
        "action": "R" if action.startswith("view_") or action.startswith("read_") else "E",
        "recorded": _instant(entry["ts"]),
        "outcome": "0",
        "purposeOfEvent": [_purpose(action)],
        "agent": [agent],
        "source": {"observer": {"display": "ClinLoop"},
                   "type": [{"system": "http://terminology.hl7.org/CodeSystem/security-source-type", "code": "4",
                             "display": "Application Server"}]},
        "entity": [{"what": {"reference": f"Patient/{pid}"},
                    "type": {"system": "http://terminology.hl7.org/CodeSystem/audit-entity-type", "code": "1",
                             "display": "Person"},
                    "role": {"system": "http://terminology.hl7.org/CodeSystem/object-role", "code": "1",
                             "display": "Patient"}}
                   for pid in entry.get("patients") or []],
    }
    if entry.get("hash"):
        event["extension"] = [{"url": HASH_EXTENSION, "extension": [
            {"url": "sequence", "valueInteger": entry["id"]},
            {"url": "prev_hash", "valueString": entry["prev_hash"]},
            {"url": "hash", "valueString": entry["hash"]}]}]
    return event


def bundle(entries: Iterable[Dict]) -> Dict:
    events: List[Dict] = [to_audit_event(e) for e in entries]
    return {"resourceType": "Bundle", "type": "collection", "total": len(events),
            "entry": [{"fullUrl": f"urn:clinloop:{e['id']}", "resource": e} for e in events]}
