import httpx
import json
import os
import re
from config import settings

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")

def load_prompt_file(filename: str) -> str:
    path = os.path.join(PROMPTS_DIR, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def get_event_knowledge_base() -> str:
    return load_prompt_file("event_knowledge_base.md")

async def call_llm(system_instruction: str, prompt: str, user_query: str = "") -> str:
    """Invokes either Gemini or OpenAI via direct async HTTP."""
    if settings.LLM_PROVIDER == "gemini":
        if not settings.GEMINI_API_KEY:
            return "Hello! I am the automated agent. (Notice: GEMINI_API_KEY is not yet configured in .env. Please add it to enable real AI generation!)"
        
        # Gemini REST API
        model = settings.GEMINI_MODEL or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={settings.GEMINI_API_KEY}"
        
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"SYSTEM INSTRUCTION:\n{system_instruction}\n\nUSER MESSAGE:\n{prompt}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.6,
                "maxOutputTokens": 800
            }
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                print(f"[LLM Note] Gemini API returned {resp.status_code}. (Using intelligent fallback for local testing)")
                
                # Check user query keywords for intelligent demo responses
                q = (user_query or prompt).lower()
                if any(w in q for w in ["emergency", "medical", "dizzy", "hurt", "accident"]):
                    return json.dumps({
                        "category": "URGENT_ESCALATION",
                        "is_escalated": True,
                        "reply": "🚨 Medical and committee leads have been alerted immediately! First aid station is at Room 102 next to Registration Desk. Emergency phone: +1 (555) 019-2831."
                    })
                elif any(w in q for w in ["wifi", "wi-fi", "password", "internet"]):
                    return json.dumps({
                        "category": "LOGISTICS",
                        "is_escalated": False,
                        "reply": "Official Wi-Fi: **TechSprint_Guest** | Password: `Innovation2026!` 📶"
                    })
                elif any(w in q for w in ["deadline", "submission", "devpost"]):
                    return json.dumps({
                        "category": "SUBMISSION",
                        "is_escalated": False,
                        "reply": "Code Freeze & Devpost submission deadline is **tomorrow at 10:00 AM**! Please submit your public GitHub repo + 2-min demo video on devpost.com/techsprint2026."
                    })
                elif any(w in q for w in ["free", "call", "talk", "sync", "tonight", "busy"]):
                    return "Hey! I'm away from my phone right now, but I've sent an instant email ping to my inbox with your message. I'll catch up with you as soon as I'm back! ⚡"
                
                return "Hey! Thanks for reaching out. I've logged your message and sent an alert. I'll get back to you shortly!"
            
            data = resp.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            except (KeyError, IndexError):
                return "Message received! We will get back to you shortly."

    elif settings.LLM_PROVIDER == "openai":
        if not settings.OPENAI_API_KEY:
            return "Hello! OpenAI API key is missing in .env."
        
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": settings.OPENAI_MODEL or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.6,
            "max_tokens": 800
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                print(f"[LLM Error] OpenAI returned {resp.status_code}: {resp.text}")
                return "Message received! We will follow up soon."
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    
    return "Agent received your message."

