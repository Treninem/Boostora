from __future__ import annotations

from app import db
from app.services.community_rules import CommunityRulesService
from app.services.legal_docs import LegalDocsService


class PlatformAgreementService:
    """Single acceptance gate for Boostora rules and legal terms.

    The bot stores both legacy document acceptances for backward compatibility
    and one append-only event for an auditable accept/decline history.
    """

    @staticmethod
    def version() -> str:
        return f"{CommunityRulesService.CURRENT_VERSION}+{LegalDocsService.CURRENT_VERSION}"

    @staticmethod
    def is_accepted(user_id: int) -> bool:
        return CommunityRulesService.is_accepted(user_id) and LegalDocsService.is_accepted(user_id)

    @staticmethod
    def _log(user_id: int, action: str, *, source: str, details: str = '') -> None:
        db.execute(
            '''
            INSERT INTO platform_agreement_events (
                user_id, agreement_version, action, source, details
            ) VALUES (?, ?, ?, ?, ?)
            ''',
            (
                int(user_id),
                PlatformAgreementService.version(),
                str(action or '')[:32],
                str(source or 'bot')[:32],
                str(details or '')[:1000],
            ),
        )

    @staticmethod
    def accept(user_id: int, *, source: str = 'bot') -> None:
        CommunityRulesService.accept(user_id, source=source)
        LegalDocsService.accept(user_id, source=source)
        PlatformAgreementService._log(user_id, 'accepted', source=source)

    @staticmethod
    def decline(user_id: int, *, source: str = 'bot') -> None:
        PlatformAgreementService._log(user_id, 'declined', source=source)

    @staticmethod
    def last_event(user_id: int):
        return db.fetch_one(
            '''
            SELECT * FROM platform_agreement_events
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
            ''',
            (int(user_id),),
        )
