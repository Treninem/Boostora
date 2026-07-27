"""Small UX helpers for clean step-by-step screens.

This module is intentionally stateless: it does not migrate or mutate user data.
It only formats progress labels that are shown in existing screens.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FlowStep:
    code: str
    number: int
    title_ru: str
    title_en: str


CAMPAIGN_STEPS = (
    FlowStep('target', 1, 'Цель задания', 'Task target'),
    FlowStep('quantity', 2, 'Количество', 'Quantity'),
    FlowStep('price', 3, 'Цена за выполнение', 'Price per completion'),
)

BROADCAST_STEPS = (
    FlowStep('text', 1, 'Текст рекламы', 'Ad text'),
    FlowStep('link', 2, 'Ссылка', 'Target link'),
    FlowStep('schedule', 3, 'График', 'Schedule'),
)


def _is_ru(language: str | None) -> bool:
    return (language or 'ru').lower().startswith('ru')


def _progress_bar(number: int, total: int) -> str:
    number = max(1, min(int(number), int(total)))
    return ' '.join('●' if idx <= number else '○' for idx in range(1, int(total) + 1))


def campaign_step_status(step_code: str, *, language: str = 'ru') -> str:
    step = next((item for item in CAMPAIGN_STEPS if item.code == step_code), CAMPAIGN_STEPS[0])
    title = step.title_ru if _is_ru(language) else step.title_en
    prefix = 'Шаг' if _is_ru(language) else 'Step'
    return f'{_progress_bar(step.number, len(CAMPAIGN_STEPS))} · {prefix} {step.number}/{len(CAMPAIGN_STEPS)} · {title}'


def broadcast_step_status(step_code: str, *, language: str = 'ru') -> str:
    step = next((item for item in BROADCAST_STEPS if item.code == step_code), BROADCAST_STEPS[0])
    title = step.title_ru if _is_ru(language) else step.title_en
    prefix = 'Шаг' if _is_ru(language) else 'Step'
    return f'{_progress_bar(step.number, len(BROADCAST_STEPS))} · {prefix} {step.number}/{len(BROADCAST_STEPS)} · {title}'
