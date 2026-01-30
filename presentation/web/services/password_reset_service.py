"""Password reset service."""
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from flask import current_app, url_for
from flask_babel import gettext as _

from core.db import db
from core.models.password_reset_token import PasswordResetToken
from core.models.user import User
from webapp.utils import determine_external_scheme
from bounded_contexts.email_service import EmailService


class PasswordResetService:
    """パスワードリセット機能を提供するサービス。"""

    TOKEN_LENGTH = 32  # 256 bits
    TOKEN_VALIDITY_MINUTES = 30

    @classmethod
    def generate_reset_token(cls) -> str:
        """セキュアなランダムトークンを生成する。
        
        Returns:
            256ビットのランダムトークン（hex文字列）
        """
        return secrets.token_urlsafe(cls.TOKEN_LENGTH)

    @classmethod
    def create_reset_request(cls, email: str) -> tuple[bool, Optional[str]]:
        """パスワードリセットリクエストを作成し、メールを送信する。
        
        セキュリティ上の理由から、メールアドレスが存在するかどうかに関わらず
        常にTrueを返す（アカウント存在確認攻撃を防ぐため）。
        ただし、メール機能が無効な場合は、ユーザーに通知するためにFalseとエラーメッセージを返す。
        
        Args:
            email: リセット対象のメールアドレス
            
        Returns:
            tuple[bool, Optional[str]]: (成功フラグ, エラーメッセージ)
                - メール機能が無効な場合: (False, エラーメッセージ)
                - その他の場合: (True, None) - セキュリティのため常に成功を返す
        """
        # メール機能が有効かチェック（先にチェックして早期リターン）
        from core.settings import settings
        if not settings.mail_enabled:
            current_app.logger.warning(
                "Password reset requested but mail is disabled",
                extra={"event": "password_reset.mail_disabled", "email": email}
            )
            return (
                False,
                _(
                    "Failed to send email. A valid mail sender is not configured. Please contact the administrator."
                ),
            )
        
        user = db.session.query(User).filter_by(email=email).first()
        
        if user and user.is_active:
            # トークン生成
            raw_token = cls.generate_reset_token()
            
            # 既存の未使用トークンを無効化
            existing_tokens = db.session.query(PasswordResetToken).filter_by(
                email=email,
                used=False
            ).all()
            for token in existing_tokens:
                token.mark_as_used()
            
            # 新しいトークンを作成
            reset_token = PasswordResetToken.create_token(
                email=email,
                raw_token=raw_token,
                validity_minutes=cls.TOKEN_VALIDITY_MINUTES
            )
            db.session.add(reset_token)
            db.session.commit()
            
            # メール送信
            try:
                cls._send_reset_email(email, raw_token)
            except Exception as e:
                current_app.logger.error(
                    f"Failed to send password reset email: {e}",
                    extra={"event": "password_reset.email_failed", "email": email}
                )
                # メール送信に失敗してもトークンは作成済みなので、
                # ユーザーには成功を返す（情報漏洩防止）
        
        # セキュリティ: メールが存在するかどうかに関わらず成功を返す
        return (True, None)

    @classmethod
    def _send_reset_email(cls, email: str, token: str) -> None:
        """パスワードリセットメールを送信する。
        
        新しいEmailServiceを使用してメールを送信します。
        
        Args:
            email: 送信先メールアドレス
            token: リセットトークン（平文）
            
        Raises:
            RuntimeError: メール機能が無効、または送信に失敗した場合
        """
        # メール機能が有効かチェック
        from core.settings import settings
        if not settings.mail_enabled:
            raise RuntimeError(
                _(
                    "Failed to send email. A valid mail sender is not configured. Please contact the administrator."
                )
            )
        
        # リセットURLを生成
        # determine_external_schemeを使用してスキームを決定
        from flask import request
        scheme = determine_external_scheme(request) if request else 'https'
        reset_url = url_for(
            'auth.password_reset',
            token=token,
            _external=True,
            _scheme=scheme
        )
        
        # EmailServiceを使用してメール送信
        email_service = EmailService()
        success = email_service.send_password_reset_email(
            email=email,
            reset_url=reset_url,
            validity_minutes=cls.TOKEN_VALIDITY_MINUTES
        )
        
        if success:
            current_app.logger.info(
                "Password reset email sent",
                extra={"event": "password_reset.email_sent", "email": email}
            )
        else:
            raise RuntimeError(
                _(
                    "Failed to send email. A valid mail sender is not configured. Please contact the administrator."
                )
            )

    @classmethod
    def verify_token(cls, token: str) -> Optional[str]:
        """トークンを検証し、対応するメールアドレスを返す。
        
        Args:
            token: 検証するトークン（平文）
            
        Returns:
            有効な場合はメールアドレス、無効な場合はNone
        """
        # トークンハッシュで検索できないため、全てのアクティブなトークンを取得
        # （有効期限内かつ未使用）
        # NOTE: パフォーマンス最適化: 実運用では古いトークンの定期的なクリーンアップを推奨
        # また、インデックス（used, expires_at）により検索は効率化される
        now = datetime.now(timezone.utc)
        active_tokens = db.session.query(PasswordResetToken).filter(
            PasswordResetToken.used == False,
            PasswordResetToken.expires_at > now
        ).all()
        
        # トークンを検証
        for reset_token in active_tokens:
            if reset_token.check_token(token):
                if reset_token.is_valid():
                    return reset_token.email
        
        return None

    @classmethod
    def reset_password(cls, token: str, new_password: str) -> bool:
        """トークンを使用してパスワードをリセットする。
        
        Args:
            token: リセットトークン（平文）
            new_password: 新しいパスワード
            
        Returns:
            成功した場合True、失敗した場合False
        """
        # トークンを検証（verify_tokenメソッドを再利用）
        email = cls.verify_token(token)
        if not email:
            return False
        
        user = db.session.query(User).filter_by(email=email).first()
        if not user or not user.is_active:
            return False
        
        # トークンオブジェクトを取得（メールアドレスから）
        now = datetime.now(timezone.utc)
        matching_token = db.session.query(PasswordResetToken).filter(
            PasswordResetToken.email == email,
            PasswordResetToken.used == False,
            PasswordResetToken.expires_at > now
        ).first()
        
        # トークンが見つからない場合（verify_tokenで検証済みのはずだが念のため）
        if not matching_token or not matching_token.check_token(token):
            return False
        
        # トークンを原子的に使用済みにマークする（並行アクセス対策）
        # この操作は、used = false の条件付きでUPDATEを実行するため、
        # 2つの並行リクエストのうち1つだけが成功する
        token_marked = PasswordResetToken.mark_as_used_atomic(
            matching_token.id, 
            email
        )
        
        if not token_marked:
            # トークンが既に使用済みの場合（並行リクエストで先に使用された）
            current_app.logger.warning(
                "Token already used (concurrent access detected)",
                extra={
                    "event": "password_reset.token_already_used",
                    "email": email,
                    "token_id": matching_token.id
                }
            )
            return False
        
        # パスワードを更新
        user.set_password(new_password)
        
        db.session.commit()
        
        current_app.logger.info(
            "Password reset successful",
            extra={"event": "password_reset.success", "email": email}
        )
        
        return True
