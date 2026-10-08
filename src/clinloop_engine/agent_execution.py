"""Agent Execution Envelope

This module defines the strict, typed envelope that every autonomous agent in ClinLoop
must produce and consume.  It implements the specification from
`CLINLOOP_Improvement.md` §3J – Agent Execution Envelope.

The envelope carries:
* traceability (trace_id)
* provenance (agent version, model version)
* security (allowed tools, autonomy level)
* audit fields (inputs/outputs hash, execution time, safety flags)
"""

import uuid
import hashlib
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any


def _hash_obj(obj: Any) -> str:
    """Create a deterministic SHA256 hash of a JSON‑serialisable object."""
    import json
    serialized = json.dumps(obj, sort_keys=True, default=str).encode()
    return hashlib.sha256(serialized).hexdigest()


@dataclass
class AgentExecutionContext:
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str = ""
    agent_version: str = "1.0"
    model_name: str = ""
    model_version: Optional[str] = None
    prompt_version: str = ""
    patient_scope: Optional[str] = None
    obligation_id: Optional[str] = None
    allowed_tools: List[str] = field(default_factory=list)
    autonomy_level: str = "A1"  # e.g. A1 = PROPOSE / ROUTE, A2 = DRAFT, etc.
    capability_grant_ids: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Runtime audit fields – populated after execution
    inputs_hash: Optional[str] = None
    outputs_hash: Optional[str] = None
    tools_called: List[str] = field(default_factory=list)
    tool_results: Dict[str, Any] = field(default_factory=dict)
    uncertainty: List[str] = field(default_factory=list)
    safety_flags: List[str] = field(default_factory=list)
    human_review_required: bool = False
    execution_time_seconds: Optional[float] = None

    def record_input(self, inputs: Any) -> None:
        self.inputs_hash = _hash_obj(inputs)

    def record_output(self, outputs: Any) -> None:
        self.outputs_hash = _hash_obj(outputs)

    def finish(self) -> None:
        self.execution_time_seconds = (datetime.now(timezone.utc) - self.started_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Convert datetime objects to isoformat for JSON friendliness
        d["started_at"] = self.started_at.isoformat()
        return d

