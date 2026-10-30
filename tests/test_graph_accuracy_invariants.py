"""Synthetic development challenges; these do not establish clinical accuracy."""
import copy
from datetime import datetime
from unittest.mock import patch

import pytest

from src.clinloop_engine.fhir_ingest import superseded_reports
from src.clinloop_engine.fhir_sync import sync_once
from src.clinloop_engine.loop_store import LoopStore
from src.clinloop_engine.patient_graph import build_patient_graph
from src.clinloop_engine.temporal_hypergraph import DynamicTemporalHypergraph

NOW = datetime(2026, 6, 1)


def event(ident="trigger", patient="SYN-GRAPH", **changes):
    row = {"event_id": ident, "patient_id": patient, "event_type": "lab_result",
           "timestamp": "2026-05-01T00:00:00Z", "status": "completed",
           "details": {"test": "FIT", "result": "positive"}, "source": "Observation/fit"}
    row.update(changes)
    return row


def test_graph_cannot_present_another_patients_events_under_requested_identity():
    with pytest.raises(ValueError, match="patient identity"):
        build_patient_graph("SYN-OTHER", [event()], NOW)


def test_temporal_graph_rejects_mixed_patient_identity_before_mutating():
    graph = DynamicTemporalHypergraph(NOW)
    with pytest.raises(ValueError, match="patient identity"):
        graph.build_from_patient_trajectory([event(), event("other", "SYN-OTHER")])
    assert graph.nodes == {}


def test_conflicting_duplicate_content_is_not_silently_discarded():
    graph = DynamicTemporalHypergraph(NOW)
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        graph.build_from_patient_trajectory([event(details={"test": "FIT", "result": "negative"}), event()])


def test_graph_rebuild_replaces_stale_followup_and_reopens_obligation():
    graph = DynamicTemporalHypergraph(NOW)
    followup = event("scope", event_type="colonoscopy", timestamp="2026-05-02", details={},
                     source="Procedure/scope")
    graph.build_from_patient_trajectory([event(), followup])
    assert next(h for h in graph.get_all_loops() if h.obligation_rule.rule_id == "R017").is_complete
    graph.build_from_patient_trajectory([event()])
    assert set(graph.nodes) == {"trigger"}
    assert [h.status for h in graph.get_all_loops() if h.obligation_rule.rule_id == "R017"] == ["open"]


def test_graph_owns_its_details_without_mutating_input_when_duplicates_conflict():
    rows = [event(), event(status="cancelled")]
    before = copy.deepcopy(rows)
    graph = DynamicTemporalHypergraph(NOW)
    graph.build_from_patient_trajectory(rows)
    graph.nodes["trigger"].details["private_internal_review"] = True
    assert rows == before


def test_supersession_uses_instants_instead_of_timestamp_text():
    def report(ident, status, issued):
        return {"resourceType": "DiagnosticReport", "id": ident, "status": status,
                "subject": {"reference": "Patient/SYN-GRAPH"}, "code": {"text": "CT chest"},
                "basedOn": [{"reference": "ServiceRequest/synthetic-order"}], "issued": issued}
    versions = [report("draft", "preliminary", "2026-05-01T00:00:00Z"),
                report("earlier", "final", "2026-05-02T09:00:00+09:00"),
                report("later", "final", "2026-05-02T01:00:00Z")]
    assert superseded_reports(versions) == {"DiagnosticReport/draft": "DiagnosticReport/later"}


def test_nested_writer_does_not_commit_outer_work_on_failure():
    store = LoopStore()
    with pytest.raises(ValueError):
        with store._writing():
            store.note_patients(["SYN-GRAPH"])
            store.save_snapshot("SYN-GRAPH", [{"resourceType": "Patient", "id": "SYN-GRAPH"}])
            store.record_audit("synthetic", "system", "synthetic_probe", None, {})
            raise ValueError("synthetic downstream failure")
    assert store.monitored_patient_count() == 0
    assert store.snapshot("SYN-GRAPH") == []
    assert store.audit_trail() == []


