from datetime import datetime, timedelta

from app.time_utils import utcnow
from app import db
from app.config import settings


class HoldService:
    @staticmethod
    def create_hold(user_id: int, amount: int, *, submission_id: int | None = None, hold_minutes: int | None = None) -> int:
        duration_minutes = hold_minutes if hold_minutes is not None else settings.default_hold_hours * 60
        release_at = utcnow() + timedelta(minutes=duration_minutes)
        return db.execute(
            '''
            INSERT INTO holds (user_id, submission_id, amount, release_at)
            VALUES (?, ?, ?, ?)
            ''',
            (user_id, submission_id, amount, release_at.isoformat(timespec='seconds')),
        )

    @staticmethod
    def get_holds_for_user(user_id: int):
        return db.fetch_all(
            'SELECT * FROM holds WHERE user_id = ? ORDER BY created_at DESC, id DESC',
            (user_id,),
        )
