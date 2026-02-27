"""
Комментарии к заявке на смену пароля (Jira AA): просмотр и добавление.
Как в боте Лупа: пользователь видит комментарии и может добавить свой.
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from states import CommentStates
from keyboards import get_main_menu_keyboard, get_cancel_keyboard
from user_storage import is_user_registered, get_user_profile
from core.password_requests import get_pending_issue_key_by_user
from core.support.api import support_api
from core.jira_aa import get_issue_comments, add_comment

CHANNEL_ID = "telegram"

logger = logging.getLogger(__name__)
router = Router()

MAX_COMMENT_LEN = 300
MAX_COMMENTS_SHOW = 10


def _format_comments(comments: list, max_len: int = 200) -> list:
    """Форматирует комментарии для отображения (новые первыми)."""
    out = []
    for c in reversed(comments[-MAX_COMMENTS_SHOW:]):
        author = (c.get("author") or {}).get("displayName", "—")
        body = (c.get("body") or "").strip()
        if len(body) > max_len:
            body = body[:max_len] + "..."
        out.append(f"👤 {author}: {body}")
    return out


@router.callback_query(lambda c: c.data == "request_comments")
async def request_comments_start(callback: CallbackQuery, state: FSMContext):
    if not is_user_registered(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию.", show_alert=True)
        return
    issue_key = get_pending_issue_key_by_user(callback.from_user.id)
    if not issue_key:
        await callback.answer("У вас нет активной заявки на смену пароля.", show_alert=True)
        return
    await state.clear()
    comments = await get_issue_comments(issue_key)
    lines = _format_comments(comments)
    text = (
        f"💬 <b>Комментарии к заявке {issue_key}</b>\n\n"
        + ("\n\n".join(lines) if lines else "Пока нет комментариев.")
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Добавить комментарий", callback_data=f"add_comment:{issue_key}")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")],
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


def _user_can_comment_issue(user_id: int, issue_key: str) -> bool:
    """Доступ: заявка в pending или в реестре привязок."""
    if get_pending_issue_key_by_user(user_id) == issue_key:
        return True
    return support_api.user_owns_issue(CHANNEL_ID, user_id, issue_key)


@router.callback_query(lambda c: c.data and c.data.startswith("add_comment:"))
async def add_comment_start(callback: CallbackQuery, state: FSMContext):
    if not is_user_registered(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию.", show_alert=True)
        return
    issue_key = (callback.data or "").split(":", 1)[-1].strip()
    if not issue_key or not _user_can_comment_issue(callback.from_user.id, issue_key):
        await callback.answer("Заявка не найдена или доступ запрещён.", show_alert=True)
        return
    await state.set_state(CommentStates.WAITING_FOR_COMMENT)
    await state.update_data(issue_key=issue_key)
    await callback.message.edit_text(
        f"✍️ Введите комментарий к заявке <b>{issue_key}</b> (или /cancel для отмены):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )
    await callback.answer()


@router.message(CommentStates.WAITING_FOR_COMMENT, F.text)
async def process_comment(message: Message, state: FSMContext):
    if message.text and message.text.strip().lower() == "/cancel":
        await state.clear()
        await message.reply("Отменено.", reply_markup=get_main_menu_keyboard(message.from_user.id))
        return
    text = (message.text or "").strip()
    if not text:
        await message.reply("Введите текст комментария или /cancel.", reply_markup=get_cancel_keyboard())
        return
    if len(text) > MAX_COMMENT_LEN:
        await message.reply(f"Комментарий не длиннее {MAX_COMMENT_LEN} символов.", reply_markup=get_cancel_keyboard())
        return
    data = await state.get_data()
    issue_key = data.get("issue_key")
    if not issue_key:
        await state.clear()
        await message.reply("Сессия истекла. Вернитесь в меню.", reply_markup=get_main_menu_keyboard(message.from_user.id))
        return
    profile = get_user_profile(message.from_user.id) or {}
    full_name = (profile.get("full_name") or "").strip() or "Пользователь"
    comment_body = f"[{full_name}] {text}"
    ok = await add_comment(issue_key, comment_body)
    await state.clear()
    if ok:
        await message.reply(
            f"✅ Комментарий добавлен к заявке {issue_key}.",
            reply_markup=get_main_menu_keyboard(message.from_user.id),
        )
        logger.info("Пользователь %s добавил комментарий к %s", message.from_user.id, issue_key)
    else:
        await message.reply(
            "❌ Не удалось добавить комментарий. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard(message.from_user.id),
        )
