"""Приватный Telegram-бот для отслеживания активности Polymarket."""

from __future__ import annotations

import asyncio
import html
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import BotCommand, KeyboardButton, MenuButtonCommands, Message, ReplyKeyboardMarkup

from db import BotDatabase
from parser import (
    POLYMARKET_PROFILE_URL,
    POLYMARKET_PROFILE_USERNAME,
    fetch_featured_markets,
    fetch_latest_news,
    fetch_polymarket_positions,
    fetch_recent_activity,
    get_profile_address,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8760748138:AAGDYqLgjZBB4aIcHpM8KK-nU8rB4-hP3RM").strip()
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "45"))
DEFAULT_ALLOWED_IDS = "776221057,427878075"
ALLOWED_USER_IDS = {
    int(user_id.strip())
    for user_id in os.getenv("ALLOWED_USER_IDS", DEFAULT_ALLOWED_IDS).split(",")
    if user_id.strip()
}

router = Router()
database = BotDatabase()
menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Обзор"), KeyboardButton(text="Новости")],
        [KeyboardButton(text="Позиции"), KeyboardButton(text="Статистика")],
        [KeyboardButton(text="Активность"), KeyboardButton(text="Рынки")],
        [KeyboardButton(text="История"), KeyboardButton(text="Настройки")],
        [KeyboardButton(text="Помощь"), KeyboardButton(text="Обновить")],
        [KeyboardButton(text="/start")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите раздел или введите /start",
)


def escape_html(text: str) -> str:
    return html.escape(text, quote=False)


def ensure_private_access(message: Message) -> bool:
    if not message.from_user:
        return False
    return message.from_user.id in ALLOWED_USER_IDS


async def deny_access(message: Message) -> None:
    await message.answer("У вас нет доступа к этому боту.")


def format_overview_message() -> str:
    stats = database.get_stats()
    positions = database.get_positions_map()
    profile_address = get_profile_address()

    lines = [
        "<b>Polymarket Tracker</b>",
        "",
        f'Профиль: <a href="{POLYMARKET_PROFILE_URL}">@{escape_html(POLYMARKET_PROFILE_USERNAME)}</a>',
        f"Адрес профиля: <code>{escape_html(profile_address)}</code>",
        "",
        "<b>Обзор</b>",
        f"Общий PnL: <code>{stats['total_pnl']:.2f}</code>",
        f"Открытых позиций: <code>{stats['open_positions']}</code>",
        f"Зафиксировано событий активности: <code>{stats['trade_count']}</code>",
        f"Разрешенные ID: <code>{', '.join(str(user_id) for user_id in sorted(ALLOWED_USER_IDS))}</code>",
    ]

    if positions:
        first_position = next(iter(positions.values()))
        lines.extend(
            [
                "",
                "<b>Главная открытая позиция</b>",
                f"{escape_html(first_position['market_name'])}",
                f"Цена: <code>{first_position['price']}</code> | Количество: <code>{first_position['amount']}</code>",
            ]
        )

    return "\n".join(lines)


def format_positions_message(positions: list[dict[str, object]]) -> str:
    if not positions:
        return "<b>Позиции</b>\n\nОткрытых позиций сейчас нет."

    lines = ["<b>Текущие позиции swisstony</b>", ""]
    for index, position in enumerate(positions, start=1):
        lines.extend(
            [
                f"<b>{index}. {escape_html(str(position['market_name']))}</b>",
                f"Цена: <code>{position['price']}</code>",
                f"Количество: <code>{position['amount']}</code>",
                f"PnL: <code>{position['pnl']}</code>",
                "",
            ]
        )
    return "\n".join(lines).strip()


def format_stats_message() -> str:
    stats = database.get_stats()
    return "\n".join(
        [
            "<b>Статистика</b>",
            "",
            f'Профиль: <a href="{POLYMARKET_PROFILE_URL}">@{escape_html(POLYMARKET_PROFILE_USERNAME)}</a>',
            f"Общий PnL: <code>{stats['total_pnl']:.2f}</code>",
            f"Количество событий активности: <code>{stats['trade_count']}</code>",
            f"Открытых позиций: <code>{stats['open_positions']}</code>",
        ]
    )


def format_activity_message() -> str:
    activities = database.get_recent_activity_events(limit=10)
    if not activities:
        return "<b>Активность</b>\n\nПока нет сохраненной активности."

    lines = ["<b>Последняя активность</b>", ""]
    for index, activity in enumerate(activities, start=1):
        lines.extend(
            [
                f"<b>{index}. {escape_html(activity['market_name'])}</b>",
                f"Тип: <code>{escape_html(activity['side'])}</code>",
                f"Цена: <code>{activity['price']}</code>",
                f"Количество: <code>{activity['amount']}</code>",
                f"Время: <code>{escape_html(activity['timestamp'])}</code>",
                "",
            ]
        )
    return "\n".join(lines).strip()


