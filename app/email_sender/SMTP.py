import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = settings.SMTP_USER          # your Gmail address
SMTP_PASSWORD = settings.SMTP_PASSWORD  # Gmail App Password (not your normal password)


def _send_email(to_email: str, subject: str, html_body: str) -> bool:
    if not SMTP_USER or not SMTP_PASSWORD:
        print("CRITICAL: SMTP_USER or SMTP_PASSWORD not found in environment variables.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Reply-To"] = SMTP_USER
    msg["X-Mailer"] = "BriefRoom"
    msg["Subject"] = subject
    msg["From"] = f"BriefRoom <{SMTP_USER}>"
    msg["To"] = to_email

    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [to_email], msg.as_string())
        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Failed to send email: {e}")
        return False


def send_contact_email(name: str, email: str, message: str) -> bool:
    receiver_email = "saeedadnan151@gmail.com"
    subject = f"New Contact Form Submission from {name}"
    message_html = message.replace("\n", "<br>")

    html_body = f"""
    <html>
    <body style="margin:0; padding:0; background-color:#f4f5f9; font-family: Arial, Helvetica, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f5f9; padding: 30px 0;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                        <tr>
                            <td style="background-color:#243166; padding: 24px 30px;">
                                <table width="100%" cellpadding="0" cellspacing="0">
                                    <tr>
                                        <td style="vertical-align:middle;">
                                            <span style="display:inline-block; font-size:20px; vertical-align:middle; margin-right:8px;">🎙️</span>
                                            <span style="color:#ffffff; font-size:20px; font-weight:bold; vertical-align:middle;">BriefRoom</span>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 30px;">
                                <h2 style="color:#1f2937; font-size:20px; margin: 0 0 12px 0;">New Message from Your Contact Form</h2>
                                <p style="color:#6b7280; font-size:14px; line-height:1.6; margin: 0 0 20px 0;">
                                    Hi there, someone just reached out through the BriefRoom contact page.
                                </p>
                                <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#eef0f7; border-radius: 8px; padding: 16px;">
                                    <tr>
                                        <td style="padding: 8px 16px;">
                                            <p style="margin:0 0 10px 0; font-size:14px; color:#374151;"><strong style="color:#243166;">Name:</strong> {name}</p>
                                            <p style="margin:0 0 10px 0; font-size:14px; color:#374151;"><strong style="color:#243166;">Email:</strong> <a href="mailto:{email}" style="color:#243166; text-decoration:none;">{email}</a></p>
                                            <p style="margin:0; font-size:14px; color:#374151; white-space:pre-wrap;"><strong style="color:#243166;">Message:</strong><br>{message_html}</p>
                                        </td>
                                    </tr>
                                </table>
                                <table cellpadding="0" cellspacing="0" style="margin-top: 24px;">
                                    <tr>
                                        <td style="border-radius: 6px; background-color:#243166;">
                                            <a href="mailto:{email}" style="display:inline-block; padding: 10px 20px; font-size:14px; color:#ffffff; text-decoration:none; font-weight:bold;">
                                                Reply to {name}
                                            </a>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 16px 30px; border-top: 1px solid #f0f0f0;">
                                <p style="margin:0; font-size:12px; color:#9ca3af;">© 2026 BriefRoom. All rights reserved.</p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    success = _send_email(receiver_email, subject, html_body)
    if success:
        print(f"Contact email sent successfully from: {name}")
    return success


def send_verification_email(to_email: str, otp_code: str) -> bool:
    subject = "Your BriefRoom Verification Code"

    html_body = f"""
    <html>
    <body style="margin:0; padding:0; background-color:#f4f5f9; font-family: Arial, Helvetica, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f5f9; padding: 30px 0;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                        <tr>
                            <td bgcolor="#4f46e5" style="background-color:#4f46e5; background-image:linear-gradient(90deg,#2563eb 0%,#4f46e5 52%,#9333ea 100%); padding:24px 30px;">
                                <span style="display:inline-block; font-size:20px; vertical-align:middle; margin-right:8px;">🎙️</span>
                                <span style="color:#ffffff; font-size:20px; font-weight:bold; vertical-align:middle;">BriefRoom</span>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 30px;">
                                <h2 style="color:#1f2937; font-size:20px; margin: 0 0 12px 0;">Verify your email</h2>
                                <p style="color:#6b7280; font-size:14px; line-height:1.6; margin: 0 0 20px 0;">
                                    Use the code below to verify your BriefRoom account. This code expires in 10 minutes.
                                </p>
                                <table width="100%" cellpadding="0" cellspacing="0">
                                    <tr>
                                        <td align="center" style="padding: 20px 0;">
                                            <span style="display:inline-block; font-size:36px; font-weight:bold; letter-spacing:10px; color:#243166; background-color:#eef0f7; padding: 16px 32px; border-radius: 8px;">
                                                {otp_code}
                                            </span>
                                        </td>
                                    </tr>
                                </table>
                                <p style="color:#9ca3af; font-size:12px; margin-top: 20px;">
                                    If you didn't create this account, you can ignore this email.
                                </p>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 16px 30px; border-top: 1px solid #f0f0f0;">
                                <p style="margin:0; font-size:12px; color:#9ca3af;">© 2026 BriefRoom. All rights reserved.</p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    success = _send_email(to_email, subject, html_body)
    if success:
        print(f"OTP email sent to: {to_email}")
    return success



