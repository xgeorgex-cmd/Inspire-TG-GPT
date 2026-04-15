import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
DATA_DIR = Path(__file__).parent / "data"
CHALLENGES_PATH = DATA_DIR / "starter_challenges_50.json"
MESSAGES_PATH = DATA_DIR / "messages_ru.json"
USER_DATA_PATH = DATA_DIR / "user_state.json"


router = Router()


def load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


MESSAGES = load_json(MESSAGES_PATH, {})
CHALLENGES = load_json(CHALLENGES_PATH, [])
USER_STATE: Dict[str, dict] = load_json(USER_DATA_PATH, {})


def get_message(key: str) -> str:
    return MESSAGES.get(key, key)


def get_user_state(user_id: int) -> dict:
    uid = str(user_id)
    if uid not in USER_STATE:
        USER_STATE[uid] = {
            "completed_count": 0,
            "current_challenge_id": None,
            "awaiting_story": False,
            "awaiting_story_challenge_id": None,
            "awaiting_custom_title": False,
            "awaiting_custom_desc": False,
            "draft_custom_title": None,
            "stories": [],
            "last_take_at": None,
            "last_active_at": datetime.utcnow().isoformat(),
            "profile": {
                "mode": None,
                "budget_tier": None,
                "city_type": None,
            },
        }
    USER_STATE[uid]["last_active_at"] = datetime.utcnow().isoformat()
    return USER_STATE[uid]


def find_challenge(challenge_id: str) -> Optional[dict]:
    for c in CHALLENGES:
        if c["id"] == challenge_id:
            return c
    return None


def list_challenges(filter_mode: Optional[str] = None) -> List[dict]:
    items = [c for c in CHALLENGES if c.get("status") == "published"]
    if filter_mode == "friend":
        items = [c for c in items if c.get("format_type") in ("friend", "mixed")]
    return items[:12]


def format_challenge(challenge: dict) -> str:
    return (
        f"**{challenge['title']}**\n\n"
        f"{challenge['short_description']}\n\n"
        f"Что сделать:\n{challenge['what_to_do']}\n\n"
        f"На что обратить внимание:\n{challenge['what_to_notice']}\n\n"
        f"⏱ {challenge['duration_min']}-{challenge['duration_max']} мин.\n"
        f"👥 {challenge['format_type']}\n"
        f"💸 {challenge['budget_tier']}\n"
        f"🏙 {challenge['city_fit']}"
    )


def build_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Быстрое на сегодня", callback_data="today")],
            [InlineKeyboardButton(text="🎯 Выбрать челлендж", callback_data="choose")],
            [InlineKeyboardButton(text="📌 Текущий челлендж", callback_data="current")],
            [InlineKeyboardButton(text="💛 Истории моих эмоций", callback_data="stories")],
            [InlineKeyboardButton(text="✍️ Поставить себе челлендж", callback_data="custom_start")],
            [InlineKeyboardButton(text="👫 С другом", callback_data="friend_mode")],
        ]
    )


def build_challenge_list(items: List[dict]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=item["title"], callback_data=f"challenge:{item['id']}")] for item in items]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_challenge_card(challenge_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Беру", callback_data=f"take:{challenge_id}")],
            [InlineKeyboardButton(text="👫 Поделиться с другом", callback_data=f"share:{challenge_id}")],
            [InlineKeyboardButton(text="🔁 Другой", callback_data="choose")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")],
        ]
    )


def build_current(challenge_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнил", callback_data=f"done:{challenge_id}")],
            [InlineKeyboardButton(text="👫 Поделиться", callback_data=f"share:{challenge_id}")],
            [InlineKeyboardButton(text="🔁 Заменить", callback_data="choose")],
            [InlineKeyboardButton(text="❌ Снять текущий", callback_data="drop_current")],
            [InlineKeyboardButton(text="⬅️ Меню", callback_data="menu")],
        ]
    )


def build_emotions(challenge_id: str) -> InlineKeyboardMarkup:
    emotions = [("like", "Понравилось"), ("ok", "Нормально"), ("dislike", "Не понравилось")]
    rows = [[InlineKeyboardButton(text=label, callback_data=f"emotion:{challenge_id}:{code}")] for code, label in emotions]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_share_link(bot_username: str, challenge_id: str, from_user_id: int) -> str:
    payload = f"share_{challenge_id}_{from_user_id}"
    return f"https://t.me/{bot_username}?start={payload}"


