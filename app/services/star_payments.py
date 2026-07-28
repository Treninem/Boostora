from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from app import db
from app.config import settings


@dataclass(frozen=True)
class StarPaymentResult:
    ok: bool
    result_key: str
    data: dict[str, Any] | None = None


class StarPaymentService:
    """Idempotent Star purchase ledger and owner-approved full refunds."""

    @staticmethod
    def apply_credit_purchase(
        *,
        user_id: int,
        invoice_payload: str,
        payment_kind: str,
        stars_amount: int,
        credits_granted: int,
        telegram_payment_charge_id: str,
        provider_payment_charge_id: str = '',
    ) -> StarPaymentResult:
        charge_id = str(telegram_payment_charge_id or '').strip()
        if not charge_id:
            return StarPaymentResult(False, 'star_payment_charge_missing')
        credits = max(1, int(credits_granted))
        stars = max(1, int(stars_amount))

        def _run(connection):
            existing = connection.execute(
                'SELECT * FROM star_payments WHERE telegram_payment_charge_id = ?',
                (charge_id,),
            ).fetchone()
            if existing:
                return StarPaymentResult(True, 'star_payment_already_applied', data={'payment_id': int(existing['id']), 'duplicate': True})
            cursor = connection.execute(
                '''INSERT INTO star_payments (
                       user_id, invoice_payload, payment_kind, stars_amount, credits_granted,
                       telegram_payment_charge_id, provider_payment_charge_id, status
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, 'paid')''',
                (
                    int(user_id), str(invoice_payload)[:255], str(payment_kind)[:64], stars, credits,
                    charge_id, str(provider_payment_charge_id or '')[:255],
                ),
            )
            payment_id = int(cursor.lastrowid)
            connection.execute('INSERT INTO wallets (user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING', (int(user_id),))
            connection.execute(
                'UPDATE wallets SET internal_balance=internal_balance+?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?',
                (credits, int(user_id)),
            )
            connection.execute(
                '''INSERT INTO transactions (
                       user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, note
                   ) VALUES (?, ?, ?, 'BST', 'credit', 'stars_topup', 'completed', ?)''',
                (int(user_id), int(user_id), credits, f'star_payment_id={payment_id}; stars={stars}'),
            )
            return StarPaymentResult(True, 'stars_topup_success', data={'payment_id': payment_id, 'credits': credits, 'stars': stars, 'duplicate': False})

        return db.run_in_transaction(_run)

    @staticmethod
    def list_user_payments(user_id: int, *, limit: int = 20):
        return db.fetch_all(
            '''SELECT * FROM star_payments WHERE user_id=? ORDER BY id DESC LIMIT ?''',
            (int(user_id), max(1, min(150, int(limit)))),
        )

    @staticmethod
    def _telegram_refund(*, user_id: int, charge_id: str) -> tuple[bool, str]:
        try:
            response = requests.post(
                f'https://api.telegram.org/bot{settings.bot_token}/refundStarPayment',
                json={'user_id': int(user_id), 'telegram_payment_charge_id': str(charge_id)},
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get('ok') and payload.get('result') is True:
                return True, ''
            return False, str(payload.get('description') or 'refund_rejected')[:300]
        except Exception as exc:
            return False, str(exc)[:300]

    @staticmethod
    def refund_credit_purchase(
        *,
        payment_id: int,
        admin_user_id: int,
        reason: str,
        bonus_to_remove: int = 0,
    ) -> StarPaymentResult:
        clean_reason = str(reason or '').strip()
        if not clean_reason:
            return StarPaymentResult(False, 'refund_reason_required')
        payment = db.fetch_one('SELECT * FROM star_payments WHERE id=?', (int(payment_id),))
        if not payment:
            return StarPaymentResult(False, 'star_payment_not_found')
        if str(payment['status']) == 'refunded':
            return StarPaymentResult(True, 'star_payment_already_refunded', data={'payment_id': int(payment_id)})
        if str(payment['status']) != 'paid':
            return StarPaymentResult(False, 'star_payment_not_refundable')
        user_id = int(payment['user_id'])
        credits = int(payment['credits_granted'] or 0)
        bonus_remove = max(0, int(bonus_to_remove))

        def _reserve(connection):
            current = connection.execute('SELECT * FROM star_payments WHERE id=?', (int(payment_id),)).fetchone()
            if not current or str(current['status']) != 'paid':
                return False, 0
            wallet = connection.execute('SELECT * FROM wallets WHERE user_id=?', (user_id,)).fetchone()
            internal = int(wallet['internal_balance'] or 0) if wallet else 0
            bonus = int(wallet['bonus_balance'] or 0) if wallet else 0
            if internal < credits:
                return False, internal
            actual_bonus = min(bonus, bonus_remove)
            connection.execute(
                '''UPDATE wallets SET internal_balance=internal_balance-?, bonus_balance=bonus_balance-?,
                       updated_at=CURRENT_TIMESTAMP WHERE user_id=?''',
                (credits, actual_bonus, user_id),
            )
            connection.execute(
                '''UPDATE star_payments SET status='refund_pending', refunded_by_user_id=?,
                       refund_reason=?, updated_at=CURRENT_TIMESTAMP WHERE id=?''',
                (int(admin_user_id), clean_reason[:1000], int(payment_id)),
            )
            connection.execute(
                '''INSERT INTO transactions (user_id,wallet_user_id,amount,currency_code,direction,entry_type,status,note)
                   VALUES (?,? ,?,'BST','debit','star_refund_credit_reversal','completed',?)''',
                (user_id, user_id, credits, f'payment_id={int(payment_id)}; admin={int(admin_user_id)}; {clean_reason[:500]}'),
            )
            if actual_bonus:
                connection.execute(
                    '''INSERT INTO transactions (user_id,wallet_user_id,amount,currency_code,direction,entry_type,status,note)
                       VALUES (?,? ,?,'BST','debit','star_refund_bonus_reversal','completed',?)''',
                    (user_id, user_id, actual_bonus, f'payment_id={int(payment_id)}; admin={int(admin_user_id)}; {clean_reason[:500]}'),
                )
            return True, actual_bonus

        reserved, actual_bonus = db.run_in_transaction(_reserve)
        if not reserved:
            wallet = db.fetch_one('SELECT internal_balance FROM wallets WHERE user_id=?', (user_id,))
            available = int(wallet['internal_balance'] or 0) if wallet else 0
            return StarPaymentResult(False, 'refund_credits_already_used', data={'required_credits': credits, 'available_credits': available})

        ok, error = StarPaymentService._telegram_refund(
            user_id=user_id,
            charge_id=str(payment['telegram_payment_charge_id']),
        )
        if not ok:
            def _rollback(connection):
                connection.execute(
                    'UPDATE wallets SET internal_balance=internal_balance+?, bonus_balance=bonus_balance+?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?',
                    (credits, actual_bonus, user_id),
                )
                connection.execute(
                    "UPDATE star_payments SET status='paid', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (int(payment_id),),
                )
                connection.execute(
                    '''INSERT INTO transactions (user_id,wallet_user_id,amount,currency_code,direction,entry_type,status,note)
                       VALUES (?,? ,?,'BST','credit','star_refund_failed_restore','completed',?)''',
                    (user_id, user_id, credits, f'payment_id={int(payment_id)}; {error}'),
                )
                if actual_bonus:
                    connection.execute(
                        '''INSERT INTO transactions (user_id,wallet_user_id,amount,currency_code,direction,entry_type,status,note)
                           VALUES (?,? ,?,'BST','credit','star_refund_failed_bonus_restore','completed',?)''',
                        (user_id, user_id, actual_bonus, f'payment_id={int(payment_id)}; {error}'),
                    )
            db.run_in_transaction(_rollback)
            return StarPaymentResult(False, 'star_refund_failed', data={'error': error})

        db.execute(
            '''UPDATE star_payments SET status='refunded', refunded_at=CURRENT_TIMESTAMP,
                   updated_at=CURRENT_TIMESTAMP WHERE id=?''',
            (int(payment_id),),
        )
        return StarPaymentResult(True, 'star_refund_completed', data={
            'payment_id': int(payment_id), 'user_id': user_id, 'credits_removed': credits,
            'bonus_removed': actual_bonus, 'stars_refunded': int(payment['stars_amount']),
        })
