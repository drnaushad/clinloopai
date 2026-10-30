"""Conflicting copies of one synthetic study must not prove follow-up completion."""
import copy
from datetime import datetime

from src.clinloop_engine.fhir_ingest import bundle_to_events
from src.clinloop_engine.imaging_fhir import imaging_study_resource
from src.clinloop_engine.temporal_hypergraph import DynamicTemporalHypergraph


def studies():
    meta = {"study_uid": "9.1", "modalities": ["CT"], "body_part": "CHEST",
            "study_date": "20260110", "study_time": "080000"}
    first = imaging_study_resource(meta, "SYN-STUDY", "pacs")
    second = imaging_study_resource({**meta, "study_time": "093000"}, "SYN-STUDY", "dicom")
    return first, second


def test_conflicting_study_copies_are_order_independent_and_never_close_followup():
    resources = list(studies())
    original = copy.deepcopy(resources)
    left, warnings = bundle_to_events(resources)
    right, _ = bundle_to_events(list(reversed(resources)))
    rows = left["SYN-STUDY"]
    assert resources == original
    assert sorted(rows, key=lambda e: e["event_id"]) == sorted(right["SYN-STUDY"], key=lambda e: e["event_id"])
    assert warnings and all("SYN-STUDY" not in w for w in warnings)
    assert all(e["status"] == "unknown" and e["details"].get("review_note_all") for e in rows)
    trigger = {"event_id": "synthetic-nodule", "patient_id": "SYN-STUDY",
               "event_type": "radiology_report", "timestamp": "2026-01-01", "status": "completed",
               "source": "DiagnosticReport/synthetic", "details": {"condition": "incidental_nodule_ge_6mm"}}
    graph = DynamicTemporalHypergraph(datetime(2026, 1, 11))
    graph.build_from_patient_trajectory([trigger, *rows])
    loops = [h for h in graph.get_all_loops() if h.obligation_rule.rule_id == "R003"]
    assert loops and all(not h.is_complete for h in loops)


def test_identical_study_copies_remain_valid_completion_evidence():
    first, _ = studies()
    patients, warnings = bundle_to_events([first, copy.deepcopy(first)])
    assert not warnings
    graph = DynamicTemporalHypergraph(datetime(2026, 1, 11))
    graph.build_from_patient_trajectory(patients["SYN-STUDY"])
    assert all(n.status == "completed" for n in graph.nodes.values())
