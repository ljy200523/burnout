from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import RewardLedger, RewardProfile, RewardRedemption, WellbeingEntry
from app.config import settings

CATALOGUE = [
    {"code": "cafe", "name": "Campus cafe voucher", "category": "Food & comfort", "description": "A coffee, matcha, or bubble tea treat.", "points": 100},
    {"code": "meal", "name": "Balanced canteen meal", "category": "Food & comfort", "description": "A meal at a participating campus eatery.", "points": 180},
    {"code": "gym", "name": "Campus gym or pool pass", "category": "Movement & rest", "description": "A guest pass or locker credit at the sports centre.", "points": 220},
    {"code": "rest_kit", "name": "Sleep and comfort kit", "category": "Movement & rest", "description": "An eye mask, laptop stand, or herbal tea pack.", "points": 300},
    {"code": "relax", "name": "Relaxation perk", "category": "Movement & rest", "description": "A campus nap pod or wellness centre credit.", "points": 350},
    {"code": "print", "name": "Bookstore or print credit", "category": "Academic relief", "description": "Printing credit or supplies from the campus bookstore.", "points": 150},
    {"code": "coffee_gift", "name": "Pay it forward: campus coffee", "category": "Kindness", "description": "Send a coffee voucher to a classmate having a crunch week.", "points": 120},
]


def award(db: Session, student_id: int, event_key: str, description: str, points: int) -> bool:
    if db.scalar(select(RewardLedger.id).where(RewardLedger.student_id == student_id, RewardLedger.event_key == event_key)):
        return False
    db.add(RewardLedger(student_id=student_id, event_key=event_key, description=description, points=points))
    return True


def weekly_balance_bonus(db: Session, student_id: int, today: date | None = None) -> int:
    today = today or datetime.now(ZoneInfo(settings.app_timezone)).date()
    if today.weekday() != 0:  # Evaluate the prior complete week on Monday.
        return 0
    week_start = today - timedelta(days=7)
    week_end = today - timedelta(days=1)
    rows = db.scalars(select(WellbeingEntry).where(
        WellbeingEntry.student_id == student_id,
        WellbeingEntry.entry_date >= week_start,
        WellbeingEntry.entry_date <= week_end,
    )).all()
    if not rows:
        return 0
    sleep = [r.sleep_hours for r in rows if r.sleep_hours is not None]
    meals = [r.meals_count for r in rows if r.meals_count is not None]
    exercise = [r.exercise_minutes for r in rows if r.exercise_minutes is not None]
    leisure = [r.leisure_minutes for r in rows if r.leisure_minutes is not None]
    if not all([sleep, meals, exercise, leisure]):
        return 0
    balanced = (5.5 <= sum(sleep) / len(sleep) <= 9.5
                and sum(meals) / len(meals) >= 2
                and sum(exercise) / len(exercise) >= 20
                and sum(leisure) / len(leisure) >= 30)
    key = f"balance:{week_start.isoformat()}"
    if balanced and award(db, student_id, key, "Four-domain balance bonus", 20):
        return 20
    return 0


def summary(db: Session, student_id: int) -> dict:
    profile = db.get(RewardProfile, student_id)
    if not profile:
        profile = RewardProfile(student_id=student_id, freeze_tokens=1)
        db.add(profile)
        db.flush()
    earned = db.scalar(select(func.coalesce(func.sum(RewardLedger.points), 0)).where(RewardLedger.student_id == student_id)) or 0
    spent = db.scalar(select(func.coalesce(func.sum(RewardRedemption.points_cost), 0)).where(
        RewardRedemption.student_id == student_id, RewardRedemption.status != "cancelled"
    )) or 0
    ledger = db.scalars(select(RewardLedger).where(RewardLedger.student_id == student_id).order_by(RewardLedger.created_at.desc()).limit(12)).all()
    redemptions = db.scalars(select(RewardRedemption).where(RewardRedemption.student_id == student_id).order_by(RewardRedemption.created_at.desc()).limit(10)).all()
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    checked_dates = set(db.scalars(select(WellbeingEntry.entry_date).where(
        WellbeingEntry.student_id == student_id, WellbeingEntry.entry_date >= cutoff.date()
    )).all())
    streak = 0
    cursor = datetime.now(ZoneInfo(settings.app_timezone)).date()
    if cursor not in checked_dates:
        cursor -= timedelta(days=1)
    while cursor in checked_dates:
        streak += 1
        cursor -= timedelta(days=1)
    freeze_date = None
    restored_date = None
    if profile.last_freeze_week:
        freeze_ledger = db.scalars(select(RewardLedger).where(RewardLedger.student_id == student_id, RewardLedger.event_key.like("freeze:%")).order_by(RewardLedger.created_at.desc())).first()
        if freeze_ledger:
            freeze_date = freeze_ledger.event_key.split(":", 1)[1]
            restored_date = date.fromisoformat(freeze_date)
    if restored_date:
        today = datetime.now(ZoneInfo(settings.app_timezone)).date()
        if today in checked_dates:
            cursor = today
        elif today - timedelta(days=1) in checked_dates:
            cursor = today - timedelta(days=1)
        else:
            cursor = None
        if cursor:
            while cursor in checked_dates or cursor == restored_date:
                streak += 1
                cursor -= timedelta(days=1)
    return {
        "points_balance": int(earned - spent), "points_earned": int(earned), "points_spent": int(spent),
        "streak_days": streak, "freeze_tokens": profile.freeze_tokens, "freeze_date": freeze_date, "catalogue": CATALOGUE,
        "ledger": [{"description": x.description, "points": x.points, "created_at": x.created_at} for x in ledger],
        "redemptions": [{"reward_name": x.reward_name, "points_cost": x.points_cost, "status": x.status,
                         "recipient_name": x.recipient_name, "created_at": x.created_at} for x in redemptions],
    }
