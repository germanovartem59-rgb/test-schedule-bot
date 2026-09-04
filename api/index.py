"""Webhook-версия для хостинга Render."""
import os
import sys
import requests
from flask import Flask, request, jsonify

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from schedule_logic import process_message, process_callback

app = Flask(__name__)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API = "https://api.telegram.org/bot{token}/{method}"
_last_bot_msg: dict[int, int] = {}


def api_call(method: str, payload: dict):
    try:
        return requests.post(
            API.format(token=BOT_TOKEN, method=method), json=payload, timeout=15
        ).json()
    except Exception:
        return {}


def show_new(chat_id: int, text: str, kb):
    """Команда текстом: удалить прошлое сообщение бота и отправить новое снизу."""
    prev = _last_bot_msg.pop(chat_id, None)
    if prev:
        api_call("deleteMessage", {"chat_id": chat_id, "message_id": prev})
    show_edit(chat_id, text, kb, edit_id=None)


def show_edit(chat_id: int, text: str, kb, edit_id: int | None = None):
    """Нажатие кнопки: отредактировать сообщение на месте."""
    markup = {"inline_keyboard": kb} if kb else None
    mid = edit_id or _last_bot_msg.get(chat_id)
    if mid:
        r = api_call("editMessageText", {
            "chat_id": chat_id, "message_id": mid,
            "text": text, "parse_mode": "HTML", "reply_markup": markup,
        })
        if r.get("ok"):
            _last_bot_msg[chat_id] = mid
            return
    r = api_call("sendMessage", {
        "chat_id": chat_id, "text": text,
        "parse_mode": "HTML", "reply_markup": markup,
    })
    new_id = (r.get("result") or {}).get("message_id")
    if new_id:
        _last_bot_msg[chat_id] = new_id


def clear_old_keyboard(chat_id: int):
    try:
        r = api_call("sendMessage", {
            "chat_id": chat_id, "text": "⌨️",
            "reply_markup": {"remove_keyboard": True},
        })
        mid = (r.get("result") or {}).get("message_id")
        if mid:
            api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
    except Exception:
        pass


@app.get("/")
def index():
    return "Bot is alive. POST /webhook for Telegram updates."


@app.post("/webhook")
def webhook():
    upd = request.get_json(force=True, silent=True) or {}
    if not BOT_TOKEN:
        return jsonify(ok=True)
    # --- нажатие inline-кнопки ---
    cb = upd.get("callback_query")
    if cb:
        msg = cb.get("message", {}) or {}
        chat = msg.get("chat", {}) or {}
        chat_id = chat.get("id")
        mid = msg.get("message_id")
        user = cb.get("from", {}) or {}
        api_call("answerCallbackQuery", {"callback_query_id": cb.get("id")})
        if chat_id:
            answer, kb = process_callback(user.get("id", 0), cb.get("data", ""))
            show_edit(chat_id, answer, kb, edit_id=mid)
        return jsonify(ok=True)
    # --- обычное сообщение ---
    msg = upd.get("message", {})
    text = msg.get("text", "")
    chat = msg.get("chat", {}) or {}
    chat_id = chat.get("id")
    chat_type = chat.get("type", "private")
    user = msg.get("from", {}) or {}
    if chat_id and text:
        answer, kb = process_message(user.get("id", 0), text, chat_type=chat_type)
        if answer is not None:
            low = text.strip().lower().lstrip("./").split("@")[0]
            if low in ("start", "старт", "привет"):
                clear_old_keyboard(chat_id)
            show_new(chat_id, answer, kb)
    return jsonify(ok=True)
