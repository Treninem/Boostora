from app import db


class InputSessionService:
    @staticmethod
    def set_session(user_id: int, mode: str, payload: str | None = None) -> None:
        db.execute(
            '''
            INSERT INTO input_sessions (user_id, mode, payload)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                mode = excluded.mode,
                payload = excluded.payload,
                updated_at = CURRENT_TIMESTAMP
            ''',
            (user_id, mode, payload),
        )

    @staticmethod
    def get_session(user_id: int):
        return db.fetch_one('SELECT * FROM input_sessions WHERE user_id = ?', (user_id,))

    @staticmethod
    def clear_session(user_id: int) -> None:
        db.execute('DELETE FROM input_sessions WHERE user_id = ?', (user_id,))
