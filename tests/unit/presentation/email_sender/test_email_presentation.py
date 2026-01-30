"""Presentation layer tests for email sender features."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch
from flask import Flask

from bounded_contexts.email_sender.application.email_service import EmailService
from bounded_contexts.email_sender.domain.email_message import EmailMessage


class TestEmailSenderAPI:
    """Test email sender API endpoints (simulated)."""

    def test_email_request_validation(self):
        """Test email request data validation."""
        # Simulate API request data validation
        valid_request_data = {
            "to": ["test@example.com"],
            "subject": "Test Subject",
            "body": "Test Body",
            "from_address": "sender@example.com"
        }
        
        # This would normally be handled by Flask-Smorest schemas
        try:
            message = EmailMessage(**valid_request_data)
            assert message.to == ["test@example.com"]
            assert message.subject == "Test Subject"
            assert message.body == "Test Body"
            assert message.from_address == "sender@example.com"
        except Exception as e:
            pytest.fail(f"Valid request data should create EmailMessage: {e}")

    def test_email_request_invalid_data(self):
        """Test handling of invalid email request data."""
        invalid_request_data = {
            "to": [],  # Empty recipients
            "subject": "Test Subject",
            "body": "Test Body",
            "from_address": "sender@example.com"
        }
        
        with pytest.raises(ValueError, match="受信者が指定されていません"):
            EmailMessage(**invalid_request_data)

    def test_email_api_response_format(self):
        """Test API response format for email sending."""
        # Mock email service
        mock_service = Mock(spec=EmailService)
        mock_service.send_email.return_value = True
        
        # Simulate API controller logic
        message = EmailMessage(
            to=["api-test@example.com"],
            subject="API Test",
            body="Testing API response",
            from_address="api@example.com"
        )
        
        success = mock_service.send_email(message)
        
        # Simulate API response
        api_response = {
            "success": success,
            "message": "Email sent successfully" if success else "Failed to send email",
            "email_id": "mock-email-id-123"
        }
        
        assert api_response["success"] is True
        assert "successfully" in api_response["message"]
        assert api_response["email_id"] is not None

    def test_email_error_response_format(self):
        """Test API error response format."""
        mock_service = Mock(spec=EmailService)
        mock_service.send_email.side_effect = ValueError("Invalid configuration")
        
        message = EmailMessage(
            to=["error-test@example.com"],
            subject="Error Test",
            body="This should fail",
            from_address="error@example.com"
        )
        
        try:
            mock_service.send_email(message)
        except ValueError as e:
            # Simulate API error response
            error_response = {
                "success": False,
                "error": str(e),
                "code": "VALIDATION_ERROR"
            }
            
            assert error_response["success"] is False
            assert "Invalid configuration" in error_response["error"]
            assert error_response["code"] == "VALIDATION_ERROR"

class TestEmailTemplateRendering:
    """Test email template rendering (if applicable)."""

    def test_plain_text_email_template(self):
        """Test rendering plain text email templates."""
        template_data = {
            "user_name": "John Doe",
            "action_url": "https://example.com/confirm",
            "company_name": "Test Company"
        }
        
        # Simple template rendering simulation
        plain_template = "Hello {user_name}, please visit {action_url}. Best regards, {company_name}"
        rendered_body = plain_template.format(**template_data)
        
        message = EmailMessage(
            to=["template-test@example.com"],
            subject="Template Test",
            body=rendered_body,
            from_address="noreply@example.com"
        )
        
        assert "John Doe" in message.body
        assert "https://example.com/confirm" in message.body
        assert "Test Company" in message.body

    def test_html_email_template(self):
        """Test rendering HTML email templates."""
        template_data = {
            "user_name": "Jane Smith",
            "action_url": "https://example.com/activate"
        }
        
        html_template = '''
        <html>
            <body>
                <h1>Welcome {user_name}!</h1>
                <p><a href="{action_url}">Click here to activate</a></p>
            </body>
        </html>
        '''
        
        rendered_html = html_template.format(**template_data)
        
        message = EmailMessage(
            to=["html-test@example.com"],
            subject="HTML Template Test",
            body="Plain text fallback",
            html_body=rendered_html,
            from_address="noreply@example.com"
        )
        
        assert "Jane Smith" in message.html_body
        assert "https://example.com/activate" in message.html_body
        assert "<h1>" in message.html_body

class TestEmailServicePresentationIntegration:
    """Test integration between presentation layer and email service."""

    def test_controller_service_integration(self):
        """Test email controller using email service."""
        # Mock service
        mock_service = Mock(spec=EmailService)
        mock_service.send_email.return_value = True
        mock_service.can_send_emails.return_value = True
        
        # Simulate controller logic
        def send_email_controller(request_data, email_service):
            """Simulated email controller."""
            if not email_service.can_send_emails():
                return {"error": "Email service not available"}, 503
            
            try:
                message = EmailMessage(**request_data)
                success = email_service.send_email(message)
                
                if success:
                    return {"message": "Email sent successfully"}, 200
                else:
                    return {"error": "Failed to send email"}, 500
            except ValueError as e:
                return {"error": str(e)}, 400
        
        # Test successful case
        request_data = {
            "to": ["controller-test@example.com"],
            "subject": "Controller Test",
            "body": "Testing controller integration",
            "from_address": "controller@example.com"
        }
        
        response, status_code = send_email_controller(request_data, mock_service)
        
        assert status_code == 200
        assert "successfully" in response["message"]
        mock_service.send_email.assert_called_once()

    def test_controller_validation_error_handling(self):
        """Test controller handling of validation errors."""
        mock_service = Mock(spec=EmailService)
        mock_service.can_send_emails.return_value = True
        
        # Simulate controller with invalid data
        def send_email_controller(request_data, email_service):
            try:
                message = EmailMessage(**request_data)
                return email_service.send_email(message)
            except ValueError as e:
                return {"error": str(e)}, 400
        
        invalid_request = {
            "to": [],  # Invalid empty recipients
            "subject": "Test",
            "body": "Test",
            "from_address": "test@example.com"
        }
        
        response, status_code = send_email_controller(invalid_request, mock_service)
        
        assert status_code == 400
        assert "error" in response
        mock_service.send_email.assert_not_called()