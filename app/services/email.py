# app/services/email.py
"""
Centralized email service for sending emails via Mailhog (local) or Postmark (production)
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Configuration from environment
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "mailhog")  # "mailhog" or "postmark"
POSTMARK_API_TOKEN = os.getenv("POSTMARK_API_TOKEN", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@betterchoices.vote")
MAILHOG_HOST = os.getenv("MAILHOG_HOST", "localhost")
MAILHOG_PORT = int(os.getenv("MAILHOG_PORT", "1025"))


class EmailService:
    """Email service that handles both Mailhog and Postmark"""
    
    def __init__(self):
        self.provider = EMAIL_PROVIDER
        self.from_email = FROM_EMAIL
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: Optional[str] = None,
        from_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send an email using the configured provider.
        
        Args:
            to_email: Recipient email address
            subject: Email subject line
            text_body: Plain text version of email
            html_body: HTML version of email (optional)
            from_email: Override default from email (optional)
        
        Returns:
            Dict with 'success' (bool) and 'message' (str)
        """
        from_addr = from_email or self.from_email
        
        try:
            if self.provider == "postmark":
                return await self._send_via_postmark(
                    to_email, subject, text_body, html_body, from_addr
                )
            else:  # Default to mailhog
                return await self._send_via_mailhog(
                    to_email, subject, text_body, html_body, from_addr
                )
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return {
                "success": False,
                "message": str(e)
            }
    
    async def _send_via_postmark(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: Optional[str],
        from_email: str
    ) -> Dict[str, Any]:
        """Send email via Postmark API"""
        import requests
        
        if not POSTMARK_API_TOKEN:
            raise ValueError("POSTMARK_API_TOKEN not configured")
        
        payload = {
            "From": from_email,
            "To": to_email,
            "Subject": subject,
            "TextBody": text_body,
            "MessageStream": "outbound"
        }
        
        if html_body:
            payload["HtmlBody"] = html_body
        
        response = requests.post(
            "https://api.postmarkapp.com/email",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Postmark-Server-Token": POSTMARK_API_TOKEN
            },
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info(f"✓ Email sent to {to_email} via Postmark")
            return {
                "success": True,
                "message": "Email sent via Postmark",
                "provider": "postmark",
                "message_id": response.json().get("MessageID")
            }
        else:
            error_msg = f"Postmark API error: {response.status_code} - {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    async def _send_via_mailhog(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: Optional[str],
        from_email: str
    ) -> Dict[str, Any]:
        """Send email via Mailhog SMTP"""
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email
        
        # Attach text version
        msg.attach(MIMEText(text_body, 'plain'))
        
        # Attach HTML version if provided
        if html_body:
            msg.attach(MIMEText(html_body, 'html'))
        
        # Send via SMTP
        smtp = smtplib.SMTP(MAILHOG_HOST, MAILHOG_PORT)
        smtp.send_message(msg)
        smtp.quit()
        
        logger.info(f"✓ Email sent to {to_email} via Mailhog")
        return {
            "success": True,
            "message": "Email sent via Mailhog",
            "provider": "mailhog",
            "note": f"Check MailHog at http://{MAILHOG_HOST}:8025 to see emails"
        }
    
    def get_provider_info(self) -> Dict[str, str]:
        """Get information about the current email provider"""
        return {
            "provider": self.provider,
            "from_email": self.from_email,
            "mailhog_url": f"http://{MAILHOG_HOST}:8025" if self.provider == "mailhog" else None
        }


# Create a singleton instance
email_service = EmailService()


# Convenience function for direct use
async def send_email(
    to_email: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    from_email: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send an email using the configured provider.
    
    Usage:
        from app.services.email import send_email
        
        result = await send_email(
            to_email="user@example.com",
            subject="Welcome!",
            text_body="Welcome to our service",
            html_body="<h1>Welcome to our service</h1>"
        )
        
        if result["success"]:
            print("Email sent!")
    """
    return await email_service.send_email(to_email, subject, text_body, html_body, from_email)


# Template functions for common emails
async def send_poll_invitation(
    voter_email: str,
    poll_title: str,
    voting_link: str
) -> Dict[str, Any]:
    """
    Send a poll invitation email.
    
    Args:
        voter_email: Email address of the voter
        poll_title: Title of the poll
        voting_link: Complete voting link with token
    
    Returns:
        Dict with 'success' (bool) and 'message' (str)
    """
    subject = f"You're invited to vote in: {poll_title}"
    
    text_body = f"""You've been invited to vote in: {poll_title}

Click here to vote: {voting_link}

This is a private poll. Only invited voters can participate.
"""
    
    html_body = f"""
<html>
  <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <h2 style="color: #333;">You're invited to vote!</h2>
    <p><strong>Poll:</strong> {poll_title}</p>
    <p style="margin: 30px 0;">
      <a href="{voting_link}" style="background-color: #1976d2; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; display: inline-block;">
        Vote Now
      </a>
    </p>
    <p style="color: #666;">Or copy this link:<br>
    <code style="background: #f5f5f5; padding: 8px; display: block; margin: 10px 0; word-break: break-all;">{voting_link}</code>
    </p>
    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
    <p style="color: #999; font-size: 12px;">This is a private poll. Only invited voters can participate.</p>
  </body>
</html>
"""
    
    return await send_email(voter_email, subject, text_body, html_body)