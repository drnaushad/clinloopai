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


if __name__ == "__main__":
    unittest.main()


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
