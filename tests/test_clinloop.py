"""
test_clinloop.py — Test Suite for ClinLoop AI Data Loader and Model Interface

Covers: data generation, model inference, loop detection, RiskScorer,
SafetyClock, DynamicTemporalHypergraph, ClinLoopDetector, baselines,
clinical ontology enums, risk ordering, abstention logic, and batch pipeline.
"""

import unittest
import os
import sys
from datetime import datetime, timedelta

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data_loader import ClinicalDataLoader
from src.model import ClinLoopModel, get_model
from src.clinloop_engine.clinical_ontology import (
    Severity, LoopStatus, OBLIGATION_RULES, get_severity_score
)
from src.clinloop_engine.risk_scorer import RiskScorer
from src.clinloop_engine.safety_clock import SafetyClock, ClockState
from src.clinloop_engine.temporal_hypergraph import DynamicTemporalHypergraph
from src.clinloop_engine.loop_detector import ClinLoopDetector
from src.clinloop_engine.baselines import EMRInboxBaseline
from src.clinloop_engine.data_generator import generate_all_scenarios


# ── Helpers shared across tests ──────────────────────────────────────────────

_PATIENT_ID = "TEST_PT_001"

def _make_hyperkalemia_events(patient_id=_PATIENT_ID, with_followup=False):
    """Minimal critical-lab (K⁺ > 6.0) event list."""
    events = [
        {
            "event_id": "EV_01",
            "patient_id": patient_id,
            "event_type": "lab_order",
            "timestamp": "2026-09-01T09:00:00",
            "details": {"test_name": "Serum Potassium", "code": "K_LEVEL"},
            "status": "completed",
        },
        {
            "event_id": "EV_02",
            "patient_id": patient_id,
            "event_type": "lab_result",
            "timestamp": "2026-09-01T11:30:00",
            "details": {
                "test_name": "Serum Potassium",
                "value": 6.3,
                "flag": "CRITICAL",
                "condition": "abnormal",
            },
            "status": "completed",
        },
    ]
    if with_followup:
        events.append({
            "event_id": "EV_03",
            "patient_id": patient_id,
            "event_type": "patient_notification",
            "timestamp": "2026-09-01T14:00:00",
            "details": {"method": "phone"},
            "status": "completed",
        })
    return events


# ── Original Tests ────────────────────────────────────────────────────────────

class TestClinLoopPipeline(unittest.TestCase):

    def setUp(self):
        self.loader = ClinicalDataLoader()
        self.model = get_model()

    def test_data_generation_and_loading(self):
        """Verify generation of synthetic clinical scenarios."""
        scenarios = self.loader.generate(n_total=10, save=False)
        self.assertEqual(len(scenarios), 10)

        # Test dataframe conversion
        df = self.loader.to_dataframe(scenarios)
        self.assertEqual(len(df), 10)
        self.assertIn("scenario_id", df.columns)
        self.assertIn("ground_truth_status", df.columns)
        self.assertIn("ground_truth_severity", df.columns)

    def test_model_inference_batch(self):
        """Verify model predictions on batch scenarios."""
        scenarios = self.loader.generate(n_total=15, save=False)
        predictions = self.model.predict_scenarios(scenarios)

        self.assertEqual(len(predictions), 15)
        for pred in predictions:
            self.assertIn("scenario_id", pred)
            self.assertIn("predicted_status", pred)
            self.assertIn("predicted_risk", pred)
            self.assertTrue(0.0 <= pred["predicted_risk"] <= 1.0)

    def test_single_patient_loop_detection(self):
        """Verify detection of an abnormal lab missing clinical follow-up."""
        events = _make_hyperkalemia_events()
        detections = self.model.detect_loops(
            patient_id=_PATIENT_ID,
            events=events,
            scenario_id="SCENARIO_HYPERKALEMIA_OPEN",
            category="critical_lab",
        )

        self.assertTrue(len(detections) > 0)
        top = detections[0]
        self.assertEqual(top.patient_id, _PATIENT_ID)
        self.assertTrue(0.0 < top.risk_score <= 1.0)

        explanation = self.model.explain(top)
        self.assertIn("ClinLoop Alert", explanation)
        self.assertIn(_PATIENT_ID, explanation)


# ── New Tests ─────────────────────────────────────────────────────────────────

