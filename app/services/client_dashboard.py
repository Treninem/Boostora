import json
import sqlite3
from datetime import datetime
from typing import Any

from app.time_utils import utcnow
from app import db
from app.services.economy import calculate_campaign_pricing


BOOST_LEVELS = {
    'recommended': 'recommended_unit_price',
    'fast': 'fast_unit_price',
    'priority': 'priority_unit_price',
}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except Exception:
        return default


def pricing_snapshot(row) -> dict[str, Any]:
    raw = ''
    try:
        raw = str(row['pricing_json'] or '')
    except Exception:
        raw = ''
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def campaign_progress(row) -> dict[str, int]:
    total = max(_as_int(row['total_quantity']), 0)
    completed = max(_as_int(row['completed_quantity']), 0)
    rejected = max(_as_int(row['rejected_quantity']), 0)
    reserved = max(_as_int(row['budget_reserved']), 0)
    remaining_quantity = max(total - completed - rejected, 0)
    progress_percent = round(completed * 100 / total) if total else 0
    reject_percent = round(rejected * 100 / max(completed + rejected, 1)) if (completed or rejected) else 0
    return {
        'total': total,
        'completed': completed,
        'rejected': rejected,
        'reserved_budget': reserved,
        'remaining_quantity': remaining_quantity,
        'progress_percent': max(0, min(100, progress_percent)),
        'reject_percent': max(0, min(100, reject_percent)),
    }


def health_label(row, *, language: str = 'ru') -> str:
    pricing = pricing_snapshot(row)
    progress = campaign_progress(row)
    status = str(row['status'] or '')
    speed = _as_int(pricing.get('speed_index'), 100)
    price_position = _as_int(pricing.get('price_position_percent'), 0)
    remaining_budget = max(_as_int(row['budget_total']) - _as_int(row['budget_spent']) - _as_int(row['budget_reserved']), 0)
    if status == 'draft':
        return 'черновик: можно проверить бюджет и запуск' if language == 'ru' else 'draft: check budget and launch'
    if status == 'paused':
        return 'пауза: задание не показывается исполнителям' if language == 'ru' else 'paused: hidden from performers'
    if status == 'completed' or progress['progress_percent'] >= 100:
        return 'готово: объём выполнен' if language == 'ru' else 'done: quantity completed'
    if remaining_budget <= 0:
        return 'нужен бюджет: остаток исчерпан' if language == 'ru' else 'needs budget: remaining budget is empty'
    if progress['reject_percent'] >= 25:
        return 'риск качества: много отклонений' if language == 'ru' else 'quality risk: many rejections'
    if speed < 110 or price_position < 20:
        return 'медленно: цена близка к минимуму' if language == 'ru' else 'slow: price is close to minimum'
    if speed < 140:
        return 'нормально: цена сбалансирована' if language == 'ru' else 'normal: balanced price'
    return 'быстро: задание заметно исполнителям' if language == 'ru' else 'fast: attractive for performers'


def action_tip(row, *, language: str = 'ru') -> str:
    pricing = pricing_snapshot(row)
    progress = campaign_progress(row)
    status = str(row['status'] or '')
    unit_price = _as_int(row['unit_price'] or row['reward_amount'])
    recommended = _as_int(pricing.get('recommended_unit_price'), unit_price)
    fast = _as_int(pricing.get('fast_unit_price'), recommended)
    priority = _as_int(pricing.get('priority_unit_price'), fast)
    speed = _as_int(pricing.get('speed_index'), 100)
    if status == 'draft':
        return 'Запустите задание, когда бюджет и цена проверены.' if language == 'ru' else 'Launch when budget and price look correct.'
    if status == 'paused':
        return 'Возобновите задание, если оно ещё актуально.' if language == 'ru' else 'Resume the task if it is still relevant.'
    if progress['reject_percent'] >= 25:
        return 'Проверьте цель, правила задания и тип проверки: исполнители могут ошибаться из-за неясного условия.' if language == 'ru' else 'Check the target, rules and verification type: performers may be confused.'
    if unit_price < recommended:
        return f'Для стабильной скорости поднимите цену хотя бы до {recommended}.' if language == 'ru' else f'For stable speed, raise the price to at least {recommended}.'
    if speed < 140 and unit_price < fast:
        return f'Если нужна скорость, ускорьте до {fast}.' if language == 'ru' else f'For speed, boost to {fast}.'
    if unit_price < priority:
        return 'Задание выглядит нормально. При срочности можно включить приоритет.' if language == 'ru' else 'The task looks fine. Use priority if it is urgent.'
    return 'Цена уже приоритетная. Дальше важнее качество цели и понятность задания.' if language == 'ru' else 'The price is already priority. Now focus on target quality and clarity.'


