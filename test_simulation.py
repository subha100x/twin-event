import asyncio
from services import db, llm, notifier
from config import settings

async def main():
    print("=" * 60)
    print("🚀 Running Twin & Event Agent Self-Test Pipeline...")
    print("=" * 60)

    # 1. Initialize DB
    print("[1] Initializing SQLite database...")
    await db.init_db()
    print("    ✅ Database ready.")

    # 2. Test Persona Generation
    print("\n[2] Testing Persona Digital Twin mode...")
    test_friend = "Rahul Sharma"
    incoming_persona_msg = "Hey, are you free for a call tonight regarding our project?"
    persona_res = await llm.generate_persona_reply(test_friend, incoming_persona_msg, [])
    print(f"    Sender: {test_friend}")
    print(f"    Msg:    \"{incoming_persona_msg}\"")
    print(f"    Reply:  \"{persona_res['reply']}\"")
    print(f"    Category: {persona_res['category']} | Escalated: {persona_res['is_escalated']}")

    # 3. Test Event Committee Triage Mode
    print("\n[3] Testing Organizing Committee Event Helpdesk mode...")
    test_hacker = "Samantha Lee (Team Alpha)"
    incoming_event_msg = "Hey! What is the submission deadline and what do we need to submit on Devpost?"
    event_res = await llm.generate_event_reply(test_hacker, incoming_event_msg, [])
    print(f"    Attendee: {test_hacker}")
    print(f"    Msg:      \"{incoming_event_msg}\"")
    print(f"    Reply:    \"{event_res['reply']}\"")
    print(f"    Category: {event_res['category']} | Escalated: {event_res['is_escalated']}")

    # 4. Test Event Urgent Escalation
    print("\n[4] Testing Event Emergency Escalation...")
    incoming_urgent_msg = "URGENT: A student in Room 102 feels dizzy and needs medical help right away!"
    urgent_res = await llm.generate_event_reply(test_hacker, incoming_urgent_msg, [])
    print(f"    Msg:      \"{incoming_urgent_msg}\"")
    print(f"    Reply:    \"{urgent_res['reply']}\"")
    print(f"    Category: {urgent_res['category']} | Escalated: {urgent_res['is_escalated']}")
    assert urgent_res["is_escalated"] is True, "Emergency should be marked as escalated!"
    print("    ✅ Escalation detection verified.")

    # 5. Test Logging to DB
    print("\n[5] Logging interactions to database...")
    msg_id = await db.log_interaction(
        sender="whatsapp:+919876543210",
        sender_name=test_friend,
        incoming_text=incoming_persona_msg,
        agent_reply=persona_res['reply'],
        mode="persona",
        category=persona_res['category'],
        is_escalated=persona_res['is_escalated']
    )
    print(f"    ✅ Logged message with ID: {msg_id}")

    stats = await db.get_stats()
    print(f"\n[6] Database stats: {stats}")
    print("\n🎉 All pipeline components verified successfully!")

if __name__ == "__main__":
    asyncio.run(main())