class TestRiskScorer(unittest.TestCase):
    """Test 4: Multi-factor risk calculation produces a score in [0, 1]."""

    def setUp(self):
        self.scorer = RiskScorer(abstention_threshold=0.7)
        self.trigger_time = datetime(2026, 9, 1, 10, 0, 0)
        self.eval_time = datetime(2026, 9, 5, 10, 0, 0)  # 4 days later

    def test_risk_score_in_unit_interval(self):
        """Score for an open HIGH-severity obligation must be in [0, 1]."""
        assessment = self.scorer.score(
            obligation_id="OBL-001",
            rule_id="R001",
            rule_name="Abnormal Lab → Patient Notification",
            severity=Severity.HIGH,
            trigger_time=self.trigger_time,
            deadline_days=3.0,
            event_details={"condition": "abnormal", "flag": "ABNORMAL"},
            n_events=2,
            is_open=True,
            evaluation_time=self.eval_time,
        )
        self.assertGreaterEqual(assessment.normalized_risk, 0.0)
        self.assertLessEqual(assessment.normalized_risk, 1.0)

    def test_closed_loop_has_zero_risk(self):
        """A closed loop must always yield a composite risk of 0."""
        assessment = self.scorer.score(
            obligation_id="OBL-002",
            rule_id="R001",
            rule_name="Abnormal Lab → Patient Notification",
            severity=Severity.HIGH,
            trigger_time=self.trigger_time,
            deadline_days=3.0,
            event_details={"condition": "abnormal"},
            n_events=3,
            is_open=False,
            evaluation_time=self.eval_time,
        )
        self.assertEqual(assessment.composite_risk, 0.0)


class TestSafetyClockUrgencyDecay(unittest.TestCase):
    """Test 5: Sigmoid urgency decay returns increasing values over time."""

    def setUp(self):
        self.clock = SafetyClock(steepness=8.0)
        self.trigger = datetime(2026, 9, 1, 0, 0, 0)
        self.deadline_days = 7.0

    def test_urgency_increases_with_elapsed_time(self):
        """time_risk at day 6 must be greater than at day 1."""
        early = self.clock.evaluate(
            "OBL-A", "R001",
            self.trigger, self.deadline_days,
            evaluation_time=self.trigger + timedelta(days=1),
        )
        late = self.clock.evaluate(
            "OBL-A", "R001",
            self.trigger, self.deadline_days,
            evaluation_time=self.trigger + timedelta(days=6),
        )
        self.assertLess(early.time_risk, late.time_risk)

    def test_overdue_clock_state_is_black(self):
        """Evaluation past the deadline must set clock state to BLACK."""
        reading = self.clock.evaluate(
            "OBL-B", "R001",
            self.trigger, self.deadline_days,
            evaluation_time=self.trigger + timedelta(days=10),
        )
        self.assertEqual(reading.clock_state, ClockState.BLACK)

    def test_time_risk_within_unit_interval(self):
        """time_risk must always be in [0, 1] regardless of elapsed time."""
        for days_offset in [0, 1, 3, 7, 14, 30]:
            reading = self.clock.evaluate(
                "OBL-C", "R001",
                self.trigger, self.deadline_days,
                evaluation_time=self.trigger + timedelta(days=days_offset),
            )
            self.assertGreaterEqual(reading.time_risk, 0.0)
            self.assertLessEqual(reading.time_risk, 1.0)


class TestDynamicTemporalHypergraph(unittest.TestCase):
    """Test 6: Node/edge creation in the temporal hypergraph."""

    def _build_graph(self, with_followup=False):
        graph = DynamicTemporalHypergraph(
            evaluation_time=datetime(2026, 9, 15)
        )
        events = _make_hyperkalemia_events(with_followup=with_followup)
        graph.build_from_patient_trajectory(events)
        return graph

    def test_nodes_created(self):
        """All input events must become nodes in the hypergraph."""
        graph = self._build_graph()
        self.assertEqual(len(graph.nodes), 2)

    def test_open_loop_detected_when_followup_absent(self):
        """Without a follow-up event, at least one open loop must be detected."""
        graph = self._build_graph(with_followup=False)
        open_loops = graph.detect_open_loops()
        self.assertGreater(len(open_loops), 0)

    def test_closed_loop_when_followup_present(self):
        """With a timely patient_notification event, the loop must close."""
        graph = self._build_graph(with_followup=True)
        closed_loops = graph.detect_closed_loops()
        self.assertGreater(len(closed_loops), 0)

    def test_graph_stats_keys(self):
        """get_graph_stats() must return expected keys."""
        graph = self._build_graph()
        stats = graph.get_graph_stats()
        for key in ("total_nodes", "total_hyperedges", "status_distribution"):
            self.assertIn(key, stats)


class TestClinLoopDetectorIncidentalFinding(unittest.TestCase):
    """Test 7: Open loop detection for an incidental radiology finding scenario."""

    def test_incidental_nodule_detected_as_open(self):
        """A radiology report with incidental nodule and no follow-up CT must be OPEN."""
        patient_id = "PT_NODULE_001"
        events = [
            {
                "event_id": "EV_N1",
                "patient_id": patient_id,
                "event_type": "radiology_report",
                "timestamp": "2026-04-01T10:00:00",
                "details": {
                    "finding": "Incidental pulmonary nodule 8mm",
                    "condition": "incidental_nodule_ge_6mm",
                },
                "status": "completed",
            }
        ]
        detector = ClinLoopDetector(evaluation_time=datetime(2026, 9, 15))
        detections = detector.process_patient(
            scenario_id="NODULE_OPEN_001",
            patient_id=patient_id,
            events=events,
            category="incidental_nodule_open",
        )
        self.assertGreater(len(detections), 0)
        statuses = {d.loop_status for d in detections}
        self.assertTrue(
            statuses & {"open", "needs_human_review"},
            f"Expected open/abstain loop, got: {statuses}"
        )
        self.assertTrue(detections[0].should_abstain)
        self.assertTrue(any(
            "FHIR Task preview (not transmitted)" in item
            for item in detections[0].evidence_chain
        ))


