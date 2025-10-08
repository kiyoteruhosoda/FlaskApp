"""Wikiドメインで利用する例外定義"""


class WikiError(Exception):
    """Wiki機能における基底例外"""


class WikiPageNotFoundError(WikiError):
    """ページが存在しない場合の例外"""


class WikiAccessDeniedError(WikiError):
    """権限不足を表す例外"""


class WikiValidationError(WikiError):
    """入力値の検証エラー"""


class WikiOperationError(WikiError):
    """その他の操作エラーを表す例外"""
