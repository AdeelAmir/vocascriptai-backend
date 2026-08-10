import os

import resend
from app.core.config import settings

def send_contact_email(name: str, email: str, message: str) -> bool:
    sender_email = "BriefRoom <onboarding@resend.dev>"
    receiver_email = "saeedadnan151@gmail.com"

    api_key = settings.RESEND_API_KEY
    if not api_key:
        print("CRITICAL: RESEND_API_KEY not found in environment variables.")
        return False

    resend.api_key = api_key

    subject = f"New Contact Form Submission from {name}"
    message_html = message.replace("\n", "<br>")

    html_body = f"""
    <html>
    <body style="margin:0; padding:0; background-color:#f4f5f9; font-family: Arial, Helvetica, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f5f9; padding: 30px 0;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                        <!-- Header -->
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

                        <!-- Body -->
                        <tr>
                            <td style="padding: 30px;">
                                <h2 style="color:#1f2937; font-size:20px; margin: 0 0 12px 0;">New Message from Your Contact Form</h2>
                                <p style="color:#6b7280; font-size:14px; line-height:1.6; margin: 0 0 20px 0;">
                                    Hi there, someone just reached out through the BriefRoom contact page.
                                </p>

                                <!-- Info box -->
                                <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#eef0f7; border-radius: 8px; padding: 16px;">
                                    <tr>
                                        <td style="padding: 8px 16px;">
                                            <p style="margin:0 0 10px 0; font-size:14px; color:#374151;"><strong style="color:#243166;">Name:</strong> {name}</p>
                                            <p style="margin:0 0 10px 0; font-size:14px; color:#374151;"><strong style="color:#243166;">Email:</strong> <a href="mailto:{email}" style="color:#243166; text-decoration:none;">{email}</a></p>
                                            <p style="margin:0; font-size:14px; color:#374151; white-space:pre-wrap;"><strong style="color:#243166;">Message:</strong><br>{message_html}</p>
                                        </td>
                                    </tr>
                                </table>

                                <!-- Reply button -->
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

                        <!-- Footer -->
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

    try:
        resend.Emails.send({
            "from": sender_email,
            "to": [receiver_email],
            "subject": subject,
            "html": html_body,
            "reply_to": email,
        })

        print(f"Contact email sent successfully from: {name}")
        return True

    except Exception as e:
        print(f"Failed to send email: {e}")
        return False
    


def send_verification_email(to_email: str, otp_code: str) -> bool:
    sender_email = "BriefRoom <onboarding@resend.dev>"

    api_key = settings.RESEND_API_KEY
    if not api_key:
        print("CRITICAL: RESEND_API_KEY not found in environment variables.")
        return False

    resend.api_key = api_key

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

    try:
        resend.Emails.send({
            "from": sender_email,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        })
        print(f"OTP email sent to: {to_email}")
        return True
    except Exception as e:
        print(f"Failed to send OTP email: {e}")
        return False
