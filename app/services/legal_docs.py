from __future__ import annotations

from dataclasses import dataclass

from app import db
from app.config import settings


@dataclass(frozen=True)
class LegalSection:
    title_key: str
    body_key: str


class LegalDocsService:
    CURRENT_VERSION = settings.legal_docs_version

    @staticmethod
    def is_required() -> bool:
        return bool(settings.legal_docs_required)

    @staticmethod
    def sections() -> tuple[LegalSection, ...]:
        return (
            LegalSection('legal_section_agreement_title', 'legal_section_agreement_body'),
            LegalSection('legal_section_services_title', 'legal_section_services_body'),
            LegalSection('legal_section_credits_title', 'legal_section_credits_body'),
            LegalSection('legal_section_commission_title', 'legal_section_commission_body'),
            LegalSection('legal_section_refunds_title', 'legal_section_refunds_body'),
            LegalSection('legal_section_network_title', 'legal_section_network_body'),
            LegalSection('legal_section_moderation_title', 'legal_section_moderation_body'),
            LegalSection('legal_section_third_party_title', 'legal_section_third_party_body'),
            LegalSection('legal_section_changes_title', 'legal_section_changes_body'),
            LegalSection('legal_section_disclaimer_title', 'legal_section_disclaimer_body'),
        )

    @staticmethod
    def is_accepted(user_id: int) -> bool:
        if not LegalDocsService.is_required():
            return True
        row = db.fetch_one(
            'SELECT 1 FROM legal_doc_acceptances WHERE user_id = ? AND legal_version = ?',
            (int(user_id), LegalDocsService.CURRENT_VERSION),
        )
        return bool(row)

    @staticmethod
    def accept(user_id: int, *, source: str = 'bot') -> None:
        db.execute(
            '''
            INSERT OR REPLACE INTO legal_doc_acceptances (user_id, legal_version, accepted_at, source)
            VALUES (?, ?, CURRENT_TIMESTAMP, ?)
            ''',
            (int(user_id), LegalDocsService.CURRENT_VERSION, str(source or 'bot')[:32]),
        )

    @staticmethod
    def summary() -> dict:
        try:
            accepted = db.fetch_one('SELECT COUNT(*) AS cnt FROM legal_doc_acceptances WHERE legal_version = ?', (LegalDocsService.CURRENT_VERSION,))
            return {
                'status': 'ready',
                'required': int(LegalDocsService.is_required()),
                'version': LegalDocsService.CURRENT_VERSION,
                'accepted': int(accepted['cnt'] or 0) if accepted else 0,
            }
        except Exception:
            return {'status': 'blocker', 'required': int(LegalDocsService.is_required()), 'version': LegalDocsService.CURRENT_VERSION, 'accepted': 0}