class TestEMRBaselinePredictions(unittest.TestCase):
    """Test 8: EMR baseline prediction returns valid results."""

    def setUp(self):
        self.baseline = EMRInboxBaseline()
        self.loader = ClinicalDataLoader()

    def test_emr_baseline_returns_valid_predictions(self):
        """EMR baseline must return one prediction per scenario with expected keys."""
        scenarios = self.loader.generate(n_total=10, save=False)
        dict_scenarios = [s.to_dict() for s in scenarios]
        predictions = self.baseline.predict(dict_scenarios)

        self.assertEqual(len(predictions), 10)
        for pred in predictions:
            self.assertIn("scenario_id", pred)
            self.assertIn("predicted_status", pred)
            self.assertIn("predicted_risk", pred)
            self.assertGreaterEqual(pred["predicted_risk"], 0.0)
            self.assertLessEqual(pred["predicted_risk"], 1.0)
            self.assertIn(pred["predicted_status"], {"open", "closed", "delayed"})


class TestDataGeneratorCategories(unittest.TestCase):
    """Test 9: generate_all_scenarios produces expected loop-status categories."""

    def test_all_three_categories_present(self):
        """Generated scenarios must include open, closed, and delayed cases."""
        scenarios = generate_all_scenarios(n_total=60)

        statuses = {s.ground_truth_status for s in scenarios}
        self.assertIn(LoopStatus.OPEN.value, statuses, "Missing OPEN scenarios")
        self.assertIn(LoopStatus.CLOSED.value, statuses, "Missing CLOSED scenarios")
        self.assertIn(LoopStatus.DELAYED.value, statuses, "Missing DELAYED scenarios")

    def test_scenario_count_matches_request(self):
        """Exact number of scenarios must be returned."""
        scenarios = generate_all_scenarios(n_total=30)
        self.assertEqual(len(scenarios), 30)


class TestClinicalOntologyEnums(unittest.TestCase):
    """Test 10: Severity enum, LoopStatus enum, and OBLIGATION_RULES presence."""

    def test_severity_enum_has_four_levels(self):
        """Severity must define CRITICAL, HIGH, MODERATE, LOW."""
        values = {s.value for s in Severity}
        self.assertSetEqual(values, {"critical", "high", "moderate", "low"})

    def test_loop_status_enum_has_four_values(self):
        """LoopStatus must define CLOSED, OPEN, DELAYED, ABSTAIN."""
        values = {s.value for s in LoopStatus}
        self.assertSetEqual(values, {"closed", "open", "delayed", "needs_human_review"})

    def test_obligation_rules_non_empty(self):
        """OBLIGATION_RULES must contain at least one rule."""
        self.assertGreater(len(OBLIGATION_RULES), 0)

    def test_severity_scores_ordered(self):
        """CRITICAL must score higher than HIGH which must score higher than LOW."""
        self.assertGreater(
            get_severity_score(Severity.CRITICAL),
            get_severity_score(Severity.HIGH),
        )
        self.assertGreater(
            get_severity_score(Severity.HIGH),
            get_severity_score(Severity.LOW),
        )


class TestRiskOrdering(unittest.TestCase):
    """Test 11: Higher-severity cases produce higher risk scores."""

    def setUp(self):
        self.scorer = RiskScorer()
        self.trigger = datetime(2026, 9, 1)
        self.eval = datetime(2026, 9, 4)  # 3 days later, past typical deadline

    def _score(self, severity: Severity) -> float:
        assessment = self.scorer.score(
            obligation_id="OBL-TEST",
            rule_id="R001",
            rule_name="Test",
            severity=severity,
            trigger_time=self.trigger,
            deadline_days=3.0,
            event_details={"condition": "abnormal", "flag": "ABNORMAL"},
            n_events=5,
            is_open=True,
            evaluation_time=self.eval,
        )
        return assessment.normalized_risk

    def test_critical_higher_than_low(self):
        """CRITICAL severity must produce a strictly higher risk than LOW."""
        self.assertGreater(self._score(Severity.CRITICAL), self._score(Severity.LOW))

    def test_high_higher_than_moderate(self):
        """HIGH severity must produce a strictly higher risk than MODERATE."""
        self.assertGreater(self._score(Severity.HIGH), self._score(Severity.MODERATE))


