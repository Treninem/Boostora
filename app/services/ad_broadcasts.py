from __future__ import annotations

import html
import json
import math
from datetime import datetime, timedelta
from urllib.parse import urlparse

from app import db
from app.services.bot_chats import BotChatService
from app.services.input_sessions import InputSessionService

MODE_TEXT = 'broadcast_text'
MODE_LINK = 'broadcast_link'
MODE_CONFIRM = 'broadcast_confirm'

REPEAT_OPTIONS = {
    1: '1 раз',
    2: '2 раза',
    3: '3 раза',
    4: '4 раза',
}

INTERVAL_OPTIONS = {
    1: [0, 3, 6, 12, 24, 48, 72],
    2: [3, 6, 12, 24, 48, 72],
    3: [3, 6, 12, 24, 48, 72],
    4: [3, 6, 12, 24, 48, 72],
}

REPEAT_MULTIPLIERS = {1: 1.0, 2: 1.85, 3: 2.6, 4: 3.3}
FAST_SURCHARGE = {0: 0.0, 3: 0.12, 6: 0.08, 12: 0.04, 24: 0.0, 48: -0.03, 72: -0.05}


class AdBroadcastService:
    @staticmethod
    def list_repeat_options():
        return REPEAT_OPTIONS

    @staticmethod
    def list_interval_options(repeats: int):
        return INTERVAL_OPTIONS.get(int(repeats), [])

    @staticmethod
    def build_schedule_code(repeats: int, interval_hours: int) -> str:
        return f'{int(repeats)}x_{int(interval_hours)}h'

    @staticmethod
    def parse_schedule_code(schedule_code: str) -> tuple[int | None, int | None]:
        try:
            repeats_part, interval_part = str(schedule_code).split('_', 1)
            if not repeats_part.endswith('x') or not interval_part.endswith('h'):
                return None, None
            repeats = int(repeats_part[:-1])
            interval_hours = int(interval_part[:-1])
        except Exception:
            return None, None
        if repeats not in REPEAT_OPTIONS:
            return None, None
        if interval_hours not in INTERVAL_OPTIONS.get(repeats, []):
            return None, None
        return repeats, interval_hours

    @staticmethod
    def promotable_chat_count() -> int:
        return len(BotChatService.list_promotable_chats())

    @staticmethod
    def start_draft(user_id: int, *, is_admin: bool = False) -> tuple[bool, str]:
        if AdBroadcastService.promotable_chat_count() <= 0:
            return False, 'broadcast_no_chats'
        payload = {'is_admin': bool(is_admin)}
        InputSessionService.set_session(user_id, MODE_TEXT, json.dumps(payload, ensure_ascii=False))
        return True, 'broadcast_text_saved'

    @staticmethod
    def get_draft(user_id: int) -> dict:
        session = InputSessionService.get_session(user_id)
        if not session:
            return {}
        payload_raw = str(session['payload'] or '').strip()
        payload = {}
        if payload_raw:
            try:
                payload = json.loads(payload_raw)
            except json.JSONDecodeError:
                payload = {}
        payload['mode'] = str(session['mode'] or '')
        return payload

    @staticmethod
    def clear_draft(user_id: int) -> None:
        session = InputSessionService.get_session(user_id)
        if session and str(session['mode'] or '').startswith('broadcast_'):
            InputSessionService.clear_session(user_id)

    @staticmethod
    def get_mode(user_id: int) -> str | None:
        draft = AdBroadcastService.get_draft(user_id)
        return str(draft.get('mode') or '') or None

    @staticmethod
    def _save(user_id: int, mode: str, payload: dict) -> None:
        InputSessionService.set_session(user_id, mode, json.dumps(payload, ensure_ascii=False))

    @staticmethod
    def validate_text(raw_text: str) -> tuple[bool, str, str]:
        text = (raw_text or '').strip()
        if len(text) < 20 or len(text) > 700:
            return False, '', 'broadcast_text_invalid'
        lowered = text.lower()
        banned = ['казино', '18+', 'эрот', 'наркот', 'скам', 'обман']
        if any(token in lowered for token in banned):
            return False, '', 'broadcast_text_invalid'
        return True, text, 'broadcast_text_saved'

    @staticmethod
    def validate_link(raw_link: str) -> tuple[bool, str, str]:
        link = (raw_link or '').strip()
        if link.startswith('t.me/'):
            link = 'https://' + link
        if link.startswith('@'):
            link = 'https://t.me/' + link[1:]
        parsed = urlparse(link)
        if parsed.scheme not in {'http', 'https', 'tg'}:
            return False, '', 'broadcast_link_invalid'
        if parsed.scheme in {'http', 'https'} and not parsed.netloc:
            return False, '', 'broadcast_link_invalid'
        return True, link, 'broadcast_link_saved'

    @staticmethod
    def consume_text(user_id: int, raw_text: str) -> tuple[bool, str]:
        draft = AdBroadcastService.get_draft(user_id)
        if not draft or AdBroadcastService.get_mode(user_id) != MODE_TEXT:
            return False, 'broadcast_draft_missing'
        ok, text, key = AdBroadcastService.validate_text(raw_text)
        if not ok:
            return False, key
        draft['ad_text'] = text
        AdBroadcastService._save(user_id, MODE_LINK, draft)
        return True, key

    @staticmethod
    def consume_link(user_id: int, raw_link: str) -> tuple[bool, str]:
        draft = AdBroadcastService.get_draft(user_id)
        if not draft or AdBroadcastService.get_mode(user_id) != MODE_LINK:
            return False, 'broadcast_draft_missing'
        ok, link, key = AdBroadcastService.validate_link(raw_link)
        if not ok:
            return False, key
        draft['target_url'] = link
        AdBroadcastService._save(user_id, MODE_CONFIRM, draft)
        return True, key

    @staticmethod
    def set_repeat_count(user_id: int, repeats: int) -> tuple[bool, str]:
        draft = AdBroadcastService.get_draft(user_id)
        repeats = int(repeats)
        if not draft or repeats not in REPEAT_OPTIONS:
            return False, 'broadcast_draft_missing'
        draft['repeat_count'] = repeats
        draft.pop('interval_hours', None)
        AdBroadcastService._save(user_id, MODE_CONFIRM, draft)
        return True, 'broadcast_repeat_saved'

    @staticmethod
    def set_interval_hours(user_id: int, interval_hours: int) -> tuple[bool, str]:
        draft = AdBroadcastService.get_draft(user_id)
        repeats = int(draft.get('repeat_count') or 0) if draft else 0
        interval_hours = int(interval_hours)
        if not draft or repeats not in REPEAT_OPTIONS or interval_hours not in INTERVAL_OPTIONS.get(repeats, []):
            return False, 'broadcast_draft_missing'
        draft['interval_hours'] = interval_hours
        draft['schedule_code'] = AdBroadcastService.build_schedule_code(repeats, interval_hours)
        AdBroadcastService._save(user_id, MODE_CONFIRM, draft)
        return True, 'broadcast_schedule_saved'

    @staticmethod
    def price_for(schedule_code: str, chat_count: int) -> int:
        repeats, interval = AdBroadcastService.parse_schedule_code(schedule_code)
        if repeats is None or interval is None:
            return 0
        base_run = max(19, math.ceil(chat_count * 1.5))
        price = base_run * REPEAT_MULTIPLIERS.get(repeats, 1.0)
        price *= 1 + FAST_SURCHARGE.get(interval, 0.0)
        return max(19, math.ceil(price))

    @staticmethod
    def interval_label(interval_hours: int) -> str:
        interval_hours = int(interval_hours)
        mapping = {0: 'сразу', 3: 'через 3 часа', 6: 'через 6 часов', 12: 'через 12 часов', 24: 'через 1 день', 48: 'через 2 дня', 72: 'через 3 дня'}
        if interval_hours in mapping:
            return mapping[interval_hours]
        return f'через {interval_hours} ч.'

    @staticmethod
    def schedule_label(schedule_code: str) -> str:
        repeats, interval_hours = AdBroadcastService.parse_schedule_code(schedule_code)
        if repeats is None or interval_hours is None:
            return schedule_code
        if repeats == 1:
            if interval_hours == 0:
                return '1 раз сразу'
            return f'1 раз {AdBroadcastService.interval_label(interval_hours)}'
        interval_map = {3: 'каждые 3 часа', 6: 'каждые 6 часов', 12: 'каждые 12 часов', 24: 'раз в 1 день', 48: 'раз в 2 дня', 72: 'раз в 3 дня'}
        return f'{repeats} раза, интервал — {interval_map.get(interval_hours, f"каждые {interval_hours} ч.")}'

    @staticmethod
    def create_pending_order(user_id: int) -> tuple[bool, str, int | None]:
        draft = AdBroadcastService.get_draft(user_id)
        if not draft or AdBroadcastService.get_mode(user_id) != MODE_CONFIRM:
            return False, 'broadcast_draft_missing', None
        schedule_code = str(draft.get('schedule_code') or '')
        repeats, interval_hours = AdBroadcastService.parse_schedule_code(schedule_code)
        if repeats is None or interval_hours is None:
            return False, 'broadcast_schedule_missing', None
        chat_count = AdBroadcastService.promotable_chat_count()
        if chat_count <= 0:
            return False, 'broadcast_no_chats', None
        price = AdBroadcastService.price_for(schedule_code, chat_count)
        row_id = db.execute(
            '''
            INSERT INTO ad_broadcasts (
                creator_user_id, ad_text, target_url, schedule_code, interval_hours,
                repeats_total, sent_runs, next_run_at, stars_price, pay_required, is_admin, status
            ) VALUES (?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP, ?, 1, 0, 'awaiting_payment')
            ''',
            (
                user_id,
                str(draft.get('ad_text') or ''),
                str(draft.get('target_url') or ''),
                schedule_code,
                int(interval_hours),
                int(repeats),
                int(price),
            ),
        )
        return True, 'broadcast_invoice_created', row_id

    @staticmethod
    def create_admin_order(user_id: int) -> tuple[bool, str, int | None]:
        draft = AdBroadcastService.get_draft(user_id)
        if not draft or AdBroadcastService.get_mode(user_id) != MODE_CONFIRM:
            return False, 'broadcast_draft_missing', None
        schedule_code = str(draft.get('schedule_code') or '')
        repeats, interval_hours = AdBroadcastService.parse_schedule_code(schedule_code)
        if repeats is None or interval_hours is None:
            return False, 'broadcast_schedule_missing', None
        row_id = db.execute(
            '''
            INSERT INTO ad_broadcasts (
                creator_user_id, ad_text, target_url, schedule_code, interval_hours,
                repeats_total, sent_runs, next_run_at, stars_price, pay_required, is_admin, status
            ) VALUES (?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP, 0, 0, 1, 'active')
            ''',
            (
                user_id,
                str(draft.get('ad_text') or ''),
                str(draft.get('target_url') or ''),
                schedule_code,
                int(interval_hours),
                int(repeats),
            ),
        )
        return True, 'broadcast_admin_created', row_id

    @staticmethod
    def get_order(order_id: int):
        return db.fetch_one('SELECT * FROM ad_broadcasts WHERE id = ?', (order_id,))

    @staticmethod
    def activate_paid_order(order_id: int, user_id: int) -> tuple[bool, str]:
        row = AdBroadcastService.get_order(order_id)
        if not row or int(row['creator_user_id']) != int(user_id):
            return False, 'broadcast_not_found'
        if str(row['status']) != 'awaiting_payment':
            return False, 'broadcast_not_found'
        db.execute(
            '''UPDATE ad_broadcasts SET status = 'active', updated_at = CURRENT_TIMESTAMP, next_run_at = CURRENT_TIMESTAMP WHERE id = ?''',
            (order_id,),
        )
        return True, 'broadcast_paid_activated'

    @staticmethod
    def due_orders():
        return db.fetch_all(
            '''
            SELECT * FROM ad_broadcasts
            WHERE status = 'active'
              AND datetime(COALESCE(next_run_at, created_at)) <= datetime('now')
            ORDER BY datetime(COALESCE(next_run_at, created_at)) ASC, id ASC
            LIMIT 10
            '''
        )

    @staticmethod
    def compose_message(row, support_username: str = '@BoostoraBot') -> str:
        text = html.escape(str(row['ad_text'] or '').strip())
        link = html.escape(str(row['target_url'] or '').strip())
        support = html.escape((support_username or '@BoostoraBot').lstrip('@'))
        return (
            f"📣 <b>Реклама через Boostora</b>\n\n{text}\n\n"
            f"🔗 <a href=\"{link}\">Перейти</a>\n\n"
            f"<i>Запустить свою рекламу: @{support}</i>"
        )

    @staticmethod
    def dispatch_order(bot, order_id: int, support_username: str = '@BoostoraBot') -> tuple[int, int]:
        row = AdBroadcastService.get_order(order_id)
        if not row or str(row['status']) != 'active':
            return 0, 0
        sent = 0
        failed = 0
        text = AdBroadcastService.compose_message(row, support_username=support_username)
        for chat in BotChatService.list_promotable_chats():
            chat_ref = str(chat['chat_ref'])
            api_ref = int(chat_ref) if chat_ref.lstrip('-').isdigit() else chat_ref
            try:
                bot.send_message(api_ref, text, disable_web_page_preview=False)
                sent += 1
            except Exception:
                failed += 1
        next_sent_runs = int(row['sent_runs'] or 0) + 1
        repeats_total = int(row['repeats_total'] or 1)
        if next_sent_runs >= repeats_total:
            db.execute(
                '''UPDATE ad_broadcasts SET sent_runs = ?, last_run_at = CURRENT_TIMESTAMP, status = 'completed', next_run_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?''',
                (next_sent_runs, order_id),
            )
        else:
            interval_hours = int(row['interval_hours'] or 24)
            next_run = datetime.utcnow() + timedelta(hours=interval_hours)
            db.execute(
                '''UPDATE ad_broadcasts SET sent_runs = ?, last_run_at = CURRENT_TIMESTAMP, next_run_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?''',
                (next_sent_runs, next_run.isoformat(timespec='seconds'), order_id),
            )
        return sent, failed

    @staticmethod
    def run_due_orders(bot, support_username: str = '@BoostoraBot') -> int:
        total_sent = 0
        for row in AdBroadcastService.due_orders():
            sent, _failed = AdBroadcastService.dispatch_order(bot, int(row['id']), support_username=support_username)
            total_sent += sent
        return total_sent
