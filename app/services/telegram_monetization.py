from __future__ import annotations

import requests

from app.config import settings


class TelegramMonetizationService:
    @staticmethod
    def _call(method: str, payload: dict | None = None) -> tuple[bool, dict | list | bool | None]:
        token = (settings.bot_token or '').strip()
        if not token:
            return False, {'description': 'BOT_TOKEN is empty'}
        url = f'https://api.telegram.org/bot{token}/{method}'
        try:
            response = requests.post(url, json=payload or {}, timeout=30)
            data = response.json()
        except Exception as exc:
            return False, {'description': str(exc)}
        if not isinstance(data, dict) or not data.get('ok'):
            return False, data
        return True, data.get('result')

    @staticmethod
    def get_available_gifts() -> list[dict]:
        ok, result = TelegramMonetizationService._call('getAvailableGifts', {})
        if not ok or not isinstance(result, dict):
            return []
        gifts = result.get('gifts') or []
        if not isinstance(gifts, list):
            return []
        normalized = []
        for gift in gifts:
            if not isinstance(gift, dict):
                continue
            sticker = gift.get('sticker') or {}
            normalized.append({
                'id': str(gift.get('id') or ''),
                'star_count': int(gift.get('star_count') or 0),
                'emoji': str(sticker.get('emoji') or '🎁'),
                'limited': bool(gift.get('total_count')),
                'is_premium_only': bool(gift.get('is_premium')),
            })
        normalized.sort(key=lambda item: (item['star_count'], item['id']))
        return normalized

    @staticmethod
    def send_gift(*, user_id: int, gift_id: str, text: str | None = None) -> tuple[bool, str]:
        payload = {'user_id': int(user_id), 'gift_id': str(gift_id)}
        if text:
            payload['text'] = text[:128]
        ok, result = TelegramMonetizationService._call('sendGift', payload)
        if ok:
            return True, 'gift_sent'
        return False, str((result or {}).get('description') or 'sendGift failed')

    @staticmethod
    def gift_premium(*, user_id: int, month_count: int, text: str | None = None) -> tuple[bool, str]:
        star_map = {3: 1000, 6: 1500, 12: 2500}
        if month_count not in star_map:
            return False, 'invalid premium month_count'
        payload = {
            'user_id': int(user_id),
            'month_count': int(month_count),
            'star_count': int(star_map[month_count]),
        }
        if text:
            payload['text'] = text[:128]
        ok, result = TelegramMonetizationService._call('giftPremiumSubscription', payload)
        if ok:
            return True, 'premium_sent'
        return False, str((result or {}).get('description') or 'giftPremiumSubscription failed')