class TestAbstentionLogic(unittest.TestCase):
    """Test 12: Abstain flag is raised when uncertainty exceeds threshold."""

    def test_abstain_triggered_on_sparse_data(self):
        """With n_events=1 and no detail keys, uncertainty > 0.7 → abstain."""
        scorer = RiskScorer(abstention_threshold=0.5)  # low threshold to reliably trigger
        trigger = datetime(2026, 9, 1)
        assessment = scorer.score(
            obligation_id="OBL-SPARSE",
            rule_id="R001",
            rule_name="Test abstention",
            severity=Severity.HIGH,
            trigger_time=trigger,
            deadline_days=3.0,
            event_details={},   # no detail keys → high uncertainty
            n_events=1,
            is_open=True,
            evaluation_time=trigger + timedelta(days=2),
        )
        self.assertTrue(
            assessment.should_abstain,
            "Expected abstention with sparse data and low threshold"
        )
        self.assertNotEqual(assessment.abstain_reason, "")

    def test_no_abstain_with_rich_data(self):
        """With many events and full detail keys, should_abstain must be False."""
        scorer = RiskScorer(abstention_threshold=0.7)
        trigger = datetime(2026, 9, 1)
        assessment = scorer.score(
            obligation_id="OBL-RICH",
            rule_id="R001",
            rule_name="Test no abstention",
            severity=Severity.HIGH,
            trigger_time=trigger,
            deadline_days=14.0,
            event_details={
                "condition": "abnormal",
                "flag": "ABNORMAL",
                "test": "K",
                "result": "6.3",
                "finding": "hyperkalemia",
            },
            n_events=10,
            is_open=True,
            evaluation_time=trigger + timedelta(days=2),
        )
        self.assertFalse(assessment.should_abstain)


class TestExplanationGeneration(unittest.TestCase):
    """Test 13: explain() returns a non-empty, well-formed string."""

    def test_explain_returns_non_empty_string(self):
        """explain() must return a non-empty string containing key sections."""
        model = get_model()
        events = _make_hyperkalemia_events()
        detections = model.detect_loops(
            patient_id=_PATIENT_ID,
            events=events,
            scenario_id="EXPLAIN_TEST",
            category="critical_lab",
        )
        self.assertTrue(len(detections) > 0, "Need at least one detection to test explain()")
        explanation = model.explain(detections[0])
        self.assertIsInstance(explanation, str)
        self.assertGreater(len(explanation), 0)
        self.assertIn("ClinLoop Alert", explanation)
        self.assertIn("Recommended Action", explanation)


class TestBatchPipeline(unittest.TestCase):
    """Test 14: Full pipeline on 50 scenarios runs without error."""

    def test_batch_pipeline_50_scenarios(self):
        """process_batch over 50 generated scenarios must not raise and return results."""
        loader = ClinicalDataLoader()
        scenarios = loader.generate(n_total=50, save=False)
        dict_scenarios = [s.to_dict() for s in scenarios]

        detector = ClinLoopDetector()
        results = detector.process_batch(dict_scenarios)

        self.assertEqual(len(results), 50)
        for sid, detections in results.items():
            self.assertIsInstance(detections, list)
            for det in detections:
                self.assertGreaterEqual(det.risk_score, 0.0)
                self.assertLessEqual(det.risk_score, 1.0)


class TestCriticalLabDetection(unittest.TestCase):
    """Test 15: Hyperkalemia (K⁺ > 6.0) is detected as a critical open loop."""

    def test_hyperkalemia_detected(self):
        """K⁺ = 6.3 flagged CRITICAL with no follow-up must produce a detection."""
        model = get_model()
        events = _make_hyperkalemia_events()
        detections = model.detect_loops(
            patient_id=_PATIENT_ID,
            events=events,
            scenario_id="HYPERKALEMIA_CRITICAL",
            category="critical_lab",
        )
        self.assertGreater(len(detections), 0, "Hyperkalemia should be detected as an open loop")
        top = detections[0]
        # Must be flagged as OPEN or abstain (not closed)
        self.assertNotEqual(
            top.loop_status, LoopStatus.CLOSED.value,
            "Critical K+ result with no follow-up must NOT be closed"
        )

    def test_hyperkalemia_risk_above_threshold(self):
        """Critical K⁺ detection must carry a meaningful risk score (> 0)."""
        model = get_model()
        events = _make_hyperkalemia_events()
        detections = model.detect_loops(
            patient_id=_PATIENT_ID,
            events=events,
            scenario_id="HYPERKALEMIA_RISK",
            category="critical_lab",
        )
        self.assertTrue(any(d.risk_score > 0 for d in detections))



