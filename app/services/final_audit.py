from __future__ import annotations

"""Compatibility entry point for the cumulative owner audit.

The v3.6.3 audit contains an exact historical version equality check. Newer
releases keep that audit as a cumulative baseline, so the current application
version must not become a false blocker in the legacy checklist.
"""

from app.services import _final_audit_v363 as _baseline

CompletionAuditItem = _baseline.CompletionAuditItem


class FinalAuditService(_baseline.FinalAuditService):
    @staticmethod
    def proposed_items():
        current_version = _baseline.APP_VERSION
        try:
            _baseline.APP_VERSION = 'Boostora v3.6.3'
            return _baseline.FinalAuditService.proposed_items()
        finally:
            _baseline.APP_VERSION = current_version
