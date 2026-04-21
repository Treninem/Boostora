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
    def spend_campaign_balance(user_id: int, amount: int, *, entry_type: str, note: str | None = None, related_campaign_id: int | None = None) -> bool:
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
            internal_balance = int(wallet['internal_balance']) if wallet else 0
            bonus_balance = int(wallet['bonus_balance']) if wallet and 'bonus_balance' in wallet.keys() else 0
            if internal_balance + bonus_balance < amount:
                return False
            from_bonus = min(bonus_balance, amount)
            from_internal = amount - from_bonus
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
                    (user_id, user_id, from_bonus, f'{entry_type}_bonus', related_campaign_id, (note or 'Campaign funding') + ' [bonus]'),
                )
            if from_internal > 0:
                connection.execute(
                    """
                    INSERT INTO transactions (
                        user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, related_campaign_id, note
                    ) VALUES (?, ?, ?, 'BST', 'debit', ?, 'completed', ?, ?)
                    """,
                    (user_id, user_id, from_internal, entry_type, related_campaign_id, (note or 'Campaign funding') + ' [earned]'),
                )
            return True

        return db.run_in_transaction(_run)

    @staticmethod
    def has_received_demo_internal_topup(user_id: int) -> bool:
        return False
