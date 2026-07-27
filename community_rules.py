from __future__ import annotations

from datetime import datetime, timedelta

from app import db
from app.config import settings
from app.services.bot_chats import BotChatService


PROMO_TEXTS = [
    "✨ <b>Boostora</b> — задания, Искры✨, VIP и честная проверка выполнения без хаоса в чате. Откройте бота и попробуйте сами.",
    "🚀 <b>Boostora</b> помогает запускать задания и зарабатывать Искры✨ в одном боте. Без спама, с понятной аналитикой и удобным кошельком.",
    "💬 Нужны подписчики, реакции, комментарии или переходы? <b>Boostora</b> уже здесь. Откройте бота и посмотрите, как всё устроено.",
]


class PromoService:
    @staticmethod
    def _interval_hours() -> int:
        value = int(getattr(settings, 'promo_interval_hours', 18) or 18)
        return max(6, value)

    @staticmethod
    def _meta_key(chat_ref: str, suffix: str) -> str:
        return f'promo:{chat_ref}:{suffix}'

    @staticmethod
    def _get_meta(chat_ref: str, suffix: str) -> str:
        row = db.fetch_one('SELECT value FROM app_meta WHERE key = ?', (PromoService._meta_key(chat_ref, suffix),))
        return str(row['value']) if row and row['value'] is not None else ''

    @staticmethod
    def _set_meta(chat_ref: str, suffix: str, value: str) -> None:
        db.execute(
            '''
            INSERT INTO app_meta (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            ''',
            (PromoService._meta_key(chat_ref, suffix), value),
        )

    @staticmethod
    def _is_due(chat_ref: str) -> bool:
        raw = PromoService._get_meta(chat_ref, 'last_sent_at')
        if not raw:
            return True
        try:
            last_sent = datetime.fromisoformat(raw)
        except ValueError:
            return True
        return datetime.utcnow() - last_sent >= timedelta(hours=PromoService._interval_hours())

    @staticmethod
    def _next_text(chat_ref: str) -> str:
        raw_idx = PromoService._get_meta(chat_ref, 'index')
        index = int(raw_idx) if raw_idx.isdigit() else 0
        text = PROMO_TEXTS[index % len(PROMO_TEXTS)]
        PromoService._set_meta(chat_ref, 'index', str(index + 1))
        return text

    @staticmethod
    def run_due_promotions(bot) -> int:
        sent = 0
        seen_refs: set[str] = set()
        for row in BotChatService.list_promotable_chats():
            chat_ref = str(row['chat_ref'])
            if not chat_ref or chat_ref in seen_refs:
                continue
            seen_refs.add(chat_ref)
            if not PromoService._is_due(chat_ref):
                continue
            api_ref: str | int = int(chat_ref) if chat_ref.lstrip('-').isdigit() else chat_ref
            try:
                bot.send_message(api_ref, PromoService._next_text(chat_ref), disable_web_page_preview=True)
            except Exception:
                continue
            PromoService._set_meta(chat_ref, 'last_sent_at', datetime.utcnow().isoformat(timespec='seconds'))
            sent += 1
        return sent