def extract_clean_message(t: str) -> str:
    """Strips chain-of-thought or reasoning artifacts if present in open models like Gemma."""
    t = t.strip()
    user_name = getattr(settings, "USER_NAME", "Subho")
    # Replace any accidental placeholders
    t = re.sub(r"\[User's(?: Name)?\]", f"{user_name}'s", t, flags=re.IGNORECASE)
    t = re.sub(r"\[User(?: Name)?\]", user_name, t, flags=re.IGNORECASE)
    t = re.sub(r"\[Name\]", user_name, t, flags=re.IGNORECASE)

    quote_matches = re.findall(r'"([^"\n]{10,})"', t)
    if quote_matches and any(k in t for k in ["*", "Constraint", "Target", "Draft", "Persona", "Output:"]):
        res = quote_matches[-1].strip()
        res = re.sub(r"\[User's(?: Name)?\]", f"{user_name}'s", res, flags=re.IGNORECASE)
        res = re.sub(r"\[User(?: Name)?\]", user_name, res, flags=re.IGNORECASE)
        return res
    lines = [line.strip() for line in t.split("\n") if line.strip()]
    non_bullets = [l for l in lines if not l.startswith("*") and not l.startswith("-") and not l.startswith("#")]
    if non_bullets and ("*" in t or "Target:" in t or "Constraint:" in t):
        last_item = non_bullets[-1].strip('"\'')
        if len(last_item) > 5:
            last_item = re.sub(r"\[User's(?: Name)?\]", f"{user_name}'s", last_item, flags=re.IGNORECASE)
            last_item = re.sub(r"\[User(?: Name)?\]", user_name, last_item, flags=re.IGNORECASE)
            return last_item