def format_news_message() -> str:
    news_items = database.get_recent_news_events(limit=10)
    if not news_items:
        return "<b>Новости</b>\n\nПока нет сохраненных новых событий Polymarket."

    lines = ["<b>Новые события Polymarket</b>", "", "Это свежие события из Gamma API:"]
    for index, item in enumerate(news_items, start=1):
        lines.extend(
            [
                "",
                f"<b>{index}. {escape_html(item['title'])}</b>",
                f"Категория: <code>{escape_html(item['category'])}</code>",
                f"Объем: <code>{item['volume']}</code>",
                f"Создано: <code>{escape_html(item['created_at'])}</code>",
                f'<a href="{escape_html(item["url"])}">Открыть в Polymarket</a>',
            ]
        )
    return "\n".join(lines)


def format_markets_message() -> str:
    markets = fetch_featured_markets(limit=5)
    lines = ["<b>Топ рынков Polymarket</b>", ""]
    for index, market in enumerate(markets, start=1):
        lines.extend(
            [
                f"<b>{index}. {escape_html(market['name'])}</b>",
                f"Цена: <code>{market['price']}</code>",
                f"Объем: <code>{market['volume']}</code>",
                f'<a href="{escape_html(market["url"])}">Открыть рынок</a>',
                "",
            ]
        )
    return "\n".join(lines).strip()


def format_history_message() -> str:
    trades = database.get_recent_trade_events(limit=10)
    if not trades:
        return "<b>История</b>\n\nИстория трейдов пока пуста."

    lines = ["<b>История изменений позиций</b>", ""]
    for trade in trades:
        lines.append(
            f"• {escape_html(trade['detected_at'])} | {escape_html(trade['market_name'])} | цена <code>{trade['price']}</code> | объем <code>{trade['amount']}</code>"
        )
    return "\n".join(lines)


def format_settings_message() -> str:
    return "\n".join(
        [
            "<b>Настройки</b>",
            "",
            f"Интервал обновления: <code>{POLL_INTERVAL_SECONDS}</code> сек.",
            f"Username профиля: <code>@{escape_html(POLYMARKET_PROFILE_USERNAME)}</code>",
            f"Адрес профиля: <code>{escape_html(get_profile_address())}</code>",
            f"Разрешенные ID: <code>{', '.join(str(user_id) for user_id in sorted(ALLOWED_USER_IDS))}</code>",
            "Источник данных: <code>официальные публичные Gamma API и Data API</code>",
        ]
    )


def format_help_message() -> str:
    return "\n".join(
        [
            "<b>Помощь</b>",
            "",
            "Команды:",
            "• /start - главное меню",
            "• /stats - статистика",
            "• /positions - позиции",
            "• /news - новые события Polymarket",
            "",
            "Разделы внизу:",
            "• Новости - новые события Polymarket",
            "• Активность - реальные сделки и активность пользователя",
            "• Позиции - текущие позиции профиля",
            "",
            "Бот не торгует и не управляет кошельком. Он только отслеживает данные.",
        ]
    )


async def sync_positions(bot: Bot, notify: bool = True) -> list[dict[str, object]]:
    current_positions = fetch_polymarket_positions()
    previous_positions = database.get_positions_map()

    new_position_events: list[dict[str, object]] = []
    for position in current_positions:
        key = str(position["position_key"])
        previous = previous_positions.get(key)
        if previous is None or float(position["amount"]) > float(previous["amount"]):
            new_position_events.append(position)

    for trade in new_position_events:
        database.add_trade_event(trade)

    database.replace_positions(current_positions)

    if notify:
        for trade in new_position_events:
            text = "\n".join(
                [
                    "<b>Новая позиция или увеличение позиции</b>",
                    f"Маркет: {escape_html(str(trade['market_name']))}",
                    f"Цена: <code>{trade['price']}</code>",
                    f"Количество: <code>{trade['amount']}</code>",
                ]
            )
            for user_id in ALLOWED_USER_IDS:
                await bot.send_message(chat_id=user_id, text=text)

    return current_positions


async def sync_activity(bot: Bot, notify: bool = True) -> None:
    activities = fetch_recent_activity(limit=15)
    for activity in reversed(activities):
        activity_id = str(activity["activity_id"])
        if database.has_activity_event(activity_id):
            continue

        database.add_activity_event(activity)
        if notify:
            text = "\n".join(
                [
                    "<b>Новая активность на Polymarket</b>",
                    f"Маркет: {escape_html(str(activity['market_name']))}",
                    f"Тип: <code>{escape_html(str(activity['side']))}</code>",
                    f"Цена: <code>{activity['price']}</code>",
                    f"Количество: <code>{activity['amount']}</code>",
                ]
            )
            for user_id in ALLOWED_USER_IDS:
                await bot.send_message(chat_id=user_id, text=text)


