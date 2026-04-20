from app import db


class UIStateService:
    @staticmethod
    def get_state(user_id: int):
        return db.fetch_one('SELECT * FROM ui_sessions WHERE user_id = ?', (user_id,))

    @staticmethod
    def get_current_version(user_id: int) -> int:
        state = UIStateService.get_state(user_id)
        if not state:
            return 0
        return int(state['screen_version'])

    @staticmethod
    def reserve_next_version(user_id: int, chat_id: int, screen_key: str) -> int:
        current_version = UIStateService.get_current_version(user_id)
        next_version = current_version + 1
        db.execute(
            '''
            INSERT INTO ui_sessions (user_id, chat_id, current_screen, screen_version)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                chat_id = excluded.chat_id,
                current_screen = excluded.current_screen,
                screen_version = excluded.screen_version,
                updated_at = CURRENT_TIMESTAMP
            ''',
            (user_id, chat_id, screen_key, next_version),
        )
        return next_version

    @staticmethod
    def bind_message(user_id: int, chat_id: int, message_id: int, screen_key: str, screen_version: int) -> None:
        db.execute(
            '''
            INSERT INTO ui_sessions (user_id, chat_id, message_id, current_screen, screen_version)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                chat_id = excluded.chat_id,
                message_id = excluded.message_id,
                current_screen = excluded.current_screen,
                screen_version = excluded.screen_version,
                updated_at = CURRENT_TIMESTAMP
            ''',
            (user_id, chat_id, message_id, screen_key, screen_version),
        )

    @staticmethod
    def get_bound_message(user_id: int) -> tuple[int, int] | None:
        state = UIStateService.get_state(user_id)
        if not state or state['chat_id'] is None or state['message_id'] is None:
            return None
        return int(state['chat_id']), int(state['message_id'])

    @staticmethod
    def is_stale(user_id: int, version: int) -> bool:
        return version != UIStateService.get_current_version(user_id)
