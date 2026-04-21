from telebot.types import User

from app import db
from app.config import settings
from app.services.economy import INTERNAL_CURRENCY_NAME_RU, SIGNUP_BONUS_SPARKS
from app.services.wallets import WalletService
from app.texts import LANGUAGES, ROLE_CLIENT, ROLE_PERFORMER, TEXTS


class UserService:
    @staticmethod
    def ensure_user(telegram_user: User, referred_by_user_id: int | None = None) -> None:
        existing = db.get_user(telegram_user.id)
        db.upsert_user(
            user_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            referred_by_user_id=referred_by_user_id,
        )
        db.ensure_wallet(telegram_user.id)
        if existing is None:
            WalletService.credit_bonus_balance(
                telegram_user.id,
                SIGNUP_BONUS_SPARKS,
                entry_type='signup_bonus',
                note='Welcome campaign bonus for first registration',
            )

    @staticmethod
    def get_or_create_user(telegram_user: User, referred_by_user_id: int | None = None):
        UserService.ensure_user(telegram_user, referred_by_user_id=referred_by_user_id)
        return db.get_user(telegram_user.id)

    @staticmethod
    def get_user(user_id: int):
        return db.get_user(user_id)

    @staticmethod
    def get_language(user_id: int) -> str:
        user = db.get_user(user_id)
        if user and user['language_code'] in TEXTS:
            return str(user['language_code'])
        return 'ru'

    @staticmethod
    def set_language(user_id: int, language_code: str) -> None:
        if language_code not in TEXTS:
            raise ValueError('Unsupported language')
        db.set_user_language(user_id, language_code)

    @staticmethod
    def set_role(user_id: int, role: str) -> None:
        if role not in {ROLE_PERFORMER, ROLE_CLIENT}:
            raise ValueError('Unsupported role')
        db.set_user_role(user_id, role)

    @staticmethod
    def get_role(user_id: int) -> str | None:
        user = db.get_user(user_id)
        return str(user['role']) if user and user['role'] else None

    @staticmethod
    def get_status(user_id: int) -> str:
        user = db.get_user(user_id)
        return str(user['status']) if user and user['status'] else 'active'

    @staticmethod
    def t(viewer_id: int, key: str, **kwargs) -> str:
        language = UserService.get_language(viewer_id)
        template = TEXTS.get(language, TEXTS['ru']).get(key) or TEXTS['en'].get(key) or TEXTS['ru'].get(key) or key
        class _SafeDict(dict):
            def __missing__(self, item):
                return '{' + item + '}'
        return template.format_map(_SafeDict(**kwargs))

    @staticmethod
    def role_label(user_id: int, role: str) -> str:
        language = UserService.get_language(user_id)
        return TEXTS[language][role]

    @staticmethod
    def language_label(language_code: str) -> str:
        return LANGUAGES[language_code]

    @staticmethod
    def internal_currency_label(user_id: int) -> str:
        return UserService.t(user_id, 'internal_currency_name')

    @staticmethod
    def owner_id() -> int | None:
        return settings.admin_ids[0] if settings.admin_ids else None

    @staticmethod
    def is_owner(user_id: int) -> bool:
        owner_id = UserService.owner_id()
        return owner_id is not None and int(user_id) == int(owner_id)

    @staticmethod
    def is_admin(user_id: int) -> bool:
        return user_id in settings.admin_ids

    @staticmethod
    def can_access_bot(user_id: int) -> bool:
        if UserService.is_admin(user_id):
            return True
        return UserService.get_status(user_id) != 'blocked'


    @staticmethod
    def count_users() -> int:
        row = db.fetch_one('SELECT COUNT(*) AS cnt FROM users')
        return int(row['cnt'] or 0) if row else 0

    @staticmethod
    def list_users(limit: int = 10, offset: int = 0):
        return db.fetch_all(
            """
            SELECT u.*, COALESCE(w.available_balance, 0) AS available_balance,
                   COALESCE(w.internal_balance, 0) AS internal_balance,
                   COALESCE(w.bonus_balance, 0) AS bonus_balance
            FROM users u
            LEFT JOIN wallets w ON w.user_id = u.user_id
            ORDER BY u.created_at DESC, u.user_id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
