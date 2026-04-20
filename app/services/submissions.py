from app import db


class SubmissionService:
    @staticmethod
    def create_submission(campaign_id: int, performer_user_id: int, reward_amount: int, *, target_url: str | None = None) -> int:
        return db.execute(
            '''
            INSERT INTO task_submissions (campaign_id, performer_user_id, reward_amount, target_url)
            VALUES (?, ?, ?, ?)
            ''',
            (campaign_id, performer_user_id, reward_amount, target_url),
        )

    @staticmethod
    def get_submission(submission_id: int):
        return db.fetch_one('SELECT * FROM task_submissions WHERE id = ?', (submission_id,))

    @staticmethod
    def get_submissions_for_user(performer_user_id: int):
        return db.fetch_all(
            'SELECT * FROM task_submissions WHERE performer_user_id = ? ORDER BY updated_at DESC, id DESC',
            (performer_user_id,),
        )