def test_failed_nested_writer_uses_savepoint_if_outer_catches_failure():
    store = LoopStore()
    with store._writing():
        store.note_patients(["SYN-KEEP"])
        try:
            with store._writing():
                store.note_patients(["SYN-ROLLBACK"])
                raise ValueError("synthetic inner failure")
        except ValueError:
            pass
        store.note_patients(["SYN-ALSO-KEEP"])
    assert store.monitored_patient_count() == 2
    assert store.verify_audit_chain()


def test_multi_patient_mapper_failure_rolls_back_mirror_loops_cursor_and_retries():
    store = LoopStore()
    class SyntheticBulkClient:
        def bind(self, target):
            self.store = target
        def changed_patients(self, since):
            self.store.mirror_upsert(("Patient", pid, pid, {"resourceType": "Patient", "id": pid})
                                     for pid in ("SYN-A", "SYN-B"))
            return {"SYN-A", "SYN-B"}, "2026-05-31T00:00:00Z"
        def patient_history(self, pid):
            return self.store.mirror_history(pid)
    client = SyntheticBulkClient()
    def mapper(history, **kwargs):
        pid = history[0]["id"]
        if pid == "SYN-B":
            raise ValueError("synthetic patient mapping failure")
        return {pid: [event(patient=pid)]}, []
    with patch("src.clinloop_engine.fhir_sync.bundle_to_events", side_effect=mapper):
        result = sync_once(store, client, now=NOW)
    assert not result["ok"]
    assert store.mirror_size() == 0
    assert store.monitored_patient_count() == 0
    assert store.worklist(include_inactive=True) == []
    assert store.get_cursor("fhir-sync") is None
    assert [r["action"] for r in store.audit_trail()] == ["ingest_failed"]
    with patch("src.clinloop_engine.fhir_sync.bundle_to_events",
               side_effect=lambda history, **kw: ({history[0]["id"]: [event(patient=history[0]["id"])]}, [])):
        result = sync_once(store, client, now=NOW)
        repeated = sync_once(store, client, now=NOW)
    assert result["ok"] and repeated["ok"]
    assert result["loops"]["new"] == 2 and repeated["loops"]["new"] == 0
    assert store.mirror_size() == 2 and store.monitored_patient_count() == 2
    assert len(store.worklist(include_inactive=True)) == 2
    assert store.verify_audit_chain()


def synthetic_bulk(store, rows):
    """Built-in bulk path with transport replaced by synthetic in-process data."""
    from src.clinloop_engine.bulk_fhir import BulkFHIRClient
    client = BulkFHIRClient("https://synthetic.invalid/fhir", store=store)
    def kick(since):
        assert not store._db.in_transaction
        return "https://synthetic.invalid/export/1"
    def download(manifest):
        assert not store._db.in_transaction
        yield from rows
    client.kick_off = kick
    client.wait = lambda url: {"output": [], "transactionTime": "2026-05-31T00:00:00Z"}
    client.download = download
    client.cancel = lambda url: None
    return client


def test_builtin_bulk_stages_mapping_before_writer_lock_and_commits_atomically():
    store = LoopStore()
    rows = [{"resourceType": "Patient", "id": pid} for pid in ("SYN-A", "SYN-B")]
    client = synthetic_bulk(store, rows)
    def mapper(history, **kwargs):
        assert not store._db.in_transaction
        assert store.mirror_size() == 0
        return {history[0]["id"]: [event(patient=history[0]["id"])]}, []
    with patch("src.clinloop_engine.fhir_sync.bundle_to_events", side_effect=mapper):
        result = sync_once(store, client, now=NOW)
    assert result["ok"] and result["loops"]["new"] == 2
    assert store.mirror_size() == 2 and store.monitored_patient_count() == 2
    assert store.get_cursor("fhir-sync") == "2026-05-31T00:00:00Z"


