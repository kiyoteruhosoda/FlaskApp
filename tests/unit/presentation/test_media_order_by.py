"""メディア一覧のソート条件がMariaDBと互換であることの回帰テスト。

`Media.shot_at.desc().nullslast()` を MariaDB 向けにコンパイルすると
`ORDER BY ... NULLS LAST` という MariaDB が解釈できない構文が生成され、
`GET /api/media` が実運用で 500（SQL構文エラー）になっていた。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects import mysql

from presentation.fastapi.routers.media import media_shot_at_order_by_criteria


def _media_model():
    from shared.kernel.database.db import db  # noqa: F401
    import shared.infrastructure.models.user  # noqa: F401
    import shared.infrastructure.models.google_account  # noqa: F401
    import bounded_contexts.photonest.infrastructure.photo_models as photo_models

    return photo_models.Media


def test_order_by_desc_has_no_nulls_last_in_mariadb_sql():
    Media = _media_model()
    criteria = media_shot_at_order_by_criteria(Media, "desc")
    sql = str(
        select(Media).order_by(*criteria).compile(dialect=mysql.dialect())
    )
    assert "NULLS LAST" not in sql.upper()
    assert "NULLS FIRST" not in sql.upper()


def test_order_by_asc_has_no_nulls_last_in_mariadb_sql():
    Media = _media_model()
    criteria = media_shot_at_order_by_criteria(Media, "asc")
    sql = str(
        select(Media).order_by(*criteria).compile(dialect=mysql.dialect())
    )
    assert "NULLS LAST" not in sql.upper()
    assert "NULLS FIRST" not in sql.upper()


def test_order_by_criteria_count_matches_expected_columns():
    """CASE式 + shot_at + id の3条件であること（NULL振り分け+実ソート+タイブレーク）。"""
    Media = _media_model()
    assert len(media_shot_at_order_by_criteria(Media, "desc")) == 3
    assert len(media_shot_at_order_by_criteria(Media, "asc")) == 3