@router.message(CommandStart(deep_link=True))
async def start_with_payload(message: Message, command: CommandStart) -> None:
    payload = command.args or ""
    get_user_state(message.from_user.id)

    if payload.startswith("share_"):
        _, challenge_id, inviter_id = payload.split("_", 2)
        challenge = find_challenge(challenge_id)
        if challenge:
            await message.answer(
                "Тебя пригласили в челлендж.\n\n" + format_challenge(challenge),
                parse_mode="Markdown",
                reply_markup=build_challenge_card(challenge_id),
            )
            return

    await message.answer(get_message("welcome"), reply_markup=build_main_menu())


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    get_user_state(message.from_user.id)
    await message.answer(get_message("welcome"), reply_markup=build_main_menu())


@router.callback_query(F.data == "menu")
async def menu_handler(callback: CallbackQuery):
    await callback.message.edit_text(get_message("menu"), reply_markup=build_main_menu())
    await callback.answer()


@router.callback_query(F.data == "today")
async def today_handler(callback: CallbackQuery):
    items = list_challenges()[:3]
    await callback.message.edit_text(get_message("today_intro"), reply_markup=build_challenge_list(items))
    await callback.answer()


@router.callback_query(F.data == "choose")
async def choose_handler(callback: CallbackQuery):
    await callback.message.edit_text(get_message("choose_intro"), reply_markup=build_challenge_list(list_challenges()))
    await callback.answer()


@router.callback_query(F.data == "friend_mode")
async def friend_handler(callback: CallbackQuery):
    await callback.message.edit_text(get_message("friend_intro"), reply_markup=build_challenge_list(list_challenges("friend")))
    await callback.answer()


@router.callback_query(F.data.startswith("challenge:"))
async def challenge_handler(callback: CallbackQuery):
    challenge_id = callback.data.split(":", 1)[1]
    challenge = find_challenge(challenge_id)
    if not challenge:
        await callback.answer("Челлендж не найден", show_alert=True)
        return
    await callback.message.edit_text(format_challenge(challenge), parse_mode="Markdown", reply_markup=build_challenge_card(challenge_id))
    await callback.answer()


@router.callback_query(F.data.startswith("take:"))
async def take_handler(callback: CallbackQuery):
    challenge_id = callback.data.split(":", 1)[1]
    state = get_user_state(callback.from_user.id)
    state["current_challenge_id"] = challenge_id
    state["last_take_at"] = datetime.utcnow().isoformat()
    save_json(USER_DATA_PATH, USER_STATE)
    await callback.message.answer(get_message("taken"), reply_markup=build_current(challenge_id))
    await callback.answer("Челлендж взят")


@router.callback_query(F.data == "current")
async def current_handler(callback: CallbackQuery):
    state = get_user_state(callback.from_user.id)
    challenge_id = state.get("current_challenge_id")
    if not challenge_id:
        await callback.message.edit_text(get_message("no_current"), reply_markup=build_main_menu())
        await callback.answer()
        return
    challenge = find_challenge(challenge_id)
    await callback.message.edit_text("Текущий челлендж:\n\n" + format_challenge(challenge), parse_mode="Markdown", reply_markup=build_current(challenge_id))
    await callback.answer()


@router.callback_query(F.data == "drop_current")
async def drop_current(callback: CallbackQuery):
    state = get_user_state(callback.from_user.id)
    state["current_challenge_id"] = None
    save_json(USER_DATA_PATH, USER_STATE)
    await callback.message.edit_text(get_message("dropped"), reply_markup=build_main_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("share:"))
async def share_handler(callback: CallbackQuery, bot: Bot):
    challenge_id = callback.data.split(":", 1)[1]
    me = await bot.get_me()
    link = make_share_link(me.username, challenge_id, callback.from_user.id)
    await callback.message.answer(get_message("share_intro") + "\n\n" + link)
    await callback.answer("Ссылка готова")


@router.callback_query(F.data.startswith("done:"))
async def done_handler(callback: CallbackQuery):
    challenge_id = callback.data.split(":", 1)[1]
    state = get_user_state(callback.from_user.id)
    state["awaiting_story"] = True
    state["awaiting_story_challenge_id"] = challenge_id
    save_json(USER_DATA_PATH, USER_STATE)
    await callback.message.answer(get_message("awaiting_story"))
    await callback.answer()


@router.callback_query(F.data.startswith("emotion:"))
async def emotion_handler(callback: CallbackQuery):
    _, challenge_id, emotion = callback.data.split(":", 2)
    state = get_user_state(callback.from_user.id)
    if state["stories"]:
        state["stories"][-1]["emotion"] = emotion
    state["completed_count"] += 1
    state["current_challenge_id"] = None
    save_json(USER_DATA_PATH, USER_STATE)
    await callback.message.edit_text(get_message("story_saved"), reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Еще похожее", callback_data="today")],
            [InlineKeyboardButton(text="🎯 Выбрать другое", callback_data="choose")],
            [InlineKeyboardButton(text="💛 Истории моих эмоций", callback_data="stories")],
        ]
    ))
    await callback.answer()


