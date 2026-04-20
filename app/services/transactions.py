from app import db


class TransactionService:
    @staticmethod
    def create_transaction(
        user_id: int,
        amount: int,
        direction: str,
        entry_type: str,
        *,
        currency_code: str = 'XTR',
        status: str = 'completed',
        related_campaign_id: int | None = None,
        related_submission_id: int | None = None,
        related_hold_id: int | None = None,
        note: str | None = None,
    ) -> int:
        db.ensure_wallet(user_id)
        return db.execute(
            '''
            INSERT INTO transactions (
                user_id,
                wallet_user_id,
                amount,
                currency_code,
                direction,
                entry_type,
                status,
                related_campaign_id,
                related_submission_id,
                related_hold_id,
                note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                user_id,
                user_id,
                amount,
                currency_code,
                direction,
                entry_type,
                status,
                related_campaign_id,
                related_submission_id,
                related_hold_id,
                note,
            ),
        )

    @staticmethod
    def get_history(user_id: int, limit: int = 50):
        return db.fetch_all(
            'SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?',
            (user_id, limit),
        )
