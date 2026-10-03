import asyncio
from fastapi.testclient import TestClient
from main import app
from services import whatsapp
from config import settings

def test_green_api_webhook_parsing():
    client = TestClient(app)

    # 1. Test ignoring non-incoming webhooks (e.g. outgoing or state change)
    outgoing_payload = {
        "typeWebhook": "outgoingAPIMessageReceived",
        "instanceData": {"idInstance": 12345, "wid": "12345@c.us", "typeInstance": "whatsapp"},
        "timestamp": 1234567890,
        "idMessage": "MSG123",
        "senderData": {"chatId": "919876543210@c.us"}
    }
    res = client.post("/whatsapp/green-api-webhook", json=outgoing_payload)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert res.json().get("status") == "ignored", f"Expected ignored, got {res.json()}"
    print("✅ Successfully ignored outgoing webhook (avoids infinite reply loop)")

    # 2. Test Green API textMessage on dedicated endpoint
    incoming_text_payload = {
        "typeWebhook": "incomingMessageReceived",
        "instanceData": {"idInstance": 12345, "wid": "12345@c.us", "typeInstance": "whatsapp"},
        "timestamp": 1234567890,
        "idMessage": "MSG_TXT_1",
        "senderData": {
            "chatId": "919876543210@c.us",
            "sender": "919876543210@c.us",
            "senderName": "Test Contact"
        },
        "messageData": {
            "typeMessage": "textMessage",
            "textMessageData": {
                "textMessage": "Hello! Are you available to chat?"
            }
        }
    }
    res = client.post("/whatsapp/green-api-webhook", json=incoming_text_payload)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert res.json().get("status") == "success", f"Expected success, got {res.json()}"
    print("✅ Successfully received and processed Green API textMessage")

    # 3. Test Green API extendedTextMessage on dual-mode /whatsapp/webhook endpoint
    incoming_ext_payload = {
        "typeWebhook": "incomingMessageReceived",
        "instanceData": {"idInstance": 12345, "wid": "12345@c.us", "typeInstance": "whatsapp"},
        "timestamp": 1234567890,
        "idMessage": "MSG_EXT_1",
        "senderData": {
            "chatId": "919876543210@c.us",
            "sender": "919876543210@c.us",
            "senderName": "Event Attendee"
        },
        "messageData": {
            "typeMessage": "extendedTextMessage",
            "extendedTextMessageData": {
                "text": "What is the Wi-Fi password for the hackathon?"
            }
        }
    }
    res = client.post("/whatsapp/webhook", json=incoming_ext_payload)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert res.json().get("status") == "success", f"Expected success, got {res.json()}"
    print("✅ Successfully routed Green API payload via generic /whatsapp/webhook endpoint")

    # 4. Test /api/status returns Green API provider information
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert "whatsapp_provider" in data
    assert "green_api_configured" in data
    print(f"✅ /api/status verified: provider = {data['whatsapp_provider']}")

if __name__ == "__main__":
    test_green_api_webhook_parsing()
    print("\n🎉 All Green API tests passed successfully!")
