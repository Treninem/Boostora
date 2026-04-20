from app import db


class AdminLogService:
    @staticmethod
    def log(admin_user_id: int, action: str, *, target_user_id: int | None = None, details: str | None = None) -> int:
        return db.execute(
            '''
            INSERT INTO admin_logs (admin_user_id, target_user_id, action, details)
            VALUES (?, ?, ?, ?)
            ''',
            (admin_user_id, target_user_id, action, details),
        )

    @staticmethod
    def get_logs(limit: int = 50):
        return db.fetch_all(
            'SELECT * FROM admin_logs ORDER BY created_at DESC, id DESC LIMIT ?',
            (limit,),
        )
