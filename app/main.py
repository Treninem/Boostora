from __future__ import annotations

import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from app.core.commands import apply_localized_commands
from app.core.settings import Settings
from app.handlers.admin import router as admin_router
from app.handlers.advertiser import router as advertiser_router
from app.handlers.earner import router as earner_router
from app.handlers.payments import router as payments_router
from app.handlers.start import router as start_router
from app.middlewares.subscription import SubscriptionRequiredMiddleware
from app.storage.admin import AdminRepository
from app.storage.billing import BillingRepository
from app.storage.campaigns import CampaignRepository
from app.storage.db import Database
from app.storage.referrals import ReferralRepository
from app.storage.task_claims import TaskClaimRepository
from app.storage.users import UserRepository
from app.storage.wallets import WalletRepository
from app.storage.memberships import MembershipRepository
from app.storage.redemptions import RedemptionRepository


async def main() -> None:
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    )

    settings = Settings.from_env()
    database = Database(settings.db_path)
    await database.init()

    users_repo = UserRepository(database)
    wallets_repo = WalletRepository(database)
    campaigns_repo = CampaignRepository(database)
    referrals_repo = ReferralRepository(database)
    task_claims_repo = TaskClaimRepository(database)
    memberships_repo = MembershipRepository(database)
    redemptions_repo = RedemptionRepository(database)
    admin_repo = AdminRepository(database)
    billing_repo = BillingRepository(database)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    bot['settings'] = settings
    bot['users_repo'] = users_repo
    bot['wallets_repo'] = wallets_repo
    bot['campaigns_repo'] = campaigns_repo
    bot['referrals_repo'] = referrals_repo
    bot['task_claims_repo'] = task_claims_repo
    bot['memberships_repo'] = memberships_repo
    bot['redemptions_repo'] = redemptions_repo
    bot['admin_repo'] = admin_repo
    bot['billing_repo'] = billing_repo


    subscription_middleware = SubscriptionRequiredMiddleware()
    dp.message.outer_middleware(subscription_middleware)
    dp.callback_query.outer_middleware(subscription_middleware)

    await apply_localized_commands(bot)

    dp.include_router(admin_router)
    dp.include_router(payments_router)
    dp.include_router(advertiser_router)
    dp.include_router(earner_router)
    dp.include_router(start_router)

    logging.info('Starting %s', settings.brand_name)
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
