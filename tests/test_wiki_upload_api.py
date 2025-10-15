import hashlib
import io
from pathlib import Path

import pytest

from core.models.photo_models import Media
from core.models.user import Permission, Role, User
from webapp.extensions import db
from webapp.services.token_service import TokenService


def _ensure_permission(user: User, code: str, role_name: str = "wiki-uploader") -> None:
    perm = Permission.query.filter_by(code=code).first()
    if not perm:
        perm = Permission(code=code)
        db.session.add(perm)
        db.session.flush()

    role = Role.query.filter_by(name=role_name).first()
    if not role:
        role = Role(name=role_name)
        db.session.add(role)
        db.session.flush()

    if perm not in role.permissions:
        role.permissions.append(perm)

    if role not in user.roles:
        user.roles.append(role)

    db.session.commit()


@pytest.fixture
def wiki_client(app_context, tmp_path):
    app = app_context
    app.config['UPLOAD_TMP_DIR'] = str(tmp_path / 'tmp')
    app.config['WIKI_UPLOAD_DIR'] = str(tmp_path / 'wiki')
    app.config['UPLOAD_MAX_SIZE'] = 1024 * 1024

    (tmp_path / 'tmp').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'wiki').mkdir(parents=True, exist_ok=True)

    with app.app_context():
        user = User(email='wiki@example.com')
        user.set_password('password')
        db.session.add(user)
        db.session.flush()
        _ensure_permission(user, 'wiki:write')

    return app.test_client()


@pytest.fixture
def wiki_auth_headers(wiki_client):
    app = wiki_client.application
    with app.app_context():
        user = User.query.filter_by(email='wiki@example.com').first()
        token = TokenService.generate_access_token(user)
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def wiki_client_no_perm(app_context, tmp_path):
    app = app_context
    app.config['UPLOAD_TMP_DIR'] = str(tmp_path / 'tmp_no_perm')
    app.config['WIKI_UPLOAD_DIR'] = str(tmp_path / 'wiki_no_perm')
    app.config['UPLOAD_MAX_SIZE'] = 1024 * 1024

    (tmp_path / 'tmp_no_perm').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'wiki_no_perm').mkdir(parents=True, exist_ok=True)

    with app.app_context():
        user = User(email='wiki-noperm@example.com')
        user.set_password('password')
        db.session.add(user)
        db.session.commit()

    return app.test_client()


@pytest.fixture
def wiki_auth_headers_no_perm(wiki_client_no_perm):
    app = wiki_client_no_perm.application
    with app.app_context():
        user = User.query.filter_by(email='wiki-noperm@example.com').first()
        token = TokenService.generate_access_token(user)
    return {'Authorization': f'Bearer {token}'}


def test_wiki_upload_creates_media_record(wiki_client, wiki_auth_headers):
    file_content = b'WikiImage'

    prepare_resp = wiki_client.post(
        '/api/upload/prepare',
        data={'file': (io.BytesIO(file_content), 'diagram.png')},
        headers=wiki_auth_headers,
        content_type='multipart/form-data',
    )
    assert prepare_resp.status_code == 200
    prepared = prepare_resp.get_json()

    commit_resp = wiki_client.post(
        '/api/upload/commit',
        json={'destination': 'wiki', 'files': [{'tempFileId': prepared['tempFileId']}]},
        headers=wiki_auth_headers,
    )
    assert commit_resp.status_code == 200
    payload = commit_resp.get_json()

    uploaded = payload['uploaded'][0]
    assert uploaded['status'] == 'success'
    assert uploaded['hashSha256'] == hashlib.sha256(file_content).hexdigest()

    media_items = payload.get('media') or []
    assert len(media_items) == 1
    media_payload = media_items[0]
    assert media_payload['sourceType'] == 'wiki-media'
    assert media_payload['hashSha256'] == uploaded['hashSha256']

    wiki_dir = Path(wiki_client.application.config['WIKI_UPLOAD_DIR'])
    stored_file = (
        wiki_dir / Path(uploaded['relativePath'])
        if uploaded.get('relativePath')
        else wiki_dir / Path(uploaded['storedPath']).name
    )
    assert stored_file.exists()
    assert stored_file.read_bytes() == file_content

    with wiki_client.application.app_context():
        media = Media.query.get(media_payload['id'])
        assert media is not None
        assert media.source_type == 'wiki-media'
        assert media.local_rel_path == media_payload['localRelPath']
        assert media.hash_sha256 == uploaded['hashSha256']


def test_wiki_upload_requires_permission(wiki_client_no_perm, wiki_auth_headers_no_perm):
    file_content = b'NoPerm'

    prepare_resp = wiki_client_no_perm.post(
        '/api/upload/prepare',
        data={'file': (io.BytesIO(file_content), 'restricted.png')},
        headers=wiki_auth_headers_no_perm,
        content_type='multipart/form-data',
    )
    assert prepare_resp.status_code == 200
    prepared = prepare_resp.get_json()

    commit_resp = wiki_client_no_perm.post(
        '/api/upload/commit',
        json={'destination': 'wiki', 'files': [{'tempFileId': prepared['tempFileId']}]},
        headers=wiki_auth_headers_no_perm,
    )
    assert commit_resp.status_code == 403
    payload = commit_resp.get_json()
    assert payload['error'] == 'forbidden'
