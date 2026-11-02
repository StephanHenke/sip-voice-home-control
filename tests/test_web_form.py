from pathlib import Path
from dataclasses import asdict
import pytest
import yaml
from voice_home.config import load_text, Caller, Action
from voice_home.web_form import form_document, form_yaml, DEFAULTS, TEMPLATES

EXAMPLE=Path(__file__).parents[1]/'config.example.yaml'


def test_form_roundtrip_all_settings_and_fixed_action():
    form=form_document(EXAMPLE.read_text(encoding='utf-8'))
    raw=form['config']
    raw['callers']=[{**TEMPLATES['callers'],'name':'Anna','number':'+4915123456789',
                     'fixed_action':'front_door_open','require_confirmation':True}]
    raw['web']['enabled']=False
    cfg=load_text(form_yaml(raw),EXAMPLE)
    assert cfg.callers[0].fixed_action=='front_door_open' and cfg.callers[0].require_confirmation
    assert cfg.web['enabled'] is False
    assert set(TEMPLATES['actions'])==set(asdict(Action('',[],[])))
    assert set(TEMPLATES['callers'])==set(asdict(Caller('','')))


def test_form_preserves_unknown_fields_for_validation():
    form=form_document('sip: {host: 192.0.2.1, custom_future: keep}\nfuture: {value: 2}')
    raw=yaml.safe_load(form_yaml(form['config']))
    assert raw['sip']['custom_future']=='keep' and raw['future']=={'value':2}


@pytest.mark.parametrize('bad',['sip: [secret', 'callers: wrong','null'])
def test_form_errors_do_not_include_input(bad):
    with pytest.raises(ValueError) as error:form_document(bad)
    assert bad not in str(error.value)
