import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os

from config import settings
from services import db, llm, notifier, whatsapp

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database and background digest worker
    print(f"[*] Starting Twin & Event Agent in mode: '{settings.AGENT_MODE.upper()}'...")
    await db.init_db()
    worker_task = None
    if not os.environ.get("VERCEL"):
        worker_task = asyncio.create_task(notifier.digest_background_worker())
    yield
    # Shutdown: cancel background worker if active
    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
    print("[*] Twin & Event Agent stopped cleanly.")

app = FastAPI(title="Twin & Event Agent", lifespan=lifespan)

# -------------------------------------------------------------
# Core Orchestration Handler
# -------------------------------------------------------------
async def process_incoming_message(
    sender: str,
    sender_name: str,
    message_text: str,
    background_tasks: BackgroundTasks
) -> str:
    """Core logic to process incoming WhatsApp messages or simulations."""
    # 1. Check if human takeover is active for this sender
    if await db.is_sender_muted(sender):
        print(f"[Human Takeover Active] Bot is muted for sender: {sender}")
        return ""

    # 2. Retrieve recent chat history for context
    history = await db.get_recent_conversation_history(sender, limit=5)

    # 3. Determine active mode
    active_mode = settings.AGENT_MODE
    if active_mode == "auto":
        event_keywords = ["event", "hackathon", "wifi", "wi-fi", "schedule", "track", "submission", "prize", "venue", "food", "team"]
        if any(k in message_text.lower() for k in event_keywords):
            active_mode = "event"
        else:
            active_mode = "persona"

    # 4. Generate AI response based on mode
    if active_mode == "event":
        result = await llm.generate_event_reply(sender_name, message_text, history)
    else:
        result = await llm.generate_persona_reply(sender_name, message_text, history)

    reply_text = result["reply"]
    category = result["category"]
    is_escalated = result["is_escalated"]

    # 5. Smart Hybrid Notification logic:
    # - Personal mode or Urgent escalations -> Instant email alert
    # - Event routine FAQ -> queued for periodic batch digest
    should_send_instant = (active_mode == "persona") or is_escalated

    # 6. Log to DB
    await db.log_interaction(
        sender=sender,
        sender_name=sender_name,
        incoming_text=message_text,
        agent_reply=reply_text,
        mode=active_mode,
        category=category,
        is_escalated=is_escalated,
        mark_digest_sent=should_send_instant
    )

    if should_send_instant:
        background_tasks.add_task(
            notifier.dispatch_instant_alert,
            sender=sender,
            sender_name=sender_name,
            incoming_text=message_text,
            agent_reply=reply_text,
            mode=active_mode,
            category=category,
            is_escalated=is_escalated
        )

    return reply_text

# -------------------------------------------------------------
# Green API Helper & Webhooks (https://green-api.com)
# -------------------------------------------------------------
async def handle_green_api_incoming(data: dict, background_tasks: BackgroundTasks) -> dict:
    """Processes notifications received from Green API webhook."""
    type_webhook = data.get("typeWebhook")

    # Only process incoming messages (ignore outgoingMessageReceived, stateInstanceChanged, etc.)
    if type_webhook != "incomingMessageReceived":
        return {"status": "ignored", "reason": f"Non-incoming event: {type_webhook}"}

    sender_data = data.get("senderData", {})
    message_data = data.get("messageData", {})

    sender_chat_id = sender_data.get("chatId") or sender_data.get("sender", "")
    sender_name = (
        sender_data.get("senderName")
        or sender_data.get("chatName")
        or sender_data.get("senderContactName")
        or sender_chat_id
    )

    type_message = message_data.get("typeMessage")
    message_text = ""

    if type_message == "textMessage":
        message_text = message_data.get("textMessageData", {}).get("textMessage", "")
    elif type_message in ("extendedTextMessage", "quotedMessage"):
        message_text = message_data.get("extendedTextMessageData", {}).get("text", "")
    elif type_message in ("imageMessage", "videoMessage", "documentMessage", "audioMessage"):
        message_text = message_data.get("fileMessageData", {}).get("caption", "")

    message_text = message_text.strip()
    if not message_text:
        return {"status": "ignored", "reason": f"No text content in type: {type_message}"}

    reply_text = await process_incoming_message(
        sender=sender_chat_id,
        sender_name=sender_name,
        message_text=message_text,
        background_tasks=background_tasks
    )

    if reply_text:
        background_tasks.add_task(
            whatsapp.send_green_api_whatsapp_message,
            to_number=sender_chat_id,
            message=reply_text
        )

    return {"status": "success", "reply_queued": bool(reply_text)}

@app.post("/whatsapp/green-api-webhook")
async def green_api_webhook(request: Request, background_tasks: BackgroundTasks):
    """Dedicated webhook endpoint for Green API."""
    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")

    return await handle_green_api_incoming(data, background_tasks)

