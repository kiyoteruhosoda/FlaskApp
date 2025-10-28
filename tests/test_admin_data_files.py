import pytest

from core.models.user import User, Role, Permission
from webapp.extensions import db


@pytest.fixture
def client(app_context):
    return app_context.test_client()


def _login(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def _setup_admin_with_directories(client, tmp_path):
    app = client.application

    originals_dir = tmp_path / "media"
    thumbs_dir = tmp_path / "thumbs"
    playback_dir = tmp_path / "playback"
    import_dir = tmp_path / "import"

    for directory in (originals_dir, thumbs_dir, playback_dir, import_dir):
        directory.mkdir(parents=True, exist_ok=True)

    (originals_dir / "2024" / "holiday").mkdir(parents=True)
    (originals_dir / "2024" / "holiday" / "photo1.jpg").write_bytes(b"a" * 2048)
    (originals_dir / "2024" / "holiday" / "photo2.jpg").write_bytes(b"b" * 1024)

    thumb_file = thumbs_dir / "256" / "2024" / "holiday" / "photo1.jpg"
    thumb_file.parent.mkdir(parents=True, exist_ok=True)
    thumb_file.write_bytes(b"c" * 512)

    playback_file = playback_dir / "2024" / "holiday" / "photo1.mp4"
    playback_file.parent.mkdir(parents=True, exist_ok=True)
    playback_file.write_bytes(b"d" * 4096)

    import_file = import_dir / "incoming" / "photo2.jpg"
    import_file.parent.mkdir(parents=True, exist_ok=True)
    import_file.write_bytes(b"e" * 256)

    app.config["MEDIA_NAS_ORIGINALS_DIRECTORY"] = str(originals_dir)
    app.config["MEDIA_NAS_THUMBNAILS_DIRECTORY"] = str(thumbs_dir)
    app.config["MEDIA_NAS_PLAYBACK_DIRECTORY"] = str(playback_dir)
    app.config["MEDIA_LOCAL_IMPORT_DIRECTORY"] = str(import_dir)

    admin_role = Role(name="admin")
    system_manage = Permission(code="system:manage")
    db.session.add_all([admin_role, system_manage])
    admin_role.permissions.append(system_manage)
    admin_user = User(email="admin@example.com")
    admin_user.set_password("secret")
    admin_user.roles.append(admin_role)
    db.session.add(admin_user)
    db.session.commit()

    _login(client, admin_user)

    return {
        "originals": originals_dir,
        "thumbs": thumbs_dir,
        "playback": playback_dir,
        "import": import_dir,
    }


def test_data_files_page_shows_selected_directory_only(client, tmp_path):
    paths = _setup_admin_with_directories(client, tmp_path)

    response = client.get("/admin/data-files")
    assert response.status_code == 200

    html = response.data.decode("utf-8")
    assert "photo1.jpg" in html
    assert "photo2.jpg" in html
    assert "photo1.mp4" not in html
    assert "incoming/photo2.jpg" not in html
    assert str(paths["originals"]) in html
    assert "Matching files" in html


def test_data_files_allows_switching_filtering_and_pagination(client, tmp_path):
    _setup_admin_with_directories(client, tmp_path)

    response = client.get("/admin/data-files?directory=MEDIA_NAS_PLAYBACK_DIRECTORY")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "photo1.mp4" in html
    assert "photo1.jpg" not in html

    response = client.get("/admin/data-files?directory=MEDIA_NAS_ORIGINALS_DIRECTORY&per_page=1")
    html = response.data.decode("utf-8")
    assert html.count("photo1.jpg") == 1
    assert "photo2.jpg" not in html
    assert "page-link" in html

    response = client.get("/admin/data-files?directory=MEDIA_NAS_ORIGINALS_DIRECTORY&per_page=1&page=2")
    html = response.data.decode("utf-8")
    assert "photo2.jpg" in html
    assert "photo1.jpg" not in html

    response = client.get("/admin/data-files?directory=MEDIA_NAS_ORIGINALS_DIRECTORY&q=photo2")
    html = response.data.decode("utf-8")
    assert "photo2.jpg" in html
    assert "photo1.jpg" not in html

    response = client.get("/admin/data-files?directory=MEDIA_NAS_ORIGINALS_DIRECTORY&q=nope")
    html = response.data.decode("utf-8")
    assert "No files matched" in html


def test_data_files_requires_system_manage_permission(client):
    user = User(email="user@example.com")
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()

    _login(client, user)

    response = client.get("/admin/data-files")
    assert response.status_code == 403
