"""Webhook-версия для хостинга Render."""
import os
import sys
import requests
from flask import Flask, request, jsonify

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from schedule_logic import process_message

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


def send_message(chat_id: int, text: str, keyboard):
    prev = _last_bot_msg.get(chat_id)
    if prev:
        api_call("deleteMessage", {"chat_id": chat_id, "message_id": prev})
    kb = {"keyboard": keyboard, "resize_keyboard": True}
    r = api_call("sendMessage", {
        "chat_id": chat_id, "text": text,
        "reply_markup": kb, "parse_mode": "HTML",
    })
    mid = (r.get("result") or {}).get("message_id")
    if mid:
        _last_bot_msg[chat_id] = mid


@app.get("/")
def index():
    return "Bot is alive. POST /webhook for Telegram updates."


@app.post("/webhook")
def webhook():
    upd = request.get_json(force=True, silent=True) or {}
    msg = upd.get("message", {})
    text = msg.get("text", "")
    chat = msg.get("chat", {}) or {}
    chat_id = chat.get("id")
    user = msg.get("from", {}) or {}
    user_id = user.get("id", 0)
    if chat_id and text and BOT_TOKEN:
        answer, kb = process_message(user_id, text)
        send_message(chat_id, answer, kb)
    return jsonify(ok=True)
