from app import db


class InvoiceMessageService:
    @staticmethod
    def get(user_id: int):
        return db.fetch_one(
            "SELECT * FROM invoice_messages WHERE user_id = ?",
            (user_id,),
        )

    @staticmethod
    def set(user_id: int, chat_id: int, invoice_message_id: int, helper_message_id: int | None = None) -> None:
        db.execute(
            """
            INSERT INTO invoice_messages (user_id, chat_id, invoice_message_id, helper_message_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                chat_id = excluded.chat_id,
                invoice_message_id = excluded.invoice_message_id,
                helper_message_id = excluded.helper_message_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, chat_id, invoice_message_id, helper_message_id),
        )

    @staticmethod
    def clear(user_id: int) -> None:
        db.execute("DELETE FROM invoice_messages WHERE user_id = ?", (user_id,))
