import sqlite3

from app import db


class WalletService:
    @staticmethod
    def ensure_wallet(user_id: int):
        db.ensure_wallet(user_id)
        return db.get_wallet(user_id)

    @staticmethod
    def get_wallet(user_id: int):
        db.ensure_wallet(user_id)
        return db.get_wallet(user_id)

    @staticmethod
    def has_paid_stars_topup(user_id: int) -> bool:
        row = db.fetch_one(
            """
            SELECT id FROM transactions
            WHERE user_id = ? AND entry_type = 'stars_topup' AND status = 'completed'
            LIMIT 1
            """,
            (user_id,),
        )
        return row is not None

    @staticmethod
    def get_summary(user_id: int) -> dict[str, int | bool]:
        wallet = WalletService.get_wallet(user_id)
        if wallet is None:
            return {
                'available_balance': 0,
                'hold_balance': 0,
                'internal_balance': 0,
                'bonus_balance': 0,
                'campaign_balance': 0,
                'redeemable_balance': 0,
                'lifetime_earned': 0,
                'total_withdrawn': 0,
                'has_paid_topup': False,
            }
        internal_balance = int(wallet['internal_balance'])
        bonus_balance = int(wallet['bonus_balance']) if 'bonus_balance' in wallet.keys() else 0
        return {
            'available_balance': int(wallet['available_balance']),
            'hold_balance': int(wallet['hold_balance']),
            'internal_balance': internal_balance,
            'bonus_balance': bonus_balance,
            'campaign_balance': internal_balance + bonus_balance,
            'redeemable_balance': internal_balance,
            'lifetime_earned': int(wallet['lifetime_earned']),
            'total_withdrawn': int(wallet['total_withdrawn']),
            'has_paid_topup': WalletService.has_paid_stars_topup(user_id),
        }

    @staticmethod
    def credit_internal_balance(user_id: int, amount: int, *, entry_type: str, note: str | None = None) -> int:
        if amount <= 0:
            raise ValueError('Amount must be positive')

        def _run(connection: sqlite3.Connection) -> int:
            connection.execute(
                """
                INSERT INTO wallets (user_id)
                VALUES (?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (user_id,),
            )
            connection.execute(
                """
                UPDATE wallets
                SET internal_balance = internal_balance + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (amount, user_id),
            )
            return int(
                connection.execute(
                    """
                    INSERT INTO transactions (
                        user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, note
                    ) VALUES (?, ?, ?, 'BST', 'credit', ?, 'completed', ?)
                    """,
                    (user_id, user_id, amount, entry_type, note),
                ).lastrowid
            )

        return db.run_in_transaction(_run)

    @staticmethod
    def credit_bonus_balance(user_id: int, amount: int, *, entry_type: str, note: str | None = None) -> int:
        if amount <= 0:
            raise ValueError('Amount must be positive')

        def _run(connection: sqlite3.Connection) -> int:
            connection.execute(
                """
                INSERT INTO wallets (user_id)
                VALUES (?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (user_id,),
            )
            connection.execute(
                """
                UPDATE wallets
                SET bonus_balance = bonus_balance + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (amount, user_id),
            )
            return int(
                connection.execute(
                    """
                    INSERT INTO transactions (
                        user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, note
                    ) VALUES (?, ?, ?, 'BST', 'credit', ?, 'completed', ?)
                    """,
                    (user_id, user_id, amount, entry_type, note),
                ).lastrowid
            )

        return db.run_in_transaction(_run)

    @staticmethod
    def spend_internal_balance(user_id: int, amount: int, *, entry_type: str, note: str | None = None) -> bool:
        if amount <= 0:
            raise ValueError('Amount must be positive')

        def _run(connection: sqlite3.Connection) -> bool:
            connection.execute(
                """
                INSERT INTO wallets (user_id)
                VALUES (?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (user_id,),
            )
            wallet = connection.execute('SELECT * FROM wallets WHERE user_id = ?', (user_id,)).fetchone()
            current_balance = int(wallet['internal_balance']) if wallet else 0
            if current_balance < amount:
                return False
            connection.execute(
                """
                UPDATE wallets
                SET internal_balance = internal_balance - ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (amount, user_id),
            )
            connection.execute(
                """
                INSERT INTO transactions (
                    user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, note
                ) VALUES (?, ?, ?, 'BST', 'debit', ?, 'completed', ?)
                """,
                (user_id, user_id, amount, entry_type, note),
            )
            return True

        return db.run_in_transaction(_run)

    @staticmethod
    def spend_with_bonus_cap(
        user_id: int,
        amount: int,
        *,
        entry_type: str,
        note: str | None = None,
        related_campaign_id: int | None = None,
        max_bonus_percent: int = 50,
    ) -> dict[str, int | bool]:
        if amount <= 0:
            raise ValueError('Amount must be positive')
        safe_percent = max(0, min(50, int(max_bonus_percent)))

        def _run(connection: sqlite3.Connection) -> dict[str, int | bool]:
            connection.execute(
                """
                INSERT INTO wallets (user_id)
                VALUES (?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (user_id,),
            )
            wallet = connection.execute('SELECT * FROM wallets WHERE user_id = ?', (user_id,)).fetchone()
            internal_balance = int(wallet['internal_balance']) if wallet else 0
            bonus_balance = int(wallet['bonus_balance']) if wallet and 'bonus_balance' in wallet.keys() else 0
            max_bonus = amount * safe_percent // 100
            from_bonus = min(bonus_balance, max_bonus)
            from_internal = amount - from_bonus
            if internal_balance < from_internal:
                return {
                    'ok': False,
                    'amount': amount,
                    'bonus_used': 0,
                    'credits_used': 0,
                    'missing': max(0, from_internal - internal_balance),
                }
            connection.execute(
                """
                UPDATE wallets
                SET bonus_balance = bonus_balance - ?,
                    internal_balance = internal_balance - ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (from_bonus, from_internal, user_id),
            )
            if from_bonus > 0:
                connection.execute(
                    """
                    INSERT INTO transactions (
                        user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, related_campaign_id, note
                    ) VALUES (?, ?, ?, 'BST', 'debit', ?, 'completed', ?, ?)
                    """,
                    (user_id, user_id, from_bonus, f'{entry_type}_bonus', related_campaign_id, (note or 'Service payment') + ' [bonus]'),
                )
            if from_internal > 0:
                connection.execute(
                    """
                    INSERT INTO transactions (
                        user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, related_campaign_id, note
                    ) VALUES (?, ?, ?, 'BST', 'debit', ?, 'completed', ?, ?)
                    """,
                    (user_id, user_id, from_internal, entry_type, related_campaign_id, (note or 'Service payment') + ' [credits]'),
                )
            return {
                'ok': True,
                'amount': amount,
                'bonus_used': from_bonus,
                'credits_used': from_internal,
                'missing': 0,
            }

        return db.run_in_transaction(_run)

    @staticmethod
    def spend_campaign_balance(user_id: int, amount: int, *, entry_type: str, note: str | None = None, related_campaign_id: int | None = None) -> bool:
        from app.services.runtime_settings import RuntimeSettingsService

        result = WalletService.spend_with_bonus_cap(
            user_id,
            amount,
            entry_type=entry_type,
            note=note,
            related_campaign_id=related_campaign_id,
            max_bonus_percent=RuntimeSettingsService.get_int('max_bonus_payment_percent'),
        )
        return bool(result['ok'])

    @staticmethod
    def refund_split(
        user_id: int,
        *,
        credits: int = 0,
        bonus: int = 0,
        entry_type: str = 'service_refund',
        note: str | None = None,
        related_campaign_id: int | None = None,
    ) -> None:
        safe_credits = max(0, int(credits))
        safe_bonus = max(0, int(bonus))
        if safe_credits <= 0 and safe_bonus <= 0:
            return

        def _run(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                INSERT INTO wallets (user_id)
                VALUES (?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (user_id,),
            )
            connection.execute(
                """
                UPDATE wallets
                SET internal_balance = internal_balance + ?,
                    bonus_balance = bonus_balance + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (safe_credits, safe_bonus, user_id),
            )
            if safe_credits:
                connection.execute(
                    """
                    INSERT INTO transactions (
                        user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, related_campaign_id, note
                    ) VALUES (?, ?, ?, 'BST', 'credit', ?, 'completed', ?, ?)
                    """,
                    (user_id, user_id, safe_credits, entry_type, related_campaign_id, (note or 'Refund') + ' [credits]'),
                )
            if safe_bonus:
                connection.execute(
                    """
                    INSERT INTO transactions (
                        user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, related_campaign_id, note
                    ) VALUES (?, ?, ?, 'BST', 'credit', ?, 'completed', ?, ?)
                    """,
                    (user_id, user_id, safe_bonus, f'{entry_type}_bonus', related_campaign_id, (note or 'Refund') + ' [bonus]'),
                )

        db.run_in_transaction(_run)

    @staticmethod
    def adjust_balance(
        user_id: int,
        *,
        balance_type: str,
        amount: int,
        reason: str,
        admin_user_id: int,
    ) -> dict[str, int | bool]:
        if balance_type not in {'credits', 'bonus'}:
            raise ValueError('Unsupported balance type')
        delta = int(amount)
        if delta == 0:
            raise ValueError('Amount must not be zero')
        if not str(reason or '').strip():
            raise ValueError('Reason is required')

        column = 'internal_balance' if balance_type == 'credits' else 'bonus_balance'
        entry_type = f'owner_adjust_{balance_type}'
        direction = 'credit' if delta > 0 else 'debit'
        absolute = abs(delta)

        def _run(connection: sqlite3.Connection) -> dict[str, int | bool]:
            connection.execute(
                """
                INSERT INTO wallets (user_id)
                VALUES (?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (user_id,),
            )
            wallet = connection.execute('SELECT * FROM wallets WHERE user_id = ?', (user_id,)).fetchone()
            current = int(wallet[column]) if wallet else 0
            if delta < 0 and current < absolute:
                return {'ok': False, 'balance': current, 'changed': 0}
            connection.execute(
                f"UPDATE wallets SET {column} = {column} + ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (delta, user_id),
            )
            connection.execute(
                """
                INSERT INTO transactions (
                    user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, note
                ) VALUES (?, ?, ?, 'BST', ?, ?, 'completed', ?)
                """,
                (user_id, user_id, absolute, direction, entry_type, f'admin={admin_user_id}; {reason.strip()}'),
            )
            return {'ok': True, 'balance': current + delta, 'changed': delta}

        return db.run_in_transaction(_run)

    @staticmethod
    def list_transactions(user_id: int, *, limit: int = 20, offset: int = 0):
        safe_limit = max(1, min(150, int(limit)))
        safe_offset = max(0, int(offset))
        return db.fetch_all(
            """
            SELECT * FROM transactions
            WHERE user_id = ? OR wallet_user_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, user_id, safe_limit, safe_offset),
        )

    @staticmethod
    def has_received_demo_internal_topup(user_id: int) -> bool:
        return False
