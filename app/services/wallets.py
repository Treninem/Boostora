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
    def get_summary(user_id: int) -> dict[str, int]:
        wallet = WalletService.get_wallet(user_id)
        if wallet is None:
            return {
                'available_balance': 0,
                'hold_balance': 0,
                'internal_balance': 0,
                'lifetime_earned': 0,
                'total_withdrawn': 0,
            }
        return {
            'available_balance': int(wallet['available_balance']),
            'hold_balance': int(wallet['hold_balance']),
            'internal_balance': int(wallet['internal_balance']),
            'lifetime_earned': int(wallet['lifetime_earned']),
            'total_withdrawn': int(wallet['total_withdrawn']),
        }

    @staticmethod
    def credit_internal_balance(user_id: int, amount: int, *, entry_type: str, note: str | None = None) -> int:
        if amount <= 0:
            raise ValueError('Amount must be positive')

        def _run(connection: sqlite3.Connection) -> int:
            connection.execute(
                '''
                INSERT INTO wallets (user_id)
                VALUES (?)
                ON CONFLICT(user_id) DO NOTHING
                ''',
                (user_id,),
            )
            connection.execute(
                '''
                UPDATE wallets
                SET internal_balance = internal_balance + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                ''',
                (amount, user_id),
            )
            return int(
                connection.execute(
                    '''
                    INSERT INTO transactions (
                        user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, note
                    ) VALUES (?, ?, ?, 'BST', 'credit', ?, 'completed', ?)
                    ''',
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
                '''
                INSERT INTO wallets (user_id)
                VALUES (?)
                ON CONFLICT(user_id) DO NOTHING
                ''',
                (user_id,),
            )
            wallet = connection.execute('SELECT * FROM wallets WHERE user_id = ?', (user_id,)).fetchone()
            current_balance = int(wallet['internal_balance']) if wallet else 0
            if current_balance < amount:
                return False
            connection.execute(
                '''
                UPDATE wallets
                SET internal_balance = internal_balance - ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                ''',
                (amount, user_id),
            )
            connection.execute(
                '''
                INSERT INTO transactions (
                    user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, note
                ) VALUES (?, ?, ?, 'BST', 'debit', ?, 'completed', ?)
                ''',
                (user_id, user_id, amount, entry_type, note),
            )
            return True

        return db.run_in_transaction(_run)

    @staticmethod
    def has_received_demo_internal_topup(user_id: int) -> bool:
        row = db.fetch_one(
            '''
            SELECT id FROM transactions
            WHERE user_id = ? AND entry_type = 'demo_internal_topup'
            LIMIT 1
            ''',
            (user_id,),
        )
        return row is not None
