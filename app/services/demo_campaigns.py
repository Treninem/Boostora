from app import db


SYSTEM_OWNER_ID = -1000
DEMO_CAMPAIGNS = [
    ('Boostora Demo · Telegram channel follow', 'channel_subscribe', 'https://t.me/durov', 12, 50),
    ('Boostora Demo · Telegram chat join', 'chat_join', 'https://t.me/+I8t5mJaHGh80ODJi', 16, 40),
    ('Boostora Demo · Open bot', 'bot_start', 'https://t.me/BoostoraBot', 10, 80),
    ('Boostora Demo · Open Mini App', 'mini_app_open', 'https://t.me/BoostoraBot/app', 18, 30),
]


class DemoCampaignService:
    @staticmethod
    def ensure_demo_campaigns() -> None:
        existing = db.fetch_one(
            'SELECT id FROM campaigns WHERE owner_user_id = ? LIMIT 1',
            (SYSTEM_OWNER_ID,),
        )
        if existing:
            return

        db.upsert_user(
            user_id=SYSTEM_OWNER_ID,
            username='boostora_system',
            first_name='Boostora',
            last_name='System',
            language_code='en',
        )
        db.ensure_wallet(SYSTEM_OWNER_ID)

        for title, task_type, target_url, reward_amount, total_quantity in DEMO_CAMPAIGNS:
            db.execute(
                '''
                INSERT INTO campaigns (
                    owner_user_id,
                    title,
                    task_type,
                    target_url,
                    reward_amount,
                    total_quantity,
                    budget_total,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
                ''',
                (
                    SYSTEM_OWNER_ID,
                    title,
                    task_type,
                    target_url,
                    reward_amount,
                    total_quantity,
                    reward_amount * total_quantity,
                ),
            )
