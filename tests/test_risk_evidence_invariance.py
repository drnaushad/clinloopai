"""Completeness is evidence-local; synthetic tests do not calibrate risk."""
from datetime import datetime, timedelta
import pytest
from src.clinloop_engine.risk_scorer import RiskScorer
from src.clinloop_engine.clinical_ontology import Severity


@pytest.mark.parametrize('details',[{}, {'condition':'synthetic'},
    {'condition':'synthetic','flag':'high','test':'synthetic','result':'abnormal','finding':'synthetic'}])
def test_unrelated_event_counts_cannot_improve_completeness(details):
    scores={RiskScorer().compute_uncertainty(details,n) for n in (0,1,10,100,10000)}
    assert len(scores)==1


@pytest.mark.parametrize('severity,days,expected_abstention',[
    (Severity.HIGH,0,True),(Severity.CRITICAL,0,False),(Severity.HIGH,40,False)])
def test_missing_context_preserves_urgent_escalation(severity,days,expected_abstention):
    now=datetime(2026,1,1)
    result=RiskScorer().score('synthetic','R018','Synthetic',severity,now,30,{},100,True,
                              evaluation_time=now+timedelta(days=days))
    assert result.should_abstain is expected_abstention
    assert any('not calibrated' in line for line in result.explanation)
