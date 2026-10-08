import asyncio
import logging
import json
import math
import os
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger("clinloop.safety_clock")


def utc_now() -> datetime:
    """Current time as a naive UTC datetime (the engine's internal time base)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_timestamp(ts: Any) -> datetime:
    """
    Parse a timestamp into a naive UTC datetime.

    EMR/FHIR feeds mix timezone-aware ("2026-03-01T09:00:00+09:00", "...Z")
    and naive values. Comparing the two raises TypeError, so every timestamp
    entering the engine is converted to one time base: aware values are
    converted to UTC, naive values are assumed to already be UTC.
    """
    if isinstance(ts, str):
        text = ts.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            ts = datetime.fromisoformat(text)
        except ValueError:
            ts = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    if not isinstance(ts, datetime):
        raise TypeError(f"Unsupported timestamp: {ts!r}")
    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
    return ts


# Global state for the watchdog
class SafetyClockState:
    is_running = False
    last_scan_time = None
    active_cases_monitored = 0
    escalations = []

clock_state = SafetyClockState()

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cases.json")

def load_cases() -> List[Dict[str, Any]]:
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    logger.error(f"Safety Clock data source missing: {DATA_PATH}")
    return []

def scan_for_violations(evaluation_time: Optional[datetime] = None):
    """
    Run the full ClinLoop detection engine over every monitored case and
    escalate each obligation whose guideline deadline has been violated.

    Uses the same rules, deadlines and clock as the detector, so the watchdog
    and the worklist can never disagree about what is overdue.
    """
    # Imported here: loop_detector depends on this module.
    from .loop_detector import ClinLoopDetector
    from .clinical_ontology import LoopStatus

    cases = load_cases()
    now = evaluation_time or utc_now()
    detector = ClinLoopDetector(evaluation_time=now)
    # DELAYED loops were completed late: a quality event, not something to escalate now
    active = (LoopStatus.OPEN.value, LoopStatus.ABSTAIN.value)

    new_escalations = []
    monitored = 0
    for case in cases:
        try:
            detections = detector.process_patient(
                case.get("scenario_id", ""), case.get("patient_id", ""),
                case.get("events", []), case.get("scenario_category", ""),
            )
        except Exception as e:  # one malformed case must not blind the watchdog
            logger.error(f"Safety Clock could not evaluate {case.get('scenario_id')}: {e}")
            new_escalations.append({
                "scenario_id": case.get("scenario_id"),
                "patient_id": case.get("patient_id"),
                "violation": f"Case could not be evaluated ({type(e).__name__}); manual review required",
                "escalation_level": "DATA_ERROR",
                "timestamp": now.isoformat(),
            })
            continue

        open_dets = [d for d in detections if d.loop_status in active]
        if open_dets:
            monitored += 1
        for det in open_dets:
            if det.clock_state != ClockState.BLACK.value:
                continue
            new_escalations.append({
                "scenario_id": det.scenario_id,
                "patient_id": det.patient_id,
                "rule_id": det.rule_id,
                "violation": f"{det.rule_name}: deadline {det.deadline} exceeded. {det.missing_step}",
                "escalation_level": det.severity.upper(),
                "timestamp": now.isoformat(),
            })

    clock_state.active_cases_monitored = monitored
    clock_state.escalations = new_escalations
    clock_state.last_scan_time = now.isoformat()
    logger.info(f"Safety Clock Scan Complete. Monitored {monitored} cases with open obligations. "
                f"Detected {len(new_escalations)} violations.")

async def safety_clock_loop():
    """
    The autonomous 24/7 loop.
    """
    clock_state.is_running = True
    logger.info("Starting Autonomous Safety Clock Watchdog...")
    
    while True:
        try:
            scan_for_violations()
        except Exception as e:
            logger.error(f"Error in Safety Clock scan: {e}")
            
        # In production, this would sleep for 6 hours (asyncio.sleep(6 * 3600))
        # For the demo backend, we'll scan every 10 seconds to keep the status fresh
        await asyncio.sleep(10)

def get_clock_status() -> Dict[str, Any]:
    """
    Return the live telemetry of the Safety Clock.
    """
    return {
        "status": "active" if clock_state.is_running else "offline",
        "watchdog": "ClinLoop Autonomous Safety Clock",
        "last_scan_time": clock_state.last_scan_time,
        "active_cases_monitored": clock_state.active_cases_monitored,
        "active_escalations": len(clock_state.escalations),
        "escalation_details": clock_state.escalations
    }

from enum import Enum
from dataclasses import dataclass

class ClockState(Enum):
    BLACK = "BLACK"
    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"

@dataclass
class SafetyClockReading:
    time_risk: float
    clock_state: ClockState
    urgency_label: str

class SafetyClock:
    def __init__(self, steepness: float = 8.0, threshold: float = 1.0):
        self.steepness = steepness
        self.threshold = threshold

    def evaluate(self, obligation_id: str, rule_id: str, trigger_time: datetime, deadline_days: float, evaluation_time: Optional[datetime] = None) -> SafetyClockReading:
        evaluation_time = normalize_timestamp(evaluation_time) if evaluation_time is not None else utc_now()
        trigger_time = normalize_timestamp(trigger_time)

        elapsed_days = (evaluation_time - trigger_time).total_seconds() / 86400.0
        
        # Sigmoid urgency decay
        try:
            # Scale elapsed days so that steepness applies meaningfully
            # If elapsed == deadline, value is 0.5.
            # R(t) = 1 / (1 + e^(-k * (t - T_crit)/T_crit)) ? 
            # Or just k * (t - T_crit) as in the formula, but scaled to be 0..1
            exponent = -self.steepness * (elapsed_days - deadline_days) / max(1.0, deadline_days)
            time_risk = 1.0 / (1.0 + math.exp(max(-500, min(500, exponent))))
        except Exception:
            time_risk = 1.0 if elapsed_days >= deadline_days else 0.0

        if elapsed_days >= deadline_days:
            state = ClockState.BLACK
            label = "Deadline violated"
        elif elapsed_days >= deadline_days * 0.8:
            state = ClockState.RED
            label = "Approaching deadline"
        elif elapsed_days >= deadline_days * 0.5:
            state = ClockState.YELLOW
            label = "Halfway to deadline"
        else:
            state = ClockState.GREEN
            label = "Safe"

        return SafetyClockReading(
            time_risk=time_risk,
            clock_state=state,
            urgency_label=label
        )
