"""
data_loader.py — Clinical Trajectory Data Loader for ClinLoop AI

Provides a unified interface to load, generate, and process clinical patient
trajectories for training, validation, and benchmarking.
"""

import os
import json
from typing import List, Dict, Optional, Union
from pathlib import Path
import pandas as pd

from src.clinloop_engine.data_generator import (
    generate_all_scenarios,
    save_scenarios,
    PatientScenario,
    ClinicalEvent
)

class ClinicalDataLoader:
    """Utility class to manage loading and exporting clinical trajectory datasets."""

    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            self.data_dir = os.path.join(base_dir, "data", "synthetic")
        else:
            self.data_dir = data_dir

    def generate(self, n_total: int = 300, save: bool = True) -> List[PatientScenario]:
        """Generates synthetic patient trajectories across all clinical archetypes."""
        scenarios = generate_all_scenarios(n_total=n_total)
        if save:
            os.makedirs(self.data_dir, exist_ok=True)
            save_scenarios(scenarios, self.data_dir)
        return scenarios

    def load_scenario_file(self, file_path: str) -> PatientScenario:
        """Loads a single clinical scenario JSON file."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        events = [
            ClinicalEvent(
                event_id=e["event_id"],
                patient_id=e["patient_id"],
                event_type=e["event_type"],
                timestamp=e["timestamp"],
                details=e.get("details", {}),
                status=e.get("status", "completed")
            )
            for e in data["events"]
        ]
        
        return PatientScenario(
            scenario_id=data["scenario_id"],
            patient_id=data["patient_id"],
            patient_age=data.get("patient_age", 50),
            patient_sex=data.get("patient_sex", "M"),
            scenario_name=data.get("scenario_name", ""),
            scenario_category=data.get("scenario_category", ""),
            applicable_rule_id=data.get("applicable_rule_id", ""),
            events=events,
            ground_truth_status=data.get("ground_truth_status", "closed"),
            ground_truth_severity=data.get("ground_truth_severity", "low"),
            ground_truth_risk_score=data.get("ground_truth_risk_score", 0.0),
            missing_followup=data.get("missing_followup", ""),
            clinical_narrative=data.get("clinical_narrative", "")
        )

    def load_all(self, directory: Optional[str] = None) -> List[PatientScenario]:
        """Loads all scenario JSON files from the target directory."""
        target_dir = directory or self.data_dir
        if not os.path.exists(target_dir):
            return self.generate(save=True)

        scenarios = []
        for filename in sorted(os.listdir(target_dir)):
            if filename.endswith(".json") and filename != "summary.json":
                path = os.path.join(target_dir, filename)
                scenarios.append(self.load_scenario_file(path))
        
        if not scenarios:
            return self.generate(save=True)
            
        return scenarios

    def to_dataframe(self, scenarios: List[PatientScenario]) -> pd.DataFrame:
        """Converts scenario metadata and labels into a tabular pandas DataFrame."""
        rows = []
        for s in scenarios:
            rows.append({
                "scenario_id": s.scenario_id,
                "patient_id": s.patient_id,
                "patient_age": s.patient_age,
                "patient_sex": s.patient_sex,
                "scenario_name": s.scenario_name,
                "ground_truth_status": s.ground_truth_status,
                "ground_truth_severity": s.ground_truth_severity,
                "ground_truth_risk_score": s.ground_truth_risk_score,
                "num_events": len(s.events),
                "missing_followup": s.missing_followup
            })
        return pd.DataFrame(rows)


def load_dataset(data_dir: Optional[str] = None) -> List[PatientScenario]:
    """Convenience helper function to load or generate the full dataset."""
    loader = ClinicalDataLoader(data_dir=data_dir)
    return loader.load_all()
