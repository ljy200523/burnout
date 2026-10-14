from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CalendarEvent, ChatMessage, WellbeingEntry


SYSTEM_INSTRUCTIONS = """You are a supportive student wellbeing assistant. Be warm, concise, and practical. Help students reflect on stress, workload, sleep, and routines without diagnosing conditions or presenting yourself as a therapist. Offer small manageable next steps and ask at most one question at a time. Do not shame or pressure the student. If a student describes imminent danger or self-harm, encourage contacting local emergency services now and reaching a trusted person immediately. You are not emergency care. Treat supplied student records as sensitive context and only use details relevant to the student's request."""


def make_supportive_reply(message: str, student_id: int, db: Session) -> str:
    """Generate a supportive reply with OpenAI Responses API; the API key stays server-side."""
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="Chat is not configured. Set OPENAI_API_KEY on the server.")

    today = date.today()
    now = datetime.now(timezone.utc)
    upcoming = db.scalars(
        select(CalendarEvent)
        .where(CalendarEvent.student_id == student_id, CalendarEvent.ends_at >= now)
        .order_by(CalendarEvent.starts_at)
        .limit(8)
    ).all()
    recent_wellbeing = db.scalars(
        select(WellbeingEntry)
        .where(WellbeingEntry.student_id == student_id)
        .order_by(WellbeingEntry.entry_date.desc())
        .limit(7)
    ).all()
    history = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.student_id == student_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(12)
    ).all()
    history.reverse()

    context_lines = [f"Today's date: {today.isoformat()}. Use dates and times as shown; event times are stored as provided."]
    if upcoming:
        context_lines.append("Upcoming calendar events: " + "; ".join(
            f"{event.title} — {event.starts_at.isoformat()} to {event.ends_at.isoformat()} ({event.category})"
            for event in upcoming
        ))
    if recent_wellbeing:
        context_lines.append("Recent optional wellbeing logs (sleep hours, mood 1-5, stress 1-5, meals, water glasses): " + "; ".join(
            f"{entry.entry_date}: {entry.sleep_hours}, {entry.mood}, {entry.stress}, {entry.meals_count}, {entry.water_glasses}"
            for entry in reversed(recent_wellbeing)
        ))

    input_items = [{"role": "developer", "content": "Private student context for this reply (use only when relevant):\n" + "\n".join(context_lines)}]
    input_items.extend({"role": row.role, "content": row.content} for row in history if row.role in {"user", "assistant"})
    input_items.append({"role": "user", "content": message})

    try:
        response = OpenAI(api_key=settings.openai_api_key).responses.create(
            model=settings.openai_model,
            instructions=SYSTEM_INSTRUCTIONS,
            input=input_items,
            max_output_tokens=350,
            store=False,
        )
    except Exception as exc:
        # Do not expose provider exception text, which may contain operational details.
        raise HTTPException(status_code=502, detail="The chatbot is temporarily unavailable. Please try again.") from exc

    reply = response.output_text.strip()
    if not reply:
        raise HTTPException(status_code=502, detail="The chatbot returned an empty response. Please try again.")
    return reply