async def sync_news(bot: Bot, notify: bool = True) -> None:
    news_items = fetch_latest_news(limit=10)
    for item in reversed(news_items):
        news_id = str(item["news_id"])
        if database.has_news_event(news_id):
            continue

        database.add_news_event(item)
        if notify:
            text = "\n".join(
                [
                    "<b>Новое событие Polymarket</b>",
                    f"Заголовок: {escape_html(str(item['title']))}",
                    f"Категория: <code>{escape_html(str(item['category']))}</code>",
                    f"Объем: <code>{item['volume']}</code>",
                    f'<a href="{escape_html(str(item["url"]))}">Открыть событие</a>',
                ]
            )
            for user_id in ALLOWED_USER_IDS:
                await bot.send_message(chat_id=user_id, text=text)


async def full_sync(bot: Bot, notify: bool = True) -> None:
    await sync_positions(bot=bot, notify=notify)
    await sync_activity(bot=bot, notify=notify)
    await sync_news(bot=bot, notify=notify)


async def polling_worker(bot: Bot) -> None:
    LOGGER.info("Background polling started with %s second interval", POLL_INTERVAL_SECONDS)
    while True:
        try:
            await full_sync(bot=bot, notify=True)
        except Exception:
            LOGGER.exception("Polling iteration failed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if not ensure_private_access(message):
        await deny_access(message)
        return
    await full_sync(bot=message.bot, notify=False)
    await message.answer(format_overview_message(), reply_markup=menu_keyboard)


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if not ensure_private_access(message):
        await deny_access(message)
        return
    await message.answer(format_stats_message())


@router.message(Command("positions"))
async def cmd_positions(message: Message) -> None:
    if not ensure_private_access(message):
        await deny_access(message)
        return
    try:
        positions = await sync_positions(bot=message.bot, notify=False)
        await message.answer(format_positions_message(positions))
    except Exception:
        LOGGER.exception("Failed to load positions")
        await message.answer(
            "Не удалось загрузить позиции с Polymarket. Попробуйте еще раз через минуту."
        )


@router.message(Command("news"))
async def cmd_news(message: Message) -> None:
    if not ensure_private_access(message):
        await deny_access(message)
        return
    await sync_news(bot=message.bot, notify=False)
    await message.answer(format_news_message())


@router.message(F.text.in_({"Обзор", "/start"}))
async def overview_button(message: Message) -> None:
    await cmd_start(message)


@router.message(F.text.in_({"Статистика", "/stats"}))
async def stats_button(message: Message) -> None:
    await cmd_stats(message)


@router.message(F.text.in_({"Позиции", "/positions"}))
async def positions_button(message: Message) -> None:
    await cmd_positions(message)


@router.message(F.text == "Новости")
async def news_button(message: Message) -> None:
    await cmd_news(message)


@router.message(F.text == "Активность")
async def activity_button(message: Message) -> None:
    if not ensure_private_access(message):
        await deny_access(message)
        return
    await sync_activity(bot=message.bot, notify=False)
    await message.answer(format_activity_message())


@router.message(F.text == "Рынки")
async def markets_button(message: Message) -> None:
    if not ensure_private_access(message):
        await deny_access(message)
        return
    await message.answer(format_markets_message())


@router.message(F.text == "История")
async def history_button(message: Message) -> None:
    if not ensure_private_access(message):
        await deny_access(message)
        return
    await message.answer(format_history_message())


@router.message(F.text == "Настройки")
async def settings_button(message: Message) -> None:
    if not ensure_private_access(message):
        await deny_access(message)
        return
    await message.answer(format_settings_message())


@router.message(F.text == "Помощь")
async def help_button(message: Message) -> None:
    if not ensure_private_access(message):
        await deny_access(message)
        return
    await message.answer(format_help_message())


@router.message(F.text == "Обновить")
async def refresh_button(message: Message) -> None:
    if not ensure_private_access(message):
        await deny_access(message)
        return
    try:
        await full_sync(bot=message.bot, notify=False)
        await message.answer("Данные обновлены.", reply_markup=menu_keyboard)
    except Exception:
        LOGGER.exception("Failed to refresh data")
        await message.answer("Не удалось обновить данные Polymarket.", reply_markup=menu_keyboard)


@router.message()
async def fallback_handler(message: Message) -> None:
    if not ensure_private_access(message):
        await deny_access(message)
        return
    if message.from_user:
        LOGGER.info("Incoming message from user_id=%s text=%s", message.from_user.id, message.text)
    await message.answer(
        "Не понял запрос. Используйте кнопки снизу или команду /start.",
        reply_markup=menu_keyboard,
    )


async def setup_bot_ui(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="stats", description="Статистика"),
            BotCommand(command="positions", description="Позиции"),
            BotCommand(command="news", description="Новые события Polymarket"),
        ]
    )
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def on_startup(bot: Bot) -> None:
    await setup_bot_ui(bot)
    await full_sync(bot=bot, notify=False)
    asyncio.create_task(polling_worker(bot))


async def main() -> None:
    if not BOT_TOKEN:
        raise ValueError("Укажите BOT_TOKEN перед запуском бота.")
    if not ALLOWED_USER_IDS:
        raise ValueError("Укажите хотя бы один user_id в ALLOWED_USER_IDS.")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    await on_startup(bot)
    LOGGER.info("Bot is starting")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
