"""Synthetic transport and completion regressions. No live model or patient records."""
import json
from unittest import mock
import pytest
from src.clinloop_engine import local_llm_engine as llm, model_registry, second_reader

INFO={'details':{'family':'synthetic'},'model_info':{'general.architecture':'synthetic','synthetic.context_length':16384},'capabilities':['completion']}
ANSWER={'model':'synthetic:1b','response':'SYNTHETIC response.','done':True,'done_reason':'stop'}

def test_public_credentialed_and_metadata_endpoints_rejected_before_any_request():
    with mock.patch.object(llm.requests,'Session') as session:
        for base in ['https://8.8.8.8','http://secret:credential@127.0.0.1:11434','http://127.0.0.1:11434/?token=secret','http://169.254.169.254','http://0.0.0.0']:
            with pytest.raises(ValueError):llm._ollama_json('POST','/api/generate',{'prompt':'SYNTHETIC'},base=base)
        session.assert_not_called()


def test_transport_ignores_environment_proxies_and_refuses_redirects():
    session=mock.MagicMock();session.__enter__.return_value=session
    response=mock.MagicMock(status_code=302);response.__enter__.return_value=response
    session.request.return_value=response
    with mock.patch.object(llm.requests,'Session',return_value=session):
        with pytest.raises(ValueError):llm._ollama_json('POST','/api/generate',{'prompt':'SYNTHETIC'},base='http://127.0.0.1:11434')
    assert session.trust_env is False
    assert session.request.call_args.kwargs['allow_redirects'] is False
    assert session.request.call_args.kwargs['stream'] is True


def test_cloud_alias_and_unknown_model_metadata_never_receive_a_report():
    for info in [{**INFO,'remote_host':'cloud.example'}, {**INFO,'details':{'remote_model':'remote'}}, {'capabilities':['completion']}, {**INFO,'capabilities':['vision']}]:
        with mock.patch.object(llm,'_ollama_json',return_value=info) as call:
            out=llm.generate_clinical_text('SYNTHETIC private marker',model='synthetic:1b')
        assert out['text']=='' and out.get('error')
        assert all(c.args[1]!='/api/generate' for c in call.call_args_list)
    with mock.patch.object(llm,'_ollama_json') as call:
        out=llm.generate_clinical_text('SYNTHETIC',model='synthetic-cloud')
        call.assert_not_called();assert out.get('error')


@pytest.mark.parametrize('changes',[{'done':False},{'done':None},{'done_reason':'length'},{'done_reason':None},{'model':'other:1b'},{'response':''},{'response':'<think>unfinished'},{'error':'SYNTHETIC secret'}])
def test_incomplete_or_mismatched_generation_never_returns_partial_text(changes):
    value={**ANSWER,**changes}
    def request(method,path,*args,**kwargs):
        if path=='/api/show':return INFO
        if value.get('error'):raise ValueError(value['error'])
        return value
    with mock.patch.object(llm,'_ollama_json',side_effect=request):out=llm.generate_clinical_text('SYNTHETIC',model='synthetic:1b')
    assert out.get('error') and out['text']=='' and 'secret' not in str(out)


def test_exception_details_cannot_echo_report_text_in_errors_or_logs(caplog):
    with mock.patch.object(llm,'_ollama_json',side_effect=ValueError('SYNTHETIC private report marker')):
        out=llm.generate_clinical_text('SYNTHETIC',model='synthetic:1b');llm.get_available_models()
    assert 'private report marker' not in json.dumps(out)+caplog.text


def test_missing_explicit_model_never_silently_substitutes_another():
    with mock.patch.dict(llm.os.environ,{'CLINLOOP_LLM_MODEL':'missing:1b'}),mock.patch.object(llm,'get_available_models',return_value=[{'name':'other:1b'}]):
        assert llm.get_best_model() is None


def test_undeclared_capabilities_are_not_reported_available():
    with mock.patch.object(model_registry,'_installed',return_value={'exaone3.5:7.8b':{}}),mock.patch.object(model_registry,'_capabilities',return_value=None),mock.patch.dict(llm.os.environ,{'CLINLOOP_LLM_MODEL':'exaone3.5:7.8b'}):
        result=model_registry.registry('http://127.0.0.1:11434')
    assert not result['all_available'];assert result['roles'][0]['status']=='capability check unavailable'



def test_complete_prompt_capacity_is_checked_before_generation():
    for info in [{**INFO,'model_info':{'synthetic.context_length':256}},{**INFO,'model_info':{'general.architecture':'synthetic'}}]:
        with mock.patch.object(llm,'_ollama_json',return_value=info) as call:
            out=llm.generate_clinical_text('SYNTHETIC complete report',model='synthetic:1b')
        assert out.get('error') and out['text']==''
        assert all(c.args[1]!='/api/generate' for c in call.call_args_list)


def test_registry_does_not_call_a_cloud_alias_available():
    with mock.patch.object(model_registry,'_installed',return_value={'exaone3.5:7.8b':{'remote_host':'synthetic-cloud'}}),mock.patch.dict(llm.os.environ,{'CLINLOOP_LLM_MODEL':'exaone3.5:7.8b'}):
        reg=model_registry.registry('http://127.0.0.1:11434')
    assert reg['roles'][0]['status']=='remote or cloud alias refused' and not reg['all_available']


def test_registry_rejects_remote_show_metadata_even_when_completion_is_declared():
    with mock.patch.object(llm,'_ollama_json',return_value={**INFO,'remote_model':'synthetic-remote'}):
        assert model_registry._capabilities('http://127.0.0.1:11434','synthetic:1b') is None