@router.callback_query(F.data == "stories")
async def stories_handler(callback: CallbackQuery):
    state = get_user_state(callback.from_user.id)
    stories = state.get("stories", [])
    if not stories:
        await callback.message.edit_text(get_message("no_stories"), reply_markup=build_main_menu())
        await callback.answer()
        return
    lines = ["💛 **Истории моих эмоций**\n"]
    for item in reversed(stories[-10:]):
        challenge = find_challenge(item["challenge_id"]) or {"title": "Мой челлендж"}
        emotion = item.get("emotion") or "без оценки"
        lines.append(f"- {challenge['title']} — {emotion}")
        if item.get("text"):
            lines.append(f"  {item['text'][:90]}")
    await callback.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=build_main_menu())
    await callback.answer()


@router.callback_query(F.data == "custom_start")
async def custom_start(callback: CallbackQuery):
    state = get_user_state(callback.from_user.id)
    state["awaiting_custom_title"] = True
    save_json(USER_DATA_PATH, USER_STATE)
    await callback.message.answer(get_message("custom_title"))
    await callback.answer()


@router.message()
async def free_text_handler(message: Message):
    state = get_user_state(message.from_user.id)

    if state.get("awaiting_custom_title"):
        state["draft_custom_title"] = message.text or "Мой челлендж"
        state["awaiting_custom_title"] = False
        state["awaiting_custom_desc"] = True
        save_json(USER_DATA_PATH, USER_STATE)
        await message.answer(get_message("custom_desc"))
        return

    if state.get("awaiting_custom_desc"):
        custom_id = f"custom_{message.from_user.id}_{int(datetime.utcnow().timestamp())}"
        CHALLENGES.append({
            "id": custom_id,
            "title": state["draft_custom_title"],
            "short_description": (message.text or "")[:140],
            "what_to_do": message.text or "",
            "what_to_notice": "Заметь, что ты почувствовал до, во время и после выполнения.",
            "category": "custom",
            "format_type": "mixed",
            "budget_tier": "free",
            "duration_min": 5,
            "duration_max": 60,
            "city_fit": "universal",
            "status": "published",
        })
        save_json(CHALLENGES_PATH, CHALLENGES)
        state["awaiting_custom_desc"] = False
        state["draft_custom_title"] = None
        state["current_challenge_id"] = custom_id
        save_json(USER_DATA_PATH, USER_STATE)
        await message.answer(get_message("custom_created"), reply_markup=build_current(custom_id))
        return

    if state.get("awaiting_story"):
        challenge_id = state["awaiting_story_challenge_id"]
        text = message.text or message.caption or ""
        photo_file_id = message.photo[-1].file_id if message.photo else None
        state["stories"].append({
            "challenge_id": challenge_id,
            "text": text,
            "photo_file_id": photo_file_id,
            "emotion": None,
            "created_at": datetime.utcnow().isoformat(),
        })
        state["awaiting_story"] = False
        state["awaiting_story_challenge_id"] = None
        save_json(USER_DATA_PATH, USER_STATE)
        await message.answer(get_message("choose_emotion"), reply_markup=build_emotions(challenge_id))
        return

    await message.answer(get_message("fallback"), reply_markup=build_main_menu())


async def reminder_loop(bot: Bot):
    while True:
        now = datetime.utcnow()
        for uid, state in list(USER_STATE.items()):
            try:
                user_id = int(uid)
            except:
                continue
            current = state.get("current_challenge_id")
            last_take_raw = state.get("last_take_at")
            last_active_raw = state.get("last_active_at")

            if current and last_take_raw:
                last_take = datetime.fromisoformat(last_take_raw)
                if now - last_take > timedelta(hours=24):
                    await bot.send_message(
                        user_id,
                        get_message("reminder_current"),
                        reply_markup=build_current(current),
                    )
                    state["last_take_at"] = now.isoformat()

            if not current and last_active_raw:
                last_active = datetime.fromisoformat(last_active_raw)
                if now - last_active > timedelta(days=7):
                    await bot.send_message(
                        user_id,
                        get_message("reminder_inactive"),
                        reply_markup=build_main_menu(),
                    )
                    state["last_active_at"] = now.isoformat()

        save_json(USER_DATA_PATH, USER_STATE)
        await asyncio.sleep(3600)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Set BOT_TOKEN in .env")
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    reminder_task = asyncio.create_task(reminder_loop(bot))
    try:
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
