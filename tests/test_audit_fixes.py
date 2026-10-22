"""Synthetic regressions for the October 22 audit; no model/network calls."""
from unittest import mock
import pytest
from src.clinloop_engine import second_reader, auth

@pytest.mark.parametrize('text', ['SYNTHETIC '+('a'*6000)+' Repeat CT.', '한'*2001, '', None])
def test_reader_never_silently_truncates(text):
    model=mock.Mock(return_value={'text':'{"items":[]}'})
    assert second_reader.read_report(text, model)['available'] is False
    model.assert_not_called()

@pytest.mark.parametrize('value', [None, [], {'text':{}}, {'text':'{"items":[]}','done':False}, {'text':'{"items":[]}','done_reason':'length'}])
def test_reader_rejects_invalid_or_incomplete_result(value):
    assert second_reader.read_report('SYNTHETIC report.', lambda *_:value)['available'] is False

def test_reader_errors_do_not_echo_model_content():
    out=second_reader.read_report('SYNTHETIC report.', lambda *_:{'error':'SYNTHETIC-PRIVATE-MARKER'})
    assert not out['available'] and 'SYNTHETIC-PRIVATE-MARKER' not in str(out)
    model=mock.Mock(side_effect=ValueError('SYNTHETIC-PRIVATE-MARKER'))
    assert not second_reader.read_report('SYNTHETIC report.', model)['available']

def test_reader_complete_boundary_input_reaches_model_unchanged():
    text='z'*6000
    model=mock.Mock(return_value={'text':'{"items":[]}','done':True,'done_reason':'stop'})
    assert second_reader.read_report(text,model)['available']
    assert model.call_args.args[0].endswith(text)

def test_missing_credentials_create_no_admin_and_log_no_token():
    with mock.patch.dict(auth.os.environ, {'CLINLOOP_API_TOKENS':'','CLINLOOP_DEMO':'0'}), mock.patch.object(auth.logger,'warning') as log:
        assert auth._load_tokens()=={}
        assert len(log.call_args.args)==1

def test_configured_credentials_still_work_and_malformed_ones_are_not_echoed():
    token='SYNTHETIC_ONLY_TOKEN_12345'
    with mock.patch.dict(auth.os.environ, {'CLINLOOP_API_TOKENS':token+':tester:admin','CLINLOOP_DEMO':'0'}):
        assert auth._load_tokens()[token].role=='admin'
    with mock.patch.dict(auth.os.environ, {'CLINLOOP_API_TOKENS':token+':bad'}):
        with pytest.raises(RuntimeError) as exc:auth._load_tokens()
        assert 'SYNTHETIC' not in str(exc.value)

def test_catalogue_browser_regressions():
    import shutil
    import subprocess
    from pathlib import Path
    if not shutil.which('node'):
        pytest.skip('Node required for browser regression checks')
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run(['node','tests/test_report_catalogue.cjs'],cwd=root,capture_output=True,text=True,timeout=30)
    assert result.returncode==0, result.stdout+result.stderr