def test_builtin_bulk_commit_failure_rolls_back_prior_patients_and_spool_import():
    store = LoopStore()
    client = synthetic_bulk(store, [{"resourceType": "Patient", "id": pid} for pid in ("SYN-A", "SYN-B")])
    original = store.upsert_detections
    def write(detections, **kwargs):
        if detections[0].patient_id == "SYN-B":
            raise RuntimeError("synthetic write failure")
        return original(detections, **kwargs)
    with patch("src.clinloop_engine.fhir_sync.bundle_to_events",
               side_effect=lambda history, **kw: ({history[0]["id"]: [event(patient=history[0]["id"])]}, [])), \
         patch.object(store, "upsert_detections", side_effect=write):
        result = sync_once(store, client, now=NOW)
    assert not result["ok"] and result["local_state_rolled_back"]
    assert store.mirror_size() == 0 and store.monitored_patient_count() == 0
    assert store.worklist(include_inactive=True) == []
    assert store.get_cursor("fhir-sync") is None
    assert [r["action"] for r in store.audit_trail()] == ["ingest_failed"]


@pytest.mark.parametrize("separate_connection", [False, True])
def test_stale_bulk_stage_cannot_overwrite_concurrent_local_evidence(tmp_path, separate_connection):
    store = LoopStore(str(tmp_path / "synthetic.sqlite"))
    concurrent = LoopStore(str(tmp_path / "synthetic.sqlite")) if separate_connection else store
    patient = {"resourceType": "Patient", "id": "SYN-A"}
    client = synthetic_bulk(store, [patient])
    newer = {**patient, "active": False}
    def mapper(history, **kwargs):
        concurrent.mirror_upsert([("Patient", "SYN-A", "SYN-A", newer)])
        return {"SYN-A": [event(patient="SYN-A")]}, []
    with patch("src.clinloop_engine.fhir_sync.bundle_to_events", side_effect=mapper):
        result = sync_once(store, client, now=NOW)
    assert not result["ok"]
    assert store.mirror_history("SYN-A") == [newer]
    assert store.worklist(include_inactive=True) == []
    assert store.get_cursor("fhir-sync") is None


def test_uncertain_completed_event_cannot_serve_as_closure_proof():
    followup = event("scope", event_type="colonoscopy", timestamp="2026-05-02", details={"review_required": True,
                     "review_note_all": "Synthetic uncertain evidence"}, source="Procedure/scope")
    graph = build_patient_graph("SYN-GRAPH", [event(), followup], NOW)
    loop = next(h for h in graph["hyperedges"] if h["rule_id"] == "R017")
    assert loop["status"] == "open" and loop["followups"] == []
    node = next(n for n in graph["nodes"] if n["id"] == "scope")
    assert node["review_required"] and node["review_note"]


def test_exact_duplicate_replay_cannot_add_graph_relations_or_self_edges():
    expected = build_patient_graph("SYN-GRAPH", [event()], NOW)
    replayed = build_patient_graph("SYN-GRAPH", [event(), event()], NOW)
    assert replayed == expected
    assert all(edge["source"] != edge["target"] for edge in replayed["edges"])


def test_manual_upload_commit_failure_preserves_all_old_snapshots_and_loops():
    from src.clinloop_engine import clinical_api
    from src.clinloop_engine.auth import User
    store = LoopStore()
    old = [{"resourceType": "Patient", "id": "SYN-GRAPH", "active": False}]
    store.save_snapshot("SYN-GRAPH", old)
    bundle = {"resourceType": "Bundle", "type": "collection", "entry": [
        {"resource": {"resourceType": "Patient", "id": "SYN-GRAPH"}},
        {"resource": {"resourceType": "Observation", "id": "fit", "status": "final",
                      "subject": {"reference": "Patient/SYN-GRAPH"},
                      "code": {"coding": [{"system": "http://loinc.org", "code": "29771-3"}]},
                      "effectiveDateTime": "2026-05-01T00:00:00Z", "valueString": "positive"}}]}
    with patch.object(clinical_api, "get_store", return_value=store), \
         patch.object(store, "upsert_detections", side_effect=RuntimeError("synthetic write failure")):
        with pytest.raises(RuntimeError):
            clinical_api.ingest_fhir(bundle, evaluation_time=NOW.isoformat(), user=User("synthetic-admin", "admin"),
                                     access=lambda *args: None)
    assert store.snapshot("SYN-GRAPH") == old
    assert store.monitored_patient_count() == 0
    assert store.worklist(include_inactive=True) == []
    assert store.audit_trail() == []