# -------------------------------------------------------------
# Dual-Mode WhatsApp Webhook (Supports both Green API & Twilio)
# -------------------------------------------------------------
@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    """Smart dual-mode WhatsApp webhook supporting both Green API (JSON) and Twilio (Form data)."""
    content_type = request.headers.get("content-type", "")

    # Green API sends application/json
    if "application/json" in content_type:
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")
        return await handle_green_api_incoming(data, background_tasks)

    # Twilio sends application/x-www-form-urlencoded
    form_data = await request.form()
    sender = form_data.get("From", "")
    body = form_data.get("Body", "")
    profile_name = form_data.get("ProfileName") or sender

    if not sender or not body:
        return Response(content="<Response></Response>", media_type="application/xml")

    reply_text = await process_incoming_message(
        sender=sender,
        sender_name=profile_name,
        message_text=body,
        background_tasks=background_tasks
    )

    if not reply_text:
        return Response(content="<Response></Response>", media_type="application/xml")

    twiml = whatsapp.build_twiml_response(reply_text)
    return Response(content=twiml, media_type="application/xml")

# -------------------------------------------------------------
# Meta WhatsApp Cloud API Webhook
# -------------------------------------------------------------
@app.get("/whatsapp/meta-webhook")
async def meta_webhook_verification(request: Request):
    """Verifies webhook with Meta Graph API."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification token mismatch")

@app.post("/whatsapp/meta-webhook")
async def meta_webhook_event(request: Request, background_tasks: BackgroundTasks):
    """Processes Meta WhatsApp Cloud API incoming messages."""
    data = await request.json()
    try:
        entry = data.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})
        contacts = value.get("contacts", [])
        messages = value.get("messages", [])

        if messages:
            msg = messages[0]
            from_number = msg.get("from")
            body = msg.get("text", {}).get("body", "")
            profile_name = contacts[0].get("profile", {}).get("name", from_number) if contacts else from_number

            reply = await process_incoming_message(
                sender=from_number,
                sender_name=profile_name,
                message_text=body,
                background_tasks=background_tasks
            )

            if reply:
                background_tasks.add_task(whatsapp.send_meta_whatsapp_message, from_number, reply)
    except Exception as e:
        print(f"[Meta Webhook Error]: {e}")

    return {"status": "ok"}

# -------------------------------------------------------------
# REST API & Web Dashboard Endpoints
# -------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """Serves the command center dashboard."""
    return templates.TemplateResponse(request=request, name="index.html", context={})

@app.get("/api/status")
async def get_status():
    stats = await db.get_stats()
    return {
        "agent_mode": settings.AGENT_MODE,
        "llm_provider": settings.LLM_PROVIDER,
        "whatsapp_provider": settings.WHATSAPP_PROVIDER,
        "green_api_configured": bool(settings.GREEN_API_INSTANCE_ID and settings.GREEN_API_API_TOKEN_INSTANCE),
        "twilio_configured": bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN),
        "stats": stats
    }

class ModeUpdate(BaseModel):
    mode: str

@app.post("/api/mode")
async def update_mode(payload: ModeUpdate):
    if payload.mode not in ("persona", "event", "auto"):
        raise HTTPException(status_code=400, detail="Invalid mode. Choose 'persona', 'event', or 'auto'.")
    settings.AGENT_MODE = payload.mode
    return {"success": True, "active_mode": settings.AGENT_MODE}

@app.get("/api/messages")
async def list_recent_messages():
    return await db.get_all_recent_messages(limit=50)

class TakeoverRequest(BaseModel):
    sender: str
    mute: bool

@app.post("/api/takeover")
async def toggle_takeover(payload: TakeoverRequest):
    await db.set_sender_mute(payload.sender, payload.mute)
    return {"success": True, "sender": payload.sender, "is_muted": payload.mute}

class SimulationRequest(BaseModel):
    sender_name: str
    message: str

@app.post("/api/simulate")
async def simulate_incoming_interaction(payload: SimulationRequest, background_tasks: BackgroundTasks):
    """Simulates an incoming WhatsApp message for instant testing."""
    simulated_sender = f"whatsapp:+1999{hash(payload.sender_name) % 10000000:07d}"
    reply = await process_incoming_message(
        sender=simulated_sender,
        sender_name=payload.sender_name,
        message_text=payload.message,
        background_tasks=background_tasks
    )
    return {"success": True, "reply": reply}

@app.post("/api/test-email")
async def trigger_test_email(background_tasks: BackgroundTasks):
    """Sends a test email to verify SMTP configuration."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD or not settings.NOTIFICATION_EMAIL_TO:
        return {
            "success": False,
            "message": "SMTP credentials or NOTIFICATION_EMAIL_TO not configured in .env yet."
        }

    background_tasks.add_task(
        notifier.dispatch_instant_alert,
        sender="whatsapp:+15551234567",
        sender_name="Verification Bot",
        incoming_text="Test alert ping to verify SMTP connection.",
        agent_reply="This is a test notification confirming email delivery is working!",
        mode="persona",
        category="TEST_VERIFICATION",
        is_escalated=False
    )
    return {"success": True, "message": f"Test alert email queued for {settings.NOTIFICATION_EMAIL_TO}."}
