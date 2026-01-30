"""Tests for EmailMessage value object."""

import pytest
from domain.email_sender.email_message import EmailMessage


class TestEmailMessage:
    """Test EmailMessage value object."""

    def test_create_simple_message(self):
        """Test creating a simple email message."""
        message = EmailMessage(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body"
        )
        
        assert message.to == ["test@example.com"]
        assert message.subject == "Test Subject"
        assert message.body == "Test Body"
        assert message.html_body is None
        assert message.from_address is None

    def test_create_message_with_html(self):
        """Test creating a message with HTML body."""
        message = EmailMessage(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body",
            html_body="<p>Test Body</p>"
        )
        
        assert message.html_body == "<p>Test Body</p>"

    def test_create_message_with_multiple_recipients(self):
        """Test creating a message with multiple recipients."""
        message = EmailMessage(
            to=["test1@example.com", "test2@example.com"],
            subject="Test Subject",
            body="Test Body"
        )
        
        assert len(message.to) == 2
        assert "test1@example.com" in message.to
        assert "test2@example.com" in message.to

    def test_create_message_with_cc_and_bcc(self):
        """Test creating a message with CC and BCC."""
        message = EmailMessage(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body",
            cc=["cc@example.com"],
            bcc=["bcc@example.com"]
        )
        
        assert message.cc == ["cc@example.com"]
        assert message.bcc == ["bcc@example.com"]

    def test_empty_recipients_raises_error(self):
        """Test that empty recipients list raises ValueError."""
        with pytest.raises(ValueError, match="受信者が指定されていません"):
            EmailMessage(
                to=[],
                subject="Test Subject",
                body="Test Body"
            )

    def test_empty_subject_raises_error(self):
        """Test that empty subject raises ValueError."""
        with pytest.raises(ValueError, match="件名が指定されていません"):
            EmailMessage(
                to=["test@example.com"],
                subject="",
                body="Test Body"
            )

    def test_empty_body_raises_error(self):
        """Test that empty body raises ValueError."""
        with pytest.raises(ValueError, match="本文が指定されていません"):
            EmailMessage(
                to=["test@example.com"],
                subject="Test Subject",
                body=""
            )

    def test_invalid_email_address_raises_error(self):
        """Test that invalid email address raises ValueError."""
        with pytest.raises(ValueError, match="無効なメールアドレス"):
            EmailMessage(
                to=["invalid-email"],
                subject="Test Subject",
                body="Test Body"
            )

    def test_invalid_cc_email_raises_error(self):
        """Test that invalid CC email raises ValueError."""
        with pytest.raises(ValueError, match="無効なCCメールアドレス"):
            EmailMessage(
                to=["test@example.com"],
                subject="Test Subject",
                body="Test Body",
                cc=["invalid-cc"]
            )

    def test_invalid_bcc_email_raises_error(self):
        """Test that invalid BCC email raises ValueError."""
        with pytest.raises(ValueError, match="無効なBCCメールアドレス"):
            EmailMessage(
                to=["test@example.com"],
                subject="Test Subject",
                body="Test Body",
                bcc=["invalid-bcc"]
            )

    def test_message_is_immutable(self):
        """Test that EmailMessage is immutable (frozen)."""
        message = EmailMessage(
            to=["test@example.com"],
            subject="Test Subject",
            body="Test Body"
        )
        
        # Attempting to modify should raise an error
        with pytest.raises(Exception):  # dataclass frozen raises FrozenInstanceError
            message.subject = "Modified Subject"
