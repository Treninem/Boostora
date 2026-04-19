from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    EARNER = 'earner'
    ADVERTISER = 'advertiser'


class UserTier(StrEnum):
    NEW = 'new'
    VERIFIED = 'verified'
    VIP = 'vip'


class WalletEntryType(StrEnum):
    TASK_REWARD_PENDING = 'task_reward_pending'
    TASK_REWARD_RELEASE = 'task_reward_release'
    TASK_REWARD_REVOKE = 'task_reward_revoke'
    REFERRAL_BONUS = 'referral_bonus'
    SPEND_INTERNAL = 'spend_internal'
    ADMIN_ADJUSTMENT = 'admin_adjustment'
    TOPUP_PENDING = 'topup_pending'
    TOPUP_CONFIRMED = 'topup_confirmed'


class HoldStatus(StrEnum):
    PENDING = 'pending'
    RELEASED = 'released'
    REVOKED = 'revoked'


class CampaignStatus(StrEnum):
    DRAFT = 'draft'
    ACTIVE = 'active'
    PAUSED = 'paused'
    REVIEW = 'review'
    COMPLETED = 'completed'
    REJECTED = 'rejected'


class TaskType(StrEnum):
    CHANNEL_JOIN = 'channel_join'
    POST_VIEW = 'post_view'
    BOT_START = 'bot_start'
    MINI_APP_OPEN = 'mini_app_open'


class ClaimStatus(StrEnum):
    TAKEN = 'taken'
    SUBMITTED = 'submitted'
    VERIFIED = 'verified'
    CANCELED = 'canceled'
    REJECTED = 'rejected'
