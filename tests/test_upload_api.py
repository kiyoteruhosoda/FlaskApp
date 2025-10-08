import io
from pathlib import Path

import pytest

from core.models.user import User
from webapp.extensions import db
from webapp.services.token_service import TokenService


@pytest.fixture
def client(app_context, tmp_path):
    app = app_context
    app.config['UPLOAD_TMP_DIR'] = str(tmp_path / 'tmp')
    app.config['UPLOAD_DESTINATION_DIR'] = str(tmp_path / 'dest')
    app.config['UPLOAD_MAX_SIZE'] = 1024 * 1024

    (tmp_path / 'tmp').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'dest').mkdir(parents=True, exist_ok=True)

    with app.app_context():
        user = User(email='upload@example.com')
        user.set_password('password')
        db.session.add(user)
        db.session.commit()

    return app.test_client()


@pytest.fixture
def auth_headers(client):
    app = client.application
    with app.app_context():
        user = User.query.filter_by(email='upload@example.com').first()
        token = TokenService.generate_access_token(user)
    return {'Authorization': f'Bearer {token}'}


def test_prepare_upload_accepts_png_image(client, auth_headers):
    file_content = b'\x89PNG\r\n\x1a\n' + (b'\x00' * 32)
    response = client.post(
        '/api/upload/prepare',
        data={'file': (io.BytesIO(file_content), 'sample.png')},
        headers=auth_headers,
        content_type='multipart/form-data',
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['fileName'] == 'sample.png'
    assert payload['status'] == 'analyzed'
    assert payload['fileSize'] == len(file_content)
    assert payload['analysisResult']['format'] == 'IMAGE'

    with client.session_transaction() as sess:
        session_id = sess.get('upload_session_id')

    assert session_id
    tmp_dir = Path(client.application.config['UPLOAD_TMP_DIR']) / session_id
    stored_path = tmp_dir / payload['tempFileId']
    metadata_path = tmp_dir / f"{payload['tempFileId']}.json"
    assert stored_path.exists()
    assert metadata_path.exists()


def test_prepare_upload_allows_mp4(client, auth_headers):
    mp4_header = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41"
    file_content = mp4_header + (b"\x00" * 1024)

    response = client.post(
        '/api/upload/prepare',
        data={'file': (io.BytesIO(file_content), 'clip.mp4')},
        headers=auth_headers,
        content_type='multipart/form-data',
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['fileName'] == 'clip.mp4'
    assert payload['fileSize'] == len(file_content)
    assert payload['analysisResult']['format'] == 'VIDEO'

    with client.session_transaction() as sess:
        session_id = sess.get('upload_session_id')

    assert session_id
    tmp_dir = Path(client.application.config['UPLOAD_TMP_DIR']) / session_id
    stored_path = tmp_dir / payload['tempFileId']
    assert stored_path.exists()
    assert stored_path.read_bytes() == file_content


def test_prepare_upload_allows_mov(client, auth_headers):
    mov_header = b"\x00\x00\x00\x14ftypqt  \x00\x00\x02\x00qt  "
    file_content = mov_header + (b"\x11" * 256)

    response = client.post(
        '/api/upload/prepare',
        data={'file': (io.BytesIO(file_content), 'scene.mov')},
        headers=auth_headers,
        content_type='multipart/form-data',
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['fileName'] == 'scene.mov'
    assert payload['fileSize'] == len(file_content)
    assert payload['analysisResult']['format'] == 'VIDEO'

    with client.session_transaction() as sess:
        session_id = sess.get('upload_session_id')

    assert session_id
    tmp_dir = Path(client.application.config['UPLOAD_TMP_DIR']) / session_id
    stored_path = tmp_dir / payload['tempFileId']
    assert stored_path.exists()
    assert stored_path.read_bytes() == file_content


def test_commit_upload_moves_files(client, auth_headers):
    file_content = b'PNGDATA'
    prepare_resp = client.post(
        '/api/upload/prepare',
        data={'file': (io.BytesIO(file_content), 'commit.png')},
        headers=auth_headers,
        content_type='multipart/form-data',
    )
    temp_payload = prepare_resp.get_json()
    assert prepare_resp.status_code == 200

    with client.session_transaction() as sess:
        session_id = sess.get('upload_session_id')

    assert session_id
    tmp_dir = Path(client.application.config['UPLOAD_TMP_DIR']) / session_id
    assert tmp_dir.exists()

    commit_resp = client.post(
        '/api/upload/commit',
        json={'files': [{'tempFileId': temp_payload['tempFileId']}]},
        headers=auth_headers,
    )
    assert commit_resp.status_code == 200
    commit_data = commit_resp.get_json()
    assert commit_data['uploaded'][0]['status'] == 'success'

    assert not tmp_dir.exists()

    with client.session_transaction() as sess:
        assert 'upload_session_id' not in sess

    app = client.application
    with app.app_context():
        user = User.query.filter_by(email='upload@example.com').first()
        dest_dir = Path(app.config['UPLOAD_DESTINATION_DIR']) / str(user.id)
        stored_file = dest_dir / 'commit.png'
        assert stored_file.exists()
        assert stored_file.read_bytes() == file_content


@pytest.mark.parametrize('filename', ['payload.csv', 'payload.tsv', 'payload.json', 'payload.txt', 'payload.exe'])
def test_prepare_rejects_unsupported_extension(client, auth_headers, filename):
    response = client.post(
        '/api/upload/prepare',
        data={'file': (io.BytesIO(b'not allowed'), filename)},
        headers=auth_headers,
        content_type='multipart/form-data',
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload['error'] == 'unsupported_format'


def test_commit_partial_keeps_session_and_files(client, auth_headers):
    first_file = b'PNG1'
    second_file = b'JPEG2'

    first_resp = client.post(
        '/api/upload/prepare',
        data={'file': (io.BytesIO(first_file), 'first.png')},
        headers=auth_headers,
        content_type='multipart/form-data',
    )
    second_resp = client.post(
        '/api/upload/prepare',
        data={'file': (io.BytesIO(second_file), 'second.jpg')},
        headers=auth_headers,
        content_type='multipart/form-data',
    )

    first_payload = first_resp.get_json()
    second_payload = second_resp.get_json()

    with client.session_transaction() as sess:
        session_id = sess.get('upload_session_id')

    assert session_id

    partial_commit = client.post(
        '/api/upload/commit',
        json={'files': [{'tempFileId': first_payload['tempFileId']}]},
        headers=auth_headers,
    )

    assert partial_commit.status_code == 200
    partial_data = partial_commit.get_json()
    assert partial_data['uploaded'][0]['status'] == 'success'

    with client.session_transaction() as sess:
        assert sess.get('upload_session_id') == session_id

    tmp_dir = Path(client.application.config['UPLOAD_TMP_DIR']) / session_id
    remaining_file = tmp_dir / second_payload['tempFileId']
    remaining_metadata = tmp_dir / f"{second_payload['tempFileId']}.json"

    assert remaining_file.exists()
    assert remaining_metadata.exists()
