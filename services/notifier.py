import aiosmtplib
import asyncio
from email.message import EmailMessage
from datetime import datetime
from config import settings
from services import db

def clean_phone_number(raw_sender: str) -> str:
    """Extracts raw digits for wa.me link from 'whatsapp:+123456789'."""
    return "".join(filter(lambda c: c.isdigit() or c == "+", raw_sender)).replace("+", "")

async def send_email_async(subject: str, html_content: str, text_content: str = "") -> bool:
    """Dispatches an email via SMTP asynchronously."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD or not settings.NOTIFICATION_EMAIL_TO:
        print(f"[Email Notification Skipped] SMTP settings not fully configured. (Subject: {subject})")
        return False

    msg = EmailMessage()
    msg["From"] = f"{settings.NOTIFICATION_FROM_NAME} <{settings.SMTP_USER}>"
    msg["To"] = settings.NOTIFICATION_EMAIL_TO
    msg["Subject"] = subject

    if not text_content:
        text_content = "Please view this email with an HTML-compatible client."

    msg.set_content(text_content)
    msg.add_alternative(html_content, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=settings.SMTP_USE_TLS,
            timeout=15.0
        )
        print(f"[Email Sent Successfully] -> {settings.NOTIFICATION_EMAIL_TO}: {subject}")
        return True
    except Exception as e:
        print(f"[SMTP Error] Failed to send email: {e}")
        return False

async def dispatch_instant_alert(
    sender: str,
    sender_name: str,
    incoming_text: str,
    agent_reply: str,
    mode: str,
    category: str,
    is_escalated: bool
):
    """Sends an immediate email notification for personal pings or event escalations."""
    clean_phone = clean_phone_number(sender)
    wa_link = f"https://wa.me/{clean_phone}" if clean_phone else "#"
    
    timestamp = datetime.now().strftime("%I:%M %p, %b %d")

    user_name = getattr(settings, "USER_NAME", "Subho")
    if is_escalated:
        subject = f"🚨 [CRITICAL ESCALATION] Event DM from {sender_name or sender} ({category})"
        header_color = "#dc2626" # Red
        badge_text = f"CRITICAL ESCALATION - {category}"
    elif mode == "persona":
        subject = f"🔔 [Persona Ping] {sender_name or sender} reached out to {user_name} on WhatsApp"
        header_color = "#2563eb" # Blue
        badge_text = f"{user_name.upper()}'S DIGITAL TWIN"
    else:
        subject = f"💬 [Event DM] New message from {sender_name or sender} ({category})"
        header_color = "#059669" # Green
        badge_text = f"ORGANIZING COMMITTEE - {category}"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f3f4f6; margin: 0; padding: 20px; }}
        .card {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
        .header {{ background-color: {header_color}; color: #ffffff; padding: 20px; text-align: left; }}
        .header h2 {{ margin: 0 0 6px 0; font-size: 20px; }}
        .badge {{ display: inline-block; background: rgba(255,255,255,0.25); color: #ffffff; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; text-transform: uppercase; }}
        .content {{ padding: 24px; color: #1f2937; }}
        .meta-row {{ margin-bottom: 16px; font-size: 14px; color: #4b5563; }}
        .bubble-label {{ font-weight: bold; font-size: 12px; text-transform: uppercase; color: #6b7280; margin-bottom: 6px; }}
        .msg-incoming {{ background: #f9fafb; border-left: 4px solid {header_color}; padding: 14px; border-radius: 6px; font-size: 15px; margin-bottom: 18px; }}
        .msg-reply {{ background: #eff6ff; border-left: 4px solid #3b82f6; padding: 14px; border-radius: 6px; font-size: 15px; margin-bottom: 24px; }}
        .btn {{ display: inline-block; background-color: #25D366; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 15px; }}
        .footer {{ padding: 16px 24px; background: #f9fafb; border-top: 1px solid #e5e7eb; font-size: 12px; color: #9ca3af; text-align: center; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="header">
          <div class="badge">{badge_text}</div>
          <h2>{subject}</h2>
        </div>
        <div class="content">
          <div class="meta-row">
            <strong>From:</strong> {sender_name} ({sender}) &bull; <strong>Time:</strong> {timestamp}
          </div>

          <div class="bubble-label">Incoming Message from Contact:</div>
          <div class="msg-incoming">
            "{incoming_text}"
          </div>

          <div class="bubble-label">Automated Agent Reply:</div>
          <div class="msg-reply">
            {agent_reply}
          </div>

          <div style="text-align: center; margin-top: 20px;">
            <a href="{wa_link}" class="btn" target="_blank">Open WhatsApp & Chat Directly</a>
          </div>
        </div>
        <div class="footer">
          Twin & Event Agent &bull; Dual Persona & Committee DM Dispatcher
        </div>
      </div>
    </body>
    </html>
    """

    text_content = f"""
{subject}
----------------------------------------
From: {sender_name} ({sender})
Time: {timestamp}
Mode: {mode.upper()} | Category: {category}

Incoming Message:
"{incoming_text}"

Automated Reply:
"{agent_reply}"

WhatsApp Link: {wa_link}
----------------------------------------
"""
    await send_email_async(subject, html_content, text_content)