def send_subscription_reminder(first_name: str, to_email: str, ends_at: str) -> bool:
    subject = "Your BriefRoom Pro plan expires in 2 days"

    html_body = f"""
    <html>
    <body style="margin:0; padding:0; background-color:#f4f5f9; font-family: Arial, Helvetica, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f5f9; padding: 30px 0;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                        <tr>
                            <td style="background-color:#243166; padding: 24px 30px;">
                                <span style="display:inline-block; font-size:20px; vertical-align:middle; margin-right:8px;">🎙️</span>
                                <span style="color:#ffffff; font-size:20px; font-weight:bold; vertical-align:middle;">BriefRoom</span>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 30px;">
                                <h2 style="color:#1f2937; font-size:20px; margin: 0 0 12px 0;">Your Pro plan expires soon, {first_name}!</h2>
                                <p style="color:#6b7280; font-size:14px; line-height:1.6; margin: 0 0 20px 0;">
                                    Your BriefRoom Pro subscription will expire on <strong style="color:#243166;">{ends_at}</strong>.
                                    After that, your account will be downgraded to the Free plan and you'll lose access to:
                                </p>
                                <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#eef0f7; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
                                    <tr>
                                        <td style="padding: 8px 16px;">
                                            <p style="margin:0 0 8px 0; font-size:14px; color:#374151;">❌ Unlimited videos</p>
                                            <p style="margin:0 0 8px 0; font-size:14px; color:#374151;">❌ Transcript in 110+ languages</p>
                                            <p style="margin:0 0 8px 0; font-size:14px; color:#374151;">❌ Summary in your own language</p>
                                            <p style="margin:0 0 8px 0; font-size:14px; color:#374151;">❌ Actionable AI prompts</p>
                                            <p style="margin:0; font-size:14px; color:#374151;">❌ Priority support</p>
                                        </td>
                                    </tr>
                                </table>
                                <p style="color:#6b7280; font-size:14px; line-height:1.6; margin: 0 0 24px 0;">
                                    Renew your subscription to keep your Pro access uninterrupted.
                                </p>
                                <table cellpadding="0" cellspacing="0">
                                    <tr>
                                        <td style="border-radius: 6px; background-color:#243166;">
                                            <a href="https://brief-room-web-with-closed-source-m-xi.vercel.app/#pricing" 
                                               style="display:inline-block; padding: 12px 28px; font-size:14px; color:#ffffff; text-decoration:none; font-weight:bold;">
                                                Renew Pro Plan →
                                            </a>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 16px 30px; border-top: 1px solid #f0f0f0;">
                                <p style="margin:0; font-size:12px; color:#9ca3af;">© 2026 BriefRoom. All rights reserved.</p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    success = _send_email(to_email, subject, html_body)
    if success:
        print(f"Subscription reminder sent to: {to_email}")
    return success


def send_subscription_cancelled_email(first_name: str, to_email: str, ends_at: str) -> bool:
    subject = "Your BriefRoom Pro subscription has been cancelled"

    html_body = f"""
    <html>
    <body style="margin:0; padding:0; background-color:#f4f5f9; font-family: Arial, Helvetica, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f5f9; padding: 30px 0;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                        <tr>
                            <td style="background-color:#243166; padding: 24px 30px;">
                                <span style="display:inline-block; font-size:20px; vertical-align:middle; margin-right:8px;">🎙️</span>
                                <span style="color:#ffffff; font-size:20px; font-weight:bold; vertical-align:middle;">BriefRoom</span>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 30px;">
                                <h2 style="color:#1f2937; font-size:20px; margin: 0 0 12px 0;">Subscription cancelled, {first_name}</h2>
                                <p style="color:#6b7280; font-size:14px; line-height:1.6; margin: 0 0 20px 0;">
                                    Your BriefRoom Pro subscription has been successfully cancelled. You will continue to have 
                                    full Pro access until <strong style="color:#243166;">{ends_at}</strong>, after which your 
                                    account will automatically switch to the Free plan.
                                </p>
                                <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#eef0f7; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
                                    <tr>
                                        <td style="padding: 8px 16px;">
                                            <p style="margin:0; font-size:14px; color:#374151;">
                                                ✅ Pro access active until: <strong>{ends_at}</strong>
                                            </p>
                                        </td>
                                    </tr>
                                </table>
                                <p style="color:#6b7280; font-size:14px; line-height:1.6; margin: 0 0 24px 0;">
                                    Changed your mind? You can resubscribe anytime from the pricing page.
                                </p>
                                <table cellpadding="0" cellspacing="0">
                                    <tr>
                                        <td style="border-radius: 6px; background-color:#243166;">
                                            <a href="https://brief-room-web-with-closed-source-m-xi.vercel.app/#pricing"
                                               style="display:inline-block; padding: 12px 28px; font-size:14px; color:#ffffff; text-decoration:none; font-weight:bold;">
                                                Resubscribe →
                                            </a>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 16px 30px; border-top: 1px solid #f0f0f0;">
                                <p style="margin:0; font-size:12px; color:#9ca3af;">© 2026 BriefRoom. All rights reserved.</p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    success = _send_email(to_email, subject, html_body)
    if success:
        print(f"Cancellation confirmation email sent to: {to_email}")
    return success
