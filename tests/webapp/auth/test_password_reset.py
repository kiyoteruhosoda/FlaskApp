"""Tests for password reset functionality."""
import pytest
from datetime import datetime, timezone, timedelta
from flask import url_for
from unittest.mock import patch, MagicMock

from core.db import db
from core.models.user import User, Role
from core.models.password_reset_token import PasswordResetToken
from webapp.services.password_reset_service import PasswordResetService


@pytest.fixture
def client(app_context):
    """Create test client."""
    return app_context.test_client()


def _create_test_user(email="test@example.com", password="oldpassword123", is_active=True):
    """Create a test user."""
    # Create guest role if it doesn't exist
    guest_role = Role.query.filter_by(name="guest").first()
    if not guest_role:
        guest_role = Role(name="guest")
        db.session.add(guest_role)
        db.session.flush()
    
    user = User(email=email, is_active=is_active)
    user.set_password(password)
    if is_active:
        user.roles.append(guest_role)
    db.session.add(user)
    db.session.commit()
    return user


class TestPasswordResetService:
    """Test PasswordResetService class."""
    
    def test_generate_reset_token(self):
        """Test token generation."""
        token = PasswordResetService.generate_reset_token()
        assert token is not None
        assert len(token) > 0
        
        # Tokens should be unique
        token2 = PasswordResetService.generate_reset_token()
        assert token != token2
    
    def test_create_reset_request_active_user(self, app_context):
        """Test creating a reset request for an active user."""
        test_user = _create_test_user()
        
        # Mock mail sending to avoid actual email
        with app_context.test_request_context():
            with patch('webapp.services.password_reset_service.mail.send') as mock_send:
                result = PasswordResetService.create_reset_request(test_user.email)
                assert result is True
                assert mock_send.called
                
                # Check that token was created
                token = PasswordResetToken.query.filter_by(email=test_user.email).first()
                assert token is not None
                assert token.used is False
                # Handle timezone-naive datetime from SQLite
                expires = token.expires_at
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                assert expires > datetime.now(timezone.utc)
    
    def test_create_reset_request_nonexistent_user(self, app_context):
        """Test creating a reset request for non-existent user returns True."""
        with app_context.test_request_context():
            with patch('webapp.services.password_reset_service.mail.send') as mock_send:
                result = PasswordResetService.create_reset_request("nonexistent@example.com")
                # Should return True to prevent user enumeration
                assert result is True
                # Mail should not be sent
                assert not mock_send.called
                
                # No token should be created
                token = PasswordResetToken.query.filter_by(email="nonexistent@example.com").first()
                assert token is None
    
    def test_create_reset_request_inactive_user(self, app_context):
        """Test creating a reset request for inactive user returns True."""
        inactive_user = _create_test_user(email="inactive@example.com", is_active=False)
        
        with app_context.test_request_context():
            with patch('webapp.services.password_reset_service.mail.send') as mock_send:
                result = PasswordResetService.create_reset_request(inactive_user.email)
                # Should return True to prevent user enumeration
                assert result is True
                # Mail should not be sent
                assert not mock_send.called
                
                # No token should be created for inactive users
                token = PasswordResetToken.query.filter_by(email=inactive_user.email).first()
                assert token is None
    
    def test_verify_token_valid(self, app_context):
        """Test verifying a valid token."""
        test_user = _create_test_user()
        raw_token = PasswordResetService.generate_reset_token()
        reset_token = PasswordResetToken.create_token(test_user.email, raw_token)
        db.session.add(reset_token)
        db.session.commit()
        
        email = PasswordResetService.verify_token(raw_token)
        assert email == test_user.email
    
    def test_verify_token_invalid(self, app_context):
        """Test verifying an invalid token."""
        email = PasswordResetService.verify_token("invalid-token")
        assert email is None
    
    def test_verify_token_expired(self, app_context):
        """Test verifying an expired token."""
        test_user = _create_test_user()
        raw_token = PasswordResetService.generate_reset_token()
        reset_token = PasswordResetToken(
            email=test_user.email,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        reset_token.set_token(raw_token)
        db.session.add(reset_token)
        db.session.commit()
        
        email = PasswordResetService.verify_token(raw_token)
        assert email is None
    
    def test_verify_token_used(self, app_context):
        """Test verifying a used token."""
        test_user = _create_test_user()
        raw_token = PasswordResetService.generate_reset_token()
        reset_token = PasswordResetToken.create_token(test_user.email, raw_token)
        reset_token.mark_as_used()
        db.session.add(reset_token)
        db.session.commit()
        
        email = PasswordResetService.verify_token(raw_token)
        assert email is None
    
    def test_reset_password_success(self, app_context):
        """Test successful password reset."""
        test_user = _create_test_user()
        raw_token = PasswordResetService.generate_reset_token()
        reset_token = PasswordResetToken.create_token(test_user.email, raw_token)
        db.session.add(reset_token)
        db.session.commit()
        
        new_password = "newpassword456"
        result = PasswordResetService.reset_password(raw_token, new_password)
        assert result is True
        
        # Verify password was changed
        user = User.query.filter_by(email=test_user.email).first()
        assert user.check_password(new_password)
        assert not user.check_password("oldpassword123")
        
        # Verify token was marked as used
        reset_token = PasswordResetToken.query.filter_by(email=test_user.email).first()
        assert reset_token.used is True
    
    def test_reset_password_invalid_token(self, app_context):
        """Test password reset with invalid token."""
        result = PasswordResetService.reset_password("invalid-token", "newpass")
        assert result is False
    
    def test_reset_password_token_reuse_prevention(self, app_context):
        """Test that a token cannot be reused."""
        test_user = _create_test_user()
        raw_token = PasswordResetService.generate_reset_token()
        reset_token = PasswordResetToken.create_token(test_user.email, raw_token)
        db.session.add(reset_token)
        db.session.commit()
        
        # First reset should succeed
        result1 = PasswordResetService.reset_password(raw_token, "newpass1")
        assert result1 is True
        
        # Second reset with same token should fail
        result2 = PasswordResetService.reset_password(raw_token, "newpass2")
        assert result2 is False
        
        # Verify password is still from first reset
        user = User.query.filter_by(email=test_user.email).first()
        assert user.check_password("newpass1")
        assert not user.check_password("newpass2")
    
    def test_atomic_token_update_prevents_race_condition(self, app_context):
        """Test that atomic token update prevents race conditions."""
        test_user = _create_test_user()
        raw_token = PasswordResetService.generate_reset_token()
        reset_token = PasswordResetToken.create_token(test_user.email, raw_token)
        db.session.add(reset_token)
        db.session.commit()
        token_id = reset_token.id
        
        # 最初のリセットでトークンを原子的にマークする
        result1 = PasswordResetToken.mark_as_used_atomic(token_id, test_user.email)
        assert result1 is True, "First atomic update should succeed"
        db.session.commit()
        
        # 2回目の試行は失敗すべき（トークンは既に使用済み）
        result2 = PasswordResetToken.mark_as_used_atomic(token_id, test_user.email)
        assert result2 is False, "Second atomic update should fail (token already used)"
        
        # トークンが使用済みであることを確認
        token_after = PasswordResetToken.query.filter_by(id=token_id).first()
        assert token_after.used is True
    
    def test_reset_password_detects_already_used_token(self, app_context):
        """Test that reset_password correctly detects and rejects already-used tokens."""
        test_user = _create_test_user()
        raw_token = PasswordResetService.generate_reset_token()
        reset_token = PasswordResetToken.create_token(test_user.email, raw_token)
        db.session.add(reset_token)
        db.session.commit()
        token_id = reset_token.id
        
        # 最初のリセットが成功
        result1 = PasswordResetService.reset_password(raw_token, "password1")
        assert result1 is True, "First password reset should succeed"
        
        # トークンが使用済みであることを確認
        db.session.expire_all()
        token_after = PasswordResetToken.query.filter_by(id=token_id).first()
        assert token_after.used is True, "Token should be marked as used"
        
        # 別のコードパスで同じトークンを原子的に更新しようとすると失敗すべき
        # （これは並行リクエストの2番目のリクエストをシミュレート）
        result2 = PasswordResetToken.mark_as_used_atomic(token_id, test_user.email)
        assert result2 is False, "Atomic update should fail on already-used token"
        
        # 2回目のパスワードリセットも失敗すべき
        result3 = PasswordResetService.reset_password(raw_token, "password2")
        assert result3 is False, "Second password reset should fail"
        
        # パスワードは最初のリセットのものであるべき
        user = User.query.filter_by(email=test_user.email).first()
        assert user.check_password("password1"), "Password should be from first reset"
        assert not user.check_password("password2"), "Password should not be from second reset"


class TestPasswordResetRoutes:
    """Test password reset routes."""
    
    def test_password_forgot_get(self, client):
        """Test GET request to password forgot page."""
        response = client.get('/auth/password/forgot')
        assert response.status_code == 200
    
    def test_password_forgot_post_valid_email(self, app_context, client):
        """Test POST request with valid email."""
        test_user = _create_test_user()
        
        with patch('webapp.services.password_reset_service.mail.send') as mock_send:
            response = client.post(
                '/auth/password/forgot',
                data={'email': test_user.email},
                follow_redirects=True
            )
            assert response.status_code == 200
            assert mock_send.called
    
    def test_password_forgot_post_invalid_email(self, client):
        """Test POST request with invalid email."""
        with patch('webapp.services.password_reset_service.mail.send') as mock_send:
            response = client.post(
                '/auth/password/forgot',
                data={'email': 'nonexistent@example.com'},
                follow_redirects=True
            )
            assert response.status_code == 200
            # Should show success message (to prevent user enumeration)
            assert not mock_send.called
    
    def test_password_forgot_post_no_email(self, client):
        """Test POST request without email."""
        response = client.post(
            '/auth/password/forgot',
            data={},
            follow_redirects=True
        )
        assert response.status_code == 200
    
    def test_password_reset_get_valid_token(self, app_context, client):
        """Test GET request with valid token."""
        test_user = _create_test_user()
        raw_token = PasswordResetService.generate_reset_token()
        reset_token = PasswordResetToken.create_token(test_user.email, raw_token)
        db.session.add(reset_token)
        db.session.commit()
        
        response = client.get(f'/auth/password/reset?token={raw_token}')
        assert response.status_code == 200
    
    def test_password_reset_get_invalid_token(self, client):
        """Test GET request with invalid token."""
        response = client.get(
            '/auth/password/reset?token=invalid-token',
            follow_redirects=True
        )
        assert response.status_code == 200
        # Should redirect to login with error message
    
    def test_password_reset_post_success(self, app_context, client):
        """Test successful password reset POST."""
        test_user = _create_test_user()
        raw_token = PasswordResetService.generate_reset_token()
        reset_token = PasswordResetToken.create_token(test_user.email, raw_token)
        db.session.add(reset_token)
        db.session.commit()
        
        response = client.post(
            '/auth/password/reset',
            data={
                'token': raw_token,
                'password': 'newpassword123',
                'password_confirm': 'newpassword123'
            },
            follow_redirects=True
        )
        assert response.status_code == 200
        
        # Verify password was changed
        user = User.query.filter_by(email=test_user.email).first()
        assert user.check_password('newpassword123')
    
    def test_password_reset_post_password_mismatch(self, app_context, client):
        """Test password reset with mismatched passwords."""
        test_user = _create_test_user()
        raw_token = PasswordResetService.generate_reset_token()
        reset_token = PasswordResetToken.create_token(test_user.email, raw_token)
        db.session.add(reset_token)
        db.session.commit()
        
        response = client.post(
            '/auth/password/reset',
            data={
                'token': raw_token,
                'password': 'newpassword123',
                'password_confirm': 'differentpassword'
            },
            follow_redirects=True
        )
        assert response.status_code == 200
    
    def test_password_reset_post_short_password(self, app_context, client):
        """Test password reset with short password."""
        test_user = _create_test_user()
        raw_token = PasswordResetService.generate_reset_token()
        reset_token = PasswordResetToken.create_token(test_user.email, raw_token)
        db.session.add(reset_token)
        db.session.commit()
        
        response = client.post(
            '/auth/password/reset',
            data={
                'token': raw_token,
                'password': 'short',
                'password_confirm': 'short'
            },
            follow_redirects=True
        )
        assert response.status_code == 200