class TestDigitalSignature(unittest.TestCase):
    def test_sign_and_verify(self):
        from src.clinloop_engine.agent_execution import AgentExecutionContext
        from src.clinloop_engine.digital_signature import sign_agent_context, verify_agent_context
        ctx = AgentExecutionContext(agent_name='test', model_name='local')
        ctx.record_input({'x': 1})
        ctx.record_output({'y': 2})
        sig = sign_agent_context(ctx)
        self.assertIsInstance(sig, str)
        self.assertTrue(len(sig) > 0)
        self.assertTrue(verify_agent_context(ctx, sig))

class TestFHIRIntegration(unittest.TestCase):
    def test_fhir_create_task_structure(self):
        from src.clinloop_engine.fhir_integration import fhir_create_task
        task = fhir_create_task('OBL-001', 'PT-123', 'Colposcopy follow-up', '2026-12-01')
        self.assertEqual(task['resourceType'], 'Task')
        self.assertIn('for', task)  # FHIR STU3 Task uses 'for', not 'subject'
        self.assertIn('status', task)

class TestSDOHMonitor(unittest.TestCase):
    def test_disparity_ratio_below_threshold(self):
        from src.clinloop_engine.sdoh_monitor import run_sdoh_monitor
        outcomes = [
            {'sdoh_flag': True, 'detected': False},
            {'sdoh_flag': True, 'detected': False},
            {'sdoh_flag': False, 'detected': True},
            {'sdoh_flag': False, 'detected': True},
        ]
        hir = []
        result = run_sdoh_monitor(outcomes, hir, threshold=0.80)
        self.assertTrue(result['alert_triggered'])
        self.assertEqual(len(hir), 1)

class TestCausalMessage(unittest.TestCase):
    def test_template_recommendation(self):
        from src.clinloop_engine.causal_message import recommend_message_template
        features = {'sdoh_flag': True, 'age': 55, 'language': 'ko', 'urgency_level': 'CRITICAL'}
        tmpl = recommend_message_template(features)
        self.assertTrue(len(tmpl.text_template) > 0)
        self.assertIsInstance(tmpl.estimated_engagement_score, float)


# ── Patient-safety regression tests ──────────────────────────────────────────

def _evt(event_id, event_type, timestamp, details=None, status="completed"):
    return {"event_id": event_id, "patient_id": _PATIENT_ID, "event_type": event_type,
            "timestamp": timestamp, "details": details or {}, "status": status}


def _loop_statuses(events, evaluation_time=datetime(2026, 6, 1)):
    graph = DynamicTemporalHypergraph(evaluation_time=evaluation_time)
    graph.build_from_patient_trajectory(events)
    return {he.obligation_rule.rule_id: he.status for he in graph.get_all_loops()}


