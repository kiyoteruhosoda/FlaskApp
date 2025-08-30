"""
JWT トークン管理サービス
"""
import secrets
import jwt
from datetime import datetime, timezone, timedelta
from flask import current_app
from typing import Tuple, Optional

from webapp.extensions import db
from core.models.user import User


class TokenService:
    """JWT アクセストークンとリフレッシュトークンの管理を行うサービス"""
    
    # トークンの有効期限設定
    ACCESS_TOKEN_EXPIRE_HOURS = 1
    REFRESH_TOKEN_EXPIRE_DAYS = 30
    
    @classmethod
    def generate_access_token(cls, user: User) -> str:
        """
        アクセストークンを生成する
        
        Args:
            user: ユーザーオブジェクト
            
        Returns:
            JWT アクセストークン文字列
        """
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user.id),  # ユーザーID（文字列）
            "email": user.email,  # デバッグ用
            "exp": now + timedelta(hours=cls.ACCESS_TOKEN_EXPIRE_HOURS),
            "iat": now,
            "jti": secrets.token_urlsafe(8),  # JWT ID
            "type": "access"
        }
        
        return jwt.encode(
            payload,
            current_app.config["JWT_SECRET_KEY"],
            algorithm="HS256"
        )
    
    @classmethod
    def generate_refresh_token(cls, user: User) -> str:
        """
        リフレッシュトークンを生成し、DBに保存する
        
        Args:
            user: ユーザーオブジェクト
            
        Returns:
            リフレッシュトークン文字列
        """
        refresh_raw = secrets.token_urlsafe(32)
        refresh_token = f"{user.id}:{refresh_raw}"
        
        # DBに保存
        user.set_refresh_token(refresh_token)
        db.session.commit()
        
        return refresh_token
    
    @classmethod
    def generate_token_pair(cls, user: User) -> Tuple[str, str]:
        """
        アクセストークンとリフレッシュトークンのペアを生成する
        
        Args:
            user: ユーザーオブジェクト
            
        Returns:
            (access_token, refresh_token) のタプル
        """
        access_token = cls.generate_access_token(user)
        refresh_token = cls.generate_refresh_token(user)
        
        return access_token, refresh_token
    
    @classmethod
    def verify_access_token(cls, token: str) -> Optional[User]:
        """
        アクセストークンを検証してユーザーを取得する
        
        Args:
            token: JWT アクセストークン
            
        Returns:
            ユーザーオブジェクト（無効な場合はNone）
        """
        try:
            payload = jwt.decode(
                token,
                current_app.config["JWT_SECRET_KEY"],
                algorithms=["HS256"]
            )
            
            user_id = int(payload["sub"])
            user = User.query.get(user_id)
            
            if not user or not user.is_active:
                return None
                
            return user
            
        except jwt.ExpiredSignatureError:
            current_app.logger.debug("JWT token expired")
            return None
        except jwt.InvalidTokenError as e:
            current_app.logger.debug(f"JWT token invalid: {e}")
            return None
        except (ValueError, TypeError):
            current_app.logger.debug("JWT token format error")
            return None
    
    @classmethod
    def verify_refresh_token(cls, refresh_token: str) -> Optional[User]:
        """
        リフレッシュトークンを検証してユーザーを取得する
        
        Args:
            refresh_token: リフレッシュトークン文字列
            
        Returns:
            ユーザーオブジェクト（無効な場合はNone）
        """
        if not refresh_token:
            return None
            
        try:
            user_id_str, _ = refresh_token.split(":", 1)
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            current_app.logger.debug("Invalid refresh token format")
            return None
        
        user = User.query.get(user_id)
        if not user or not user.check_refresh_token(refresh_token):
            current_app.logger.debug("Refresh token verification failed")
            return None
            
        return user
    
    @classmethod
    def refresh_tokens(cls, refresh_token: str) -> Optional[Tuple[str, str]]:
        """
        リフレッシュトークンから新しいトークンペアを生成する
        
        Args:
            refresh_token: 現在のリフレッシュトークン
            
        Returns:
            新しい (access_token, refresh_token) のタプル（失敗時はNone）
        """
        user = cls.verify_refresh_token(refresh_token)
        if not user:
            return None
            
        # 新しいトークンペアを生成（リフレッシュトークンローテーション）
        return cls.generate_token_pair(user)
    
    @classmethod
    def revoke_refresh_token(cls, user: User) -> None:
        """
        ユーザーのリフレッシュトークンを無効化する
        
        Args:
            user: ユーザーオブジェクト
        """
        user.set_refresh_token(None)
        db.session.commit()