async def dispatch_digest_email():
    """Compiles routine queries into a batch digest to prevent inbox flooding during events."""
    unnotified = await db.get_unnotified_digest_messages()
    if not unnotified:
        return

    count = len(unnotified)
    subject = f"📊 [Event Desk Digest] {count} Routine WhatsApp Inquiries Handled"

    rows_html = ""
    msg_ids = []
    for row in unnotified:
        m_id, sender, name, incoming, reply, mode, cat, created = row
        msg_ids.append(m_id)
        clean_phone = clean_phone_number(sender)
        rows_html += f"""
        <tr style="border-bottom: 1px solid #e5e7eb;">
          <td style="padding: 10px; font-size: 13px;"><strong>{name or sender}</strong><br><a href="https://wa.me/{clean_phone}" style="color: #2563eb; font-size: 11px;">wa.me/{clean_phone}</a></td>
          <td style="padding: 10px; font-size: 13px;"><span style="background: #e0e7ff; color: #3730a3; padding: 2px 6px; border-radius: 4px; font-size: 11px;">{cat}</span></td>
          <td style="padding: 10px; font-size: 13px;">{incoming}</td>
          <td style="padding: 10px; font-size: 13px; color: #4b5563;">{reply}</td>
        </tr>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f3f4f6; margin: 0; padding: 20px; }}
        .card {{ max-width: 800px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
        .header {{ background-color: #0f172a; color: #ffffff; padding: 20px; }}
        .content {{ padding: 20px; }}
        table {{ width: 100%; border-collapse: collapse; text-align: left; }}
        th {{ background: #f8fafc; padding: 10px; font-size: 12px; text-transform: uppercase; color: #64748b; border-bottom: 2px solid #e2e8f0; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="header">
          <h2 style="margin: 0;">Event Organizing Committee DM Digest</h2>
          <p style="margin: 6px 0 0 0; color: #94a3b8; font-size: 14px;">Summary of {count} routine participant inquiries answered automatically by AI.</p>
        </div>
        <div class="content">
          <table>
            <thead>
              <tr>
                <th>Attendee</th>
                <th>Category</th>
                <th>Inquiry</th>
                <th>Agent Response</th>
              </tr>
            </thead>
            <tbody>
              {rows_html}
            </tbody>
          </table>
        </div>
      </div>
    </body>
    </html>
    """

    sent = await send_email_async(subject, html_content)
    if sent or not settings.SMTP_USER:
        # Mark as digested even if test mode so we don't repeat endlessly
        await db.mark_messages_as_digested(msg_ids)

async def digest_background_worker():
    """Background task running continuously to flush digests."""
    while True:
        try:
            await asyncio.sleep(settings.DIGEST_INTERVAL_SECONDS)
            await dispatch_digest_email()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[Digest Worker Error]: {e}")
            await asyncio.sleep(10)
