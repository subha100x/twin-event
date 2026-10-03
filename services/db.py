import aiosqlite
import os
from datetime import datetime
from config import settings

DB_FILE = settings.DB_PATH

async def init_db():
    """Initializes the database schema if not already present."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,
                sender_name TEXT DEFAULT '',
                incoming_text TEXT NOT NULL,
                agent_reply TEXT NOT NULL,
                mode TEXT NOT NULL,
                category TEXT DEFAULT 'GENERAL',
                is_escalated INTEGER DEFAULT 0,
                emailed_in_digest INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                sender TEXT PRIMARY KEY,
                sender_name TEXT DEFAULT '',
                is_muted INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_docs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS persona_profile (
                id INTEGER PRIMARY KEY,
                user_name TEXT DEFAULT 'Subho',
                occupation TEXT DEFAULT '',
                current_status TEXT DEFAULT '',
                communication_tone TEXT DEFAULT 'casual',
                common_greetings TEXT DEFAULT '',
                common_slang TEXT DEFAULT '',
                sample_chats TEXT DEFAULT '',
                custom_rules TEXT DEFAULT '',
                compiled_prompt TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.commit()

async def get_persona_profile() -> dict:
    """Fetches the saved persona profile and compiled prompt."""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM persona_profile WHERE id = 1") as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
    # Default initial profile
    return {
        "id": 1,
        "user_name": getattr(settings, "USER_NAME", "Subho") or "Subho",
        "occupation": "Developer & Tech enthusiast",
        "current_status": "Away from phone / in classes or meetings",
        "communication_tone": "casual",
        "common_greetings": "Hey, yo, what's up",
        "common_slang": "bet, sounds good, on it",
        "sample_chats": "",
        "custom_rules": "Acknowledge urgent messages and confirm Subho is notified via email alert.",
        "compiled_prompt": "",
        "updated_at": datetime.utcnow().isoformat()
    }

async def save_persona_profile(data: dict):
    """Inserts or updates the singleton persona profile in the database."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT INTO persona_profile (
                id, user_name, occupation, current_status, communication_tone,
                common_greetings, common_slang, sample_chats, custom_rules,
                compiled_prompt, updated_at
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                user_name = excluded.user_name,
                occupation = excluded.occupation,
                current_status = excluded.current_status,
                communication_tone = excluded.communication_tone,
                common_greetings = excluded.common_greetings,
                common_slang = excluded.common_slang,
                sample_chats = excluded.sample_chats,
                custom_rules = excluded.custom_rules,
                compiled_prompt = excluded.compiled_prompt,
                updated_at = excluded.updated_at
        """, (
            data.get("user_name", "Subho"),
            data.get("occupation", ""),
            data.get("current_status", ""),
            data.get("communication_tone", "casual"),
            data.get("common_greetings", ""),
            data.get("common_slang", ""),
            data.get("sample_chats", ""),
            data.get("custom_rules", ""),
            data.get("compiled_prompt", ""),
            datetime.utcnow().isoformat()
        ))
        await db.commit()

async def log_interaction(
    sender: str,
    sender_name: str,
    incoming_text: str,
    agent_reply: str,
    mode: str,
    category: str,
    is_escalated: bool,
    mark_digest_sent: bool = False
) -> int:
    """Logs an incoming message and AI reply into the database."""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("""
            INSERT INTO messages (
                sender, sender_name, incoming_text, agent_reply,
                mode, category, is_escalated, emailed_in_digest, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sender,
            sender_name or sender,
            incoming_text,
            agent_reply,
            mode,
            category,
            1 if is_escalated else 0,
            1 if mark_digest_sent else 0,
            datetime.utcnow().isoformat()
        ))
        msg_id = cursor.lastrowid

        # Update conversation status
        await db.execute("""
            INSERT INTO conversations (sender, sender_name, last_message_at)
            VALUES (?, ?, ?)
            ON CONFLICT(sender) DO UPDATE SET
                sender_name = excluded.sender_name,
                last_message_at = excluded.last_message_at
        """, (sender, sender_name or sender, datetime.utcnow().isoformat()))

        await db.commit()
        return msg_id

async def is_sender_muted(sender: str) -> bool:
    """Checks if a sender has been muted (i.e. Human Takeover active)."""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT is_muted FROM conversations WHERE sender = ?", (sender,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0] == 1:
                return True
            return False

async def set_sender_mute(sender: str, mute: bool):
    """Mutes or unmutes AI responses for a specific sender."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT INTO conversations (sender, is_muted, last_message_at)
            VALUES (?, ?, ?)
            ON CONFLICT(sender) DO UPDATE SET is_muted = excluded.is_muted
        """, (sender, 1 if mute else 0, datetime.utcnow().isoformat()))
        await db.commit()

async def get_recent_conversation_history(sender: str, limit: int = 5):
    """Retrieves recent conversation turns for context."""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("""
            SELECT incoming_text, agent_reply, created_at
            FROM messages
            WHERE sender = ?
            ORDER BY id DESC LIMIT ?
        """, (sender, limit)) as cursor:
            rows = await cursor.fetchall()
            # Return in chronological order
            return list(reversed(rows))

async def get_unnotified_digest_messages():
    """Fetches non-escalated messages that haven't been emailed yet."""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("""
            SELECT id, sender, sender_name, incoming_text, agent_reply, mode, category, created_at
            FROM messages
            WHERE emailed_in_digest = 0 AND is_escalated = 0
            ORDER BY id ASC
        """) as cursor:
            return await cursor.fetchall()

async def mark_messages_as_digested(message_ids: list[int]):
    """Marks messages as included in a sent digest."""
    if not message_ids:
        return
    placeholders = ",".join("?" for _ in message_ids)
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(f"""
            UPDATE messages SET emailed_in_digest = 1 WHERE id IN ({placeholders})
        """, message_ids)
        await db.commit()

async def get_all_recent_messages(limit: int = 50):
    """Fetches recent interactions for the admin dashboard."""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT id, sender, sender_name, incoming_text, agent_reply, mode, category, is_escalated, created_at
            FROM messages
            ORDER BY id DESC LIMIT ?
        """, (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_stats():
    """Gets total counts for the admin dashboard."""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT COUNT(*) FROM messages") as cursor:
            total_msgs = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(DISTINCT sender) FROM messages") as cursor:
            total_senders = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM messages WHERE is_escalated = 1") as cursor:
            escalations = (await cursor.fetchone())[0]
        return {
            "total_messages": total_msgs,
            "unique_contacts": total_senders,
            "escalations": escalations
        }