def dashboard_summary(owner_user_id: int, *, language: str = 'ru') -> dict[str, Any]:
    stats = db.fetch_one(
        '''
        SELECT
            COUNT(*) AS total,
            COALESCE(SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END), 0) AS active,
            COALESCE(SUM(CASE WHEN status = 'paused' THEN 1 ELSE 0 END), 0) AS paused,
            COALESCE(SUM(CASE WHEN status = 'draft' THEN 1 ELSE 0 END), 0) AS drafts,
            COALESCE(SUM(total_quantity), 0) AS quantity_total,
            COALESCE(SUM(completed_quantity), 0) AS completed_total,
            COALESCE(SUM(rejected_quantity), 0) AS rejected_total,
            COALESCE(SUM(budget_total), 0) AS budget_total,
            COALESCE(SUM(budget_spent), 0) AS budget_spent,
            COALESCE(SUM(budget_reserved), 0) AS budget_reserved
        FROM campaigns
        WHERE owner_user_id = ?
        ''',
        (owner_user_id,),
    )
    campaigns = db.fetch_all(
        '''
        SELECT * FROM campaigns
        WHERE owner_user_id = ?
        ORDER BY
            CASE status WHEN 'active' THEN 0 WHEN 'paused' THEN 1 WHEN 'draft' THEN 2 ELSE 3 END,
            updated_at DESC,
            id DESC
        LIMIT 8
        ''',
        (owner_user_id,),
    )
    slow_count = 0
    quality_risk_count = 0
    rows = []
    for row in campaigns:
        pricing = pricing_snapshot(row)
        progress = campaign_progress(row)
        speed = _as_int(pricing.get('speed_index'), 100)
        if str(row['status']) == 'active' and speed < 110:
            slow_count += 1
        if progress['reject_percent'] >= 25:
            quality_risk_count += 1
        rows.append({
            'id': _as_int(row['id']),
            'title': str(row['title'] or f"#{_as_int(row['id'])}"),
            'status': str(row['status'] or ''),
            'progress_percent': progress['progress_percent'],
            'speed': speed,
            'health': health_label(row, language=language),
            'tip': action_tip(row, language=language),
        })
    total = _as_int(stats['total']) if stats else 0
    budget_total = _as_int(stats['budget_total']) if stats else 0
    budget_spent = _as_int(stats['budget_spent']) if stats else 0
    budget_reserved = _as_int(stats['budget_reserved']) if stats else 0
    quantity_total = _as_int(stats['quantity_total']) if stats else 0
    completed_total = _as_int(stats['completed_total']) if stats else 0
    return {
        'total': total,
        'active': _as_int(stats['active']) if stats else 0,
        'paused': _as_int(stats['paused']) if stats else 0,
        'drafts': _as_int(stats['drafts']) if stats else 0,
        'quantity_total': quantity_total,
        'completed_total': completed_total,
        'progress_percent': round(completed_total * 100 / quantity_total) if quantity_total else 0,
        'rejected_total': _as_int(stats['rejected_total']) if stats else 0,
        'budget_total': budget_total,
        'budget_spent': budget_spent,
        'budget_reserved': budget_reserved,
        'budget_remaining': max(budget_total - budget_spent - budget_reserved, 0),
        'slow_count': slow_count,
        'quality_risk_count': quality_risk_count,
        'rows': rows,
    }


def boost_options(row) -> dict[str, dict[str, int | str]]:
    pricing = pricing_snapshot(row)
    progress = campaign_progress(row)
    current_unit = _as_int(row['unit_price'] or row['reward_amount'])
    total_quantity = max(_as_int(row['total_quantity']), 1)
    remaining_quantity = progress['remaining_quantity']
    options: dict[str, dict[str, int | str]] = {}
    for level, key in BOOST_LEVELS.items():
        target_unit = _as_int(pricing.get(key), current_unit)
        if target_unit <= current_unit:
            continue
        try:
            updated = calculate_campaign_pricing(str(row['task_type']), total_quantity, target_unit)
        except ValueError:
            continue
        extra_unit = target_unit - current_unit
        extra_total = extra_unit * remaining_quantity
        options[level] = {
            'level': level,
            'target_unit_price': target_unit,
            'extra_unit_price': extra_unit,
            'remaining_quantity': remaining_quantity,
            'extra_total': extra_total,
            'new_reward': _as_int(updated['performer_reward']),
            'new_speed': _as_int(updated['speed_index']),
        }
    return options


def boost_options_text(row, *, language: str = 'ru', internal_name: str = 'Искры✨') -> str:
    options = boost_options(row)
    if not options:
        return 'Ускорение сейчас не требуется: цена уже на верхнем ориентире.' if language == 'ru' else 'Boost is not needed: price is already high.'
    labels_ru = {'recommended': 'до рекомендованной', 'fast': 'до быстрой', 'priority': 'до приоритетной'}
    labels_en = {'recommended': 'to recommended', 'fast': 'to fast', 'priority': 'to priority'}
    labels = labels_ru if language == 'ru' else labels_en
    lines = []
    for level in ('recommended', 'fast', 'priority'):
        option = options.get(level)
        if not option:
            continue
        lines.append(
            f"• {labels[level]}: {option['target_unit_price']} {internal_name} · доплата {option['extra_total']} {internal_name} · скорость {option['new_speed']}%"
        )
    return '\n'.join(lines)


