from __future__ import annotations

from pathlib import Path

from typing import Any

from aiogram.types import FSInputFile, Message

ROOT_DIR = Path(__file__).resolve().parents[2]
BANNERS_DIR = ROOT_DIR / 'assets' / 'banners'


def banner_path(name: str) -> Path:
    return BANNERS_DIR / name


async def send_banner(message: Message, banner_name: str, caption: str, reply_markup: Any | None = None) -> None:
    path = banner_path(banner_name)
    if path.exists():
        await message.answer_photo(FSInputFile(path), caption=caption, reply_markup=reply_markup)
        return
    await message.answer(caption, reply_markup=reply_markup)
