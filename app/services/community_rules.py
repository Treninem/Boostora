from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app import db
from app.config import settings


@dataclass(frozen=True)
class CommunityRuleSection:
    code: str
    title_key: str
    body_key: str


class CommunityRulesService:
    """Community rules acceptance gate with original Boostora wording."""

    CURRENT_VERSION = settings.community_rules_version

    @staticmethod
    def sections() -> list[CommunityRuleSection]:
        return [
            CommunityRuleSection('entry', 'community_rules_entry_title', 'community_rules_entry_body'),
            CommunityRuleSection('content', 'community_rules_content_title', 'community_rules_content_body'),
            CommunityRuleSection('no_groups', 'community_rules_no_groups_title', 'community_rules_no_groups_body'),
            CommunityRuleSection('self_promo', 'community_rules_self_promo_title', 'community_rules_self_promo_body'),
            CommunityRuleSection('respect', 'community_rules_respect_title', 'community_rules_respect_body'),
            CommunityRuleSection('activity', 'community_rules_activity_title', 'community_rules_activity_body'),
            CommunityRuleSection('support', 'community_rules_support_title', 'community_rules_support_body'),
            CommunityRuleSection('feedback', 'community_rules_feedback_title', 'community_rules_feedback_body'),
            CommunityRuleSection('exit', 'community_rules_exit_title', 'community_rules_exit_body'),
            CommunityRuleSection('finance', 'community_rules_finance_title', 'community_rules_finance_body'),
        ]

    @staticmethod
    def is_required() -> bool:
        return bool(settings.community_rules_required)

    @staticmethod
    def is_accepted(user_id: int) -> bool:
        if not CommunityRulesService.is_required():
            return True
        row = db.fetch_one(
            '''
            SELECT accepted_at
            FROM community_rule_acceptances
            WHERE user_id = ? AND rules_version = ?
            ''',
            (int(user_id), CommunityRulesService.CURRENT_VERSION),
        )
        return row is not None

    @staticmethod
    def accept(user_id: int, source: str = 'bot') -> None:
        db.execute(
            '''
            INSERT INTO community_rule_acceptances (user_id, rules_version, source)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, rules_version) DO UPDATE SET
                accepted_at = CURRENT_TIMESTAMP,
                source = excluded.source
            ''',
            (int(user_id), CommunityRulesService.CURRENT_VERSION, source[:32]),
        )

    @staticmethod
    def acceptance_count() -> int:
        row = db.fetch_one(
            'SELECT COUNT(*) AS cnt FROM community_rule_acceptances WHERE rules_version = ?',
            (CommunityRulesService.CURRENT_VERSION,),
        )
        return int(row['cnt'] or 0) if row else 0

    @staticmethod
    def summary() -> dict[str, Any]:
        has_table = bool(db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name='community_rule_acceptances'"))
        return {
            'required': int(CommunityRulesService.is_required()),
            'version': CommunityRulesService.CURRENT_VERSION,
            'table_ready': int(has_table),
            'accepted_users': CommunityRulesService.acceptance_count() if has_table else 0,
            'sections': len(CommunityRulesService.sections()),
            'state': 'ready' if has_table and len(CommunityRulesService.sections()) >= 8 else 'review',
        }