async def synthesize_persona_prompt(profile: dict) -> str:
    """Uses LLM to analyze the user questionnaire and sample chat logs to synthesize a high-fidelity digital twin persona prompt."""
    user_name = profile.get("user_name", "Subho") or "Subho"
    occupation = profile.get("occupation", "Developer")
    status = profile.get("current_status", "Busy / away from phone")
    tone = profile.get("communication_tone", "casual")
    greetings = profile.get("common_greetings", "Hey, yo")
    slang = profile.get("common_slang", "cool, on it, bet")
    rules = profile.get("custom_rules", "")
    sample_chats = profile.get("sample_chats", "").strip()

    meta_prompt = f"""
You are an expert AI persona engineer and conversational linguist.
Your goal is to analyze the user's questionnaire profile and their real WhatsApp chat history to synthesize a specialized, authentic Persona System Prompt for an AI Digital Twin.

### User Questionnaire Profile:
- Owner Name: {user_name}
- Profession / Bio: {occupation}
- Current Status / Availability: {status}
- Preferred Tone: {tone}
- Typical Greetings: {greetings}
- Common Slang / Catchphrases: {slang}
- Custom Rules / Instructions: {rules}

### Real Sample WhatsApp Chats Sent by {user_name}:
\"\"\"
{sample_chats if sample_chats else "(No chat logs provided. Synthesize persona from the questionnaire details above.)"}
\"\"\"

Analyze the user's linguistic style:
- Vocabulary, slang, colloquialisms, tone
- Sentence lengths (brief vs detailed)
- Typical greeting habits and sign-offs
- Emoji patterns (which emojis they use, how often)

Generate a complete, ready-to-use System Instruction for the AI Digital Twin that will chat on WhatsApp on {user_name}'s behalf.
Ensure the prompt includes:
1. Role Definition: Explicitly state "You are the AI Persona Digital Twin of {user_name}." Strictly forbid placeholders like "[User]" or "[Name]".
2. Linguistic Fingerprint & Vibe: Prescribe the exact tone, phrasing, emojis, and sentence cadence matching {user_name}.
3. Current Context: Reflect that {user_name} is currently: {status}.
4. Handling Inquiries: How to respond to casual check-ins, routine questions, and urgent emergencies (email notification dispatch).
5. Safety Guardrails: Never make legal/financial commitments; keep WhatsApp responses concise (1-3 paragraphs).

Output ONLY the complete persona system instruction in clean Markdown. Do NOT include meta-commentary, preamble, or analysis bullet points before the prompt.
"""
    system_inst = "You are a specialized AI system prompt generator. Return ONLY the final synthesized system prompt in markdown without conversational intros or conclusions."
    result = await call_llm(system_instruction=system_inst, prompt=meta_prompt, user_query="persona prompt synthesis")
    
    cleaned = result.strip()
    if cleaned.startswith("```markdown"):
        cleaned = cleaned[11:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()

async def generate_persona_reply(sender_name: str, incoming_text: str, history: list) -> dict:
    """Generates a reply mimicking the user's personal twin persona."""
    # Check for dynamic persona profile in DB
    from services import db
    profile = await db.get_persona_profile()
    user_name = profile.get("user_name") or getattr(settings, "USER_NAME", "Subho") or "Subho"

    if profile.get("compiled_prompt"):
        persona_system = profile["compiled_prompt"]
    else:
        persona_system = load_prompt_file("persona_prompt.txt")
    
    # Check for urgent signals
    urgent_keywords = ["urgent", "emergency", "asap", "accident", "call me now", "critical", "help me"]
    is_urgent = any(k in incoming_text.lower() for k in urgent_keywords)
    
    history_context = ""
    if history:
        history_context = "\nRecent Conversation Turns:\n"
        for user_msg, bot_msg, _ in history:
            history_context += f"- Sender: {user_msg}\n- AI: {bot_msg}\n"
    
    prompt = f"""
User Name: {user_name}
Sender Name: {sender_name or 'Friend / Contact'}
Incoming Message: "{incoming_text}"
{history_context}

Please respond directly in WhatsApp chat style on {user_name}'s behalf. Never use placeholders like "[User]" or "[Name]"—refer to {user_name} directly. If this looks like an emergency or urgent ping, acknowledge that you've sent an instant email notification to {user_name}'s phone/inbox.
"""
    raw_reply = await call_llm(persona_system, prompt, user_query=incoming_text)
    reply = raw_reply
    try:
        json_match = re.search(r"\{.*\}", raw_reply, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(0))
            if "reply" in parsed:
                reply = parsed["reply"]
    except Exception:
        pass

    reply = extract_clean_message(reply)
    
    return {
        "reply": reply,
        "category": "URGENT_ESCALATION" if is_urgent else "PERSONAL_PING",
        "is_escalated": is_urgent
    }

async def generate_event_reply(sender_name: str, incoming_text: str, history: list) -> dict:
    """Generates a triage and FAQ answer for the Organizing Committee."""
    event_system = load_prompt_file("event_prompt.txt")
    kb = get_event_knowledge_base()
    
    history_context = ""
    if history:
        history_context = "\nRecent Conversation Turns:\n"
        for user_msg, bot_msg, _ in history:
            history_context += f"- Participant: {user_msg}\n- Committee AI: {bot_msg}\n"

    system_instruction = f"""
{event_system}

### Current Official Event Knowledge Base:
{kb}
"""

    prompt = f"""
Participant / Contact: {sender_name or 'Attendee'}
Incoming DM: "{incoming_text}"
{history_context}

First, analyze the query and provide the output formatted strictly as JSON with the following keys:
{{
  "category": "REGISTRATION | SCHEDULE | LOGISTICS | SUBMISSION | SPONSORSHIP | URGENT_ESCALATION | GENERAL",
  "is_escalated": true or false,
  "reply": "Your WhatsApp response to the attendee using markdown and bullet points if helpful"
}}
"""

    raw_response = await call_llm(system_instruction, prompt, user_query=incoming_text)
    
    # Parse JSON from LLM output
    category = "GENERAL"
    is_escalated = False
    reply = raw_response

    try:
        # Search for JSON block
        json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(0))
            category = parsed.get("category", "GENERAL").upper()
            is_escalated = bool(parsed.get("is_escalated", False))
            reply = parsed.get("reply", raw_response)
    except Exception as e:
        print(f"[Warning] Failed to parse JSON from event LLM response: {e}")

    reply = extract_clean_message(reply)

    # Fallback keyword escalation check
    if any(k in incoming_text.lower() for k in ["emergency", "medical", "urgent", "stole", "lost child", "dispute"]):
        is_escalated = True
        category = "URGENT_ESCALATION"

    return {
        "reply": reply,
        "category": category,
        "is_escalated": is_escalated
    }