@pytest.mark.parametrize("kind,regions", [("biopsy_result", []), ("pathology_result", []),
                                         ("pathology_result", ["liver"]), ("biopsy_result", ["thyroid"])])
def test_region_specific_biopsy_requires_matching_site(kind, regions):
    trigger = event(event_type="radiology_report", details={"condition": "radiologist_rec_biopsy",
                    "followup_regions": {"R036": ["thyroid"]}})
    followup = event("biopsy", event_type=kind, timestamp="2026-05-02", details={"body_regions": regions})
    graph = DynamicTemporalHypergraph(NOW)
    graph.build_from_patient_trajectory([trigger, followup])
    loop = next(h for h in graph.get_all_loops() if h.obligation_rule.rule_id == "R036")
    assert loop.is_complete == (regions == ["thyroid"])


def test_completed_late_has_no_outstanding_urgency_or_overdue_graph_flag():
    from src.clinloop_engine.loop_detector import ClinLoopDetector
    trigger = event(timestamp="2026-01-01")
    followup = event("scope", event_type="colonoscopy", timestamp="2026-05-01", details={})
    detector = ClinLoopDetector(NOW)
    result = next(d for d in detector.process_patient("synthetic", "SYN-GRAPH", [trigger, followup])
                  if d.rule_id == "R017")
    assert result.loop_status == "delayed"
    assert result.clock_state == "CLOSED" and result.risk_score == 0
    assert "URGENT" not in result.recommended_action and "Completed late" in result.missing_step
    graph = DynamicTemporalHypergraph(NOW)
    graph.build_from_patient_trajectory([trigger, followup])
    exported = next(h for h in graph.export_causal_json()["hyperedges"] if h["rule"] == "R017")
    assert not exported["is_overdue"]


def test_resolution_withdraws_old_drafts_and_reopening_resets_escalation():
    from datetime import timedelta
    from src.clinloop_engine.loop_detector import ClinLoopDetector
    store = LoopStore()
    detector = ClinLoopDetector(NOW)
    trigger = event(timestamp="2026-01-01")
    followup = event("scope", event_type="colonoscopy", timestamp="2026-02-01", details={})
    def ingest(rows):
        return store.upsert_detections(detector.process_patient("synthetic", "SYN-GRAPH", rows))
    ingest([trigger])
    key = store.worklist()[0]["loop_key"]
    draft = store.add_outreach_draft(key, "synthetic", "clinician", "Synthetic text", "en", "test", [])
    store.escalate_overdue(now=NOW)
    store.escalate_overdue(now=NOW + timedelta(days=2))
    assert store.get(key)["escalation_level"] > 0
    ingest([trigger, followup])
    assert store.get_outreach(draft["id"])["status"] == "withdrawn"
    ingest([trigger, {**followup, "status": "cancelled"}])
    assert store.get(key)["escalation_level"] == 0 and store.get(key)["last_escalated_at"] is None
    assert store.escalate_overdue(now=NOW)