def boost_campaign(owner_user_id: int, campaign_id: int, level: str) -> tuple[bool, str]:
    if level not in BOOST_LEVELS:
        return False, 'campaign_boost_invalid'

    def _run(connection: sqlite3.Connection) -> tuple[bool, str]:
        campaign = connection.execute(
            'SELECT * FROM campaigns WHERE id = ? AND owner_user_id = ?',
            (campaign_id, owner_user_id),
        ).fetchone()
        if not campaign:
            return False, 'campaign_not_found'
        if str(campaign['status']) not in {'draft', 'active', 'paused'}:
            return False, 'campaign_boost_status_invalid'
        options = boost_options(campaign)
        option = options.get(level)
        if not option:
            return False, 'campaign_boost_not_needed'
        extra_total = _as_int(option['extra_total'])
        if extra_total <= 0:
            return False, 'campaign_boost_not_needed'
        owner_wallet = connection.execute('SELECT * FROM wallets WHERE user_id = ?', (owner_user_id,)).fetchone()
        is_funded = _as_int(campaign['is_funded']) == 1 or str(campaign['status']) in {'active', 'paused'}
        from_bonus = 0
        from_internal = 0
        if is_funded:
            internal_balance = _as_int(owner_wallet['internal_balance']) if owner_wallet else 0
            bonus_balance = _as_int(owner_wallet['bonus_balance']) if owner_wallet and 'bonus_balance' in owner_wallet.keys() else 0
            if internal_balance + bonus_balance < extra_total:
                return False, 'campaign_boost_balance_low'
            from_bonus = min(bonus_balance, extra_total)
            from_internal = extra_total - from_bonus
            connection.execute(
                '''
                UPDATE wallets
                SET bonus_balance = bonus_balance - ?,
                    internal_balance = internal_balance - ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                ''',
                (from_bonus, from_internal, owner_user_id),
            )
            if from_bonus > 0:
                connection.execute(
                    '''
                    INSERT INTO transactions (
                        user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, related_campaign_id, note
                    ) VALUES (?, ?, ?, 'BST', 'debit', 'campaign_boost_bonus', 'completed', ?, ?)
                    ''',
                    (owner_user_id, owner_user_id, from_bonus, campaign_id, f'Campaign boosted to {level} from bonus sparks'),
                )
            if from_internal > 0:
                connection.execute(
                    '''
                    INSERT INTO transactions (
                        user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, related_campaign_id, note
                    ) VALUES (?, ?, ?, 'BST', 'debit', 'campaign_boost', 'completed', ?, ?)
                    ''',
                    (owner_user_id, owner_user_id, from_internal, campaign_id, f'Campaign boosted to {level}'),
                )
        target_unit = _as_int(option['target_unit_price'])
        total_quantity = max(_as_int(campaign['total_quantity']), 1)
        pricing = calculate_campaign_pricing(str(campaign['task_type']), total_quantity, target_unit)
        old_budget_total = _as_int(campaign['budget_total'])
        new_budget_total = old_budget_total + extra_total
        new_reward_budget_total = _as_int(campaign['reward_budget_total']) + max((_as_int(pricing['performer_reward']) - _as_int(campaign['reward_amount'])) * _as_int(option['remaining_quantity']), 0)
        new_service_fee_total = max(new_budget_total - new_reward_budget_total, 0)
        snapshot = pricing_snapshot(campaign)
        snapshot.update({
            'boost_level': level,
            'boosted_at': utcnow().isoformat(timespec='seconds'),
            'client_unit_price': _as_int(pricing['client_unit_price']),
            'performer_reward': _as_int(pricing['performer_reward']),
            'speed_index': _as_int(pricing['speed_index']),
            'price_position_percent': _as_int(pricing['price_position_percent']),
            'recommended_unit_price': _as_int(pricing['recommended_unit_price']),
            'fast_unit_price': _as_int(pricing['fast_unit_price']),
            'priority_unit_price': _as_int(pricing['priority_unit_price']),
        })
        connection.execute(
            '''
            UPDATE campaigns
            SET unit_price = ?,
                reward_amount = ?,
                reward_budget_total = ?,
                service_fee_total = ?,
                budget_total = ?,
                pricing_json = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND owner_user_id = ?
            ''',
            (
                _as_int(pricing['client_unit_price']),
                _as_int(pricing['performer_reward']),
                new_reward_budget_total,
                new_service_fee_total,
                new_budget_total,
                json.dumps(snapshot, ensure_ascii=False),
                campaign_id,
                owner_user_id,
            ),
        )
        return True, 'campaign_boosted'

    return db.run_in_transaction(_run)
