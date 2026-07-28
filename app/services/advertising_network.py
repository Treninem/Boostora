from __future__ import annotations

import html
import math
import re
import secrets
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from app import db
from app.services.bot_chats import BotChatService
from app.services.runtime_settings import RuntimeSettingsService
from app.services.wallets import WalletService
from app.config import settings


@dataclass(frozen=True)
class NetworkResult:
    ok: bool
    result_key: str
    data: Any = None


class AdvertisingNetworkService:
    """Budget-based Telegram advertising network with reciprocal protection.

    A user may connect several channels/chats. Every eligible connected platform
    automatically participates in the network. Campaigns are funded with
    internal credits; bonuses can cover at most the owner-configured cap (never
    above 50%). New participants are paired reciprocally so neither side receives
    a lasting placement without keeping the bot active on its own platform.
    """

    @staticmethod
    def _minimum_members() -> int:
        return RuntimeSettingsService.get_int('network_min_members')

    @staticmethod
    def _base_cost() -> int:
        return RuntimeSettingsService.get_int('network_base_placement_credits')

    @staticmethod
    def _max_bonus_percent() -> int:
        return RuntimeSettingsService.get_int('max_bonus_payment_percent')

    @staticmethod
    def _placement_hours() -> int:
        return RuntimeSettingsService.get_int('network_placement_hours')

    @staticmethod
    def _parse_db_time(value: str | None) -> datetime | None:
        raw = str(value or '').strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None

    @staticmethod
    def _clock_minutes(value: str, fallback: int) -> int:
        try:
            hour_text, minute_text = str(value or '').split(':', 1)
            hour, minute = int(hour_text), int(minute_text)
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour * 60 + minute
        except Exception:
            pass
        return fallback

    @staticmethod
    def _platform_availability(platform_row, now_utc: datetime | None = None) -> tuple[bool, str]:
        if not platform_row:
            return False, 'host_unavailable'
        if not int(platform_row['is_active'] or 0) or not int(platform_row['can_post'] or 0):
            return False, 'host_unavailable'
        if not int(platform_row['network_enabled'] or 0) or str(platform_row['network_status'] or '') != 'eligible':
            return False, 'host_not_eligible'
        now = now_utc or datetime.now(timezone.utc)
        offset = max(-720, min(840, int(platform_row['timezone_offset_minutes'] or 0)))
        local_now = now + timedelta(minutes=offset)
        start = AdvertisingNetworkService._clock_minutes(str(platform_row['window_start'] or ''), 9 * 60)
        end = AdvertisingNetworkService._clock_minutes(str(platform_row['window_end'] or ''), 22 * 60)
        current = local_now.hour * 60 + local_now.minute
        if start != end:
            in_window = (start <= current < end) if start < end else (current >= start or current < end)
            if not in_window:
                return False, 'outside_platform_schedule'

        local_day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        utc_day_start = local_day_start - timedelta(minutes=offset)
        utc_day_end = utc_day_start + timedelta(days=1)
        count_row = db.fetch_one(
            '''SELECT COUNT(*) AS cnt FROM network_placements
               WHERE host_chat_id=? AND published_at IS NOT NULL
                 AND datetime(published_at)>=datetime(?) AND datetime(published_at)<datetime(?)''',
            (int(platform_row['chat_id']), utc_day_start.strftime('%Y-%m-%d %H:%M:%S'), utc_day_end.strftime('%Y-%m-%d %H:%M:%S')),
        )
        if count_row and int(count_row['cnt'] or 0) >= max(1, int(platform_row['daily_limit'] or 1)):
            return False, 'platform_daily_limit_reached'
        last_row = db.fetch_one(
            '''SELECT MAX(published_at) AS last_published FROM network_placements
               WHERE host_chat_id=? AND published_at IS NOT NULL''',
            (int(platform_row['chat_id']),),
        )
        last_published = AdvertisingNetworkService._parse_db_time(str(last_row['last_published'] or '') if last_row else '')
        interval = max(1, int(platform_row['min_interval_hours'] or 1))
        if last_published and now < last_published + timedelta(hours=interval):
            return False, 'platform_interval_not_elapsed'
        return True, 'available'

    @staticmethod
    def _currently_available_platforms(owner_user_id: int) -> list[Any]:
        return [
            row for row in AdvertisingNetworkService._eligible_platforms(owner_user_id)
            if AdvertisingNetworkService._platform_availability(row)[0]
        ]

    @staticmethod
    def _normalize_target(raw: str) -> str | None:
        value = str(raw or '').strip()
        if value.startswith('@') and re.fullmatch(r'@[A-Za-z0-9_]{5,32}', value):
            return f'https://t.me/{value[1:]}'
        if value.lower().startswith(('t.me/', 'telegram.me/')):
            value = f'https://{value}'
        if re.fullmatch(r'https://(?:www\.)?(?:t\.me|telegram\.me)/[^\s]+', value, flags=re.I):
            return value
        return None

    @staticmethod
    def _resolve_user_target(user_id: int, *, target_url: str = '', target_chat_id: int | None = None):
        rows = BotChatService.list_user_network_chats(int(user_id))
        selected = None
        if target_chat_id:
            selected = next((row for row in rows if int(row['chat_id']) == int(target_chat_id)), None)
        else:
            normalized = AdvertisingNetworkService._normalize_target(target_url)
            if normalized:
                path = urlsplit(normalized).path.strip('/').split('/', 1)[0].lower()
                selected = next((row for row in rows if str(row['username'] or '').lower() == path), None)
        if not selected:
            return None
        if (str(selected['network_status'] or '') != 'eligible' or not int(selected['network_enabled'] or 0)
                or not int(selected['can_invite_users'] or 0)):
            return None
        public_url = BotChatService.chat_link(selected) or str(target_url or '').strip() or f"chat:{int(selected['chat_id'])}"
        return selected, public_url

    @staticmethod
    def _active_audience(row) -> int:
        members = max(0, int(row['member_count'] or 0))
        quality = max(20, min(100, int(row['quality_score'] or 50)))
        return max(0, int(members * (quality / 100.0)))

    @staticmethod
    def _history(chat_id: int) -> dict[str, float]:
        row = db.fetch_one(
            '''
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                   SUM(joins) AS joins,
                   SUM(retained_7d) AS retained,
                   MAX(COALESCE(published_at, created_at)) AS last_used
            FROM network_placements
            WHERE host_chat_id = ?
            ''',
            (int(chat_id),),
        )
        total = int(row['total'] or 0) if row else 0
        completed = int(row['completed'] or 0) if row else 0
        joins = int(row['joins'] or 0) if row else 0
        retained = int(row['retained'] or 0) if row else 0
        reliability = (completed / total) if total else 0.75
        retention = (retained / joins) if joins else 0.6
        return {
            'total': float(total),
            'reliability': max(0.35, min(1.0, reliability)),
            'retention': max(0.25, min(1.0, retention)),
            'last_used': str(row['last_used'] or '') if row else '',
        }

    @staticmethod
    def _topic_match(row, topic_code: str, language_code: str) -> float:
        platform_topic = str(row['topic_code'] or 'general')
        platform_language = str(row['language_code'] or 'ru')
        topic = str(topic_code or 'general')
        language = str(language_code or 'ru')
        if platform_language not in {language, 'all', 'any'}:
            return 0.0
        if platform_topic == topic:
            return 1.0
        if 'general' in {platform_topic, topic}:
            return 0.76
        return 0.58

    @staticmethod
    def _candidate(row, *, topic_code: str, language_code: str) -> dict[str, Any] | None:
        match = AdvertisingNetworkService._topic_match(row, topic_code, language_code)
        if match < 0.6:
            return None
        active = AdvertisingNetworkService._active_audience(row)
        if active < int(AdvertisingNetworkService._minimum_members() * 0.35):
            return None
        history = AdvertisingNetworkService._history(int(row['chat_id']))
        quality = max(0.55, min(1.35, int(row['quality_score'] or 50) / 70.0))
        audience_factor = max(0.5, math.sqrt(max(active, 1) / 300.0))
        reliability_factor = 0.7 + history['reliability'] * 0.3
        raw_cost = int(round(AdvertisingNetworkService._base_cost() * audience_factor * quality * reliability_factor * match))
        cost = max(max(1, AdvertisingNetworkService._base_cost() // 2), min(raw_cost, AdvertisingNetworkService._base_cost() * 25))
        expected_clicks = max(1, int(active * (0.008 + 0.012 * match) * quality))
        expected_joins = max(0, int(expected_clicks * (0.18 + 0.22 * match) * history['retention']))
        efficiency = (expected_joins + expected_clicks * 0.12) / max(cost, 1)
        rotation = 1.18 if not history['last_used'] else max(1.0, 1.08 - min(history['total'], 8.0) * 0.01)
        score = efficiency * 0.65 + match * 0.2 + history['reliability'] * 0.1 + rotation * 0.05
        return {
            'chat_id': int(row['chat_id']),
            'owner_user_id': int(row['owner_user_id'] or 0),
            'title': str(row['title'] or 'Площадка'),
            'chat_type': str(row['chat_type'] or ''),
            'members': int(row['member_count'] or 0),
            'active_audience': active,
            'quality': int(row['quality_score'] or 50),
            'match': match,
            'cost': cost,
            'expected_clicks': expected_clicks,
            'expected_joins': expected_joins,
            'score': score,
            'new_platform': history['total'] <= 0,
            'rotation_priority': rotation,
        }

    @staticmethod
    def _select(user_id: int, budget: int, *, topic_code: str, language_code: str) -> list[dict[str, Any]]:
        rows = BotChatService.list_network_eligible(exclude_owner_user_id=int(user_id), limit=2000)
        candidates = [
            candidate
            for row in rows
            if (candidate := AdvertisingNetworkService._candidate(row, topic_code=topic_code, language_code=language_code)) is not None
        ]
        if not candidates:
            return []

        best = sorted(candidates, key=lambda item: (item['score'], item['active_audience']), reverse=True)
        rotation = sorted(candidates, key=lambda item: (item['rotation_priority'], item['score']), reverse=True)
        testing = sorted((item for item in candidates if item['new_platform']), key=lambda item: item['score'], reverse=True)
        best_share, rotation_share, test_share = RuntimeSettingsService.normalized_network_shares()
        targets = [('best', best_share, best), ('rotation', rotation_share, rotation), ('test', test_share, testing)]
        selected: list[dict[str, Any]] = []
        used: set[int] = set()
        remaining = max(0, int(budget))

        for bucket, share, pool in targets:
            bucket_limit = max(0, int(budget * share))
            bucket_spent = 0
            for item in pool:
                if item['chat_id'] in used or item['cost'] > remaining:
                    continue
                if bucket_spent and bucket_spent + item['cost'] > bucket_limit:
                    continue
                chosen = dict(item)
                chosen['bucket'] = bucket
                selected.append(chosen)
                used.add(item['chat_id'])
                remaining -= item['cost']
                bucket_spent += item['cost']
                if remaining <= 0:
                    break

        for item in best:
            if item['chat_id'] in used or item['cost'] > remaining:
                continue
            chosen = dict(item)
            chosen['bucket'] = 'best_fill'
            selected.append(chosen)
            used.add(item['chat_id'])
            remaining -= item['cost']
        return selected

    @staticmethod
    def quote_budget(
        user_id: int,
        *,
        budget_credits: int,
        target_url: str = '',
        target_chat_id: int | None = None,
        topic_code: str = 'general',
        language_code: str = 'ru',
    ) -> NetworkResult:
        budget = int(budget_credits)
        minimum = AdvertisingNetworkService._base_cost()
        if budget < minimum:
            return NetworkResult(False, 'network_budget_too_low', data={'minimum': minimum})
        target = AdvertisingNetworkService._resolve_user_target(
            int(user_id), target_url=target_url, target_chat_id=target_chat_id
        )
        if not target:
            return NetworkResult(False, 'network_target_platform_required')
        target_platform, normalized_target = target
        platforms = BotChatService.list_user_network_chats(int(user_id))
        eligible_user_platforms = [row for row in platforms if str(row['network_status'] or '') == 'eligible' and bool(int(row['network_enabled'] or 0))]
        if not eligible_user_platforms:
            return NetworkResult(False, 'network_platform_required', data={'minimum_members': AdvertisingNetworkService._minimum_members()})
        selected = AdvertisingNetworkService._select(int(user_id), budget, topic_code=topic_code, language_code=language_code)
        if not selected:
            return NetworkResult(False, 'network_no_matching_platforms')
        spent = sum(int(item['cost']) for item in selected)
        reach = sum(int(item['active_audience']) for item in selected)
        clicks = sum(int(item['expected_clicks']) for item in selected)
        joins = sum(int(item['expected_joins']) for item in selected)
        return NetworkResult(
            True,
            'network_quote_ready',
            data={
                'budget_credits': budget,
                'estimated_spend': spent,
                'unused_budget': max(0, budget - spent),
                'platform_count': len(selected),
                'reach_min': int(reach * 0.55),
                'reach_max': int(reach * 1.05),
                'clicks_min': int(clicks * 0.55),
                'clicks_max': max(int(clicks * 1.35), clicks),
                'subscribers_min': int(joins * 0.5),
                'subscribers_max': max(int(joins * 1.45), joins),
                'estimated_days_min': 1,
                'estimated_days_max': max(2, math.ceil(len(selected) / 2)),
                'placements': selected,
                'target_url': normalized_target,
                'target_chat_id': int(target_platform['chat_id']),
                'target_title': str(target_platform['title'] or 'Площадка'),
                'topic_code': str(topic_code or 'general')[:48],
                'language_code': str(language_code or 'ru')[:8],
                'forecast_only': True,
            },
        )

    @staticmethod
    def create_campaign(
        user_id: int,
        *,
        budget_credits: int,
        target_url: str = '',
        target_chat_id: int | None = None,
        ad_text: str,
        topic_code: str = 'general',
        language_code: str = 'ru',
        title: str = '',
        expected_spend: int | None = None,
    ) -> NetworkResult:
        quote = AdvertisingNetworkService.quote_budget(
            int(user_id),
            budget_credits=int(budget_credits),
            target_url=target_url,
            target_chat_id=target_chat_id,
            topic_code=topic_code,
            language_code=language_code,
        )
        if not quote.ok:
            return quote
        q = quote.data
        actual_cost = int(q['estimated_spend'])
        if expected_spend is not None and int(expected_spend) != actual_cost:
            return NetworkResult(False, 'network_quote_changed', data=q)
        clean_text = str(ad_text or '').strip()
        if len(clean_text) < 10:
            return NetworkResult(False, 'network_ad_text_too_short')
        payment = WalletService.spend_with_bonus_cap(
            int(user_id),
            actual_cost,
            entry_type='network_campaign_purchase',
            note='Advertising network campaign',
            max_bonus_percent=AdvertisingNetworkService._max_bonus_percent(),
        )
        if not bool(payment.get('ok')):
            return NetworkResult(False, 'insufficient_internal_balance', data={'credit_cost': actual_cost, 'missing': int(payment.get('missing') or 0)})

        try:
            def _insert(connection):
                campaign_id = int(connection.execute(
                    '''
                    INSERT INTO network_campaigns (
                        owner_user_id, title, ad_text, target_url, target_chat_id, topic_code, language_code,
                        budget_credits, bonus_used, paid_credits,
                        predicted_reach_min, predicted_reach_max,
                        predicted_subscribers_min, predicted_subscribers_max,
                        contribution_units_required, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'awaiting_contribution')
                    ''',
                    (
                        int(user_id), str(title or '')[:120], clean_text[:2000], str(q['target_url'])[:255], int(q['target_chat_id']),
                        str(topic_code or 'general')[:48], str(language_code or 'ru')[:8], actual_cost,
                        int(payment.get('bonus_used') or 0), int(payment.get('credits_used') or 0),
                        int(q['reach_min']), int(q['reach_max']), int(q['subscribers_min']), int(q['subscribers_max']),
                        float(actual_cost / max(1, AdvertisingNetworkService._base_cost())),
                    ),
                ).lastrowid)
                for item in q['placements']:
                    connection.execute(
                        '''
                        INSERT INTO network_placements (
                            campaign_id, host_chat_id, host_owner_user_id, placement_cost_credits,
                            network_units, score, status
                        ) VALUES (?, ?, ?, ?, ?, ?, 'locked')
                        ''',
                        (
                            campaign_id, int(item['chat_id']), int(item['owner_user_id'] or 0) or None,
                            int(item['cost']), float(item['cost'] / max(1, AdvertisingNetworkService._base_cost())),
                            float(item['score']),
                        ),
                    )
                return campaign_id
            campaign_id = db.run_in_transaction(_insert)
        except Exception:
            WalletService.refund_split(
                int(user_id),
                credits=int(payment.get('credits_used') or 0),
                bonus=int(payment.get('bonus_used') or 0),
                entry_type='network_campaign_create_refund',
                note='Campaign record could not be created',
            )
            raise
        return NetworkResult(True, 'network_campaign_created', data={
            'campaign_id': campaign_id,
            **q,
            'bonus_used': int(payment.get('bonus_used') or 0),
            'credits_used': int(payment.get('credits_used') or 0),
        })

    @staticmethod
    def _available_contribution_units(user_id: int) -> float:
        row = db.fetch_one(
            'SELECT COALESCE(SUM(units), 0) AS units FROM network_contribution_ledger WHERE user_id = ?',
            (int(user_id),),
        )
        return float(row['units'] or 0) if row else 0.0

    @staticmethod
    def _log_contribution(
        user_id: int,
        units: float,
        *,
        entry_type: str,
        placement_id: int | None = None,
        campaign_id: int | None = None,
        reason: str = '',
    ) -> None:
        db.execute(
            '''INSERT INTO network_contribution_ledger
               (user_id, placement_id, campaign_id, units, entry_type, reason)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (int(user_id), placement_id, campaign_id, float(units), str(entry_type)[:64], str(reason)[:255]),
        )

    @staticmethod
    def _bonus_multiplier(owner_user_id: int) -> float:
        eligible_count = len([
            row for row in BotChatService.list_user_network_chats(int(owner_user_id))
            if str(row['network_status'] or '') == 'eligible' and int(row['network_enabled'] or 0)
        ])
        platform_multiplier = 1.0 if eligible_count <= 1 else (1.05 if eligible_count <= 3 else (1.10 if eligible_count <= 6 else 1.15))
        row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM network_placements WHERE host_owner_user_id = ? AND status = 'completed'",
            (int(owner_user_id),),
        )
        completed = int(row['cnt'] or 0) if row else 0
        level_multiplier = 1.0 if completed < 5 else (1.10 if completed < 20 else (1.20 if completed < 50 else 1.30))
        return min(1.40, platform_multiplier * level_multiplier)

    @staticmethod
    def _tracking_origin() -> str:
        raw = str(settings.mini_app_url or '').strip()
        if not raw:
            return ''
        parsed = urlsplit(raw)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            return ''
        return f'{parsed.scheme}://{parsed.netloc}'

    @staticmethod
    def _prepare_tracking_link(bot, placement_row, campaign_row) -> str:  # noqa: ANN001
        existing_token = str(placement_row['tracking_token'] or '')
        existing_invite = str(placement_row['invite_link'] or '')
        if existing_token and existing_invite:
            origin = AdvertisingNetworkService._tracking_origin()
            return f'{origin}/r/{existing_token}' if origin else existing_invite
        target_chat_id = int(campaign_row['target_chat_id'] or 0)
        if not target_chat_id:
            raise RuntimeError('target_platform_not_connected')
        invite = bot.create_chat_invite_link(
            target_chat_id,
            name=f'Boostora {int(campaign_row["campaign_id"])}-{int(placement_row["id"])}'[:32],
            creates_join_request=False,
        )
        invite_link = str(getattr(invite, 'invite_link', '') or '')
        if not invite_link:
            raise RuntimeError('target_invite_link_unavailable')
        token = secrets.token_urlsafe(18)
        db.execute(
            '''UPDATE network_placements SET tracking_token=?, invite_link=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?''',
            (token, invite_link[:512], int(placement_row['id'])),
        )
        origin = AdvertisingNetworkService._tracking_origin()
        return f'{origin}/r/{token}' if origin else invite_link

    @staticmethod
    def resolve_tracking_click(token: str) -> str | None:
        clean = str(token or '').strip()[:128]
        if not clean:
            return None
        row = db.fetch_one(
            '''SELECT id, invite_link FROM network_placements
               WHERE tracking_token=? AND status='published'
                 AND (expires_at IS NULL OR datetime(expires_at)>CURRENT_TIMESTAMP)''',
            (clean,),
        )
        if not row or not str(row['invite_link'] or ''):
            return None
        db.execute(
            '''UPDATE network_placements SET clicks=clicks+1, updated_at=CURRENT_TIMESTAMP
               WHERE id=? AND status='published' ''',
            (int(row['id']),),
        )
        return str(row['invite_link'])

    @staticmethod
    def track_join(update) -> bool:  # noqa: ANN001
        chat = getattr(update, 'chat', None)
        new_member = getattr(update, 'new_chat_member', None)
        if not chat or not new_member:
            return False
        member_user = getattr(new_member, 'user', None)
        if not member_user:
            return False
        user_id = int(getattr(member_user, 'id', 0) or 0)
        if user_id <= 0 or bool(getattr(member_user, 'is_bot', False)):
            return False
        status = str(getattr(new_member, 'status', '') or '')
        if status in {'left', 'kicked'}:
            db.execute(
                '''UPDATE network_join_events SET left_at=COALESCE(left_at, CURRENT_TIMESTAMP)
                   WHERE target_chat_id=? AND user_id=? AND left_at IS NULL''',
                (int(chat.id), user_id),
            )
            return False
        if status not in {'member', 'administrator', 'creator', 'restricted'}:
            return False
        invite_obj = getattr(update, 'invite_link', None)
        invite_link = str(getattr(invite_obj, 'invite_link', '') or '')
        if not invite_link:
            return False
        placement = db.fetch_one(
            '''SELECT p.id, p.campaign_id, c.target_chat_id
               FROM network_placements p JOIN network_campaigns c ON c.id=p.campaign_id
               WHERE p.invite_link=? AND p.status='published'
                 AND (p.expires_at IS NULL OR datetime(p.expires_at)>CURRENT_TIMESTAMP)''',
            (invite_link,),
        )
        if not placement or int(placement['target_chat_id'] or 0) != int(chat.id):
            return False
        def _insert(connection):
            cursor = connection.execute(
                '''INSERT OR IGNORE INTO network_join_events
                   (placement_id, campaign_id, target_chat_id, user_id) VALUES (?, ?, ?, ?)''',
                (int(placement['id']), int(placement['campaign_id']), int(chat.id), user_id),
            )
            if int(cursor.rowcount or 0) > 0:
                connection.execute('UPDATE network_placements SET joins=joins+1, updated_at=CURRENT_TIMESTAMP WHERE id=?', (int(placement['id']),))
                return True
            return False
        return bool(db.run_in_transaction(_insert))

    @staticmethod
    def refresh_join_retention(bot, limit: int = 100) -> dict[str, int]:  # noqa: ANN001
        rows = db.fetch_all(
            '''SELECT * FROM network_join_events
               WHERE (checked_24h_at IS NULL AND datetime(joined_at)<=datetime('now','-24 hours'))
                  OR (checked_7d_at IS NULL AND datetime(joined_at)<=datetime('now','-7 days'))
               ORDER BY joined_at ASC LIMIT ?''',
            (max(1, min(int(limit), 500)),),
        )
        checked_24h = checked_7d = 0
        for row in rows:
            active = False
            try:
                member = bot.get_chat_member(int(row['target_chat_id']), int(row['user_id']))
                active = str(getattr(member, 'status', '') or '') not in {'left', 'kicked'}
            except Exception:
                continue
            if not str(row['checked_24h_at'] or ''):
                db.execute(
                    '''UPDATE network_join_events SET retained_24h=?, checked_24h_at=CURRENT_TIMESTAMP,
                           left_at=CASE WHEN ?=0 THEN COALESCE(left_at,CURRENT_TIMESTAMP) ELSE left_at END WHERE id=?''',
                    (1 if active else 0, 1 if active else 0, int(row['id'])),
                )
                if active:
                    db.execute('UPDATE network_placements SET retained_24h=retained_24h+1 WHERE id=?', (int(row['placement_id']),))
                checked_24h += 1
            if not str(row['checked_7d_at'] or '') and AdvertisingNetworkService._parse_db_time(str(row['joined_at'])) and datetime.now(timezone.utc) >= AdvertisingNetworkService._parse_db_time(str(row['joined_at'])) + timedelta(days=7):
                db.execute(
                    '''UPDATE network_join_events SET retained_7d=?, checked_7d_at=CURRENT_TIMESTAMP,
                           left_at=CASE WHEN ?=0 THEN COALESCE(left_at,CURRENT_TIMESTAMP) ELSE left_at END WHERE id=?''',
                    (1 if active else 0, 1 if active else 0, int(row['id'])),
                )
                if active:
                    db.execute('UPDATE network_placements SET retained_7d=retained_7d+1 WHERE id=?', (int(row['placement_id']),))
                checked_7d += 1
        return {'checked_24h': checked_24h, 'checked_7d': checked_7d}

    @staticmethod
    def _message_text(campaign_row) -> str:
        title = html.escape(str(campaign_row['title'] or 'Рекомендация'))
        body = html.escape(str(campaign_row['ad_text'] or '').strip())
        return f'<b>{title}</b>\n\n{body}\n\nРекламное размещение через Boostora'

    @staticmethod
    def _send(bot, placement_row, campaign_row) -> int:  # noqa: ANN001
        tracking_url = AdvertisingNetworkService._prepare_tracking_link(bot, placement_row, campaign_row)
        try:
            from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton('Открыть', url=tracking_url))
        except Exception as exc:
            raise RuntimeError('advertising_button_unavailable') from exc
        message = bot.send_message(
            int(placement_row['host_chat_id']),
            AdvertisingNetworkService._message_text(campaign_row),
            reply_markup=markup,
            disable_web_page_preview=False,
        )
        return int(getattr(message, 'message_id', 0) or 0)

    @staticmethod
    def _publish(bot, placement_id: int, *, consume_units: bool, reciprocal_id: int | None = None) -> bool:  # noqa: ANN001
        row = db.fetch_one(
            '''SELECT p.*, c.owner_user_id AS campaign_owner_user_id, c.title, c.ad_text, c.target_url, c.target_chat_id,
                      c.status AS campaign_status
               FROM network_placements p JOIN network_campaigns c ON c.id=p.campaign_id
               WHERE p.id=?''',
            (int(placement_id),),
        )
        if not row or str(row['status']) != 'locked':
            return False
        platform = db.fetch_one('SELECT * FROM bot_chats WHERE chat_id = ?', (int(row['host_chat_id']),))
        available, availability_reason = AdvertisingNetworkService._platform_availability(platform)
        if not available:
            if availability_reason in {'host_unavailable', 'host_not_eligible'}:
                db.execute("UPDATE network_placements SET status='failed', last_error=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (availability_reason, int(placement_id)))
            else:
                db.execute("UPDATE network_placements SET last_error=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='locked'", (availability_reason, int(placement_id)))
            return False
        units = float(row['network_units'] or 0)
        owner_id = int(row['campaign_owner_user_id'])
        if consume_units and AdvertisingNetworkService._available_contribution_units(owner_id) + 1e-9 < units:
            return False
        db.execute("UPDATE network_placements SET status='publishing', updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='locked'", (int(placement_id),))
        try:
            message_id = AdvertisingNetworkService._send(bot, row, row)
        except Exception as exc:
            db.execute(
                "UPDATE network_placements SET status='locked', last_error=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (str(exc)[:300], int(placement_id)),
            )
            return False
        if consume_units:
            AdvertisingNetworkService._log_contribution(
                owner_id,
                -units,
                entry_type='campaign_placement_reserved',
                placement_id=int(placement_id),
                campaign_id=int(row['campaign_id']),
                reason='Own advertising placement opened',
            )
        db.execute(
            '''UPDATE network_placements
               SET status='published', message_id=?, scheduled_at=COALESCE(scheduled_at, CURRENT_TIMESTAMP), published_at=CURRENT_TIMESTAMP,
                   expires_at=datetime('now', ?), reciprocal_placement_id=?,
                   contribution_reserved=?, last_error=NULL, updated_at=CURRENT_TIMESTAMP
               WHERE id=?''',
            (message_id, f'+{AdvertisingNetworkService._placement_hours()} hours', reciprocal_id,
             units if consume_units else 0.0, int(placement_id)),
        )
        db.execute(
            "UPDATE network_campaigns SET status='active', updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (int(row['campaign_id']),),
        )
        return True

    @staticmethod
    def _eligible_platforms(owner_user_id: int) -> list[Any]:
        return [
            row for row in BotChatService.list_user_network_chats(int(owner_user_id))
            if str(row['network_status'] or '') == 'eligible' and int(row['network_enabled'] or 0)
        ]

    @staticmethod
    def _replace_host_for_pair(placement_row, host_row, campaign_row) -> bool:
        candidate = AdvertisingNetworkService._candidate(
            host_row,
            topic_code=str(campaign_row['topic_code'] or 'general'),
            language_code=str(campaign_row['language_code'] or 'ru'),
        )
        if not candidate:
            return False
        old_cost = int(placement_row['placement_cost_credits'] or 0)
        new_cost = int(candidate['cost'])
        if old_cost <= 0 or not (old_cost * 0.65 <= new_cost <= old_cost * 1.35):
            return False
        db.execute(
            '''UPDATE network_placements
               SET host_chat_id=?, host_owner_user_id=?, placement_cost_credits=?,
                   network_units=?, score=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=? AND status='locked' ''',
            (
                int(host_row['chat_id']), int(host_row['owner_user_id'] or 0) or None,
                new_cost, float(new_cost / max(1, AdvertisingNetworkService._base_cost())),
                float(candidate['score']), int(placement_row['id']),
            ),
        )
        return True

    @staticmethod
    def _pair_waiting_campaigns(bot, limit: int = 10) -> int:  # noqa: ANN001
        rows = db.fetch_all(
            '''SELECT c.* FROM network_campaigns c
               WHERE c.status IN ('awaiting_contribution','active')
                 AND EXISTS (SELECT 1 FROM network_placements p WHERE p.campaign_id=c.id AND p.status='locked')
               ORDER BY c.created_at ASC LIMIT ?''',
            (max(2, int(limit) * 2),),
        )
        paired = 0
        used_campaigns: set[int] = set()
        for left in rows:
            left_id = int(left['id'])
            left_owner = int(left['owner_user_id'])
            if left_id in used_campaigns or AdvertisingNetworkService._available_contribution_units(left_owner) > 0:
                continue
            left_platforms = AdvertisingNetworkService._currently_available_platforms(left_owner)
            if not left_platforms:
                continue
            left_placement = db.fetch_one("SELECT * FROM network_placements WHERE campaign_id=? AND status='locked' ORDER BY score DESC LIMIT 1", (left_id,))
            if not left_placement:
                continue
            for right in rows:
                right_id = int(right['id'])
                right_owner = int(right['owner_user_id'])
                if right_id == left_id or right_id in used_campaigns or right_owner == left_owner:
                    continue
                if AdvertisingNetworkService._available_contribution_units(right_owner) > 0:
                    continue
                right_platforms = AdvertisingNetworkService._currently_available_platforms(right_owner)
                if not right_platforms:
                    continue
                right_placement = db.fetch_one("SELECT * FROM network_placements WHERE campaign_id=? AND status='locked' ORDER BY score DESC LIMIT 1", (right_id,))
                if not right_placement:
                    continue
                left_host = next((p for p in right_platforms if AdvertisingNetworkService._candidate(p, topic_code=str(left['topic_code']), language_code=str(left['language_code']))), None)
                right_host = next((p for p in left_platforms if AdvertisingNetworkService._candidate(p, topic_code=str(right['topic_code']), language_code=str(right['language_code']))), None)
                if not left_host or not right_host:
                    continue
                if not AdvertisingNetworkService._replace_host_for_pair(left_placement, left_host, left):
                    continue
                if not AdvertisingNetworkService._replace_host_for_pair(right_placement, right_host, right):
                    continue
                left_pid = int(left_placement['id'])
                right_pid = int(right_placement['id'])
                if not AdvertisingNetworkService._publish(bot, left_pid, consume_units=False, reciprocal_id=right_pid):
                    continue
                if not AdvertisingNetworkService._publish(bot, right_pid, consume_units=False, reciprocal_id=left_pid):
                    first = db.fetch_one('SELECT host_chat_id, message_id FROM network_placements WHERE id=?', (left_pid,))
                    if first and int(first['message_id'] or 0):
                        try:
                            bot.delete_message(int(first['host_chat_id']), int(first['message_id']))
                        except Exception:
                            pass
                    db.execute("UPDATE network_placements SET status='locked', message_id=NULL, published_at=NULL, expires_at=NULL, reciprocal_placement_id=NULL WHERE id=?", (left_pid,))
                    continue
                used_campaigns.update({left_id, right_id})
                paired += 2
                break
            if paired >= limit:
                break
        return paired

    @staticmethod
    def _publish_with_contribution(bot, limit: int = 20) -> int:  # noqa: ANN001
        published = 0
        campaigns = db.fetch_all(
            '''SELECT * FROM network_campaigns
               WHERE status IN ('awaiting_contribution','active')
               ORDER BY created_at ASC LIMIT 100'''
        )
        for campaign in campaigns:
            owner_id = int(campaign['owner_user_id'])
            available = AdvertisingNetworkService._available_contribution_units(owner_id)
            if available <= 0:
                continue
            placements = db.fetch_all(
                "SELECT * FROM network_placements WHERE campaign_id=? AND status='locked' AND network_units<=? ORDER BY score DESC LIMIT 50",
                (int(campaign['id']), float(available) + 1e-9),
            )
            placement = None
            for candidate_placement in placements:
                platform = db.fetch_one('SELECT * FROM bot_chats WHERE chat_id=?', (int(candidate_placement['host_chat_id']),))
                if AdvertisingNetworkService._platform_availability(platform)[0]:
                    placement = candidate_placement
                    break
            if placement and AdvertisingNetworkService._publish(bot, int(placement['id']), consume_units=True):
                published += 1
                if published >= limit:
                    break
        return published

    @staticmethod
    def _refund_failed_placement(placement_row, *, reason: str) -> None:
        fresh = db.fetch_one('SELECT * FROM network_placements WHERE id=?', (int(placement_row['id']),))
        if not fresh or str(fresh['refunded_at'] or ''):
            return
        campaign = db.fetch_one('SELECT * FROM network_campaigns WHERE id=?', (int(fresh['campaign_id']),))
        if not campaign:
            return
        placement_row = fresh
        total = max(1, int(campaign['budget_credits'] or 0))
        cost = max(0, int(placement_row['placement_cost_credits'] or 0))
        bonus_ratio = max(0.0, min(1.0, int(campaign['bonus_used'] or 0) / total))
        bonus = min(cost, int(round(cost * bonus_ratio)))
        credits = max(0, cost - bonus)
        WalletService.refund_split(
            int(campaign['owner_user_id']),
            credits=credits,
            bonus=bonus,
            entry_type='network_failed_placement_refund',
            note=f'Placement #{int(placement_row["id"])}: {reason}',
        )
        db.execute(
            '''UPDATE network_campaigns SET refunded_credits=refunded_credits+?,
                   refunded_bonus=refunded_bonus+?, updated_at=CURRENT_TIMESTAMP WHERE id=?''',
            (credits, bonus, int(campaign['id'])),
        )
        db.execute(
            '''UPDATE network_placements SET refunded_credits=?, refunded_bonus=?,
                   refunded_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=? AND refunded_at IS NULL''',
            (credits, bonus, int(placement_row['id'])),
        )

    @staticmethod
    def _apply_contribution_progress(owner_user_id: int, units: float) -> None:
        remaining_units = max(0.0, float(units))
        while remaining_units > 1e-9:
            campaign = db.fetch_one(
                '''SELECT id, contribution_units_required, contribution_units_completed
                   FROM network_campaigns
                   WHERE owner_user_id=? AND status IN ('awaiting_contribution','active')
                     AND contribution_units_completed < contribution_units_required
                   ORDER BY created_at ASC, id ASC LIMIT 1''',
                (int(owner_user_id),),
            )
            if not campaign:
                break
            gap = max(0.0, float(campaign['contribution_units_required'] or 0) - float(campaign['contribution_units_completed'] or 0))
            applied = min(gap, remaining_units)
            if applied <= 0:
                break
            db.execute(
                '''UPDATE network_campaigns SET contribution_units_completed=MIN(contribution_units_required, contribution_units_completed+?),
                       updated_at=CURRENT_TIMESTAMP WHERE id=?''',
                (applied, int(campaign['id'])),
            )
            remaining_units -= applied

    @staticmethod
    def _complete_one(placement_row) -> bool:
        platform = db.fetch_one('SELECT * FROM bot_chats WHERE chat_id=?', (int(placement_row['host_chat_id']),))
        if not platform or not int(platform['is_active'] or 0) or not int(platform['can_post'] or 0):
            return False
        owner_id = int(placement_row['host_owner_user_id'] or 0)
        campaign = db.fetch_one('SELECT * FROM network_campaigns WHERE id=?', (int(placement_row['campaign_id']),))
        if not campaign:
            return False
        units = float(placement_row['network_units'] or 0)
        db.execute(
            "UPDATE network_placements SET status='completed', completed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='published'",
            (int(placement_row['id']),),
        )
        if owner_id > 0:
            AdvertisingNetworkService._log_contribution(
                owner_id, units, entry_type='host_placement_completed',
                placement_id=int(placement_row['id']), campaign_id=int(campaign['id']),
                reason='Advertising placement completed on own platform',
            )
            bonus_rate = RuntimeSettingsService.get_int('network_bonus_percent') / 100.0
            value = max(1, int(round(int(placement_row['placement_cost_credits'] or 0) * bonus_rate * AdvertisingNetworkService._bonus_multiplier(owner_id))))
            WalletService.credit_bonus_balance(owner_id, value, entry_type='network_placement_bonus', note=f'Placement #{int(placement_row["id"])} completed')
            db.execute(
                '''INSERT INTO network_bonus_ledger (user_id, placement_id, amount, status, reason)
                   VALUES (?, ?, ?, 'earned', 'completed_network_placement')''',
                (owner_id, int(placement_row['id']), value),
            )
        if not float(placement_row['contribution_reserved'] or 0):
            AdvertisingNetworkService._log_contribution(
                int(campaign['owner_user_id']), -units,
                entry_type='reciprocal_campaign_placement', placement_id=int(placement_row['id']),
                campaign_id=int(campaign['id']), reason='Reciprocal placement completed',
            )
        if owner_id > 0:
            AdvertisingNetworkService._apply_contribution_progress(owner_id, units)
        remaining = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM network_placements WHERE campaign_id=? AND status IN ('locked','publishing','published')",
            (int(campaign['id']),),
        )
        if remaining and int(remaining['cnt'] or 0) == 0:
            db.execute("UPDATE network_campaigns SET status='completed', updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(campaign['id']),))
        return True

    @staticmethod
    def _complete_due(limit: int = 100) -> int:
        rows = db.fetch_all(
            '''SELECT * FROM network_placements WHERE status='published'
               AND expires_at IS NOT NULL AND datetime(expires_at)<=CURRENT_TIMESTAMP
               ORDER BY expires_at ASC LIMIT ?''',
            (max(1, min(int(limit), 500)),),
        )
        completed = 0
        for row in rows:
            if AdvertisingNetworkService._complete_one(row):
                completed += 1
            else:
                db.execute(
                    "UPDATE network_placements SET status='failed', last_error='host_access_lost', revoked_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (int(row['id']),),
                )
                AdvertisingNetworkService._refund_failed_placement(row, reason='Площадка перестала быть доступна')
        return completed

    @staticmethod
    def run_due_placements(bot) -> dict[str, int]:  # noqa: ANN001
        retention = AdvertisingNetworkService.refresh_join_retention(bot)
        completed = AdvertisingNetworkService._complete_due()
        published = AdvertisingNetworkService._publish_with_contribution(bot)
        paired = AdvertisingNetworkService._pair_waiting_campaigns(bot)
        return {'completed': completed, 'published': published, 'paired': paired, **retention}

    @staticmethod
    def handle_platform_deactivated(bot, chat_id: int) -> int:  # noqa: ANN001
        rows = db.fetch_all(
            "SELECT * FROM network_placements WHERE host_chat_id=? AND status IN ('publishing','published')",
            (int(chat_id),),
        )
        affected = 0
        platform = db.fetch_one('SELECT owner_user_id FROM bot_chats WHERE chat_id=?', (int(chat_id),))
        violating_owner = int(platform['owner_user_id'] or 0) if platform else 0
        for row in rows:
            db.execute(
                "UPDATE network_placements SET status='failed', last_error='host_removed_bot', revoked_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (int(row['id']),),
            )
            AdvertisingNetworkService._refund_failed_placement(row, reason='Владелец площадки удалил бота или снял права')
            reciprocal_id = int(row['reciprocal_placement_id'] or 0)
            if reciprocal_id:
                reciprocal = db.fetch_one('SELECT * FROM network_placements WHERE id=?', (reciprocal_id,))
                if reciprocal and str(reciprocal['status']) in {'publishing', 'published'}:
                    if int(reciprocal['message_id'] or 0):
                        try:
                            bot.delete_message(int(reciprocal['host_chat_id']), int(reciprocal['message_id']))
                        except Exception:
                            pass
                    db.execute(
                        "UPDATE network_placements SET status='revoked', last_error='reciprocal_host_violation', revoked_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (reciprocal_id,),
                    )
                    # The violating owner does not receive a refund for the ad
                    # removed as a consequence of their own platform violation.
            affected += 1
        if violating_owner > 0 and not AdvertisingNetworkService._eligible_platforms(violating_owner):
            db.execute(
                "UPDATE network_campaigns SET status='paused_platform_required', updated_at=CURRENT_TIMESTAMP WHERE owner_user_id=? AND status IN ('awaiting_contribution','active')",
                (violating_owner,),
            )
        return affected

    @staticmethod
    def user_summary(user_id: int) -> dict[str, Any]:
        platforms = BotChatService.list_user_network_chats(int(user_id))
        campaigns = db.fetch_all(
            '''SELECT c.*,
                      COALESCE(SUM(p.clicks),0) AS clicks,
                      COALESCE(SUM(p.joins),0) AS joins,
                      COALESCE(SUM(p.retained_24h),0) AS retained_24h,
                      COALESCE(SUM(p.retained_7d),0) AS retained_7d,
                      SUM(CASE WHEN p.status='completed' THEN 1 ELSE 0 END) AS completed_placements,
                      COUNT(p.id) AS total_placements
               FROM network_campaigns c LEFT JOIN network_placements p ON p.campaign_id=c.id
               WHERE c.owner_user_id=? GROUP BY c.id ORDER BY c.id DESC LIMIT 50''',
            (int(user_id),),
        )
        contribution = db.fetch_one(
            '''SELECT COALESCE(SUM(units), 0) AS units FROM network_contribution_ledger WHERE user_id = ?''',
            (int(user_id),),
        )
        completed = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM network_placements WHERE host_owner_user_id=? AND status='completed'",
            (int(user_id),),
        )
        return {
            'platforms': [dict(row) for row in platforms],
            'campaigns': [dict(row) for row in campaigns],
            'contribution_units': float(contribution['units'] or 0) if contribution else 0.0,
            'completed_host_placements': int(completed['cnt'] or 0) if completed else 0,
            'minimum_members': AdvertisingNetworkService._minimum_members(),
            'max_platforms': RuntimeSettingsService.get_int('network_max_platforms_per_user'),
            'base_placement_credits': AdvertisingNetworkService._base_cost(),
            'max_bonus_percent': AdvertisingNetworkService._max_bonus_percent(),
            'placement_hours': AdvertisingNetworkService._placement_hours(),
        }

    @staticmethod
    def complete_host_placement(placement_id: int) -> NetworkResult:
        row = db.fetch_one('SELECT * FROM network_placements WHERE id = ?', (int(placement_id),))
        if not row:
            return NetworkResult(False, 'network_placement_not_found')
        if str(row['status'] or '') == 'completed':
            return NetworkResult(True, 'network_placement_already_completed')
        if str(row['status'] or '') != 'published':
            return NetworkResult(False, 'network_placement_not_ready')
        if not AdvertisingNetworkService._complete_one(row):
            return NetworkResult(False, 'network_platform_unavailable')
        return NetworkResult(True, 'network_placement_completed')
