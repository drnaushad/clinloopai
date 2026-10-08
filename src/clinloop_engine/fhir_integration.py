import uuid
from datetime import datetime, timezone, timezone
import datetime as dt_module

def fhir_create_task(obligation_id: str, patient_id: str, action_desc: str, deadline_str: str) -> dict:
    """Wraps an obligation into a FHIR-STU-3 Task resource."""
    return {
        "resourceType": "Task",
        "id": f"task-{uuid.uuid4()}",
        "status": "requested",
        "intent": "order",
        "priority": "stat",
        "description": action_desc,
        "for": {
            "reference": f"Patient/{patient_id}"
        },
        "executionPeriod": {
            "end": deadline_str
        },
        "identifier": [
            {
                "system": "http://clinloop.ai/obligations",
                "value": obligation_id
            }
        ],
        "authoredOn": datetime.now(timezone.utc).isoformat() + "Z"
    }

def fhir_create_observation(patient_id: str, finding_code: str, value_str: str) -> dict:
    """Creates a FHIR Observation for an open loop."""
    return {
        "resourceType": "Observation",
        "id": f"obs-{uuid.uuid4()}",
        "status": "preliminary",
        "subject": {
            "reference": f"Patient/{patient_id}"
        },
        "code": {
            "coding": [
                {
                    "system": "http://snomed.info/sct",
                    "code": finding_code
                }
            ]
        },
        "valueString": value_str,
        "issued": datetime.now(timezone.utc).isoformat() + "Z"
    }

def fhir_add_provenance_extension(resource: dict, hash_value: str) -> dict:
    """Injects ClinLoop AI cryptographic provenance into a FHIR resource."""
    if "extension" not in resource:
        resource["extension"] = []
    
    resource["extension"].append({
        "url": "http://clinloop.ai/fhir/StructureDefinition/provenance-hash",
        "valueString": hash_value
    })
    return resource
