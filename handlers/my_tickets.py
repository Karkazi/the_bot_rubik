"""
Мои заявки: список по реестру привязок из Core, переход к просмотру/комментариям.
"""
import logging
from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from user_storage import is_user_registered
from core.support.api import support_api

logger = logging.getLogger(__name__)
router = Router()
CHANNEL_ID = "telegram"


@router.callback_query(lambda c: c.data == "my_tickets")
async def my_tickets_list(callback: CallbackQuery):
    if not is_user_registered(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию.", show_alert=True)
        return
    tickets = await support_api.get_my_tickets_filtered(CHANNEL_ID, callback.from_user.id)
    if not tickets:
        await callback.message.edit_text(
            "📋 <b>Мои заявки</b>\n\nУ вас пока нет заявок.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")],
            ]),
        )
        await callback.answer()
        return
    lines = []
    for t in tickets:
        issue_key = t.get("issue_key") or "—"
        url = t.get("customer_request_url") or ""
        if url and issue_key != "—":
            lines.append(f'• <a href="{url}">{issue_key}</a>')
        else:
            lines.append(f"• {issue_key}")
    text = "📋 <b>Мои заявки</b>\n\n" + "\n".join(lines) + "\n\nВыберите заявку (или откройте по ссылке):"
    buttons = []
    for t in tickets:
        issue_key = t.get("issue_key")
        if issue_key:
            buttons.append([InlineKeyboardButton(text=issue_key, callback_data=f"open_issue:{issue_key}")])
    buttons.append([InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("open_issue:"))
async def open_issue_view(callback: CallbackQuery):
    if not is_user_registered(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию.", show_alert=True)
        return
    issue_key = (callback.data or "").split(":", 1)[-1].strip()
    if not support_api.user_owns_issue(CHANNEL_ID, callback.from_user.id, issue_key):
        await callback.answer("Заявка не найдена.", show_alert=True)
        return
    from core.jira_aa import get_issue_info, get_issue_comments

    info = await get_issue_info(issue_key)
    comments = await get_issue_comments(issue_key)
    summary = (info or {}).get("summary") or "—"
    status = (info or {}).get("status") or "—"
    def _fmt(comments, max_len=200):
        out = []
        for c in reversed(comments[-10:]):
            author = (c.get("author") or {}).get("displayName", "—")
            body = (c.get("body") or "").strip()
            if len(body) > max_len:
                body = body[:max_len] + "..."
            out.append(f"👤 {author}: {body}")
        return out
    lines = _fmt(comments)
    jira_url = support_api.get_jira_customer_request_url(issue_key)
    text = (
        f"💬 <b>Заявка {issue_key}</b>\n"
        f"Тема: {summary}\nСтатус: {status}\n\n"
        + ("\n\n".join(lines) if lines else "Пока нет комментариев.")
    )
    keyboard_rows = []
    if jira_url:
        keyboard_rows.append([InlineKeyboardButton(text="🔗 Открыть в Jira", url=jira_url)])
    keyboard_rows.extend([
        [InlineKeyboardButton(text="✏️ Добавить комментарий", callback_data=f"add_comment:{issue_key}")],
        [InlineKeyboardButton(text="🔙 К списку заявок", callback_data="my_tickets")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")],
    ])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()
