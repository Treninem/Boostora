from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app import db
from app.services.campaigns import CampaignService
from app.services.payments import BASE_SPARKS_PER_STAR, calculate_custom_stars_for_sparks, make_payload, make_start_parameter
from app.services.performer import PerformerService
from app.services.users import UserService


class FakeMember:
    def __init__(self, status: str, is_member: bool = False):
        self.status = status
        self.is_member = is_member


class FakeBot:
    def __init__(self, status: str = 'member', fail: bool = False):
        self.status = status
        self.fail = fail

    def get_chat_member(self, chat_id, user_id):
        if self.fail:
            raise RuntimeError('membership unavailable')
        return FakeMember(self.status)


def fake_user(user_id: int, username: str) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, username=username, first_name=username, last_name='', is_bot=False)


def main() -> None:
    db.init_db()
    owner = fake_user(1001, 'owner')
    perf = fake_user(1002, 'worker')
    UserService.ensure_user(owner)
    UserService.ensure_user(perf)

    # Empty owner stats should not crash and should be all zeros.
    stats = CampaignService.get_owner_stats(owner.id)
    assert stats['active_campaigns'] == 0
    assert stats['budget_total'] == 0

    # start_parameter must satisfy Telegram restrictions.
    start = make_start_parameter('sparks_custom', '120', perf.id)
    assert 1 <= len(start) <= 64
    assert all(ch.isalnum() or ch in '_-' for ch in start)
    assert calculate_custom_stars_for_sparks(120) >= 1
    assert calculate_custom_stars_for_sparks(BASE_SPARKS_PER_STAR) == 1

    # Verifiable task: channel subscribe. First failure, then success.
    campaign_id = CampaignService.create_campaign(
        owner_user_id=owner.id,
        title='Подписка',
        task_type='channel_subscribe',
        target_url='@boostorachat',
        reward_amount=18,
        unit_price=26,
        reward_budget_total=18,
        service_fee_total=8,
        total_quantity=10,
        status='active',
        is_funded=True,
    )
    ok, _, submission_id = PerformerService.take_task(perf.id, campaign_id)
    assert ok and submission_id
    ok, result_key, _ = PerformerService.submit_for_check(FakeBot(status='left'), perf.id, submission_id)
    assert not ok and result_key == 'task_verification_failed'
    row = PerformerService.get_submission(submission_id)
    assert str(row['status']) == 'taken'
    ok, result_key, _ = PerformerService.submit_for_check(FakeBot(status='member'), perf.id, submission_id)
    assert ok and result_key == 'proof_accepted'
    row = PerformerService.get_submission(submission_id)
    assert str(row['status']) == 'approved'

    # Unsupported task type should go to manual review without fake proof text.
    campaign2_id = CampaignService.create_campaign(
        owner_user_id=owner.id,
        title='Лайк',
        task_type='post_like',
        target_url='https://t.me/boostorachat/1',
        reward_amount=4,
        unit_price=7,
        reward_budget_total=4,
        service_fee_total=3,
        total_quantity=10,
        status='active',
        is_funded=True,
    )
    ok, _, submission2_id = PerformerService.take_task(perf.id, campaign2_id)
    assert ok and submission2_id
    ok, result_key, _ = PerformerService.submit_for_check(FakeBot(status='member'), perf.id, submission2_id)
    assert ok and result_key == 'proof_sent_manual_review'
    row = PerformerService.get_submission(submission2_id)
    assert str(row['status']) == 'manual_review'

    print('OK: release regression test passed')


if __name__ == '__main__':
    main()
