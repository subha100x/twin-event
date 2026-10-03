import httpx
from typing import Optional
from config import settings

def build_twiml_response(reply_text: str) -> str:
    """Creates a Twilio TwiML XML response string."""
    from xml.sax.saxutils import escape
    safe_reply = escape(reply_text)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{safe_reply}</Message>
</Response>"""

async def send_twilio_whatsapp_message(to_number: str, message: str) -> bool:
    """Sends an outbound WhatsApp message using Twilio REST API."""
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        print("[Twilio] SID or Token not configured.")
        return False
    
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"
    data = {
        "From": settings.TWILIO_WHATSAPP_NUMBER or "whatsapp:+14155238886",
        "To": to_number if to_number.startswith("whatsapp:") else f"whatsapp:{to_number}",
        "Body": message
    }
    
    auth = (settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, data=data, auth=auth, timeout=15.0)
            if resp.status_code in (200, 201):
                print(f"[Twilio Sent] To {to_number}")
                return True
            else:
                print(f"[Twilio Error] {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            print(f"[Twilio Send Exception]: {e}")
            return False

async def send_green_api_whatsapp_message(to_number: str, message: str) -> bool:
    """Sends an outbound WhatsApp message using Green API REST API.
    
    Docs: https://green-api.com/en/docs/api/sending/SendMessage/
    """
    if not settings.GREEN_API_INSTANCE_ID or not settings.GREEN_API_API_TOKEN_INSTANCE:
        print("[Green API] Instance ID or API Token not configured in .env.")
        return False

    clean_target = to_number.strip()
    # If not already formatted as Green API chatId (@c.us or @g.us), format it
    if not (clean_target.endswith("@c.us") or clean_target.endswith("@g.us")):
        digits_only = "".join(filter(str.isdigit, clean_target))
        if not digits_only:
            print(f"[Green API] Invalid recipient phone number: {to_number}")
            return False
        clean_target = f"{digits_only}@c.us"

    host = settings.GREEN_API_HOST.rstrip("/")
    url = f"{host}/waInstance{settings.GREEN_API_INSTANCE_ID}/sendMessage/{settings.GREEN_API_API_TOKEN_INSTANCE}"
    payload = {
        "chatId": clean_target,
        "message": message
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, timeout=15.0)
            if resp.status_code == 200:
                data = resp.json()
                print(f"[Green API Sent] To {clean_target} | idMessage: {data.get('idMessage')}")
                return True
            else:
                print(f"[Green API Error] HTTP {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            print(f"[Green API Send Exception]: {e}")
            return False

async def send_meta_whatsapp_message(to_number: str, message: str) -> bool:
    """Sends outbound WhatsApp message using Meta WhatsApp Cloud API."""
    if not settings.WHATSAPP_CLOUD_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
        return False
    
    clean_number = "".join(filter(str.isdigit, to_number))
    url = f"https://graph.facebook.com/v19.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_CLOUD_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_number,
        "type": "text",
        "text": {"preview_url": False, "body": message}
    }
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, headers=headers, json=payload, timeout=15.0)
            return resp.status_code == 200
        except Exception as e:
            print(f"[Meta Cloud API Error]: {e}")
            return False

async def send_whatsapp_message(to_number: str, message: str) -> bool:
    """Dispatches WhatsApp message using configured provider (Green API, Twilio, or Meta)."""
    provider = settings.WHATSAPP_PROVIDER

    if provider == "green_api" or (provider == "auto" and settings.GREEN_API_INSTANCE_ID):
        return await send_green_api_whatsapp_message(to_number, message)
    elif provider == "twilio" or (provider == "auto" and settings.TWILIO_ACCOUNT_SID):
        return await send_twilio_whatsapp_message(to_number, message)
    elif provider == "meta" or (provider == "auto" and settings.WHATSAPP_CLOUD_TOKEN):
        return await send_meta_whatsapp_message(to_number, message)
    else:
        # Fallback to green_api if credentials exist, else twilio
        if settings.GREEN_API_INSTANCE_ID:
            return await send_green_api_whatsapp_message(to_number, message)
        return await send_twilio_whatsapp_message(to_number, message)

