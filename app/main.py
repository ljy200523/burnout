from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app.models import CalendarEvent, ChatMessage, Student, WellbeingEntry
from app.schemas import (
    CalendarEventRead,
    CalendarSyncRequest,
    CalendarSyncResponse,
    CalendarEventWrite,
    ChatMessageRead,
    ChatReply,
    ChatRequest,
    StudentCreate,
    StudentRead,
    StudentUpdate,
    WellbeingRead,
    WellbeingWrite,
    WorkloadDay,
)
from app.services.chat import make_supportive_reply

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name, version="0.1.0", description="Student workload and well-being MVP API")
api = settings.api_prefix
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/static/{filename}", include_in_schema=False)
def static_file(filename: str):
    if filename not in {"styles.css", "app.js"}:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(STATIC_DIR / filename)


def get_student_or_404(student_id: int, db: Session) -> Student:
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post(f"{api}/students", response_model=StudentRead, status_code=status.HTTP_201_CREATED)
def create_student(payload: StudentCreate, db: Session = Depends(get_db)):
    student = Student(display_name=payload.display_name)
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


@app.get(f"{api}/students/{{student_id}}", response_model=StudentRead)
def read_student(student_id: int, db: Session = Depends(get_db)):
    return get_student_or_404(student_id, db)


@app.patch(f"{api}/students/{{student_id}}", response_model=StudentRead)
def update_student(student_id: int, payload: StudentUpdate, db: Session = Depends(get_db)):
    student = get_student_or_404(student_id, db)
    student.display_name = payload.display_name
    db.commit()
    db.refresh(student)
    return student


@app.put(f"{api}/students/{{student_id}}/wellbeing", response_model=WellbeingRead)
def upsert_wellbeing(student_id: int, payload: WellbeingWrite, db: Session = Depends(get_db)):
    get_student_or_404(student_id, db)
    entry = db.scalar(select(WellbeingEntry).where(WellbeingEntry.student_id == student_id, WellbeingEntry.entry_date == payload.entry_date))
    if entry is None:
        entry = WellbeingEntry(student_id=student_id, **payload.model_dump())
        db.add(entry)
    else:
        for key, value in payload.model_dump().items():
            setattr(entry, key, value)
    db.commit()
    db.refresh(entry)
    return entry


@app.get(f"{api}/students/{{student_id}}/wellbeing", response_model=list[WellbeingRead])
def list_wellbeing(
    student_id: int,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(default=30, ge=1, le=180),
    db: Session = Depends(get_db),
):
    get_student_or_404(student_id, db)
    stmt = select(WellbeingEntry).where(WellbeingEntry.student_id == student_id)
    if start:
        stmt = stmt.where(WellbeingEntry.entry_date >= start)
    if end:
        stmt = stmt.where(WellbeingEntry.entry_date <= end)
    return db.scalars(stmt.order_by(WellbeingEntry.entry_date.desc()).limit(limit)).all()


@app.post(f"{api}/students/{{student_id}}/calendar/events", response_model=CalendarEventRead, status_code=status.HTTP_201_CREATED)
def create_calendar_event(student_id: int, payload: CalendarEventWrite, db: Session = Depends(get_db)):
    get_student_or_404(student_id, db)
    event = CalendarEvent(student_id=student_id, **payload.model_dump())
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An event with this provider and external ID already exists")
    db.refresh(event)
    return event


@app.get(f"{api}/students/{{student_id}}/calendar/events", response_model=list[CalendarEventRead])
def list_calendar_events(
    student_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
):
    get_student_or_404(student_id, db)
    stmt = select(CalendarEvent).where(CalendarEvent.student_id == student_id)
    if start:
        stmt = stmt.where(CalendarEvent.ends_at >= start)
    if end:
        stmt = stmt.where(CalendarEvent.starts_at <= end)
    return db.scalars(stmt.order_by(CalendarEvent.starts_at)).all()


@app.post(f"{api}/students/{{student_id}}/calendar/sync", response_model=CalendarSyncResponse)
def sync_calendar(student_id: int, payload: CalendarSyncRequest, db: Session = Depends(get_db)):
    """Import normalized provider events. OAuth/provider fetching belongs in a future connector."""
    get_student_or_404(student_id, db)
    imported = updated = 0
    for item in payload.events:
        if item.provider not in (payload.provider, "manual"):
            raise HTTPException(status_code=422, detail="Event provider must match sync provider")
        values = item.model_dump()
        values["provider"] = payload.provider
        event = db.scalar(select(CalendarEvent).where(
            CalendarEvent.student_id == student_id,
            CalendarEvent.provider == payload.provider,
            CalendarEvent.external_id == item.external_id,
        )) if item.external_id else None
        if event:
            for key, value in values.items():
                setattr(event, key, value)
            updated += 1
        else:
            db.add(CalendarEvent(student_id=student_id, **values))
            imported += 1
    db.commit()
    return CalendarSyncResponse(provider=payload.provider, imported=imported, updated=updated)


@app.get(f"{api}/students/{{student_id}}/calendar/workload", response_model=list[WorkloadDay])
def workload(student_id: int, start: date, days: int = Query(default=7, ge=1, le=90), db: Session = Depends(get_db)):
    get_student_or_404(student_id, db)
    range_start = datetime.combine(start, time.min, tzinfo=timezone.utc)
    range_end = range_start + timedelta(days=days)
    events = db.scalars(select(CalendarEvent).where(
        CalendarEvent.student_id == student_id,
        CalendarEvent.starts_at < range_end,
        CalendarEvent.ends_at > range_start,
    )).all()
    totals: dict[date, list[float | int]] = {}
    for event in events:
        start_dt = event.starts_at if event.starts_at.tzinfo else event.starts_at.replace(tzinfo=timezone.utc)
        end_dt = event.ends_at if event.ends_at.tzinfo else event.ends_at.replace(tzinfo=timezone.utc)
        cursor = max(start_dt, range_start)
        end_dt = min(end_dt, range_end)
        while cursor < end_dt:
            day = cursor.date()
            boundary = min(datetime.combine(day + timedelta(days=1), time.min, tzinfo=timezone.utc), end_dt)
            row = totals.setdefault(day, [0, 0.0])
            row[0] += 1
            row[1] += (boundary - cursor).total_seconds() / 3600
            cursor = boundary
    return [WorkloadDay(day=start + timedelta(days=i), event_count=int(totals.get(start + timedelta(days=i), [0, 0])[0]), scheduled_hours=round(float(totals.get(start + timedelta(days=i), [0, 0])[1]), 2)) for i in range(days)]


@app.post(f"{api}/students/{{student_id}}/chat", response_model=ChatReply)
def chat(student_id: int, payload: ChatRequest, db: Session = Depends(get_db)):
    get_student_or_404(student_id, db)
    user_message = ChatMessage(student_id=student_id, role="user", content=payload.message)
    db.add(user_message)
    reply_text = make_supportive_reply(payload.message, student_id, db)
    assistant_message = ChatMessage(student_id=student_id, role="assistant", content=reply_text)
    db.add(assistant_message)
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)
    return ChatReply(user_message_id=user_message.id, assistant_message_id=assistant_message.id, reply=reply_text, source="openai")


@app.get(f"{api}/students/{{student_id}}/chat/history", response_model=list[ChatMessageRead])
def chat_history(student_id: int, limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    get_student_or_404(student_id, db)
    rows = db.scalars(select(ChatMessage).where(ChatMessage.student_id == student_id).order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(limit)).all()
    return list(reversed(rows))