class TestSafetyRegressions(unittest.TestCase):
    """Each test pins a failure mode that would silently drop a patient."""

    def test_all_logic_requires_every_followup(self):
        """R009 needs notification AND referral; notification alone stays open."""
        statuses = _loop_statuses([
            _evt("a", "pathology_result", "2026-03-01T09:00:00",
                 {"condition": "abnormal", "result": "adenocarcinoma"}),
            _evt("b", "patient_notification", "2026-03-02T09:00:00"),
        ])
        self.assertEqual(statuses["R009"], LoopStatus.OPEN.value)

    def test_all_logic_closes_when_every_followup_present(self):
        statuses = _loop_statuses([
            _evt("a", "pathology_result", "2026-03-01T09:00:00", {"condition": "abnormal"}),
            _evt("b", "patient_notification", "2026-03-02T09:00:00"),
            _evt("c", "specialist_referral", "2026-03-03T09:00:00"),
        ])
        self.assertEqual(statuses["R009"], LoopStatus.CLOSED.value)

    def test_any_logic_still_closes_on_one_followup(self):
        """R004 is disjunctive: a urology referral alone satisfies it."""
        statuses = _loop_statuses([
            _evt("a", "lab_result", "2026-03-01T09:00:00", {"condition": "elevated_psa"}),
            _evt("b", "specialist_referral", "2026-03-10T09:00:00"),
        ])
        self.assertEqual(statuses["R004"], LoopStatus.CLOSED.value)

    def test_cancelled_followup_does_not_close_loop(self):
        statuses = _loop_statuses([
            _evt("a", "radiology_report", "2026-01-01T09:00:00",
                 {"finding": "incidental_pulmonary_nodule", "nodule_size_mm": 7}),
            _evt("b", "followup_ct", "2026-03-01T09:00:00", status="cancelled"),
        ])
        self.assertEqual(statuses["R003"], LoopStatus.OPEN.value)

    def test_cancelled_followup_is_named_in_evidence_chain(self):
        detections = ClinLoopDetector(evaluation_time=datetime(2026, 9, 1)).process_patient(
            "CANCELLED", _PATIENT_ID, [
                _evt("a", "radiology_report", "2026-01-01T09:00:00",
                     {"finding": "incidental_pulmonary_nodule", "nodule_size_mm": 7}),
                _evt("b", "followup_ct", "2026-03-01T09:00:00", status="no_show"),
            ])
        chain = " ".join(detections[0].evidence_chain)
        self.assertIn("followup_ct [no_show]", chain)

    def test_followup_after_evaluation_time_ignored(self):
        statuses = _loop_statuses([
            _evt("a", "lab_result", "2026-05-01T09:00:00",
                 {"condition": "abnormal_cervical_cytology"}),
            _evt("b", "colposcopy_referral", "2026-12-01T09:00:00"),
        ])
        self.assertEqual(statuses["R005"], LoopStatus.OPEN.value)

    def test_diagnosis_containing_mi_substring_is_not_mi(self):
        for dx in ("iron_deficiency_anemia", "hypokalemia", "septicemia", "migraine"):
            statuses = _loop_statuses([
                _evt("a", "discharge", "2026-03-01T09:00:00", {"primary_diagnosis": dx}),
            ])
            self.assertNotIn("R014", statuses, dx)

    def test_true_mi_discharge_triggers_r014(self):
        for dx in ("acute_mi", "NSTEMI", "myocardial_infarction"):
            statuses = _loop_statuses([
                _evt("a", "discharge", "2026-03-01T09:00:00", {"primary_diagnosis": dx}),
            ])
            self.assertIn("R014", statuses, dx)

    def test_timezone_aware_and_mixed_timestamps(self):
        events = [
            _evt("a", "lab_result", "2026-05-01T09:00:00+09:00", {"flag": "ABNORMAL"}),
            _evt("b", "patient_notification", "2026-05-01T12:00:00Z"),
        ]
        detections = ClinLoopDetector().process_patient("TZ", _PATIENT_ID, events)
        self.assertGreater(len(detections), 0)

    def test_overdue_critical_loop_is_escalated_not_abstained(self):
        detections = ClinLoopDetector(evaluation_time=datetime(2026, 6, 1)).process_patient(
            "CULTURE", _PATIENT_ID, [
                _evt("a", "culture_result", "2026-03-01T09:00:00",
                     {"condition": "positive_post_discharge", "organism": "S. aureus"}),
            ])
        top = detections[0]
        self.assertEqual(top.loop_status, LoopStatus.OPEN.value)
        self.assertFalse(top.should_abstain)
        self.assertTrue(top.recommended_action.startswith("URGENT"))

    def test_overdue_loop_uses_observed_failure_not_prior(self):
        """A missed deadline is an observed failure: risk must not be discounted by a low prior."""
        detections = ClinLoopDetector(evaluation_time=datetime(2026, 6, 1)).process_patient(
            "CULTURE", _PATIENT_ID, [
                _evt("a", "culture_result", "2026-03-01T09:00:00",
                     {"condition": "positive_post_discharge", "organism": "S. aureus"}),
            ])
        top = detections[0]
        self.assertTrue(any(line.startswith("Failure: observed") for line in top.explanation))
        self.assertGreater(top.risk_score, 0.5)

    def test_large_nodule_uses_three_month_window(self):
        """Fleischner 2017: >8 mm solid nodule needs follow-up at ~3 months."""
        statuses = _loop_statuses([
            _evt("a", "radiology_report", "2026-01-01T09:00:00",
                 {"finding": "incidental_pulmonary_nodule", "nodule_size_mm": 12}),
            _evt("b", "followup_ct", "2026-05-15T09:00:00"),
        ])
        self.assertEqual(statuses["R003"], LoopStatus.DELAYED.value)

    def test_levothyroxine_uses_six_to_eight_week_window(self):
        statuses = _loop_statuses([
            _evt("a", "medication_change", "2026-03-01T09:00:00",
                 {"drug": "levothyroxine", "condition": "requires_monitoring"}),
            _evt("b", "followup_lab", "2026-04-15T09:00:00"),
        ])
        self.assertEqual(statuses["R010"], LoopStatus.CLOSED.value)

    def test_open_loop_ranked_before_closed(self):
        detections = ClinLoopDetector(evaluation_time=datetime(2026, 6, 1)).process_patient(
            "RANK", _PATIENT_ID, [
                _evt("a", "lab_result", "2026-03-01T09:00:00", {"flag": "NORMAL"}),
                _evt("b", "provider_review", "2026-03-02T09:00:00"),
                _evt("c", "lab_result", "2026-03-03T09:00:00",
                     {"condition": "abnormal_cervical_cytology"}),
            ])
        self.assertNotEqual(detections[0].loop_status, LoopStatus.CLOSED.value)


