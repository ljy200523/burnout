from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CalendarEvent, WellbeingEntry


def make_supportive_reply(message: str, student_id: int, db: Session) -> str:
    """Local MVP responder. Replace with a vetted LLM provider behind this function."""
    text = message.casefold()
    today = date.today()
    if any(word in text for word in ("deadline", "workload", "busy", "schedule", "calendar")):
        upcoming = db.scalars(
            select(CalendarEvent)
            .where(CalendarEvent.student_id == student_id, CalendarEvent.starts_at >= today)
            .order_by(CalendarEvent.starts_at)
            .limit(3)
        ).all()
        if upcoming:
            items = "; ".join(f"{event.title} ({event.starts_at:%b %d})" for event in upcoming)
            return f"It sounds like your workload is on your mind. Your next scheduled items are: {items}. Which one feels most urgent, and what is one small step you can take today?"
        return "It sounds like your workload is on your mind. Try listing everything due, then choose one small next step and a short recovery break. You can add events to your calendar here so we can look at the week together."
    if any(word in text for word in ("sleep", "tired", "exhausted")):
        entry = db.scalar(select(WellbeingEntry).where(WellbeingEntry.student_id == student_id).order_by(WellbeingEntry.entry_date.desc()).limit(1))
        if entry and entry.sleep_hours is not None:
            return f"You logged {entry.sleep_hours:g} hours of sleep most recently. How rested do you feel today? A consistent wind-down routine can be a gentle place to start."
        return "Feeling tired can make everything harder. If you can, give yourself a consistent wind-down time tonight and note how you feel tomorrow. What has been getting in the way of rest?"
    if any(word in text for word in ("stress", "anxious", "overwhelmed", "burnout")):
        return "I’m sorry things feel heavy. Pause for one slow breath, then name just the next manageable task. If this keeps affecting your day-to-day life, consider reaching out to someone you trust or a campus counselor."
    if any(word in text for word in ("hurt myself", "suicid", "end my life", "kill myself")):
        return "I’m really sorry you’re dealing with this. If you may be in immediate danger, contact your local emergency number now or go to an emergency department. Please reach out to someone you trust and stay with them. I’m an automated support tool, not emergency care."
    return "Thanks for sharing that with me. What feels like the biggest thing affecting your well-being today? We can take it one step at a time."