def test_outreach_cannot_send_from_inside_a_retriable_atomic_scope():
    from src.clinloop_engine.loop_detector import ClinLoopDetector
    from src.clinloop_engine.loop_store import WorkflowError
    from unittest.mock import Mock
    store = LoopStore()
    store.upsert_detections(ClinLoopDetector(NOW).process_patient("synthetic", "SYN-GRAPH", [event()]))
    key = store.worklist()[0]["loop_key"]
    draft = store.add_outreach_draft(key, "synthetic", "clinician", "Synthetic text", "en", "test", [])
    provider = Mock()
    with store.atomic():
        with pytest.raises(WorkflowError, match="transaction"):
            store.decide_outreach(draft["id"], "synthetic", "clinician", True, provider=provider)
    provider.send.assert_not_called()
    assert store.get_outreach(draft["id"])["status"] == "draft"


@pytest.mark.parametrize("offset", ["+0999", "+1500", "-1300", "-0000", "invalid", "+09:00"])
def test_invalid_supplied_dicom_timezone_never_invents_a_completion_instant(offset):
    from src.clinloop_engine.imaging_fhir import dicom_datetime
    assert dicom_datetime("20260501", "120000", offset) is None


@pytest.mark.parametrize("time", ["250000", "126000", "120099", "12:30:00", "not-a-time", "120000.extra"])
def test_invalid_supplied_dicom_time_never_falls_back_to_midnight(time):
    from src.clinloop_engine.imaging_fhir import dicom_datetime
    assert dicom_datetime("20260501", time, "+0900") is None


def test_dicom_valid_offset_date_only_and_fractional_seconds_are_preserved():
    from src.clinloop_engine.imaging_fhir import dicom_datetime
    assert dicom_datetime("20260501", None, "+0900") == "2026-05-01T00:00:00+09:00"
    assert dicom_datetime("20260501", "123000.125", "+0900") == "2026-05-01T12:30:00.125000+09:00"
    assert dicom_datetime("20260501", "12", "+0000") == "2026-05-01T12:00:00+00:00"


def test_invalid_dicom_timing_cannot_close_an_imaging_obligation():
    from src.clinloop_engine.fhir_ingest import bundle_to_events
    from src.clinloop_engine.imaging_fhir import imaging_study_resource
    study = imaging_study_resource({"study_uid": "1.2.3", "modalities": ["CT"], "body_part": "CHEST",
                                    "study_date": "20260502", "study_time": "250000"}, "SYN-GRAPH", "synthetic")
    assert "started" not in study
    events, warnings = bundle_to_events([study], evaluation_time=NOW)
    assert not events and any("no timestamp" in warning for warning in warnings)


def test_invalid_configured_dicom_timezone_is_unavailable_instead_of_assumed_utc():
    from src.clinloop_engine.imaging_fhir import dicom_datetime
    with patch.dict("os.environ", {"CLINLOOP_LOCAL_TZ": "Synthetic/InvalidZone"}):
        assert dicom_datetime("20260501", "120000") is None


def test_delayed_quality_event_stays_out_of_worklist_escalation_outreach_and_active_counts():
    from src.clinloop_engine.loop_detector import ClinLoopDetector
    from src.clinloop_engine.loop_store import WorkflowError
    from src.clinloop_engine.pilot import overdue_candidates
    store = LoopStore()
    trigger = event(timestamp="2026-01-01")
    followup = event("scope", event_type="colonoscopy", timestamp="2026-05-01", details={})
    detections = ClinLoopDetector(NOW).process_patient("synthetic", "SYN-GRAPH", [trigger, followup])
    store.upsert_detections(detections)
    assert store.worklist() == [] and store.escalate_overdue(now=NOW) == []
    assert overdue_candidates(store, NOW) == []
    row = store.worklist(include_inactive=True)[0]
    assert row["engine_status"] == "delayed" and row["workflow_state"] == "resolved_by_engine"
    assert store.open_loop_rate(now=NOW)["groups"]["all"]["missed"] == 1
    with pytest.raises(WorkflowError):
        store.add_outreach_draft(row["loop_key"], "synthetic", "clinician", "Synthetic text", "en", "test", [])
