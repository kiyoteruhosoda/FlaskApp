import base64
from typer.testing import CliRunner

from fpv.cli import app
from fpv.config import PhotoNestConfig


def _base_env(tmp_path):
    key = base64.urlsafe_b64encode(b'0' * 32).decode('utf-8')
    return {
        'FPV_DB_URL': 'mysql+pymysql://user:pass@localhost/db',
        'FPV_NAS_ORIG_DIR': str(tmp_path / 'orig'),
        'FPV_NAS_PLAY_DIR': str(tmp_path / 'play'),
        'FPV_NAS_THUMBS_DIR': str(tmp_path / 'thumbs'),
        'FPV_TMP_DIR': str(tmp_path / 'tmp'),
        'FPV_GOOGLE_CLIENT_ID': 'client',
        'FPV_GOOGLE_CLIENT_SECRET': 'secret',
        'FPV_OAUTH_KEY': f'base64:{key}',
    }


def test_config_check_valid(tmp_path):
    env = _base_env(tmp_path)
    cfg = PhotoNestConfig.from_env(env)
    warns, errs = cfg.validate()
    assert errs == []
    runner = CliRunner()
    result = runner.invoke(app, ['config', 'check'], env=env)
    assert result.exit_code == 0
    assert 'Configuration is valid' in result.stdout


def test_config_check_missing_required(tmp_path):
    env = _base_env(tmp_path)
    del env['FPV_DB_URL']
    cfg = PhotoNestConfig.from_env(env)
    _, errs = cfg.validate()
    assert 'FPV_DB_URL: not set' in errs
    runner = CliRunner()
    result = runner.invoke(app, ['config', 'check'], env=env)
    assert result.exit_code != 0
    assert 'FPV_DB_URL: not set' in result.stdout


def test_config_fpv_oauth_token_key_file(tmp_path):
    env = _base_env(tmp_path)
    key_val = env['FPV_OAUTH_KEY']
    key_file = tmp_path / 'keyfile'
    key_file.write_text(key_val)
    del env['FPV_OAUTH_KEY']
    env['FPV_OAUTH_TOKEN_KEY_FILE'] = str(key_file)
    cfg = PhotoNestConfig.from_env(env)
    assert cfg.oauth_key == key_val
    warns, errs = cfg.validate()
    assert errs == []
    runner = CliRunner()
    result = runner.invoke(app, ['config', 'check'], env=env)
    assert result.exit_code == 0
    assert 'Configuration is valid' in result.stdout