class TestPrivacyAndAgentRegressions(unittest.TestCase):

    def test_phi_scrubber_removes_embedded_identifiers(self):
        from src.clinloop_engine.phi_deidentifier import PHIDeidentifier
        safe, log = PHIDeidentifier().deidentify_patient({
            "name": "김민수",
            "clinical_context": "Patient 김민수 (MRN: 12345678) seen 2026년 3월 5일, "
                                "call 010-1234-5678, lives at 테헤란로 123. Nodule 8.5 mm.",
        })
        text = safe["clinical"]["clinical_context"]
        for identifier in ("김민수", "12345678", "3월 5일", "010-1234-5678", "테헤란로 123"):
            self.assertNotIn(identifier, text)
        self.assertIn("8.5 mm", text)
        self.assertTrue(log["safe_to_send_cloud"])

    def test_outreach_blocks_definitive_diagnosis(self):
        from unittest.mock import patch
        from src.clinloop_engine.patient_outreach_agent import (
            OutreachRequest, generate_dynamic_outreach, FALLBACK_MESSAGES,
        )
        request = OutreachRequest("P", "O", "follow_up", {"finding": "lung nodule"}, "en",
                                  None, "kakao", None, "HIGH", [])
        with patch("src.clinloop_engine.patient_outreach_agent.generate_kakao_message",
                   return_value={"text": "You have cancer. Book now."}):
            draft = generate_dynamic_outreach(request)
        self.assertEqual(draft.message_text, FALLBACK_MESSAGES["en"])
        self.assertIn("unsupported_claim_blocked_fallback_used", draft.safety_flags)
        self.assertTrue(draft.requires_human_review)

    def test_evidence_agent_uses_reported_nodule_size(self):
        from src.clinloop_engine.evidence_agent import run_evidence_synthesis
        small = run_evidence_synthesis("Incidental 7 mm nodule on CT")
        large = run_evidence_synthesis("Incidental 14 mm nodule on CT")
        self.assertEqual(small[0].temporal_expression, "180 days")
        self.assertEqual(large[0].temporal_expression, "90 days")
        self.assertEqual(run_evidence_synthesis("Incidental nodule, size not reported"), [])

    def test_fhir_timestamp_is_valid_iso(self):
        from src.clinloop_engine.fhir_integration import fhir_create_task
        authored = fhir_create_task("O", "P", "d", "2026-12-01")["authoredOn"]
        self.assertFalse(authored.endswith("Z") and "+" in authored)
        datetime.fromisoformat(authored)

    def test_watchdog_monitors_demo_cases(self):
        from src.clinloop_engine.safety_clock import scan_for_violations, clock_state
        scan_for_violations(evaluation_time=datetime(2026, 9, 22))
        self.assertGreater(clock_state.active_cases_monitored, 0)
        self.assertGreater(len(clock_state.escalations), 0)



class TestWaveOneRules(unittest.TestCase):
    """Wave 1 life-saving rules (docs/LIFE_SAVING_ROADMAP.md §2)."""

    def test_positive_fit_without_colonoscopy_is_open(self):
        statuses = _loop_statuses([
            _evt("a", "lab_result", "2026-01-05T09:00:00",
                 {"test": "FIT", "result": "positive", "flag": "ABNORMAL"}),
        ])
        self.assertEqual(statuses["R017"], LoopStatus.OPEN.value)

    def test_positive_fit_with_timely_colonoscopy_closes(self):
        statuses = _loop_statuses([
            _evt("a", "lab_result", "2026-01-05T09:00:00", {"test": "FIT", "result": "positive"}),
            _evt("b", "colonoscopy", "2026-02-20T09:00:00"),
        ])
        self.assertEqual(statuses["R017"], LoopStatus.CLOSED.value)

    def test_birads_4_requires_biopsy(self):
        statuses = _loop_statuses([
            _evt("a", "radiology_report", "2026-03-01T09:00:00", {"birads": "4B"}),
        ])
        self.assertEqual(statuses["R018"], LoopStatus.OPEN.value)

    def test_lung_rads_categories(self):
        self.assertIn("R019", _loop_statuses([
            _evt("a", "radiology_report", "2026-03-01T09:00:00", {"lung_rads": "4A"})]))
        statuses = _loop_statuses([
            _evt("a", "radiology_report", "2026-03-01T09:00:00", {"lung_rads": "4X"}),
            _evt("b", "specialist_referral", "2026-03-10T09:00:00"),
        ])
        self.assertEqual(statuses["R020"], LoopStatus.CLOSED.value)

    def test_abnormal_result_after_discharge_needs_review(self):
        statuses = _loop_statuses([
            _evt("a", "lab_result", "2026-03-01T09:00:00",
                 {"flag": "ABNORMAL", "resulted_after_discharge": True}),
        ])
        self.assertEqual(statuses["R021"], LoopStatus.OPEN.value)
        self.assertIn("R001", statuses)  # still also an abnormal result

    def test_critical_value_carries_both_obligations(self):
        """A panic K+ needs a 1-hour clinician call AND the abnormal-result follow-up."""
        events = _make_hyperkalemia_events() + [
            _evt("n", "critical_value_notification", "2026-09-01T12:00:00"),
        ]
        statuses = _loop_statuses(events, evaluation_time=datetime(2026, 9, 2))
        self.assertEqual(statuses["R022"], LoopStatus.CLOSED.value)
        self.assertEqual(statuses["R001"], LoopStatus.OPEN.value)

    def test_late_critical_notification_is_delayed(self):
        events = _make_hyperkalemia_events() + [
            _evt("n", "critical_value_notification", "2026-09-01T14:00:00"),
        ]
        statuses = _loop_statuses(events, evaluation_time=datetime(2026, 9, 2))
        self.assertEqual(statuses["R022"], LoopStatus.DELAYED.value)

    def test_one_hour_window_reads_naturally(self):
        detections = ClinLoopDetector(evaluation_time=datetime(2026, 9, 2)).process_patient(
            "CRIT", _PATIENT_ID, _make_hyperkalemia_events())
        r022 = next(d for d in detections if d.rule_id == "R022")
        self.assertIn("within 1 hour", r022.missing_step)

    def test_all_rules_await_specialist_review(self):
        for rule in OBLIGATION_RULES:
            self.assertEqual(rule.review_status, "pending_specialist_review", rule.rule_id)



