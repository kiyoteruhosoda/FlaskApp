"""共有 ORM モデル（複数 bounded context から参照される横断的エンティティ）。

このパッケージを import すると、すべての共有モデルが SQLAlchemy のマッパー
レジストリに登録される。モデル間の relationship 文字列解決に必要なため、
外部から個別サブモジュールを import した場合も、依存モデルを連鎖登録する
副作用として利用される。
"""

from .user import User, Role, Permission
from .group import Group, GroupHierarchyError, group_user_membership
from .google_account import GoogleAccount
from .passkey import PasskeyCredential
from .password_reset_token import PasswordResetToken
from .service_account import ServiceAccount
from .service_account_api_key import ServiceAccountApiKey, ServiceAccountApiKeyLog
from .system_setting import SystemSetting
from .log import Log
from .worker_log import WorkerLog
from .celery_task import CeleryTaskRecord, CeleryTaskStatus
from .job_sync import JobSync

__all__ = [
    "User",
    "Role",
    "Permission",
    "Group",
    "GroupHierarchyError",
    "group_user_membership",
    "GoogleAccount",
    "PasskeyCredential",
    "PasswordResetToken",
    "ServiceAccount",
    "ServiceAccountApiKey",
    "ServiceAccountApiKeyLog",
    "SystemSetting",
    "Log",
    "WorkerLog",
    "CeleryTaskRecord",
    "CeleryTaskStatus",
    "JobSync",
]
