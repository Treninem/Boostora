import os
import sys
from pathlib import Path

os.environ.setdefault('BOT_TOKEN', 'dummy-token-for-local-tests')

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tempfile
from types import SimpleNamespace

from app.config import settings
from app.db import fetch_one, init_db
from app.router import SCREEN_MAIN_MENU, SCREEN_REQUIRED_SUBSCRIPTION, SCREEN_ROLE, resolve_next_screen
from app.services.ui_state import UIStateService
from app.services.users import UserService
from app.utils.callbacks import pack_callback, parse_callback


class FakeBot:
    def __init__(self, subscribed: bool = False) -> None:
        self.subscribed = subscribed

    def get_chat_member(self, chat_id: int, user_id: int):
        if self.subscribed:
            return SimpleNamespace(status='member', is_member=True)
        return SimpleNamespace(status='left', is_member=False)



def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_file = Path(temp_dir) / 'stage3.db'
        original_db_path = settings.db_path
        object.__setattr__(settings, 'db_path', str(db_file))
        try:
            init_db()
            user = SimpleNamespace(id=3001, username='stage3', first_name='Stage', last_name='Three')
            UserService.ensure_user(user)
            UserService.set_language(3001, 'en')

            assert resolve_next_screen(FakeBot(subscribed=False), 3001, 777) == SCREEN_ROLE
            UserService.set_role(3001, 'performer')
            assert resolve_next_screen(FakeBot(subscribed=False), 3001, 777) == SCREEN_REQUIRED_SUBSCRIPTION
            assert resolve_next_screen(FakeBot(subscribed=False), 3001, settings.required_chat_id) == SCREEN_MAIN_MENU
            assert resolve_next_screen(FakeBot(subscribed=True), 3001, 777) == SCREEN_MAIN_MENU

            version = UIStateService.reserve_next_version(3001, 777, 'language')
            assert version == 1
            UIStateService.bind_message(3001, 777, 55, 'language', version)
            state = fetch_one('SELECT * FROM ui_sessions WHERE user_id = ?', (3001,))
            assert state is not None
            assert int(state['message_id']) == 55
            assert UIStateService.is_stale(3001, 0) is True
            assert UIStateService.is_stale(3001, 1) is False

            callback = pack_callback(1, 'go', 'main_menu')
            parsed = parse_callback(callback)
            assert parsed is not None
            assert parsed.version == 1
            assert parsed.action == 'go'
            assert parsed.value == 'main_menu'

            print('OK: stage 3 smoke test passed')
        finally:
            object.__setattr__(settings, 'db_path', original_db_path)


if __name__ == '__main__':
    main()
