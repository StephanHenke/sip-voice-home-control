from pathlib import Path
import json
import os
import pytest
import yaml
from voice_home.config import load, load_text, credential
from voice_home.credentials import protect_config, encrypt_text, parse_yaml, key_file, web_settings
from voice_home.web import Store

EXAMPLE = Path(__file__).parents[1] / 'config.example.yaml'


@pytest.fixture
def config(tmp_path):
    p = tmp_path / 'config.yaml'
    p.write_text(EXAMPLE.read_text(encoding='utf-8').replace('CHANGE_ME','private-sip-value').replace('token: ""','token: "private-token-value"'),encoding='utf-8')
    return p


def test_roundtrip_idempotent_preserves_comments(config):
    protect_config(config)
    content = config.read_text(encoding='utf-8')
    key = key_file(config).read_bytes()
    assert 'private-sip-value' not in content and 'private-token-value' not in content
    assert 'enc:v1:' in content and '# Keine Freigabe' in content
    cfg = load(config)
    assert credential(cfg.sip,'password') == 'private-sip-value'
    assert credential(cfg.openhab,'token') == 'private-token-value'
    protect_config(config)
    assert config.read_text(encoding='utf-8') == content and key_file(config).read_bytes() == key
    if os.name != 'nt':
        assert key_file(config).stat().st_mode & 0o777 == 0o600
        assert config.stat().st_mode & 0o777 == 0o600


def test_wrong_missing_key_and_tampering_fail_closed(config):
    protect_config(config)
    key_file(config).unlink()
    with pytest.raises(ValueError): protect_config(config)
    assert not key_file(config).exists()  # Never invent replacement key for encrypted YAML.
    from cryptography.fernet import Fernet
    key_file(config).write_bytes(Fernet.generate_key()); key_file(config).chmod(0o600)
    with pytest.raises(ValueError): load(config)


def test_web_save_and_old_versions_never_store_plaintext(config):
    versions = config.parent / '.versions';versions.mkdir()
    (versions/'old.yaml').write_text(config.read_text(encoding='utf-8'),encoding='utf-8')
    store = Store(config)
    current=store.read()
    raw=parse_yaml(current['yaml']);raw['sip']['password']='replacement-private'
    saved=store.save(yaml.safe_dump(raw),current['revision'])
    assert credential(load(config).sip,'password')=='replacement-private'
    assert saved['yaml']==config.read_text(encoding='utf-8')
    for p in [config,*versions.glob('*.yaml')]:
        text=p.read_text(encoding='utf-8')
        assert 'private-sip-value' not in text and 'replacement-private' not in text
    assert not list(config.parent.glob('.validate-*'))


def test_validation_does_not_write_plaintext_or_generate_key(config):
    store=Store(config)
    old_files={p.name:p.read_bytes() for p in config.parent.iterdir() if p.is_file()}
    raw=parse_yaml(store.read()['yaml']);raw['sip']['password']='temporary-private'
    store.validate(yaml.safe_dump(raw))
    assert old_files=={p.name:p.read_bytes() for p in config.parent.iterdir() if p.is_file()}


def test_export_import_with_key(config,tmp_path):
    protect_config(config)
    other=tmp_path/'new';other.mkdir();p=other/'config.yaml';p.write_bytes(config.read_bytes())
    with pytest.raises(ValueError): load(p)
    key_file(p).write_bytes(key_file(config).read_bytes());key_file(p).chmod(0o600)
    assert credential(load(p).sip,'password')=='private-sip-value'


def test_relative_secret_file_unchanged(config):
    raw=parse_yaml(config.read_text(encoding='utf-8'))
    raw['sip'].pop('password');raw['sip']['password_file']='sip.secret'
    source=config.parent/'sip.secret';source.write_text('external-secret')
    config.write_text(yaml.safe_dump(raw),encoding='utf-8');protect_config(config)
    assert credential(load(config).sip,'password')=='external-secret'
    assert source.read_text()=='external-secret'


def test_multiline_password_keeps_next_field(config):
    text='sip:\n  password: |\n    two\n    lines\n  host: 192.0.2.1\n'
    encoded=encrypt_text(text,config)
    assert parse_yaml(encoded)['sip']['host']=='192.0.2.1'


@pytest.mark.parametrize('text',['sip: {password: a, password: b}', 'x: &x [*x]'])
def test_ambiguous_yaml_rejected(text):
    with pytest.raises(ValueError):parse_yaml(text)


def test_disabled_web_opens_no_listener(config,monkeypatch):
    from voice_home import web
    raw=parse_yaml(config.read_text(encoding='utf-8'));raw['web']['enabled']=False
    config.write_text(yaml.safe_dump(raw),encoding='utf-8')
    calls=[]
    monkeypatch.setattr(web.os,'execv',lambda *args:calls.append(args))
    monkeypatch.setattr(web,'initialize_password',lambda:pytest.fail('Auth must not initialize'))
    monkeypatch.setattr(web,'ThreadingHTTPServer',lambda *a:pytest.fail('Listener must not open'))
    web.serve(config)
    assert calls and calls[0][1][-1]=='serve'


@pytest.mark.parametrize('value', ['false',0,None])
def test_disabled_requires_real_boolean(value):
    with pytest.raises(ValueError):web_settings({'web':{'enabled':value}})
