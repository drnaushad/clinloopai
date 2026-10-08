
import asyncio
import logging
import json
import os
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger("clinloop.safety_clock")

# Global state for the watchdog
class SafetyClockState:
    is_running = False
    last_scan_time = None
    active_cases_monitored = 0
    escalations = []
    
clock_state = SafetyClockState()

DATA_PATH = os.path.join(os.path.dirname(__file__), "../../demo/data/cases.json")

def load_cases() -> List[Dict[str, Any]]:
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def parse_iso_date(date_str: str) -> datetime:
    # Handle ISO format with or without timezone
    if 'T' in date_str:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    return datetime.now()

def scan_for_violations():
    """
    Scans all open cases and checks if their elapsed time violates BioMCP safety guidelines.
    """
    cases = load_cases()
    open_cases = [c for c in cases if c.get("ground_truth_status") == "open"]
    
    clock_state.active_cases_monitored = len(open_cases)
    new_escalations = []
    
    # Simulate current time for the demo context (Sept 2026)
    current_simulated_time = datetime.fromisoformat("2026-09-22T00:00:00+09:00")
    
    for case in open_cases:
        events = case.get("events", [])
        if not events:
            continue
            
        # Get the timestamp of the first critical event
        critical_event = events[0]
        event_time_str = critical_event.get("timestamp")
        
        if event_time_str:
            event_time = parse_iso_date(event_time_str)
            # Remove tzinfo for simple delta calculation
            event_time = event_time.replace(tzinfo=None)
            sim_time = current_simulated_time.replace(tzinfo=None)
            
            elapsed_days = (sim_time - event_time).days
            
            # Simple heuristic for time window based on BioMCP rules
            # E.g. HSIL colposcopy -> 30 days
            # Lung nodule CT -> 180 days
            time_window_limit = 30 # Default safe fallback
            
            if "HSIL" in case.get("clinical_narrative", ""):
                time_window_limit = 30
            elif "nodule" in case.get("clinical_narrative", "").lower():
                time_window_limit = 180
                
            if elapsed_days > time_window_limit:
                new_escalations.append({
                    "scenario_id": case.get("scenario_id"),
                    "patient_id": case.get("patient_id"),
                    "violation": f"Exceeded BioMCP limit: {elapsed_days} days elapsed (Limit: {time_window_limit} days)",
                    "escalation_level": "CRITICAL_MALPRACTICE_RISK",
                    "timestamp": datetime.now().isoformat()
                })
                
    clock_state.escalations = new_escalations
    clock_state.last_scan_time = datetime.now().isoformat()
    logger.info(f"Safety Clock Scan Complete. Monitored {len(open_cases)} cases. Detected {len(new_escalations)} violations.")

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

    def evaluate(self, obligation_id: str, rule_id: str, trigger_time: datetime, deadline_days: float, evaluation_time: datetime = None) -> SafetyClockReading:
        import math
        if evaluation_time is None:
            evaluation_time = datetime.now()
        
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
