"""
EHR MCP Server: Model Context Protocol Server for Hospital EHR Integration.
Simulates Epic/Cerner API connections for querying historical encounters
and pushing FHIR tasks/orders back into the hospital system.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger("ehr_mcp_server")

TOOLS = [
    {
        "name": "ehr_query_encounters",
        "description": "Query the hospital EHR (Epic/Cerner) for a patient's historical visits and encounters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string", "description": "The MRN or unique patient identifier."},
                "limit": {"type": "integer", "description": "Maximum number of recent encounters to fetch."}
            },
            "required": ["patient_id"]
        }
    },
    {
        "name": "ehr_push_fhir_task",
        "description": "Push an HL7 FHIR Task or ServiceRequest (e.g. 1-click order) back to the hospital EHR.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "task_type": {"type": "string", "enum": ["schedule_followup", "order_imaging", "order_labs"]},
                "priority": {"type": "string", "enum": ["routine", "urgent", "stat"]}
            },
            "required": ["patient_id", "task_type"]
        }
    }
]

def handle_call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle MCP Tool Call requests for EHR integration."""
    
    if name == "ehr_query_encounters":
        pid = arguments.get("patient_id")
        limit = arguments.get("limit", 5)
        logger.info("Mock EHR: Querying encounters (limit=%s)", limit)
        
        # Simulated response from an Epic/Cerner database
        return {
            "simulated": True, "ehr_connected": False, "clinical_use": False,
            "content": [
                {
                    "type": "text",
                    "text": "Synthetic example encounters; no patient chart was queried:\n"
                            "1. 2026-08-14: ER Visit (Abdominal Pain). Discharged to home.\n"
                            "2. 2026-08-15: Radiology (CT Abdomen/Pelvis w/ contrast)."
                }
            ]
        }
        
    elif name == "ehr_push_fhir_task":
        pid = arguments.get("patient_id")
        task_type = arguments.get("task_type")
        priority = arguments.get("priority", "routine")
        
        logger.info("Mock EHR: Task requested")
        
        return {
            "simulated": True, "transmitted": False, "ehr_connected": False,
            "content": [
                {
                    "type": "text",
                    "text": "Synthetic task preview only. No EHR is connected; no order or task was transmitted."
                }
            ]
        }
        
    else:
        raise ValueError("Unknown EHR mock tool")