class TestWaveTwoRules(unittest.TestCase):
    """Wave 2 and radiologist-recommendation rules."""

    def _discharge(self, dx, **extra):
        return _evt("d", "discharge", "2026-03-01T09:00:00", {"primary_diagnosis": dx, **extra})

    def test_heart_failure_discharge_needs_visit_within_7_days(self):
        late = _loop_statuses([self._discharge("acute_on_chronic_heart_failure"),
                               _evt("v", "followup_appointment", "2026-03-12T09:00:00")])
        self.assertEqual(late["R023"], LoopStatus.DELAYED.value)
        on_time = _loop_statuses([self._discharge("chf_exacerbation"),
                                  _evt("v", "followup_appointment", "2026-03-06T09:00:00")])
        self.assertEqual(on_time["R023"], LoopStatus.CLOSED.value)

    def test_postpartum_bp_check_window_depends_on_severity(self):
        mild = _loop_statuses([self._discharge("gestational_hypertension"),
                               _evt("b", "bp_check", "2026-03-06T09:00:00")])
        self.assertEqual(mild["R024"], LoopStatus.CLOSED.value)
        severe = _loop_statuses([self._discharge("preeclampsia_with_severe_features", severe_hypertension=True),
                                 _evt("b", "bp_check", "2026-03-06T09:00:00")])
        self.assertEqual(severe["R024"], LoopStatus.DELAYED.value)

    def test_gestational_diabetes_postpartum_glucose_test(self):
        self.assertEqual(_loop_statuses([self._discharge("vaginal_delivery_gestational_diabetes")])["R025"],
                         LoopStatus.OPEN.value)

    def test_hcv_antibody_needs_rna(self):
        statuses = _loop_statuses([
            _evt("a", "lab_result", "2026-03-01T09:00:00", {"condition": "hcv_antibody_positive"}),
            _evt("b", "hcv_rna_test", "2026-03-10T09:00:00"),
        ])
        self.assertEqual(statuses["R026"], LoopStatus.CLOSED.value)

    def test_hcc_surveillance_chain(self):
        """Diagnosis → first ultrasound; each surveillance ultrasound starts the next 6-month clock."""
        statuses = _loop_statuses([
            _evt("dx", "diagnosis", "2025-01-01T09:00:00", {"hcc_risk": True}),
            _evt("us1", "liver_imaging", "2025-03-01T09:00:00", {"hcc_surveillance": True}),
        ], evaluation_time=datetime(2026, 1, 1))
        self.assertEqual(statuses["R027"], LoopStatus.CLOSED.value)
        self.assertEqual(statuses["R028"], LoopStatus.OPEN.value)   # next scan overdue

    def test_self_harm_discharge_is_critical_and_clinician_only(self):
        from src.clinloop_engine.clinical_ontology import get_rule_by_id
        statuses = _loop_statuses([self._discharge("intentional_self_harm_overdose")])
        self.assertEqual(statuses["R029"], LoopStatus.OPEN.value)
        self.assertFalse(get_rule_by_id("R029").patient_outreach)

    def test_radiologist_recommendation_deadline_comes_from_report(self):
        from src.clinloop_engine.clinical_ontology import get_rule_by_id, get_deadline_days
        rule = get_rule_by_id("R031")
        self.assertAlmostEqual(get_deadline_days(rule, {"recommended_interval_days": 182.6}), 182.6 + 30)
        self.assertAlmostEqual(get_deadline_days(rule, {"recommended_interval_days": 14}), 14 + 7)
        statuses = _loop_statuses([
            _evt("r", "radiology_report", "2026-01-01T09:00:00",
                 {"recommended_modality": "mri", "recommended_interval_days": 90}),
            _evt("m", "imaging_mri", "2026-03-20T09:00:00"),
        ])
        self.assertEqual(statuses["R031"], LoopStatus.CLOSED.value)


if __name__ == "__main__":
    unittest.main()
