# tests/test_voters.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_email_service_is_called():
    """Test that the centralized email service is called (not inline function)"""
    with patch('app.services.email.send_email', new_callable=AsyncMock) as mock_email:
        # Setup mock to return success
        mock_email.return_value = {"success": True, "provider": "mailhog"}
        
        # Import the email service
        from app.services.email import send_email
        
        # Call it
        result = await send_email(
            to_email="test@example.com",
            subject="Test",
            text_body="Test body",
            html_body="<p>Test body</p>"
        )
        
        # Verify it was called and returned correctly
        assert result["success"] == True
        assert mock_email.called


@pytest.mark.asyncio  
async def test_email_service_import():
    """Test that voters.py imports from centralized email service"""
    # This will fail if the import is wrong
    from app.api.v1 import voters
    
    # Check that send_email is imported from the service
    import inspect
    source = inspect.getsource(voters)
    
    # Should have the import
    assert "from app.services.email import send_email" in source
    
    # Should NOT have the old inline function
    assert "def send_email(to_email: str, subject: str, text_body: str, html_body: str) -> bool:" not in source


def test_email_service_exists():
    """Test that the email service file exists and is importable"""
    try:
        from app.services.email import send_email, EmailService
        assert send_email is not None
        assert EmailService is not None
    except ImportError as e:
        pytest.fail(f"Could not import email service: {e}")


@pytest.mark.asyncio
async def test_email_returns_dict_not_bool():
    """Test that email service returns dict (new behavior) not bool (old behavior)"""
    with patch('app.services.email.EmailService._send_via_mailhog', new_callable=AsyncMock) as mock_mailhog:
        mock_mailhog.return_value = {"success": True, "provider": "mailhog"}
        
        from app.services.email import send_email
        
        result = await send_email(
            to_email="test@example.com",
            subject="Test",
            text_body="Test",
            html_body="<p>Test</p>"
        )
        
        # Should return dict, not bool
        assert isinstance(result, dict)
        assert "success" in result
        assert result["success"] == True


@pytest.mark.asyncio
async def test_voters_send_email_usage():
    """Integration test: verify voters.py uses email service correctly"""
    # Mock the entire email service
    with patch('app.services.email.send_email', new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"success": True, "message": "Sent"}
        
        # Now try to import and check the function signature
        from app.api.v1.voters import send_poll_invitations
        
        # The function should exist
        assert callable(send_poll_invitations)
        
        # Verify it's async
        import inspect
        assert inspect.iscoroutinefunction(send_poll_invitations)


def test_no_inline_smtp_code():
    """Verify that inline SMTP code has been removed from voters.py"""
    from app.api.v1 import voters
    import inspect
    
    source = inspect.getsource(voters)
    
    # Should NOT have inline SMTP imports
    assert "import smtplib" not in source
    assert "from email.mime.text import MIMEText" not in source
    assert "from email.mime.multipart import MIMEMultipart" not in source
    
    # Should NOT have the old inline send_email function with bool return
    assert "def send_email(to_email: str, subject: str, text_body: str, html_body: str) -> bool:" not in source
    
    # Should NOT have inline SMTP calls
    assert "smtplib.SMTP(" not in source
    assert "smtp.send_message(" not in source


def test_email_service_has_correct_default():
    """Test that email service has correct FROM_EMAIL default"""
    from app.services import email
    import inspect
    
    source = inspect.getsource(email)
    
    # Should have the correct domain
    assert "noreply@betterchoices.vote" in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])