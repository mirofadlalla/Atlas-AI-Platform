import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending email notifications (e.g. invitation tokens)."""

    @staticmethod
    def send_email(
        to_email: str, subject: str, body_html: str, body_text: str = None
    ) -> bool:
        """
        Send an email via SMTP server. If credentials are not configured,
        logs the email content so tokens are visible in development logs.
        """
        if not settings.smtp_username or not settings.smtp_password:
            logger.warning(
                f"[DEV EMAIL LOG] SMTP credentials not set. "
                f"Email to '{to_email}' with subject '{subject}' NOT sent over SMTP.\n"
                f"Body content:\n{body_text or body_html}"
            )
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = settings.email_from
            msg["To"] = to_email

            if body_text:
                msg.attach(MIMEText(body_text, "plain"))
            msg.attach(MIMEText(body_html, "html"))

            with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as server:
                server.starttls()
                server.login(settings.smtp_username, settings.smtp_password)
                server.sendmail(settings.email_from, to_email, msg.as_string())

            logger.info(f"Email successfully sent to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False

    @staticmethod
    def send_invitation_email(to_email: str, token: str, tenant_id: str) -> bool:
        """
        Send an invitation email containing the invitation token and registration link.
        """
        registration_url = f"{settings.frontend_url}/register-via-invitation?token={token}&tenant_id={tenant_id}"

        subject = "You're Invited to Join Atlas AI Platform"

        body_html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
                    <h2 style="color: #4F46E5;">Atlas AI Platform Invitation</h2>
                    <p>You have been invited to join an organization workspace on <strong>Atlas AI Platform</strong>.</p>
                    <p><strong>Tenant ID:</strong> <code>{tenant_id}</code></p>
                    <p>Your invitation token is:</p>
                    <div style="background: #f4f4f5; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 16px; word-break: break-all; margin: 15px 0;">
                        {token}
                    </div>
                    <p>Click the button below to accept your invitation and create your account:</p>
                    <p style="text-align: center; margin: 25px 0;">
                        <a href="{registration_url}" style="background-color: #4F46E5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">Accept Invitation & Register</a>
                    </p>
                    <p style="font-size: 12px; color: #71717a;">This token will expire in 7 days. If you did not expect this invitation, you can safely ignore this email.</p>
                </div>
            </body>
        </html>
        """

        body_text = f"""
        Atlas AI Platform Invitation
        
        You have been invited to join an organization workspace on Atlas AI Platform.
        
        Tenant ID: {tenant_id}
        Invitation Token: {token}
        
        Register Link: {registration_url}
        
        This invitation token will expire in 7 days.
        """

        return EmailService.send_email(to_email, subject, body_html, body_text)

    @staticmethod
    def send_welcome_email(to_email: str, user_name: str, org_name: str) -> bool:
        """Send welcome email upon tenant creation or user signup."""
        subject = f"Welcome to Atlas AI Platform, {user_name}!"
        body_html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
                    <h2 style="color: #4F46E5;">Welcome to Atlas AI, {user_name}!</h2>
                    <p>Your workspace for <strong>{org_name}</strong> is ready.</p>
                    <p>You can now log in to manage documents, search knowledge bases, and utilize high-performance RAG features.</p>
                </div>
            </body>
        </html>
        """
        body_text = f"Welcome to Atlas AI Platform, {user_name}!\nYour workspace for {org_name} is now ready."
        return EmailService.send_email(to_email, subject, body_html, body_text)

    @staticmethod
    def send_approval_status_email(to_email: str, user_name: str, status: str) -> bool:
        """Send email when admin approves or rejects user registration."""
        is_approved = status.lower() == "approved"
        subject = f"Account Registration {'Approved' if is_approved else 'Updated'}"

        if is_approved:
            body_html = f"""
            <html>
                <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
                        <h2 style="color: #10B981;">Account Approved!</h2>
                        <p>Hi {user_name},</p>
                        <p>Your registration for Atlas AI Platform has been approved by your workspace administrator.</p>
                        <p>You may now log in to your account.</p>
                    </div>
                </body>
            </html>
            """
            body_text = f"Hi {user_name},\nYour registration for Atlas AI Platform has been approved by your administrator."
        else:
            body_html = f"""
            <html>
                <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
                        <h2 style="color: #EF4444;">Account Registration Update</h2>
                        <p>Hi {user_name},</p>
                        <p>Your registration request for Atlas AI Platform was not approved by the workspace administrator.</p>
                    </div>
                </body>
            </html>
            """
            body_text = f"Hi {user_name},\nYour registration request for Atlas AI Platform was not approved by the administrator."

        return EmailService.send_email(to_email, subject, body_html, body_text)
