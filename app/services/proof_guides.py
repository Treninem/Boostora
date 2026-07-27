from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any


@dataclass(frozen=True)
class ProofGuide:
    task_type: str
    label: dict[str, str]
    client_hint: dict[str, str]
    performer_steps: dict[str, tuple[str, ...]]
    proof_template: dict[str, str]
    quality_warning: dict[str, str]
    auto_check_hint: dict[str, str]


class ProofGuideService:
    """Human proof and instruction layer for Boostora engagement tasks.

    This layer does not approve work by itself and does not bypass antifraud,
    automatic checks, moderation, holds or wallet logic. It only explains to
    clients what link to provide and to performers what clean proof should look
    like when manual proof is needed.
    """

    _DEFAULT = ProofGuide(
        task_type='default',
        label={'ru': 'Задание', 'en': 'Task'},
        client_hint={
            'ru': 'Укажи прямую ссылку на цель задания. Чем точнее ссылка, тем меньше спорных выполнений.',
            'en': 'Provide a direct task target link. The clearer the link, the fewer disputed completions.',
        },
        performer_steps={
            'ru': (
                'Открой цель задания по кнопке.',
                'Выполни только то действие, которое указано в карточке.',
                'Не отправляй пустые, одинаковые или случайные подтверждения.',
            ),
            'en': (
                'Open the target from the button.',
                'Complete only the action shown in the task card.',
                'Do not send empty, repeated or random proof.',
            ),
        },
        proof_template={
            'ru': 'Выполнил задание. Цель: {target_url}. Мой @username/ID: _____.',
            'en': 'Task completed. Target: {target_url}. My @username/ID: _____.',
        },
        quality_warning={
            'ru': 'Плохой proof может уйти на ручную проверку или быть отклонён.',
            'en': 'Poor proof may be sent to manual review or rejected.',
        },
        auto_check_hint={
            'ru': 'Если автопроверка доступна, бот попробует проверить действие сам.',
            'en': 'If automatic verification is available, the bot will try to verify the action itself.',
        },
    )

    _GUIDES: dict[str, ProofGuide] = {
        'post_reaction': ProofGuide(
            task_type='post_reaction',
            label={'ru': 'Реакция под постом', 'en': 'Post reaction'},
            client_hint={
                'ru': 'Для реакций нужна прямая ссылка на конкретный пост Telegram. Бот должен видеть пост и реакции, поэтому для надёжной проверки добавь бота в канал/чат с нужными правами.',
                'en': 'For reactions, provide a direct Telegram post link. The bot should be able to see the post and reactions, so add it to the channel/chat with the needed rights for reliable checks.',
            },
            performer_steps={
                'ru': (
                    'Открой пост по кнопке.',
                    'Поставь реакцию/эмодзи под этим постом.',
                    'Не снимай реакцию до проверки и начисления холда.',
                ),
                'en': (
                    'Open the post from the button.',
                    'Add a reaction/emoji to that post.',
                    'Do not remove the reaction until verification and hold credit.',
                ),
            },
            proof_template={
                'ru': 'Поставил реакцию на пост: {target_url}. Мой @username/ID: _____.',
                'en': 'I reacted to the post: {target_url}. My @username/ID: _____.',
            },
            quality_warning={
                'ru': 'Если реакция не видна боту, отправь короткое подтверждение без лишнего текста.',
                'en': 'If the bot cannot see the reaction, send short proof without extra text.',
            },
            auto_check_hint={
                'ru': 'Реакции могут проверяться автоматически, если Telegram отдаёт событие реакции боту.',
                'en': 'Reactions can be auto-verified when Telegram delivers the reaction event to the bot.',
            },
        ),
        'post_like': ProofGuide(
            task_type='post_like',
            label={'ru': 'Лайк/эмодзи под постом', 'en': 'Post like/emoji'},
            client_hint={
                'ru': 'Для лайков и эмодзи укажи прямую ссылку на пост. В описании задания лучше не просить конкретный запрещённый или спорный сценарий.',
                'en': 'For likes and emojis, provide a direct post link. Avoid requesting prohibited or disputed behavior in the task description.',
            },
            performer_steps={
                'ru': (
                    'Открой пост.',
                    'Поставь лайк или подходящий эмодзи.',
                    'Сохрани действие до проверки.',
                ),
                'en': (
                    'Open the post.',
                    'Add a like or relevant emoji.',
                    'Keep the action until verification.',
                ),
            },
            proof_template={
                'ru': 'Лайк/эмодзи поставлен под постом: {target_url}. Мой @username/ID: _____.',
                'en': 'Like/emoji added under the post: {target_url}. My @username/ID: _____.',
            },
            quality_warning={
                'ru': 'Не отправляй один и тот же proof в разные задания — антифрод это видит.',
                'en': 'Do not reuse the same proof across tasks; antifraud can detect it.',
            },
            auto_check_hint={
                'ru': 'Для лайков чаще нужна ручная проверка или системные события, если они доступны.',
                'en': 'Likes usually need manual review or system events when available.',
            },
        ),
        'post_comment': ProofGuide(
            task_type='post_comment',
            label={'ru': 'Комментарий под постом', 'en': 'Post comment'},
            client_hint={
                'ru': 'Для комментариев нужна ссылка на пост с открытым обсуждением. Не проси спам: лучше укажи, что комментарий должен быть осмысленным и по теме.',
                'en': 'For comments, provide a post link with open discussion. Do not ask for spam; require a meaningful on-topic comment.',
            },
            performer_steps={
                'ru': (
                    'Открой пост и обсуждение.',
                    'Оставь нормальный комментарий по теме, без спама и оскорблений.',
                    'В proof укажи свой @username и коротко текст комментария.',
                ),
                'en': (
                    'Open the post and discussion.',
                    'Leave a normal on-topic comment without spam or insults.',
                    'In proof, include your @username and a short comment excerpt.',
                ),
            },
            proof_template={
                'ru': 'Комментарий оставлен под постом: {target_url}. Мой @username: _____. Текст комментария: «_____».',
                'en': 'Comment posted under: {target_url}. My @username: _____. Comment text: "_____."',
            },
            quality_warning={
                'ru': 'Короткие однотипные комментарии вроде “+”, “ок”, “топ” могут уйти на ручную проверку или отклонение.',
                'en': 'Very short repeated comments like “+”, “ok”, “top” may be manually reviewed or rejected.',
            },
            auto_check_hint={
                'ru': 'Комментарии могут проверяться автоматически, если бот видит обсуждение и событие комментария.',
                'en': 'Comments can be auto-verified if the bot can see the discussion and the comment event.',
            },
        ),
        'channel_subscribe': ProofGuide(
            task_type='channel_subscribe',
            label={'ru': 'Подписка на канал', 'en': 'Channel subscription'},
            client_hint={
                'ru': 'Укажи @username канала или ссылку на канал. Для автопроверки бот должен иметь доступ к проверке участников.',
                'en': 'Provide a channel @username or link. For auto-checks, the bot needs access to member verification.',
            },
            performer_steps={
                'ru': ('Открой канал.', 'Подпишись и не выходи до проверки.', 'Нажми кнопку проверки в карточке задания.'),
                'en': ('Open the channel.', 'Subscribe and do not leave before verification.', 'Press the verification button in the task card.'),
            },
            proof_template={'ru': 'Подписался на канал: {target_url}. Мой @username/ID: _____.', 'en': 'Subscribed to channel: {target_url}. My @username/ID: _____.'},
            quality_warning={'ru': 'Если выйти сразу после выполнения, задание может быть отклонено.', 'en': 'Leaving immediately after completion may cause rejection.'},
            auto_check_hint={'ru': 'Подписки обычно проверяются автоматически через Telegram.', 'en': 'Subscriptions are usually checked automatically through Telegram.'},
        ),
        'chat_join': ProofGuide(
            task_type='chat_join',
            label={'ru': 'Вступление в чат', 'en': 'Chat join'},
            client_hint={'ru': 'Укажи ссылку или @username чата. Для стабильной проверки бот должен быть в чате.', 'en': 'Provide a chat link or @username. For stable checks, the bot should be in the chat.'},
            performer_steps={'ru': ('Открой чат.', 'Вступи и не выходи до проверки.', 'Нажми кнопку проверки.'), 'en': ('Open the chat.', 'Join and do not leave before verification.', 'Press the verification button.')},
            proof_template={'ru': 'Вступил в чат: {target_url}. Мой @username/ID: _____.', 'en': 'Joined chat: {target_url}. My @username/ID: _____.'},
            quality_warning={'ru': 'Выход из чата до проверки может привести к отклонению.', 'en': 'Leaving before verification can lead to rejection.'},
            auto_check_hint={'ru': 'Вступления обычно проверяются автоматически.', 'en': 'Joins are usually auto-checked.'},
        ),
        'post_view': ProofGuide(
            task_type='post_view',
            label={'ru': 'Просмотр поста', 'en': 'Post view'},
            client_hint={'ru': 'Укажи прямую ссылку на пост. Просмотры сложнее проверить автоматически, поэтому ставь разумную награду и лимит.', 'en': 'Provide a direct post link. Views are harder to auto-check, so use a reasonable reward and limit.'},
            performer_steps={'ru': ('Открой пост.', 'Посмотри публикацию без накрутки и спама.', 'При необходимости отправь короткий proof.'), 'en': ('Open the post.', 'View it normally without spam.', 'Send short proof if needed.')},
            proof_template={'ru': 'Пост просмотрен: {target_url}. Мой @username/ID: _____.', 'en': 'Post viewed: {target_url}. My @username/ID: _____.'},
            quality_warning={'ru': 'Случайные тексты вместо proof могут быть отклонены.', 'en': 'Random text instead of proof can be rejected.'},
            auto_check_hint={'ru': 'Для просмотров чаще применяется ручная или косвенная проверка.', 'en': 'Views usually rely on manual or indirect checks.'},
        ),
        'post_share': ProofGuide(
            task_type='post_share',
            label={'ru': 'Репост/поделиться', 'en': 'Post share'},
            client_hint={'ru': 'Укажи пост, которым нужно поделиться. В описании лучше уточнить, куда разрешён репост.', 'en': 'Provide the post to share. Clarify where sharing is allowed.'},
            performer_steps={'ru': ('Открой пост.', 'Поделись им разрешённым способом.', 'В proof укажи куда отправил/сохранил репост.'), 'en': ('Open the post.', 'Share it using an allowed method.', 'In proof, state where it was shared/saved.')},
            proof_template={'ru': 'Поделился постом: {target_url}. Куда: _____. Мой @username/ID: _____.', 'en': 'Shared post: {target_url}. Where: _____. My @username/ID: _____.'},
            quality_warning={'ru': 'Не делай репост в чужие чаты без разрешения.', 'en': 'Do not repost into other chats without permission.'},
            auto_check_hint={'ru': 'Репосты чаще требуют ручного proof.', 'en': 'Shares usually require manual proof.'},
        ),
        'poll_vote': ProofGuide(
            task_type='poll_vote',
            label={'ru': 'Голос в опросе', 'en': 'Poll vote'},
            client_hint={'ru': 'Укажи ссылку на пост с опросом. Бот должен видеть исходный опрос для проверки.', 'en': 'Provide a link to the poll post. The bot should see the original poll for verification.'},
            performer_steps={'ru': ('Открой опрос.', 'Проголосуй согласно заданию.', 'Не меняй голос до проверки.'), 'en': ('Open the poll.', 'Vote as required.', 'Do not change the vote before verification.')},
            proof_template={'ru': 'Проголосовал в опросе: {target_url}. Мой @username/ID: _____.', 'en': 'Voted in poll: {target_url}. My @username/ID: _____.'},
            quality_warning={'ru': 'Если опрос не виден боту, проверка может уйти вручную.', 'en': 'If the bot cannot see the poll, review may be manual.'},
            auto_check_hint={'ru': 'Опросы могут проверяться автоматически по Telegram-событию ответа.', 'en': 'Polls can be auto-verified by Telegram poll answer events.'},
        ),
        'bot_start': ProofGuide(
            task_type='bot_start',
            label={'ru': 'Старт бота', 'en': 'Bot start'},
            client_hint={'ru': 'Укажи ссылку вида t.me/BotName?start=... чтобы бот понимал целевое действие.', 'en': 'Provide a link like t.me/BotName?start=... so the target action is clear.'},
            performer_steps={'ru': ('Открой бота по ссылке.', 'Нажми Start/Запустить.', 'Не удаляй диалог до проверки.'), 'en': ('Open the bot link.', 'Press Start.', 'Do not delete the chat before verification.')},
            proof_template={'ru': 'Запустил бота по ссылке: {target_url}. Мой @username/ID: _____.', 'en': 'Started bot via: {target_url}. My @username/ID: _____.'},
            quality_warning={'ru': 'Для точной проверки важен start-параметр в ссылке.', 'en': 'A start parameter helps precise verification.'},
            auto_check_hint={'ru': 'Старт бота может проверяться автоматически, если событие зарегистрировано.', 'en': 'Bot starts can be auto-verified when the event is recorded.'},
        ),
        'mini_app_open': ProofGuide(
            task_type='mini_app_open',
            label={'ru': 'Открытие Mini App', 'en': 'Mini App open'},
            client_hint={'ru': 'Укажи ссылку на Mini App с startapp-подсказкой, если она есть.', 'en': 'Provide a Mini App link with a startapp hint if available.'},
            performer_steps={'ru': ('Открой Mini App.', 'Дождись загрузки экрана.', 'Выполни действие внутри приложения, если оно указано.'), 'en': ('Open the Mini App.', 'Wait until it loads.', 'Complete the in-app action if requested.')},
            proof_template={'ru': 'Открыл Mini App: {target_url}. Мой @username/ID: _____.', 'en': 'Opened Mini App: {target_url}. My @username/ID: _____.'},
            quality_warning={'ru': 'Если приложение не отправляет событие, проверка может быть ручной.', 'en': 'If the app does not send an event, review may be manual.'},
            auto_check_hint={'ru': 'Mini App может проверяться автоматически через подписанное серверное событие.', 'en': 'Mini App can be auto-verified through a signed server-side event.'},
        ),
    }

    @staticmethod
    def _lang(language: str | None) -> str:
        return 'ru' if (language or '').lower().startswith('ru') else 'en'

    @staticmethod
    def guide_for(task_type: str | None) -> ProofGuide:
        return ProofGuideService._GUIDES.get(str(task_type or '').strip(), ProofGuideService._DEFAULT)

    @staticmethod
    def _text(mapper: dict[str, str], language: str | None) -> str:
        lang = ProofGuideService._lang(language)
        return mapper.get(lang) or mapper.get('en') or mapper.get('ru') or ''

    @staticmethod
    def _steps(guide: ProofGuide, language: str | None) -> tuple[str, ...]:
        lang = ProofGuideService._lang(language)
        return guide.performer_steps.get(lang) or guide.performer_steps.get('en') or guide.performer_steps.get('ru') or ()

    @staticmethod
    def client_hint(task_type: str | None, language: str | None = 'ru') -> str:
        guide = ProofGuideService.guide_for(task_type)
        return ProofGuideService._text(guide.client_hint, language)

    @staticmethod
    def task_detail_block(task_type: str | None, language: str | None = 'ru') -> str:
        guide = ProofGuideService.guide_for(task_type)
        steps = '\n'.join(f'• {item}' for item in ProofGuideService._steps(guide, language))
        return '\n'.join(part for part in [
            f"<b>{ProofGuideService._text(guide.label, language)}</b>",
            steps,
            ProofGuideService._text(guide.auto_check_hint, language),
            ProofGuideService._text(guide.quality_warning, language),
        ] if part)

    @staticmethod
    def proof_prompt_block(task_type: str | None, target_url: str | None, language: str | None = 'ru') -> str:
        guide = ProofGuideService.guide_for(task_type)
        safe_target = escape(str(target_url or '—'))
        template = ProofGuideService._text(guide.proof_template, language).format(target_url=safe_target)
        steps = '\n'.join(f'• {item}' for item in ProofGuideService._steps(guide, language))
        title = ProofGuideService._text(guide.label, language)
        if ProofGuideService._lang(language) == 'ru':
            return (
                f"<b>{title}</b>\n{steps}\n\n"
                f"<b>Шаблон proof</b>\n<code>{template}</code>\n\n"
                f"{ProofGuideService._text(guide.quality_warning, language)}"
            )
        return (
            f"<b>{title}</b>\n{steps}\n\n"
            f"<b>Proof template</b>\n<code>{template}</code>\n\n"
            f"{ProofGuideService._text(guide.quality_warning, language)}"
        )

    @staticmethod
    def preview_block(task_type: str | None, language: str | None = 'ru') -> str:
        guide = ProofGuideService.guide_for(task_type)
        if ProofGuideService._lang(language) == 'ru':
            return f"<b>Proof для исполнителя</b>\n{ProofGuideService._text(guide.client_hint, language)}\n{ProofGuideService._text(guide.auto_check_hint, language)}"
        return f"<b>Performer proof</b>\n{ProofGuideService._text(guide.client_hint, language)}\n{ProofGuideService._text(guide.auto_check_hint, language)}"

    @staticmethod
    def summary() -> dict[str, Any]:
        required = {'post_reaction', 'post_like', 'post_comment'}
        available = set(ProofGuideService._GUIDES)
        return {
            'guide_count': len(ProofGuideService._GUIDES),
            'required_ready': len(required & available),
            'required_total': len(required),
            'has_default': True,
        }
